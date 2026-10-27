"""
posting_core.py - pure ledger rules (no Django). Easy to unit-test.

Rules
-----
* every entry needs at least two lines
* a line has an account key, a side ('D' or 'C') and an amount > 0
* total debit must equal total credit, to the paisa
* a running balance follows the nature of the account (debit-nature: assets/expenses, credit-nature: the rest)
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

DEBIT_NATURE = ('asset', 'expense')


class PostingError(Exception):
    """Raised when an entry cannot be posted (unbalanced, unmapped account, bad amount...)."""


def q2(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), ROUND_HALF_UP)


@dataclass
class Line:
    account: object          # an Account instance, or any key in tests
    side: str                # 'D' or 'C'
    amount: Decimal
    memo: str = ''
    party: str = ''          # Step 4: 'C12' = customer 12, 'V3' = vendor 3 ('' = no party)


def party_key(kind, pk):
    """'C' (customer) or 'V' (vendor) + id, e.g. party_key('C', 12) -> 'C12'. Empty when there is no party."""
    if not pk:
        return ''
    if kind not in ('C', 'V'):
        raise PostingError(f'Bad party kind {kind!r} (use C or V).')
    return f'{kind}{int(pk)}'


def split_party(key):
    """'C12' -> ('C', 12).  '' -> (None, None)."""
    key = (key or '').strip()
    if not key:
        return None, None
    return key[0], int(key[1:])


def D(account, amount, memo='', party=''):
    return Line(account, 'D', q2(amount), memo, party or '')


def C(account, amount, memo='', party=''):
    return Line(account, 'C', q2(amount), memo, party or '')


def clean_lines(lines):
    """Round, drop zero lines, merge nothing. Raises PostingError on bad data."""
    out = []
    for ln in lines:
        if ln.side not in ('D', 'C'):
            raise PostingError(f'Bad side {ln.side!r} (use D or C).')
        amt = q2(ln.amount)
        if amt < 0:
            raise PostingError('Negative amount. Post the opposite side instead.')
        if amt == 0:
            continue
        out.append(Line(ln.account, ln.side, amt, ln.memo, getattr(ln, 'party', '') or ''))
    if len(out) < 2:
        raise PostingError('An entry needs at least two lines with an amount.')
    return out


def totals(lines):
    debit = sum((ln.amount for ln in lines if ln.side == 'D'), Decimal('0.00'))
    credit = sum((ln.amount for ln in lines if ln.side == 'C'), Decimal('0.00'))
    return debit, credit


def check_balanced(lines):
    debit, credit = totals(lines)
    if debit != credit:
        raise PostingError(f'Entry is not balanced: debit {debit} / credit {credit}.')
    return debit


def next_balance(previous, debit, credit, account_class):
    """Running balance after one more ledger row."""
    previous, debit, credit = q2(previous), q2(debit), q2(credit)
    if account_class in DEBIT_NATURE:
        return previous + debit - credit
    return previous + credit - debit


def line_signature(lines):
    """Comparable form of an entry: sorted [(account id/key, side, amount, party)]. Used to skip no-change re-posts.
    The party is part of it: moving a bill to another customer must re-post, even when the amounts are the same."""
    out = []
    for ln in lines:
        acc = getattr(ln.account, 'pk', ln.account)
        out.append((acc, ln.side, q2(ln.amount), getattr(ln, 'party', '') or ''))
    return sorted(out, key=lambda t: (str(t[0]), t[1], t[2], t[3]))


def prorate(total_cost, total_qty, qty):
    """Cost of `qty` units out of a document line that cost `total_cost` for `total_qty` units (to the paisa).
    Used for returns: a returned unit goes back into stock at the cost it left at, not at its selling price."""
    total_cost, total_qty, qty = Decimal(str(total_cost or 0)), Decimal(str(total_qty or 0)), Decimal(str(qty or 0))
    if total_qty <= 0 or qty <= 0 or total_cost <= 0:
        return Decimal('0.00')
    qty = min(qty, total_qty)               # never give back more than was sold
    return q2(total_cost * qty / total_qty)


def paid_gap(rows, unlinked=0):
    """
    Money written on bills (`paid`) that has no payment record.
    rows      = [(paid_on_bill, recorded_payments_for_that_bill), ...]
    unlinked  = payments of the same party that are not tied to one bill (ledger screen); they were spread over the bills
    A bill with MORE records than `paid` (e.g. EMI receipts) never hides the gap of another bill.
    """
    gap = sum((max(Decimal('0'), Decimal(str(p or 0)) - Decimal(str(r or 0))) for p, r in rows), Decimal('0'))
    return max(Decimal('0.00'), q2(gap - Decimal(str(unlinked or 0))))


def split_vendor_gap(rows, unlinked=0):
    """
    Who paid the vendor money that has no payment record?  rows = [(paid, recorded, cash_used, shareholder_funded), ...]
    Returns (cash, shareholder, other):  cash = the cash the bill says was used, shareholder = the rest of a bill
    that was deducted from shareholders, other = everything else (bank / unknown -> mapped by the 'bill_paid' rule).
    `unlinked` vendor payments are taken off 'other' first, then cash, then shareholder.
    """
    cash = share = other = Decimal('0')
    for paid, recorded, cash_used, sh in rows:
        paid, recorded, cash_used = Decimal(str(paid or 0)), Decimal(str(recorded or 0)), Decimal(str(cash_used or 0))
        gap = max(Decimal('0'), paid - recorded)
        c = min(gap, max(Decimal('0'), cash_used))
        s = min(gap - c, max(Decimal('0'), paid - cash_used)) if sh else Decimal('0')
        cash, share, other = cash + c, share + s, other + (gap - c - s)
    parts = {'other': other, 'cash': cash, 'share': share}
    left = Decimal(str(unlinked or 0))
    for name in ('other', 'cash', 'share'):
        take = min(left, parts[name])
        parts[name] -= take
        left -= take
    cash, share, other = parts['cash'], parts['share'], parts['other']
    return q2(cash), q2(share), q2(other)


# ---------------------------------------------------------------------------
# Step 4: customer / vendor sub-ledger rules (pure, no Django)
# ---------------------------------------------------------------------------
AGING_BUCKETS = ('0-30', '31-60', '61-90', '91+')


def bucket_for(days):
    """Age in days -> bucket label (same labels the old aging reports use)."""
    if days <= 30:
        return '0-30'
    if days <= 60:
        return '31-60'
    if days <= 90:
        return '61-90'
    return '91+'


def statement_rows(opening, rows, credit_nature=False):
    """
    Running balance for one party.
    opening        balance before the first row (already in the party's own nature)
    rows           [(date, debit, credit, ...anything)] in date order; extra items are carried along
    credit_nature  False for customers (receivable: debit raises the balance), True for vendors (payable: credit raises it)
    Returns [(*row, balance)] and the closing balance.
    """
    running = q2(opening)
    out = []
    for row in rows:
        debit, credit = q2(row[1]), q2(row[2])
        running += (credit - debit) if credit_nature else (debit - credit)
        out.append((*row, running))
    return out, running


def age_open_items(opening, rows, as_of, credit_nature=False):
    """
    Ageing straight from the ledger, without matching a payment to a bill:
    every credit (customer paid / vendor was paid / return) is applied to the OLDEST open charge first (FIFO).
    What is left of the charges is aged by the date of the charge.

    opening  balance before `rows` (an old balance counts as the oldest charge, aged from `opening_date` if rows[0] is later)
    rows     [(date, debit, credit)] in date order
    as_of    the day the age is counted to
    Returns  (buckets, unapplied)   buckets = {'0-30': Decimal, ...}   unapplied = money paid in advance
             (a customer who paid more than they owe, a vendor we paid more than we owe). Never negative.
    """
    charges = []                       # [[date, remaining]]
    unapplied = Decimal('0.00')
    opening = q2(opening)
    first_date = rows[0][0] if rows else as_of
    if opening > 0:
        charges.append([first_date, opening])
    elif opening < 0:
        unapplied = -opening
    for row in rows:
        day = row[0]
        debit, credit = q2(row[1]), q2(row[2])
        charge, settle = (credit, debit) if credit_nature else (debit, credit)
        if charge > 0:
            use = min(unapplied, charge)         # an earlier advance covers the new charge first
            unapplied -= use
            if charge - use > 0:
                charges.append([day, charge - use])
        if settle > 0:
            left = settle
            for c in charges:
                if left <= 0:
                    break
                take = min(c[1], left)
                c[1] -= take
                left -= take
            unapplied += left
    buckets = {b: Decimal('0.00') for b in AGING_BUCKETS}
    for day, remaining in charges:
        if remaining > 0:
            buckets[bucket_for(max((as_of - day).days, 0))] += remaining
    return buckets, q2(unapplied)


# ---------------------------------------------------------------------------
# Step 5: what is a cash-book row?  (pure, no Django)
# ---------------------------------------------------------------------------
import re as _re

# Rows the cash book writes for money that another document ALREADY books on its own. Booking them again would count twice.
CASH_SKIP_PREFIXES = ('Vendor payment',            # VendorPayment  (posted as vendor_payment)
                      'Expense #')                 # Expense        (posted as expense)

# (transaction type, description regex, account key).  First match wins.  Account keys are PostingRule keys.
# Special keys: 'customer_refund' (receivable of the customer on the sale), 'loan_return' (principal / interest split).
CASH_RULES = [
    # --- money going out ---------------------------------------------------------------------------------------
    ('withdraw', r'^Void refund ', 'customer_refund'),
    ('withdraw', r'^Dividend (Payment|allocation)|^Balance Dividend withdrawal', 'dividends'),
    ('withdraw', r'^Shareholder withdrawal|^Withdrawal to |^Initial deposit for new shareholder', 'shareholder_funds'),
    ('withdraw', r'^Refund (to|for)|^Transfer cancellation', 'share_capital'),
    ('withdraw', r'^Loan Return #', 'loan_return'),
    ('withdraw', r'^Loan Given to ', 'loans_receivable'),
    ('withdraw', r'^Emergency Fund:', 'emergency_fund'),
    ('withdraw', r'^\[Personal Use\]', 'owner_drawings'),
    ('withdraw', r'^\[(Rent Payment|Utility Bills|Transportation|Mobile Load)\]', 'expense_default'),
    # --- money coming in ---------------------------------------------------------------------------------------
    ('deposit', r'^(Share investment from|Additional investment from|Share purchase by|Share buyback from)', 'share_capital'),
    ('deposit', r'^Deposit from .* - Request #', 'shareholder_funds'),
    ('deposit', r'^Dividend refund from', 'dividends'),
    ('deposit', r'^Loan Received:', 'loans_payable'),
    ('deposit', r'^Loan repayment from ', 'loans_receivable'),
    ('deposit', r'^Emergency Withdrawal:', 'emergency_fund'),
    ('deposit', r'^investment - ', 'owner_capital'),
]


def classify_cash_row(transaction_type, description):
    """
    Which account is on the other side of a cash-book row?  Returns an account key, or None when the row must NOT be
    booked here (a document posts it already, or it is not a deposit / withdrawal).
    Anything the rules do not recognise goes to 'suspense' - the books stay balanced and `post_ledger --check` lists
    the amount so it can be moved to the right account.
    """
    if transaction_type not in ('deposit', 'withdraw'):
        return None
    text = (description or '').strip()
    if transaction_type == 'withdraw' and text.startswith(CASH_SKIP_PREFIXES):
        return None
    for kind, pattern, key in CASH_RULES:
        if kind == transaction_type and _re.search(pattern, text):
            return key
    return 'suspense'


def first_match(pattern, text):
    """First capture group of `pattern` in `text`, or ''."""
    m = _re.search(pattern, text or '')
    return m.group(1).strip() if m else ''


def split_loan_return(total, principal):
    """(principal part, interest + charges part) of a loan repayment. Missing / too big principal -> everything is principal."""
    total, principal = q2(total), q2(principal)
    if principal <= 0 or principal >= total:
        return total, Decimal('0.00')
    return principal, total - principal


def payroll_amounts(earnings, absence, other, tax, loan):
    """
    One paid salary -> (expense, cash paid, tax withheld, loan recovered).
    Expense = what the employee earned after absence / other cuts; cash = expense - tax - loan recovery. Never negative.
    """
    earnings, absence, other, tax, loan = (q2(x) for x in (earnings, absence, other, tax, loan))
    expense = earnings - absence - other
    cash = expense - tax - loan
    if expense < 0 or cash < 0:
        raise PostingError('Salary deductions are bigger than the earnings.')
    return expense, cash, tax, loan
