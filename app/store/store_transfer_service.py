"""
store_transfer_service.py - store se store transfer: dispatch / receive / cancel.

Qaide
-----
* Dispatch: takes the source store stock out by FIFO (Inventory + StockBatch in one transaction).
* Goods in transit: neither in the source nor in the destination. Shown in the Transfer record.
* Receive: stock increases at the destination as new batches with the same cost.
* Short received (short/damage): the short quantity goes back to the same batch in the SOURCE store (goods never disappear).
  A reason is required.
* Cancel: only while in transit; all goods go back to the source.
"""
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

from ..models import (Inventory, StockBatch, StoreTransfer, StoreTransferBatchUsage,
                     StoreTransferItem)
from .store_issue_service import EPS, StoreIssueError, allocate_fifo

StoreTransferError = StoreIssueError      # one single error type, both views can catch it


def _d(x):
    return Decimal(str(x))


def _check_store(wh, role):
    profile = getattr(wh, 'store_profile', None)
    if profile is None:
        return
    if not profile.is_active:
        raise StoreTransferError(f"{wh.name} is not active.")
    if role == 'from' and not profile.can_issue:
        raise StoreTransferError(f"Sending goods from {wh.name} is not allowed.")


@transaction.atomic
def dispatch_transfer(*, user, from_warehouse, to_warehouse, purpose, items, transfer_date=None,
                      production_order=None, notes=''):
    """items: [(product, qty, remarks)]. Returns StoreTransfer (status in_transit)."""
    if not from_warehouse or not to_warehouse:
        raise StoreTransferError("Select both the sending store and the receiving store.")
    if from_warehouse.pk == to_warehouse.pk:
        raise StoreTransferError("The sending and receiving stores must be different.")
    if purpose not in {k for k, _ in StoreTransfer.PURPOSES}:
        raise StoreTransferError("Invalid purpose.")
    _check_store(from_warehouse, 'from')
    _check_store(to_warehouse, 'to')

    merged = {}
    for product, qty, remarks in items:
        try:
            qty = round(float(qty), 3)
        except (TypeError, ValueError):
            raise StoreTransferError(f"{product.name}: quantity is not valid.")
        if qty <= 0:
            raise StoreTransferError(f"{product.name}: quantity must be greater than zero.")
        if product.pk in merged:
            merged[product.pk][1] = round(merged[product.pk][1] + qty, 3)
        else:
            merged[product.pk] = [product, qty, (remarks or '')[:200]]
    if not merged:
        raise StoreTransferError("Add at least one item.")

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
        raise StoreTransferError("Not enough stock: " + "; ".join(shortages))

    transfer = StoreTransfer.objects.create(
        transfer_no='TMP-' + uuid.uuid4().hex[:12], transfer_date=transfer_date or now(),
        from_warehouse=from_warehouse, to_warehouse=to_warehouse, purpose=purpose,
        production_order=production_order, notes=(notes or '').strip(), created_by=user)
    transfer.transfer_no = f"TR-{transfer.pk:06d}"

    grand = Decimal('0.00')
    for product, qty, remarks, inv, batch_map, takes in plan:
        item = StoreTransferItem.objects.create(transfer=transfer, product=product, qty_sent=qty, remarks=remarks)
        item_total = Decimal('0')
        for batch_id, take in takes:
            batch = batch_map[batch_id]
            StockBatch.objects.filter(pk=batch_id).update(remaining_qty=F('remaining_qty') - take)
            StoreTransferBatchUsage.objects.create(item=item, batch_id=batch_id, qty=take, price=batch.price,
                                                   batch_no=batch.batch_no, expiry_date=batch.expiry_date)  # [agri-edition:usage-snapshot]
            item_total += _d(take) * batch.price
        item.total_cost = item_total.quantize(Decimal('0.01'), ROUND_HALF_UP)
        item.unit_cost = (item_total / _d(qty)).quantize(Decimal('0.0001'), ROUND_HALF_UP)
        item.save(update_fields=['total_cost', 'unit_cost'])
        inv.stock = round(inv.stock - qty, 6)
        inv.save(update_fields=['stock'])
        grand += item.total_cost
    transfer.total_cost = grand
    transfer.save(update_fields=['transfer_no', 'total_cost'])
    from . import store_accounting as _acc
    _acc.on_transfer_dispatched(transfer, user)
    return transfer


def _return_to_source(usage, qty, source_wh, product):
    """qty goes back to the same batch in the source (if the batch was deleted, a new batch at the same cost)."""
    if qty <= EPS:
        return
    if usage.batch_id and StockBatch.objects.filter(pk=usage.batch_id).exists():
        StockBatch.objects.filter(pk=usage.batch_id).update(remaining_qty=F('remaining_qty') + qty)
    else:
        StockBatch.objects.create(product=product, warehouse=source_wh, qty=qty, remaining_qty=qty, price=usage.price,
                                  batch_no=usage.batch_no, expiry_date=usage.expiry_date)  # [agri-edition:usage-snapshot]


def _add_stock(inv_wh, product, qty):
    inv, _ = Inventory.objects.select_for_update().get_or_create(product=product, warehouse=inv_wh)
    inv.stock = round(inv.stock + qty, 6)
    inv.save(update_fields=['stock'])


@transaction.atomic
def receive_transfer(transfer_id, user, received, reasons=None, notes=''):
    """
    received: {item_id: qty_received}   reasons: {item_id: text}
    Items whose qty is not given are treated as fully received.
    """
    reasons = reasons or {}
    transfer = (StoreTransfer.objects.select_for_update()
                .select_related('from_warehouse', 'to_warehouse').get(pk=transfer_id))
    if transfer.status != 'in_transit':
        raise StoreTransferError("This transfer can no longer be received (it was already received or cancelled).")
    _check_store(transfer.to_warehouse, 'to')

    items = list(transfer.items.select_related('product').prefetch_related('usages__batch'))
    # check everything first, then change anything
    plan = []
    for item in items:
        got = received.get(item.pk, item.qty_sent)
        try:
            got = round(float(got), 3)
        except (TypeError, ValueError):
            raise StoreTransferError(f"{item.product.name}: the receive quantity is not valid.")
        if got < 0 or got > item.qty_sent + EPS:
            raise StoreTransferError(f"{item.product.name}: the receive quantity must be between 0 and {item.qty_sent:g}.")
        got = min(got, item.qty_sent)
        reason = (reasons.get(item.pk) or '').strip()
        if item.qty_sent - got > EPS and not reason:
            raise StoreTransferError(f"{item.product.name}: less was received, a reason is required.")
        plan.append((item, got, reason))

    grand_received = Decimal('0.00')
    for item, got, reason in plan:
        usages = list(item.usages.all())
        takes, _short = allocate_fifo([(u.pk, u.qty) for u in usages], got)
        take_map = dict(takes)
        for u in usages:
            recv = take_map.get(u.pk, 0.0)
            if recv > EPS:
                nb = StockBatch.add_batch(item.product, recv, u.price, warehouse=transfer.to_warehouse,
                                          batch_no=u.batch_no or getattr(u.batch, 'batch_no', None),         # [agri-edition:transfer-recv]
                                          expiry_date=u.expiry_date or getattr(u.batch, 'expiry_date', None))
                u.dest_batch = nb
            _return_to_source(u, u.qty - recv, transfer.from_warehouse, item.product)
            u.received_qty = recv
            u.save(update_fields=['received_qty', 'dest_batch'])
        if got > EPS:
            _add_stock(transfer.to_warehouse, item.product, got)
        back = round(item.qty_sent - got, 6)
        if back > EPS:
            _add_stock(transfer.from_warehouse, item.product, back)
        item.qty_received = got
        item.short_reason = reason[:200]
        item.save(update_fields=['qty_received', 'short_reason'])
        grand_received += (item.unit_cost * _d(got)).quantize(Decimal('0.01'), ROUND_HALF_UP)

    transfer.status = 'received'
    transfer.received_by = user
    transfer.received_at = now()
    transfer.receive_notes = (notes or '')[:255]
    transfer.save(update_fields=['status', 'received_by', 'received_at', 'receive_notes'])
    from . import store_accounting as _acc
    _acc.on_transfer_received(transfer, user)
    return transfer


@transaction.atomic
def cancel_transfer(transfer_id, user, reason=''):
    """Cancel a transfer with goods in transit: all goods go back to the source."""
    transfer = (StoreTransfer.objects.select_for_update()
                .select_related('from_warehouse').get(pk=transfer_id))
    if transfer.status != 'in_transit':
        raise StoreTransferError("Only a transfer that is in transit can be cancelled.")
    for item in transfer.items.select_related('product').prefetch_related('usages__batch'):
        for u in item.usages.all():
            _return_to_source(u, u.qty, transfer.from_warehouse, item.product)
        _add_stock(transfer.from_warehouse, item.product, item.qty_sent)
    transfer.status = 'cancelled'
    transfer.cancelled_by = user
    transfer.cancelled_at = now()
    transfer.cancel_reason = (reason or '')[:255]
    transfer.save(update_fields=['status', 'cancelled_by', 'cancelled_at', 'cancel_reason'])
    from . import store_accounting as _acc
    _acc.on_transfer_cancelled(transfer, user, reason)
    return transfer
