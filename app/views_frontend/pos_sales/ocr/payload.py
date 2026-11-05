"""Price / stock / batch JSON of the products shown in the scan result (3 queries for all of them)."""
from ....models import Inventory, StockBatch
from ....utils.pos import ocr_core as core
from .common import _int_or_none


def _load_batches(product_ids, warehouse_id):
    """{product_id: [(batch_id, remaining, cost, selling), ...]} oldest first - ONE query for all products."""
    qs = StockBatch.objects.filter(product_id__in=product_ids, remaining_qty__gt=0)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    out = {}
    for bid, pid, rem, price, sp in qs.order_by('id').values_list('id', 'product_id', 'remaining_qty', 'price',
                                                                    'selling_price'):
        out.setdefault(pid, []).append((bid, rem, price, sp))
    return out


def _load_stock(product_ids, warehouse_id):
    """{product_id: Inventory.stock} in the warehouse - ONE query."""
    out = {}
    if not warehouse_id:
        return out
    for pid, stock in Inventory.objects.filter(product_id__in=product_ids, warehouse_id=warehouse_id) \
            .order_by('id').values_list('product_id', 'stock'):
        out.setdefault(pid, stock)                 # first row wins, like the old .first()
    return out


def _payload_from(product, batches, inv_stock, warehouse_id):
    """Same fields as search_products_ajax / the old _payload, built from rows that are already loaded."""
    b = core.batch_summary(batches, inv_stock, bool(warehouse_id))
    sp = b['selling_price']
    lb = b['latest_batch_price']
    has_sp = sp > 0
    return {
        'id': product.id,
        'name': product.name,
        'barcode': product.barcode or '',
        'serial_no': product.serial_no or '',
        'price': str(sp if has_sp else 0),
        'cost_price': str(lb if lb > 0 else float(product.price or 0)),
        'stock': b['stock'],
        'unit': product.unit.name if getattr(product, 'unit', None) else '',
        'has_selling_price': has_sp,
        'warning': b['warning'],
        'selling_price': str(sp if has_sp else 0),
        'batch_count': b['batch_count'],
        'latest_batch_price': str(lb if lb > 0 else 0),
        'batch_remaining_qty': str(b['batch_remaining']),
        'batch_id': b['batch_id'],
    }


def _payload(product, warehouse_id):
    """Single product (kept for old callers). The scan view uses the batched loaders instead."""
    wid = _int_or_none(warehouse_id)
    return _payload_from(product, _load_batches([product.id], wid).get(product.id, []),
                         _load_stock([product.id], wid).get(product.id), wid)
