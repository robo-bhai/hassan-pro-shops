"""
store_accounting.py - linking store activity to the Chart of Accounts (journal entries).

Default: OFF (StoreSetting.accounting_enabled = False). Map the accounts in Store Settings before turning it on.

Entries
-------
* Issue        : Dr Expense/WIP (by issue type)      Cr Inventory (of that store)
* Issue cancel : ulti entry (JournalEntry.reverse)
* Return       : Dr Inventory                                 Cr Kharch/WIP
* Transfer     : only when the Inventory accounts of the two stores are different:
                 bhejte waqt  Dr In-transit  Cr Inventory(from)
                 on receive  Dr Inventory(to) [received]  Dr Inventory(from) [short received, returned]  Cr In-transit
                 cancel       ulti entry
* Count         : kam  -> Dr Stock loss  Cr Inventory      zyada -> Dr Inventory  Cr Stock gain
If the mapping is incomplete and accounting is ON, the document is not created at all (stock and accounts never get out of sync).
"""
from decimal import Decimal, ROUND_HALF_UP

from .models import (Account, JournalEntry, JournalEntryItem, StoreAccountRule, StoreIssue, StoreJournalLink,
                     StoreSetting)
from .store_issue_service import StoreIssueError


class AccountingMappingError(StoreIssueError):
    pass


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), ROUND_HALF_UP)


def enabled():
    return StoreSetting.get().accounting_enabled


def _rule(kind, key=''):
    r = StoreAccountRule.objects.select_related('account').filter(kind=kind, key=key).first()
    return r.account if r else None


def inventory_account(warehouse):
    acc = _rule('inventory', str(warehouse.pk)) or _rule('inventory', '')
    if not acc:
        raise AccountingMappingError(
            f"Accounting is ON but the Inventory account for {warehouse.name} is not set (map it in Store Settings).")
    return acc


def expense_account(issue_type):
    acc = _rule('expense', issue_type) or _rule('expense', '')
    if not acc:
        raise AccountingMappingError(
            f"Accounting is ON but the expense account for '{issue_type}' is not set (map it in Store Settings).")
    return acc


def _simple_account(kind, label):
    acc = _rule(kind, '')
    if not acc:
        raise AccountingMappingError(f"Accounting is ON but the {label} account is not set (map it in Store Settings).")
    return acc


def _post(entry_date, reference, description, lines, user, doc_type, doc_id):
    """lines: [(account, is_debit, amount, text)]. Creates a balanced entry and posts it."""
    lines = [(a, d, _q(amt), t) for a, d, amt, t in lines if _q(amt) > 0]
    if not lines:
        return None
    dr = sum(a for _, d, a, _ in lines if d)
    cr = sum(a for _, d, a, _ in lines if not d)
    if dr != cr:
        raise AccountingMappingError(f"The journal entry does not balance (Dr {dr} / Cr {cr}).")
    entry = JournalEntry.objects.create(
        entry_date=entry_date, entry_type='adjustment', reference=(reference or '')[:100],
        description=description, created_by=user, status='draft')
    for acc, is_debit, amt, text in lines:
        JournalEntryItem.objects.create(journal_entry=entry, account=acc, is_debit=is_debit, amount=amt,
                                        description=(text or '')[:255])
    entry.post(user)
    StoreJournalLink.objects.create(doc_type=doc_type, doc_id=doc_id, journal_entry=entry, amount=dr)
    return entry


def _reverse(doc_type, doc_id, user, reason):
    link = (StoreJournalLink.objects.filter(doc_type=doc_type, doc_id=doc_id, journal_entry__isnull=False)
            .select_related('journal_entry').order_by('-id').first())
    if link and link.journal_entry.status == 'posted':
        link.journal_entry.reverse(user, reason or 'store document cancel')


# ---------------------------------------------------------------- issue / return
def on_issue_created(issue, user):
    if not enabled() or issue.total_cost <= 0:
        return
    _post(issue.issue_date.date(), issue.issue_no, f"Store issue {issue.issue_no} ({issue.get_issue_type_display()})",
          [(expense_account(issue.issue_type), True, issue.total_cost, issue.issue_no),
           (inventory_account(issue.from_warehouse), False, issue.total_cost, issue.from_warehouse.name)],
          user, 'issue', issue.pk)


def on_issue_cancelled(issue, user, reason=''):
    if StoreJournalLink.objects.filter(doc_type='issue', doc_id=issue.pk).exists():
        _reverse('issue', issue.pk, user, f"{issue.issue_no} cancel: {reason}")


def on_return_created(ret, user):
    if not enabled() or ret.total_cost <= 0:
        return
    issue = ret.issue
    _post(ret.return_date.date(), ret.return_no, f"Store return {ret.return_no} (issue {issue.issue_no})",
          [(inventory_account(issue.from_warehouse), True, ret.total_cost, issue.from_warehouse.name),
           (expense_account(issue.issue_type), False, ret.total_cost, ret.return_no)],
          user, 'return', ret.pk)


# ---------------------------------------------------------------- transfer
def _accounts_differ(transfer):
    return inventory_account(transfer.from_warehouse).pk != inventory_account(transfer.to_warehouse).pk


def on_transfer_dispatched(transfer, user):
    if not enabled() or transfer.total_cost <= 0 or not _accounts_differ(transfer):
        return
    _post(transfer.transfer_date.date(), transfer.transfer_no, f"Store transfer {transfer.transfer_no} bheja gaya",
          [(_simple_account('transit', 'In-transit'), True, transfer.total_cost, transfer.to_warehouse.name),
           (inventory_account(transfer.from_warehouse), False, transfer.total_cost, transfer.from_warehouse.name)],
          user, 'transfer_send', transfer.pk)


def on_transfer_received(transfer, user):
    if not enabled() or transfer.total_cost <= 0 or not _accounts_differ(transfer):
        return
    got = sum((_q(i.unit_cost * Decimal(str(i.qty_received or 0))) for i in transfer.items.all()), Decimal('0.00'))
    short = _q(transfer.total_cost) - got
    transit = _simple_account('transit', 'In-transit')
    lines = [(transit, False, transfer.total_cost, transfer.transfer_no),
             (inventory_account(transfer.to_warehouse), True, got, transfer.to_warehouse.name)]
    if short > 0:
        lines.append((inventory_account(transfer.from_warehouse), True, short, 'short received, returned'))
    _post(transfer.received_at.date() if transfer.received_at else transfer.transfer_date.date(),
          transfer.transfer_no, f"Store transfer {transfer.transfer_no} receive hua", lines, user,
          'transfer_receive', transfer.pk)


def on_transfer_cancelled(transfer, user, reason=''):
    if StoreJournalLink.objects.filter(doc_type='transfer_send', doc_id=transfer.pk).exists():
        _reverse('transfer_send', transfer.pk, user, f"{transfer.transfer_no} cancel: {reason}")


# ---------------------------------------------------------------- count
def on_count_posted(count, user):
    if not enabled():
        return
    loss, gain = _q(count.loss_value), _q(count.gain_value)
    inv = inventory_account(count.warehouse)
    lines = []
    if loss > 0:
        lines += [(_simple_account('count_loss', 'Stock loss'), True, loss, count.count_no),
                  (inv, False, loss, count.warehouse.name)]
    if gain > 0:
        lines += [(inv, True, gain, count.warehouse.name),
                  (_simple_account('count_gain', 'Stock gain'), False, gain, count.count_no)]
    _post(count.posted_at.date() if count.posted_at else count.count_date.date(), count.count_no,
          f"Physical count {count.count_no} ({count.warehouse.name})", lines, user, 'count', count.pk)


# ---------------------------------------------------------------- opening stock
def post_opening_entry(user, stores):
    """Maujooda stock ki value ek dafa Inventory account me daalna (Dr Inventory / Cr Opening equity)."""
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum
    from django.utils.timezone import localdate
    from .models import StockBatch
    if StoreJournalLink.objects.filter(doc_type='opening').exists():
        raise AccountingMappingError("The opening stock entry has already been created. Creating it again would double the value.")
    opening = _simple_account('opening', 'Opening balance (equity)')
    lines, total = [], Decimal('0.00')
    for wh in stores:
        val = StockBatch.objects.filter(warehouse=wh, remaining_qty__gt=0).aggregate(
            t=Sum(ExpressionWrapper(F('remaining_qty') * F('price'),
                                    output_field=DecimalField(max_digits=18, decimal_places=2))))['t'] or Decimal('0')
        val = _q(val)
        if val > 0:
            lines.append((inventory_account(wh), True, val, f"Opening stock {wh.name}"))
            total += val
    if total <= 0:
        raise AccountingMappingError("No stock value was found in any store.")
    lines.append((opening, False, total, 'Opening stock'))
    return _post(localdate(), 'OPENING-STOCK', 'Opening stock value (stores)', lines, user, 'opening', 0), total
