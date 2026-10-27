"""
signals_gl.py - live ledger posting (Step 2).

Whenever a sale, payment, purchase or expense is saved or deleted, its ledger entry is brought up to date
right after the database transaction commits (so a sale's items and payments are all there by then).

* Failures never break the sale/purchase screen: they are logged, and `post_ledger --backfill` books anything missed.
* Switch off with  GL_LIVE_POSTING = False  in settings.
* Pause inside your own code:   with gl_paused(): ...
"""
import logging
import threading
from contextlib import contextmanager

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save

from . import posting
from ..models import (CashTransaction, CustomerPayment, DailyClosing, Expense, Payroll, Purchase, PurchaseItem, PurchaseRetrn,
                     PurchaseRetrnItem, Sale, SaleItem, SalePayment, SaleRetrn, SaleRetrnItem, StockAdjustment,
                     StockAdjustmentItem, Vendor, VendorPayment)

logger = logging.getLogger(__name__)
_state = threading.local()


@contextmanager
def gl_paused():
    """Skip live posting inside this block (used by imports and bulk tools)."""
    previous = getattr(_state, 'paused', False)
    _state.paused = True
    try:
        yield
    finally:
        _state.paused = previous


def _enabled():
    return getattr(settings, 'GL_LIVE_POSTING', True) and not getattr(_state, 'paused', False)


def _run(source_type, pk):
    model = posting.SOURCES[source_type][0]
    try:
        obj = model.objects.filter(pk=pk).first()
        if obj is None:                                   # document was deleted
            posting.reverse_posting(source_type, pk, reason='Document deleted')
        else:
            posting.post_document(source_type, obj, repost=True)
    except Exception:                                      # never break the user's screen
        logger.exception('Ledger posting failed for %s #%s (run: manage.py post_ledger --backfill)', source_type, pk)


def _schedule(source_type, pk):
    if pk and _enabled():
        transaction.on_commit(lambda: _run(source_type, pk))


def _saved(source_type):
    def handler(sender, instance, raw=False, **kwargs):
        if not raw:
            _schedule(source_type, instance.pk)
    return handler


def _deleted(source_type):
    def handler(sender, instance, **kwargs):
        _schedule(source_type, instance.pk)
    return handler


def _parent_saved(source_type, parent_attr):
    def handler(sender, instance, raw=False, **kwargs):
        if not raw:
            _schedule(source_type, getattr(instance, parent_attr + '_id', None))
    return handler


def _parent_deleted(source_type, parent_attr):
    def handler(sender, instance, **kwargs):
        _schedule(source_type, getattr(instance, parent_attr + '_id', None))
    return handler


# document -> its own entry
for _type, _model in [('sale', Sale), ('sale_payment', SalePayment), ('customer_payment', CustomerPayment),
                      ('purchase', Purchase), ('vendor_payment', VendorPayment), ('expense', Expense),
                      # Step 3 - the same Sale row also drives the cost entry
                      ('sale_cogs', Sale), ('sale_return', SaleRetrn), ('purchase_return', PurchaseRetrn),
                      ('stock_adjustment', StockAdjustment),
                      # Step 2b - opening cash balance row
                      ('cash_opening', CashTransaction),
                      # Step 5 - cash book deposits / withdrawals, salaries, daily closing
                      ('cash_book', CashTransaction), ('payroll', Payroll), ('daily_closing', DailyClosing),
                      # Step 4 - a vendor's opening balance (booked again if the number on the vendor changes)
                      ('vendor_opening', Vendor)]:
    post_save.connect(_saved(_type), sender=_model, weak=False, dispatch_uid=f'gl_save_{_type}')
    post_delete.connect(_deleted(_type), sender=_model, weak=False, dispatch_uid=f'gl_delete_{_type}')

# line items change their parent document's total
post_save.connect(_parent_saved('sale', 'sale'), sender=SaleItem, weak=False, dispatch_uid='gl_save_saleitem')
post_delete.connect(_parent_deleted('sale', 'sale'), sender=SaleItem, weak=False, dispatch_uid='gl_delete_saleitem')
post_save.connect(_parent_saved('purchase', 'purchase'), sender=PurchaseItem, weak=False, dispatch_uid='gl_save_purchaseitem')
post_delete.connect(_parent_deleted('purchase', 'purchase'), sender=PurchaseItem, weak=False, dispatch_uid='gl_delete_purchaseitem')

# Step 3 - stock and cost
post_save.connect(_parent_saved('sale_cogs', 'sale'), sender=SaleItem, weak=False, dispatch_uid='gl_save_saleitem_cogs')
post_delete.connect(_parent_deleted('sale_cogs', 'sale'), sender=SaleItem, weak=False, dispatch_uid='gl_delete_saleitem_cogs')
post_save.connect(_parent_saved('sale_return', 'sale_return'), sender=SaleRetrnItem, weak=False, dispatch_uid='gl_save_saleretitem')
post_delete.connect(_parent_deleted('sale_return', 'sale_return'), sender=SaleRetrnItem, weak=False, dispatch_uid='gl_delete_saleretitem')
post_save.connect(_parent_saved('purchase_return', 'purchase_return'), sender=PurchaseRetrnItem, weak=False, dispatch_uid='gl_save_purretitem')
post_delete.connect(_parent_deleted('purchase_return', 'purchase_return'), sender=PurchaseRetrnItem, weak=False, dispatch_uid='gl_delete_purretitem')
post_save.connect(_parent_saved('stock_adjustment', 'adjustment'), sender=StockAdjustmentItem, weak=False, dispatch_uid='gl_save_stockadjitem')
post_delete.connect(_parent_deleted('stock_adjustment', 'adjustment'), sender=StockAdjustmentItem, weak=False, dispatch_uid='gl_delete_stockadjitem')

# Step 2b - money paid on the bill itself. One entry per customer / vendor, so any change to a bill's `paid`
# or to a payment record re-checks that party.
def _via(source_type, getter, deleted=False):
    def handler(sender, instance, raw=False, **kwargs):
        if raw:
            return
        try:
            _schedule(source_type, getter(instance))
        except Exception:                                  # parent already gone (cascade delete)
            pass
    return handler


for _model, _getter in [(Sale, lambda i: i.customer_id), (SalePayment, lambda i: i.sale.customer_id),
                        (CustomerPayment, lambda i: i.customer_id)]:
    post_save.connect(_via('customer_paid_gap', _getter), sender=_model, weak=False, dispatch_uid=f'gl_save_cgap_{_model.__name__}')
    post_delete.connect(_via('customer_paid_gap', _getter), sender=_model, weak=False, dispatch_uid=f'gl_delete_cgap_{_model.__name__}')
for _model, _getter in [(Purchase, lambda i: i.vendor_id), (VendorPayment, lambda i: i.vendor_id)]:
    post_save.connect(_via('vendor_paid_gap', _getter), sender=_model, weak=False, dispatch_uid=f'gl_save_vgap_{_model.__name__}')
    post_delete.connect(_via('vendor_paid_gap', _getter), sender=_model, weak=False, dispatch_uid=f'gl_delete_vgap_{_model.__name__}')
