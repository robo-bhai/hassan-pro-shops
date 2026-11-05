"""
store_ops_service.py - approval (issue request), physical count aur return to store ka engine.
Every action in one transaction: if anything fails, both stock and accounts go back to how they were.
"""
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

from . import store_access as _sa
from . import store_accounting as _acc
from .models import (Inventory, StockBatch, StoreCount, StoreCountLine, StoreIssue, StoreIssueItem,
                     StoreIssueRequest, StoreIssueRequestItem, StoreReturn, StoreReturnBatch, StoreReturnLine,
                     StoreSetting)
from .store_issue_service import EPS, StoreIssueError, allocate_fifo, create_issue

StoreOpsError = StoreIssueError


def _d(x):
    return Decimal(str(x))


def _temp():
    return 'TMP-' + uuid.uuid4().hex[:12]


# ===========================================================================
# APPROVAL
# ===========================================================================
def estimate_cost(from_warehouse, items):
    """items: [(product, qty)]. estimated cost by FIFO (without a lock, only for deciding)."""
    total = Decimal('0')
    for product, qty in items:
        left = float(qty)
        rows = (StockBatch.objects.filter(product=product, warehouse=from_warehouse, remaining_qty__gt=0)
                .order_by('id').values_list('remaining_qty', 'price'))
        for rem, price in rows:
            if left <= EPS:
                break
            take = min(left, rem)
            total += _d(take) * price
            left -= take
    return total.quantize(Decimal('0.01'), ROUND_HALF_UP)


def needs_approval(user, from_warehouse, est_cost):
    s = StoreSetting.get()
    if s.approval_mode == 'off':
        return False
    if user.is_superuser or _sa.can(user, from_warehouse.pk, 'manager'):
        return False            # manager / superuser can issue by themselves
    if s.approval_mode == 'always':
        return True
    return est_cost > s.approval_limit


@transaction.atomic
def create_request(*, user, from_warehouse, issue_type, items, issue_date=None, department=None,
                   production_order=None, received_by='', purpose=''):
    """items: [(product, qty, remarks)]. Stock does not move yet; the issue is created on manager approval."""
    if not from_warehouse:
        raise StoreOpsError("Select a store.")
    received_by = (received_by or '').strip()
    if not (department or received_by or production_order):
        raise StoreOpsError("At least one of Department, receiver or production order is required.")
    if issue_type not in {k for k, _ in StoreIssue.ISSUE_TYPES}:
        raise StoreOpsError("Invalid issue type.")
    merged = {}
    for product, qty, remarks in items:
        qty = round(float(qty), 3)
        if qty <= 0:
            raise StoreOpsError(f"{product.name}: quantity must be greater than zero.")
        if product.pk in merged:
            merged[product.pk][1] = round(merged[product.pk][1] + qty, 3)
        else:
            merged[product.pk] = [product, qty, (remarks or '')[:200]]
    if not merged:
        raise StoreOpsError("Add at least one item.")
    est = estimate_cost(from_warehouse, [(p, q) for p, q, _ in merged.values()])
    req = StoreIssueRequest.objects.create(
        request_no=_temp(), from_warehouse=from_warehouse, issue_type=issue_type, department=department,
        production_order=production_order, received_by=received_by, purpose=(purpose or '').strip(),
        issue_date=issue_date or now(), est_cost=est, requested_by=user)
    req.request_no = f"RQ-{req.pk:06d}"
    req.save(update_fields=['request_no'])
    for product, qty, remarks in merged.values():
        StoreIssueRequestItem.objects.create(request=req, product=product, qty=qty, remarks=remarks)
    return req


@transaction.atomic
def approve_request(request_id, user, note='', allow_self=False):
    req = (StoreIssueRequest.objects.select_for_update().select_related('from_warehouse', 'department',
                                                                         'production_order', 'requested_by')
           .get(pk=request_id))
    if req.status != 'pending':
        raise StoreOpsError("This request is no longer pending.")
    if req.requested_by_id == user.pk and not allow_self:
        raise StoreOpsError("You cannot approve your own request; another manager will approve it.")
    items = [(i.product, i.qty, i.remarks) for i in req.items.select_related('product')]
    issue = create_issue(user=req.requested_by or user, from_warehouse=req.from_warehouse,
                         issue_type=req.issue_type, items=items, issue_date=req.issue_date,
                         department=req.department, production_order=req.production_order,
                         received_by=req.received_by, purpose=req.purpose)
    req.status, req.issue = 'approved', issue
    req.decided_by, req.decided_at, req.decision_note = user, now(), (note or '')[:255]
    req.save(update_fields=['status', 'issue', 'decided_by', 'decided_at', 'decision_note'])
    return req


@transaction.atomic
def reject_request(request_id, user, note):
    note = (note or '').strip()
    if not note:
        raise StoreOpsError("A reason for rejection is required.")
    req = StoreIssueRequest.objects.select_for_update().get(pk=request_id)
    if req.status != 'pending':
        raise StoreOpsError("This request is no longer pending.")
    req.status, req.decided_by, req.decided_at, req.decision_note = 'rejected', user, now(), note[:255]
    req.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
    return req


@transaction.atomic
def cancel_request(request_id, user):
    req = StoreIssueRequest.objects.select_for_update().get(pk=request_id)
    if req.status != 'pending':
        raise StoreOpsError("Only a pending request can be cancelled.")
    req.status, req.decided_by, req.decided_at, req.decision_note = 'cancelled', user, now(), 'Cancelled'
    req.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
    return req


# ===========================================================================
# PHYSICAL COUNT
# ===========================================================================
@transaction.atomic
def start_count(user, warehouse, notes='', include_zero=False):
    if StoreCount.objects.filter(warehouse=warehouse, status__in=['counting', 'submitted']).exists():
        raise StoreOpsError(f"{warehouse.name} already has an open count. Post or cancel it first.")
    rows = Inventory.objects.filter(warehouse=warehouse).select_related('product')
    rows = rows if include_zero else rows.filter(stock__gt=0)
    rows = list(rows.order_by('product__name'))
    if not rows:
        raise StoreOpsError(f"There are no items to count in {warehouse.name}.")
    count = StoreCount.objects.create(count_no=_temp(), warehouse=warehouse, notes=(notes or '')[:255],
                                      created_by=user)
    count.count_no = f"CT-{count.pk:06d}"
    count.save(update_fields=['count_no'])
    StoreCountLine.objects.bulk_create([StoreCountLine(count=count, product=r.product, system_qty=r.stock)
                                        for r in rows])
    return count


@transaction.atomic
def save_counts(count_id, counted, reasons=None):
    """counted: {line_id: float|None}. Only when the status is counting."""
    reasons = reasons or {}
    count = StoreCount.objects.select_for_update().get(pk=count_id)
    if count.status != 'counting':
        raise StoreOpsError("This count can no longer be edited.")
    for line in count.lines.all():
        if line.pk in counted:
            val = counted[line.pk]
            if val is not None:
                val = round(float(val), 3)
                if val < 0:
                    raise StoreOpsError(f"{line.product.name}: the count cannot be negative.")
            line.counted_qty = val
        if line.pk in reasons:
            line.reason = (reasons[line.pk] or '')[:200]
        line.save(update_fields=['counted_qty', 'reason'])
    return count


@transaction.atomic
def submit_count(count_id, user):
    count = StoreCount.objects.select_for_update().get(pk=count_id)
    if count.status != 'counting':
        raise StoreOpsError("This count has already been submitted.")
    missing = count.lines.filter(counted_qty__isnull=True).count()
    if missing:
        raise StoreOpsError(f"The count of {missing} item(s) is still pending. Enter the count for all items (0 if there is none).")
    count.status, count.submitted_by, count.submitted_at = 'submitted', user, now()
    count.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    return count


@transaction.atomic
def cancel_count(count_id, user):
    count = StoreCount.objects.select_for_update().get(pk=count_id)
    if count.status not in ('counting', 'submitted'):
        raise StoreOpsError("This count cannot be cancelled.")
    count.status = 'cancelled'
    count.save(update_fields=['status'])
    return count


def _avg_cost(product, warehouse):
    rows = list(StockBatch.objects.filter(product=product, warehouse=warehouse, remaining_qty__gt=0)
                .values_list('remaining_qty', 'price'))
    qty = sum(r for r, _ in rows)
    if qty > EPS:
        return (sum(_d(r) * p for r, p in rows) / _d(qty)).quantize(Decimal('0.0001'), ROUND_HALF_UP)
    last = StockBatch.objects.filter(product=product).order_by('-id').first()
    return _d(last.price) if last else None


@transaction.atomic
def post_count(count_id, user, unit_costs=None, reasons=None, allow_self=False):
    """Applying the difference (short/extra) to stock. Short: taken out by FIFO. Extra: a new batch at average cost."""
    unit_costs, reasons = unit_costs or {}, reasons or {}
    count = StoreCount.objects.select_for_update().select_related('warehouse').get(pk=count_id)
    if count.status != 'submitted':
        raise StoreOpsError("Only a submitted count can be posted.")
    if count.submitted_by_id == user.pk and not allow_self:
        raise StoreOpsError("The person who submitted the count cannot post it; a manager or superuser will post it.")
    wh = count.warehouse
    loss, gain = Decimal('0.00'), Decimal('0.00')

    for line in count.lines.select_related('product'):
        if line.pk in reasons:
            line.reason = (reasons[line.pk] or '')[:200]
        inv, _ = Inventory.objects.select_for_update().get_or_create(product=line.product, warehouse=wh)
        current = inv.stock
        line.posted_system_qty = current
        diff = round(line.counted_qty - current, 6)
        if abs(diff) <= EPS:
            line.diff_qty, line.diff_value = 0, Decimal('0.00')
            line.save()
            continue
        if not (line.reason or '').strip():
            raise StoreOpsError(f"{line.product.name}: there is a difference ({diff:+g}), a reason is required.")
        if diff < 0:
            qty = -diff
            batches = list(StockBatch.objects.select_for_update()
                           .filter(product=line.product, warehouse=wh, remaining_qty__gt=0)
                           .order_by(F('expiry_date').asc(nulls_last=True), 'id'))  # [agri-edition:fefo]
            takes, short = allocate_fifo([(b.pk, b.remaining_qty) for b in batches], qty)
            if short > EPS:
                raise StoreOpsError(f"{line.product.name}: batch records cover only {qty - short:g} (stock audit).")
            bmap = {b.pk: b for b in batches}
            cost = Decimal('0')
            for bid, take in takes:
                StockBatch.objects.filter(pk=bid).update(remaining_qty=F('remaining_qty') - take)
                cost += _d(take) * bmap[bid].price
            cost = cost.quantize(Decimal('0.01'), ROUND_HALF_UP)
            line.unit_cost = (cost / _d(qty)).quantize(Decimal('0.0001'), ROUND_HALF_UP)
            line.diff_value = -cost
            loss += cost
        else:
            price = unit_costs.get(line.pk)
            price = _d(price) if price not in (None, '') else _avg_cost(line.product, wh)
            if price is None or price <= 0:
                raise StoreOpsError(f"{line.product.name}: the cost of the extra goods is unknown, enter the unit cost on the review page.")
            price = _d(price).quantize(Decimal('0.01'), ROUND_HALF_UP)
            StockBatch.add_batch(line.product, diff, price, warehouse=wh)
            value = (_d(diff) * price).quantize(Decimal('0.01'), ROUND_HALF_UP)
            line.unit_cost, line.diff_value = price, value
            gain += value
        inv.stock = line.counted_qty
        inv.save(update_fields=['stock'])
        line.diff_qty = diff
        line.save()

    count.loss_value, count.gain_value = loss, gain
    count.status, count.posted_by, count.posted_at = 'posted', user, now()
    count.save(update_fields=['loss_value', 'gain_value', 'status', 'posted_by', 'posted_at'])
    _acc.on_count_posted(count, user)
    return count


# ===========================================================================
# RETURN TO STORE
# ===========================================================================
@transaction.atomic
def create_return(*, user, issue_id, quantities, returned_by='', notes='', return_date=None):
    """quantities: {issue_item_id: qty}. Goods go back to the batch they came from (last out, first back)."""
    issue = StoreIssue.objects.select_for_update().select_related('from_warehouse').get(pk=issue_id)
    if issue.status != 'issued':
        raise StoreOpsError("Goods can be returned only from an active (issued) issue.")
    quantities = {k: round(float(v), 3) for k, v in quantities.items() if v not in (None, '') and float(v) > 0}
    if not quantities:
        raise StoreOpsError("Enter the return quantity for at least one item.")

    items = {i.pk: i for i in issue.items.select_related('product')}
    ret = StoreReturn.objects.create(return_no=_temp(), issue=issue, return_date=return_date or now(),
                                     returned_by=(returned_by or '')[:100], notes=(notes or '')[:255],
                                     created_by=user)
    ret.return_no = f"RT-{ret.pk:06d}"
    grand = Decimal('0.00')
    for item_id, qty in quantities.items():
        item = items.get(item_id)
        if item is None:
            raise StoreOpsError("The item does not belong to this issue.")
        already = sum(l.qty for l in item.return_lines.all())
        room = round(item.qty - already, 6)
        if qty > room + EPS:
            raise StoreOpsError(f"{item.product.name}: only {room:g} can be returned (issued {item.qty:g}, already returned {already:g}).")
        line = StoreReturnLine.objects.create(ret=ret, issue_item=item, qty=qty)
        left, cost = qty, Decimal('0')
        for usage in item.usages.select_for_update().order_by('-id'):
            if left <= EPS:
                break
            used_back = sum(b.qty for b in usage.returns.all())
            available = round(usage.qty - used_back, 6)
            if available <= EPS:
                continue
            take = min(left, available)
            if usage.batch_id and StockBatch.objects.filter(pk=usage.batch_id).exists():
                StockBatch.objects.filter(pk=usage.batch_id).update(remaining_qty=F('remaining_qty') + take)
            else:
                StockBatch.objects.create(product=item.product, warehouse=issue.from_warehouse, qty=take,
                                          remaining_qty=take, price=usage.price,
                                          batch_no=usage.batch_no, expiry_date=usage.expiry_date)  # [agri-edition:usage-snapshot]
            StoreReturnBatch.objects.create(line=line, usage=usage, qty=take)
            cost += _d(take) * usage.price
            left -= take
        if left > EPS:
            raise StoreOpsError(f"{item.product.name}: the return accounting was not found in the batch records.")
        inv, _ = Inventory.objects.select_for_update().get_or_create(product=item.product,
                                                                    warehouse=issue.from_warehouse)
        inv.stock = round(inv.stock + qty, 6)
        inv.save(update_fields=['stock'])
        line.total_cost = cost.quantize(Decimal('0.01'), ROUND_HALF_UP)
        line.save(update_fields=['total_cost'])
        grand += line.total_cost
    ret.total_cost = grand
    ret.save(update_fields=['return_no', 'total_cost'])
    _acc.on_return_created(ret, user)
    return ret
