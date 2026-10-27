"""
posting_gaps.py - Step 2b: money that was written on the bill but has no payment record.

Where it comes from
    * Sale.paid / Purchase.paid typed on the bill screen (down payments, advances carried over from a sale order,
      the 'paid' box of the purchase screen)
    * the customer / vendor ledger screens that raise `paid` on the oldest bills

What is booked (one entry per customer / vendor, re-posted whenever the gap changes, reversed when it is gone)
    Customer   Dr Cash (or the account mapped to 'bill_paid')          Cr Accounts Receivable
    Vendor     Dr Accounts Payable                                     Cr Cash          (the cash the bill says was used)
                                                                       Cr Shareholder Funds (bill deducted from shareholders)
                                                                       Cr 'bill_paid' account / Cash (everything else)
    Opening cash book row (CashTransaction type 'opening')              Dr Cash   Cr Opening Balance Equity

Already covered, so NOT booked here:
    * EMI payments - EmiPayment.mark_paid creates a SalePayment, which Step 2 posts.
    * CashTransaction 'sale' / 'purchase' / 'expense' rows - duplicates of documents that are posted on their own.
    * CashTransaction 'deposit' / 'withdraw' rows - the same screen also writes vendor payments as 'withdraw', so booking
      them blindly would count the money twice. They are shown in `post_ledger --check` and handled in Step 5.

Choose the account with  PostingRule  key `bill_paid`  (default: the cash account). Change it to the bank account if most
down payments arrive by bank.
"""
from django.db.models import Min, Sum

from ..models import (CashTransaction, Customer, CustomerPayment, GLPosting, JournalEntry, Purchase, SalePayment, Sale, Vendor,
                     VendorPayment)
from .posting import SOURCES, _day, account_for, cust, method_account, post_entry, vend
from .posting_core import C, D, paid_gap, q2, split_vendor_gap

__all__ = ['post_customer_paid_gap', 'post_vendor_paid_gap', 'post_cash_opening', 'post_vendor_opening']


def _by(qs, key):
    """{id: total amount}. order_by() clears the model's default ordering, which would break the GROUP BY."""
    return {k: (t or 0) for k, t in qs.order_by().values_list(key).annotate(t=Sum('amount'))}


def post_customer_paid_gap(customer, user=None, repost=False):
    sales = list(Sale.objects.filter(customer=customer).values('pk', 'paid', 'sale_date'))
    if not any(s['paid'] for s in sales):
        return None
    recorded = _by(SalePayment.objects.filter(sale__customer=customer), 'sale_id')
    for k, v in _by(CustomerPayment.objects.filter(customer=customer, sale__isnull=False), 'sale_id').items():
        recorded[k] = recorded.get(k, 0) + v
    unlinked = CustomerPayment.objects.filter(customer=customer, sale__isnull=True).aggregate(t=Sum('amount'))['t'] or 0
    gap = paid_gap([(s['paid'], recorded.get(s['pk'], 0)) for s in sales if s['paid']], unlinked)
    if gap <= 0:
        return None
    return post_entry(
        entry_date=_day(max(s['sale_date'] for s in sales if s['paid'])), entry_type='receipt',
        source_type='customer_paid_gap', source_id=customer.pk,
        description=f'Paid on bills (no payment record) - {customer.name}', reference=f'PAID-C{customer.pk}',
        lines=[D(account_for('bill_paid', fallback='cash'), gap, 'Received on the bill'),
               C(account_for('receivable'), gap, 'Customer paid on the bill', cust(customer.pk))],
        user=user, repost=repost,
    )


def post_vendor_paid_gap(vendor, user=None, repost=False):
    purchases = list(Purchase.objects.filter(vendor=vendor).values(
        'pk', 'paid', 'cash_used', 'pur_date', 'shareholder_deduction_done', 'shareholder_deduction_type'))
    if not any(p['paid'] for p in purchases):
        return None
    recorded = _by(VendorPayment.objects.filter(vendor=vendor, purchase__isnull=False), 'purchase_id')
    unlinked = VendorPayment.objects.filter(vendor=vendor, purchase__isnull=True).aggregate(t=Sum('amount'))['t'] or 0
    rows = [(p['paid'], recorded.get(p['pk'], 0), p['cash_used'],
             bool(p['shareholder_deduction_done']) and p['shareholder_deduction_type'] != 'skip')
            for p in purchases if p['paid']]
    cash, share, other = split_vendor_gap(rows, unlinked)
    total = cash + share + other
    if total <= 0:
        return None
    lines = [D(account_for('payable'), total, 'Vendor paid on the bill', vend(vendor.pk)),
             C(account_for('cash'), cash, 'Cash used on the bill'),
             C(account_for('shareholder_funds'), share, 'Paid from shareholder funds'),
             C(account_for('bill_paid', fallback='cash'), other, 'Paid on the bill')]
    return post_entry(
        entry_date=_day(max(p['pur_date'] for p in purchases if p['paid'])), entry_type='payment',
        source_type='vendor_paid_gap', source_id=vendor.pk,
        description=f'Paid on bills (no payment record) - {vendor.name}', reference=f'PAID-V{vendor.pk}',
        lines=lines, user=user, repost=repost,
    )


def post_cash_opening(txn, user=None, repost=False):
    """The opening balance typed into the old cash book."""
    if txn.transaction_type != 'opening':
        return None
    amount = q2(txn.amount)
    if amount <= 0:
        return None
    return post_entry(
        entry_date=_day(txn.date), entry_type='adjustment', source_type='cash_opening', source_id=txn.pk,
        description=f'Opening cash balance ({txn.payment_method})', reference=txn.reference_no or f'OPEN-{txn.pk}',
        lines=[D(method_account(txn.payment_method), amount, 'Opening balance'),
               C(account_for('opening_equity'), amount, 'Opening balance equity')],
        user=user, repost=repost,
    )


def _vendor_opening_date(vendor):
    """Fixed once booked. First time: the vendor's first purchase, or the first day of the books, or today."""
    gp = GLPosting.objects.select_related('journal_entry').filter(
        source_type='vendor_opening', source_id=vendor.pk, is_active=True).first()
    if gp:
        return gp.journal_entry.entry_date
    days = [d for d in (Purchase.objects.filter(vendor=vendor).aggregate(m=Min('pur_date'))['m'],
                        JournalEntry.objects.aggregate(m=Min('entry_date'))['m']) if d]
    return min(_day(d) for d in days) if days else _day(None)


def post_vendor_opening(vendor, user=None, repost=False):
    """
    Step 4: the balance a vendor already had before the system (Vendor.opening_balance), so the vendor sub-ledger
    starts from the same number as the vendor screen.
        we owe the vendor   Dr Opening Balance Equity   Cr Accounts Payable (vendor)
        vendor owes us      Dr Accounts Payable (vendor) Cr Opening Balance Equity
    (Customers have no opening-balance field; an old customer balance enters through its sales.)
    """
    amount = q2(vendor.opening_balance)
    if amount == 0:
        return None
    equity, payable = account_for('opening_equity'), account_for('payable')
    if amount > 0:
        lines = [D(equity, amount, 'Opening balance equity'), C(payable, amount, 'Opening balance', vend(vendor.pk))]
    else:
        lines = [D(payable, -amount, 'Opening balance (vendor owes us)', vend(vendor.pk)), C(equity, -amount, 'Opening balance equity')]
    return post_entry(
        entry_date=_vendor_opening_date(vendor), entry_type='adjustment', source_type='vendor_opening',
        source_id=vendor.pk, description=f'Opening balance - {vendor.name}', reference=f'OPEN-V{vendor.pk}',
        lines=lines, user=user, repost=repost,
    )


SOURCES.update({
    'vendor_opening': (Vendor, post_vendor_opening),
    'customer_paid_gap': (Customer, post_customer_paid_gap),
    'vendor_paid_gap': (Vendor, post_vendor_paid_gap),
    'cash_opening': (CashTransaction, post_cash_opening),
})
