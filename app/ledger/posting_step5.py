"""
posting_step5.py - Step 5: the remaining modules.

    Cash book rows   deposit / withdraw rows of the old cash book that no other document books
                       (owner and shareholder money, dividends, loans received / given / repaid, refunds, emergency fund,
                        manual cash-in / cash-out screens)
    Payroll (paid)   Dr Salaries            Cr Cash / Bank (net pay)   Cr Tax Withheld   Cr Employee Loans (recovered)
    Daily closing    Cash over / short - only when GL_POST_CLOSING_DIFF = True in settings (off by default, see below)

The cash book is the one place that already records every cash movement of loans, shareholders and dividends, so those
flows are booked from its rows (`classify_cash_row` in posting_core.py decides the other account). A row that another
document already books is skipped:  vendor payments, paid expenses, sales, purchases and opening balances.

Anything the rules do not recognise goes to the 'suspense' account (Unclassified Cash Movements). The books stay balanced;
`post_ledger --check` shows the amount so you can move it to the right account.

Daily closing: the old closing screen compares counted cash with "opening + sales paid - expenses", which ignores purchases,
vendor payments and withdrawals, so its "difference" is not a reliable shortage. It is therefore NOT booked unless you set
GL_POST_CLOSING_DIFF = True.
"""
from django.conf import settings

from ..models import CashTransaction, DailyClosing, LoanReturn, Payroll, Sale
from .posting import SOURCES, _day, account_for, cust, method_account, post_entry
from .posting_core import C, D, classify_cash_row, first_match, payroll_amounts, q2, split_loan_return

__all__ = ['post_cash_book', 'post_payroll', 'post_daily_closing']


def post_cash_book(txn, user=None, repost=False):
    """One cash-book deposit / withdrawal -> one entry against the Cash account (or the mapped method account)."""
    key = classify_cash_row(txn.transaction_type, txn.description)
    amount = q2(txn.amount)
    if key is None or amount <= 0:
        return None
    cash = method_account(txn.payment_method)
    text = (txn.description or '').strip()
    inflow = txn.transaction_type == 'deposit'
    party = ''
    lines = []

    if key == 'customer_refund':
        sale = Sale.objects.filter(bill_no=first_match(r'^Void refund (.+?) - ', text)).first()
        party = cust(sale.customer_id) if sale else ''
        lines = [D(account_for('receivable'), amount, 'Cash refunded to the customer', party), C(cash, amount, 'Refund paid')]
    elif key == 'loan_return':
        ret = LoanReturn.objects.filter(return_no=first_match(r'^Loan Return #(\S+)', text)).first()
        principal, charges = split_loan_return(amount, ret.principal_amount if ret else 0)
        lines = [D(account_for('loans_payable'), principal, 'Loan principal repaid'),
                 D(account_for('interest_expense'), charges, 'Loan interest and charges'),
                 C(cash, amount, 'Loan repayment')]
    elif inflow:
        lines = [D(cash, amount, text[:200] or 'Cash in'), C(account_for(key), amount, text[:200] or 'Cash in')]
    else:
        lines = [D(account_for(key), amount, text[:200] or 'Cash out'), C(cash, amount, text[:200] or 'Cash out')]

    return post_entry(
        entry_date=_day(txn.date), entry_type='receipt' if inflow else 'payment', source_type='cash_book',
        source_id=txn.pk, description=text[:200] or f'Cash book #{txn.pk}', reference=txn.reference_no or f'CB-{txn.pk}',
        lines=lines, user=user, repost=repost,
    )


def post_payroll(payroll, user=None, repost=False):
    """Booked when the salary is marked paid."""
    if payroll.status != 'paid':
        return None
    expense, cash, tax, loan = payroll_amounts(payroll.total_earnings(), payroll.absence_deduction, payroll.other_deduction,
                                               payroll.tax_deduction, payroll.loan_deduction)
    if expense <= 0:
        return None
    month = payroll.month.strftime('%b %Y')
    return post_entry(
        entry_date=_day(payroll.payment_date or payroll.month), entry_type='payment', source_type='payroll',
        source_id=payroll.pk, description=f'Salary {payroll.employee.name} - {month}', reference=f'PAY-{payroll.pk}',
        lines=[D(account_for('salary_expense'), expense, f'Salary {month}'),
               C(method_account(payroll.payment_method or 'cash'), cash, 'Net salary paid'),
               C(account_for('tax_payable'), tax, 'Tax withheld'),
               C(account_for('employee_loans'), loan, 'Employee loan recovered')],
        user=user, repost=repost,
    )


def post_daily_closing(closing, user=None, repost=False):
    """Cash over / short of a closed day. Off unless GL_POST_CLOSING_DIFF = True (see the module note)."""
    if not getattr(settings, 'GL_POST_CLOSING_DIFF', False) or not closing.is_closed:
        return None
    diff = q2(closing.cash_difference)
    if diff == 0:
        return None
    over_short, cash = account_for('cash_over_short'), account_for('cash')
    lines = ([D(cash, diff, 'Cash counted above the expected amount'), C(over_short, diff, 'Cash over')] if diff > 0 else
             [D(over_short, -diff, 'Cash short'), C(cash, -diff, 'Cash counted below the expected amount')])
    return post_entry(
        entry_date=closing.closing_date, entry_type='adjustment', source_type='daily_closing', source_id=closing.pk,
        description=f'Cash over / short - closing {closing.closing_date}', reference=f'CLOSE-{closing.closing_date}',
        lines=lines, user=user, repost=repost,
    )


SOURCES.update({
    'cash_book': (CashTransaction, post_cash_book),
    'payroll': (Payroll, post_payroll),
    'daily_closing': (DailyClosing, post_daily_closing),
})
