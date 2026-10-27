"""
subledger.py - Step 4: customer and vendor sub-ledgers, read straight from the general ledger.

    Receivable account  -> one balance per customer   (debit nature: what the customer owes us)
    Payable account     -> one balance per vendor     (credit nature: what we owe the vendor)

Nothing here is a separate balance: every number is a sum of LedgerEntry rows whose `customer` / `vendor`
was stamped when the entry was posted (posting.py).  The control account (Receivable / Payable) and the
sum of its parties therefore always agree, except for lines that name nobody (`unassigned`), which
`post_ledger --check` lists.

Reversed entries and their reversals cancel each other, so statements hide both by default
(`include_reversed=True` shows them, e.g. for an audit).
"""
from datetime import date as _date
from decimal import Decimal

from django.db.models import Sum

from ..models import Customer, GLPosting, LedgerEntry, PostingRule, Vendor
from .posting_core import AGING_BUCKETS, age_open_items, q2, statement_rows

__all__ = ['KINDS', 'control_account', 'party_balances', 'party_statement', 'aging_report', 'unassigned_balance']

# kind -> (party model, party column on LedgerEntry, PostingRule key of the control account, credit nature?)
KINDS = {
    'customer': (Customer, 'customer', 'receivable', False),
    'vendor': (Vendor, 'vendor', 'payable', True),
}

ZERO = Decimal('0.00')


def control_account(kind):
    """The Receivable (customers) or Payable (vendors) account, or None when it is not mapped yet."""
    rule = PostingRule.objects.select_related('account').filter(key=KINDS[kind][2]).first()
    return rule.account if rule else None


def _rows(kind, account, party_id=None, include_reversed=False):
    """LedgerEntry rows of one party (or of all parties) on the control account."""
    column = KINDS[kind][1]
    qs = LedgerEntry.objects.filter(account=account)
    qs = qs.filter(**{f'{column}_id': party_id}) if party_id else qs.filter(**{f'{column}__isnull': False})
    if not include_reversed:
        qs = qs.exclude(journal_entry__status='reversed').exclude(journal_entry__reversed_from__isnull=False)
    return qs


def _signed(debit, credit, credit_nature):
    return (credit - debit) if credit_nature else (debit - credit)


def party_balances(kind, as_of=None, include_reversed=False):
    """
    {party_id: balance} for every customer / vendor that has ledger rows, in the party's own nature
    (positive = they owe us / we owe them).  `as_of` counts rows up to and including that day.
    """
    account = control_account(kind)
    if account is None:
        return {}
    credit_nature = KINDS[kind][3]
    column = KINDS[kind][1]
    qs = _rows(kind, account, include_reversed=include_reversed)
    if as_of:
        qs = qs.filter(date__lte=as_of)
    out = {}
    for pid, d, c in qs.order_by().values_list(f'{column}_id').annotate(d=Sum('debit'), c=Sum('credit')):
        out[pid] = q2(_signed(q2(d or 0), q2(c or 0), credit_nature))
    return out


def unassigned_balance(kind):
    """Net movement on the control account that names no customer / vendor (manual entries, old entries before
    `--backfill-party`).  Reversed pairs cancel out, so this is the real amount that is missing a party."""
    account = control_account(kind)
    if account is None:
        return ZERO
    column = KINDS[kind][1]
    agg = (LedgerEntry.objects.filter(account=account, **{f'{column}__isnull': True})
           .exclude(journal_entry__status='reversed').exclude(journal_entry__reversed_from__isnull=False)
           .aggregate(d=Sum('debit'), c=Sum('credit')))
    return q2(_signed(q2(agg['d'] or 0), q2(agg['c'] or 0), KINDS[kind][3]))


def _source_map(entry_ids):
    """{journal_entry_id: (source_type, source_id)} so a statement line can link back to its document."""
    out = {}
    for gp in GLPosting.objects.filter(journal_entry_id__in=entry_ids).order_by('id'):
        out.setdefault(gp.journal_entry_id, (gp.source_type, gp.source_id))
    return out


def party_statement(kind, party, date_from=None, date_to=None, include_reversed=False):
    """
    The statement of one customer / vendor, taken from the ledger.

    Returns a dict:
        party, account, date_from, date_to,
        opening   balance before date_from,
        rows      [{'date','reference','description','debit','credit','balance','entry','source_type','source_id'}],
        total_debit, total_credit, closing, credit_nature
    The balance is in the party's own nature: positive = the customer owes us / we owe the vendor.
    """
    account = control_account(kind)
    credit_nature = KINDS[kind][3]
    result = {'party': party, 'kind': kind, 'account': account, 'date_from': date_from, 'date_to': date_to,
              'opening': ZERO, 'rows': [], 'total_debit': ZERO, 'total_credit': ZERO, 'closing': ZERO,
              'credit_nature': credit_nature}
    if account is None:
        return result

    qs = _rows(kind, account, party.pk, include_reversed)
    opening = ZERO
    if date_from:
        agg = qs.filter(date__lt=date_from).aggregate(d=Sum('debit'), c=Sum('credit'))
        opening = q2(_signed(q2(agg['d'] or 0), q2(agg['c'] or 0), credit_nature))
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    ledger_rows = list(qs.select_related('journal_entry').order_by('date', 'id'))
    sources = _source_map({r.journal_entry_id for r in ledger_rows})
    raw = [(r.date, r.debit, r.credit, r) for r in ledger_rows]
    rows, closing = statement_rows(opening, raw, credit_nature)

    out = []
    for day, debit, credit, r, balance in rows:
        src = sources.get(r.journal_entry_id, (None, None))
        out.append({'date': day, 'reference': r.reference or r.journal_entry.entry_no, 'description': r.description or '',
                    'debit': q2(debit), 'credit': q2(credit), 'balance': balance, 'entry': r.journal_entry,
                    'source_type': src[0], 'source_id': src[1]})
    result.update(opening=opening, rows=out, closing=closing,
                  total_debit=q2(sum((r['debit'] for r in out), ZERO)),
                  total_credit=q2(sum((r['credit'] for r in out), ZERO)))
    return result


def aging_report(kind, as_of=None, only_overdue=False):
    """
    Ageing of every customer / vendor, computed from the ledger (see posting_core.age_open_items: payments and
    credits are applied to the oldest charge first).

    Returns {'as_of', 'rows': [{'party','balance','buckets','advance','oldest'}], 'totals': {bucket: Decimal},
             'total', 'advance', 'unassigned'}
    Parties with nothing owed and nothing paid in advance are left out.
    """
    as_of = as_of or _date.today()
    account = control_account(kind)
    credit_nature = KINDS[kind][3]
    column = KINDS[kind][1]
    result = {'as_of': as_of, 'rows': [], 'totals': {b: ZERO for b in AGING_BUCKETS}, 'total': ZERO, 'advance': ZERO,
              'unassigned': unassigned_balance(kind), 'kind': kind}
    if account is None:
        return result

    by_party = {}
    qs = _rows(kind, account).filter(date__lte=as_of).order_by('date', 'id').values_list(f'{column}_id', 'date', 'debit', 'credit')
    for pid, day, debit, credit in qs.iterator():
        by_party.setdefault(pid, []).append((day, debit, credit))

    parties = KINDS[kind][0].objects.in_bulk(list(by_party))
    for pid, rows in by_party.items():
        buckets, advance = age_open_items(ZERO, rows, as_of, credit_nature)
        owed = q2(sum(buckets.values(), ZERO))
        if owed <= 0 and advance <= 0:
            continue
        if only_overdue and not any(buckets[b] > 0 for b in AGING_BUCKETS[1:]):
            continue
        oldest = next((r[0] for r in rows), None)
        result['rows'].append({'party': parties.get(pid), 'party_id': pid, 'balance': owed, 'buckets': buckets,
                               'advance': advance, 'oldest': oldest})
        for b in AGING_BUCKETS:
            result['totals'][b] += buckets[b]
        result['advance'] += advance
    result['rows'].sort(key=lambda r: (r['buckets']['91+'], r['buckets']['61-90'], r['balance']), reverse=True)
    result['total'] = q2(sum(result['totals'].values(), ZERO))
    result['advance'] = q2(result['advance'])
    return result
