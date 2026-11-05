"""
store_issue_service.py - engine for internally issuing / cancelling stock.

Rules
-----
* Only the stock of the selected store (warehouse) is used.
* FIFO: oldest batch first (like a sale), cost from the batch price.
* Inventory + StockBatch are both updated in one transaction; if any item is short,
  the WHOLE issue is rolled back (half the stock is never taken out).
* On cancel the stock goes back to the batch it came from.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

from .models import (Inventory, StockBatch, StoreIssue, StoreIssueBatchUsage,
                     StoreIssueItem, Warehouse)

EPS = 1e-9


class StoreIssueError(Exception):
    pass


def allocate_fifo(batches, qty):
    """
    batches: [(key, remaining_qty), ...] purane se naye.
    Returns ([(key, take), ...], shortfall)
    """
    takes, left = [], float(qty)
    for key, remaining in batches:
        if left <= EPS:
            break
        if remaining <= EPS:
            continue
        take = min(left, float(remaining))
        takes.append((key, take))
        left -= take
    return takes, max(left, 0.0)


def _d(x):
    return Decimal(str(x))


@transaction.atomic
def create_issue(*, user, from_warehouse, issue_type, items, issue_date=None, department=None,
                 production_order=None, received_by='', purpose=''):
    """
    items: list of (product, qty, remarks)
    Returns the created StoreIssue. Raises StoreIssueError with a readable message.
    """
    valid_types = {k for k, _ in StoreIssue.ISSUE_TYPES}
    if issue_type not in valid_types:
        raise StoreIssueError("Invalid issue type.")
    if not from_warehouse:
        raise StoreIssueError("Select a store.")

    profile = getattr(from_warehouse, 'store_profile', None)
    if profile and (not profile.is_active or not profile.can_issue):
        raise StoreIssueError(f"Issuing from {from_warehouse.name} is not allowed.")

    received_by = (received_by or '').strip()
    if not (department or received_by or production_order):
        raise StoreIssueError("At least one of Department, receiver (given to whom) or production order is required.")

    # merge lines of the same product
    merged = {}
    for product, qty, remarks in items:
        try:
            qty = round(float(qty), 3)
        except (TypeError, ValueError):
            raise StoreIssueError(f"{product.name}: quantity is not valid.")
        if qty <= 0:
            raise StoreIssueError(f"{product.name}: quantity must be greater than zero.")
        if product.pk in merged:
            merged[product.pk][1] = round(merged[product.pk][1] + qty, 3)
        else:
            merged[product.pk] = [product, qty, (remarks or '')[:200]]
    if not merged:
        raise StoreIssueError("Add at least one item.")

    # ---- 1) lock + check + FIFO plan (before changing anything)
    shortages, plan = [], []
    for product, qty, remarks in merged.values():
        inv = Inventory.objects.select_for_update().filter(product=product, warehouse=from_warehouse).first()
        available = inv.available_stock if inv else 0.0
        if inv is None or available + EPS < qty:
            shortages.append(f"{product.name}: available {available:g}, needed {qty:g}")
            continue
        batches = list(StockBatch.objects.select_for_update()
                       .filter(product=product, warehouse=from_warehouse, remaining_qty__gt=0)
                       .order_by(F('expiry_date').asc(nulls_last=True), 'id'))  # [agri-edition:fefo]
        takes, short = allocate_fifo([(b.pk, b.remaining_qty) for b in batches], qty)
        if short > EPS:
            shortages.append(f"{product.name}: batch records cover only {qty - short:g} (audit the stock)")
            continue
        plan.append((product, qty, remarks, inv, {b.pk: b for b in batches}, takes))
    if shortages:
        raise StoreIssueError("Not enough stock: " + "; ".join(shortages))

    # ---- 2) document banao
    import uuid
    issue = StoreIssue.objects.create(
        issue_no='TMP-' + uuid.uuid4().hex[:12],
        issue_date=issue_date or now(), from_warehouse=from_warehouse, issue_type=issue_type,
        department=department, production_order=production_order, received_by=received_by,
        purpose=(purpose or '').strip(), created_by=user,
    )
    issue.issue_no = f"SI-{issue.pk:06d}"

    # ---- 3) stock nikalo
    grand = Decimal('0.00')
    for product, qty, remarks, inv, batch_map, takes in plan:
        item_total = Decimal('0')
        item = StoreIssueItem.objects.create(issue=issue, product=product, qty=qty, remarks=remarks)
        for batch_id, take in takes:
            batch = batch_map[batch_id]
            StockBatch.objects.filter(pk=batch_id).update(remaining_qty=F('remaining_qty') - take)
            StoreIssueBatchUsage.objects.create(item=item, batch_id=batch_id, qty=take, price=batch.price,
                                                batch_no=batch.batch_no, expiry_date=batch.expiry_date)  # [agri-edition:usage-snapshot]
            item_total += _d(take) * batch.price
        item.total_cost = item_total.quantize(Decimal('0.01'), ROUND_HALF_UP)
        item.unit_cost = (item_total / _d(qty)).quantize(Decimal('0.0001'), ROUND_HALF_UP)
        item.save(update_fields=['total_cost', 'unit_cost'])
        inv.stock = round(inv.stock - qty, 6)
        inv.save(update_fields=['stock'])           # the low-stock signal runs from here
        grand += item.total_cost
    issue.total_cost = grand
    issue.save(update_fields=['issue_no', 'total_cost'])
    from . import store_accounting as _acc          # accounting on ho to journal entry (usi transaction me)
    _acc.on_issue_created(issue, user)
    return issue


@transaction.atomic
def cancel_issue(issue_id, user, reason=''):
    """Issue cancel: stock goes back to the same batch."""
    issue = StoreIssue.objects.select_for_update().get(pk=issue_id)
    if issue.status == 'cancelled':
        raise StoreIssueError("This issue has already been cancelled.")
    from .models import StoreReturn
    if StoreReturn.objects.filter(issue=issue).exists():
        raise StoreIssueError("Goods have already been returned from this issue, so it cannot be cancelled.")

    for item in issue.items.select_related('product').prefetch_related('usages__batch'):
        for u in item.usages.all():
            if u.batch_id and StockBatch.objects.filter(pk=u.batch_id).exists():
                StockBatch.objects.filter(pk=u.batch_id).update(remaining_qty=F('remaining_qty') + u.qty)
            else:   # the batch is already deleted - the new batch gets the same cost
                StockBatch.objects.create(product=item.product, warehouse=issue.from_warehouse,
                                          qty=u.qty, remaining_qty=u.qty, price=u.price,
                                          batch_no=u.batch_no, expiry_date=u.expiry_date)  # [agri-edition:usage-snapshot]
        inv, _ = Inventory.objects.select_for_update().get_or_create(product=item.product,
                                                                    warehouse=issue.from_warehouse)
        inv.stock = round(inv.stock + item.qty, 6)
        inv.save(update_fields=['stock'])

    issue.status = 'cancelled'
    issue.cancelled_by = user
    issue.cancelled_at = now()
    issue.cancel_reason = (reason or '')[:255]
    issue.save(update_fields=['status', 'cancelled_by', 'cancelled_at', 'cancel_reason'])
    from . import store_accounting as _acc
    _acc.on_issue_cancelled(issue, user, reason)
    return issue
