"""Agri Edition: write expired / damaged stock off a batch.

The stock leaves the batch and the Inventory row exactly like a physical-count loss
(queryset.update, no Sale / StockBatch.save()). When Store accounting is ON the loss is posted
(Dr Stock loss / Cr Inventory) with the same account mapping the stock count uses; if the mapping
is missing the whole write-off is rolled back and the message says what to map.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F

EPS = 1e-9
REASONS = ('expired', 'damaged', 'vendor_return')


class WriteOffError(Exception):
    pass


def writeoff_value(qty, unit_cost):
    return (Decimal(str(qty)) * Decimal(str(unit_cost))).quantize(Decimal('0.01'), ROUND_HALF_UP)


@transaction.atomic
def write_off_batch(batch_id, user, reason='expired', note='', qty=None):
    """Write off `qty` (default: everything left) of one batch. Returns the ExpiryWriteOff row."""
    from ..models import ExpiryWriteOff, Inventory, StockBatch, StoreJournalLink
    from ..store import store_accounting as acc

    if reason not in REASONS:
        raise WriteOffError('Wajah (reason) sahi nahi hai.')
    batch = (StockBatch.objects.select_for_update().select_related('product', 'warehouse')
             .filter(pk=batch_id).first())
    if batch is None:
        raise WriteOffError('Batch nahi mila.')
    left = float(batch.remaining_qty)
    if left <= EPS:
        raise WriteOffError('%s ka is batch mein koi maal baaqi nahi.' % batch.product.name)
    take = left if qty in (None, '') else round(float(qty), 6)
    if take <= EPS:
        raise WriteOffError('Miqdar zero se zyada honi chahiye.')
    if take > left + EPS:
        raise WriteOffError('%s: sirf %g baaqi hai, aap ne %g likha.' % (batch.product.name, left, take))
    take = min(take, left)

    value = writeoff_value(take, batch.price)
    StockBatch.objects.filter(pk=batch.pk).update(remaining_qty=F('remaining_qty') - take)
    inv, _ = Inventory.objects.select_for_update().get_or_create(product=batch.product, warehouse=batch.warehouse)
    inv.stock = round(float(inv.stock) - take, 6)
    inv.save(update_fields=['stock'])

    row = ExpiryWriteOff.objects.create(
        product=batch.product, warehouse=batch.warehouse, batch=batch, batch_no=batch.batch_no,
        expiry_date=batch.expiry_date, qty=take, unit_cost=batch.price, value=value, reason=reason,
        note=(note or '')[:200], created_by=user)

    if value > 0 and acc.enabled():
        label = dict(row.REASONS).get(reason, reason)
        loss = acc._simple_account('count_loss', 'Stock loss')
        inv_acc = acc.inventory_account(batch.warehouse)
        acc._post(row.created_at.date(), 'AGRI-WO-%06d' % row.pk,
                  'Agri write-off (%s): %s x %g' % (label, batch.product.name, take),
                  [(loss, True, value, batch.product.name), (inv_acc, False, value, batch.warehouse.name)],
                  user, 'agri_writeoff', row.pk)
    return row
