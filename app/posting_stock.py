"""
posting_stock.py - Step 3: stock and cost entries.

    Sale (cost)          Dr Cost of Goods Sold      Cr Inventory            (FIFO cost saved on each SaleItem)
    Sale return          Dr Sales Returns           Cr Accounts Receivable  (what the customer is credited)
                         Dr Inventory               Cr Cost of Goods Sold   (goods back in stock at the cost they left at)
    Purchase return      Dr Accounts Payable        Cr Inventory
    Stock adjustment +   Dr Inventory               Cr Stock Gain
    Stock adjustment -   Dr Stock Loss              Cr Inventory

Store issue / transfer / count are NOT here: they already post through store_accounting.py.
Moving stock between two warehouses changes nothing in the books while all warehouses share one Inventory account.

Everything goes through posting.post_entry, so each document is booked once, re-posted when it changes and
reversed when it is deleted - exactly like the Step 1 / Step 2 documents.
"""
from decimal import Decimal

from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from .models import LedgerEntry, PostingRule, PurchaseRetrn, Sale, SaleItem, SaleRetrn, StockAdjustment, StockBatch
from .posting import SOURCES, _day, account_for, cust, optional_account, post_entry, vend
from .posting_core import C, D, prorate, q2

__all__ = ['post_sale_cogs', 'post_sale_return', 'post_purchase_return', 'post_stock_adjustment',
           'inventory_figures', 'post_opening_stock']


def post_sale_cogs(sale, user=None, repost=False):
    """Cost of the goods on a sale. Items without a saved cost (old sales) count as 0 until `--backfill-cost` runs."""
    cost = q2(sale.saleitem_set.aggregate(t=Sum('cost_amount'))['t'] or 0)
    if cost <= 0:
        return None
    return post_entry(
        entry_date=_day(sale.sale_date), entry_type='sale', source_type='sale_cogs', source_id=sale.pk,
        description=f'Cost of sale {sale.bill_no} - {sale.customer.name}', reference=sale.bill_no,
        lines=[D(account_for('cogs'), cost, 'Cost of goods sold'),
               C(account_for('inventory'), cost, 'Stock issued to customer')],
        user=user, repost=repost, links={'sale': sale},
    )


def _returned_cost(ret):
    """Original FIFO cost of the returned goods, taken from the sale they came from (pro-rata by quantity)."""
    if not ret.sale_id:
        return Decimal('0.00')
    total = Decimal('0.00')
    for item in ret.return_items.all():
        agg = SaleItem.objects.filter(sale_id=ret.sale_id, product_id=item.product_id).aggregate(
            cost=Sum('cost_amount'), qty=Sum('qty'))
        total += prorate(agg['cost'], agg['qty'], item.qty)
    return q2(total)


def post_sale_return(ret, user=None, repost=False):
    revenue = q2(ret.return_items.aggregate(t=Sum('total_amt'))['t'] or 0)
    if revenue <= 0:
        return None
    cost = _returned_cost(ret)

    # Sale-level discount. Default OFF because the sale-return screen credits the customer the item price only;
    # with GL_RETURN_DISCOUNT = True the customer is credited the price net of the discount share
    # (change the screen the same way, otherwise the ledger and the customer balance differ).
    share = Decimal('0.00')
    if ret.sale_id and getattr(settings, 'GL_RETURN_DISCOUNT', False):
        gross, discount = q2(ret.sale.total_without_discount()), q2(ret.sale.discount_value)
        if gross > 0 and discount > 0:
            share = min(q2(discount * revenue / gross), discount)
    discount_acc = optional_account('sales_discount') if share > 0 else None

    lines = [D(account_for('sales_returns', fallback='sales_revenue'), revenue if discount_acc else revenue - share, 'Sales return'),
             C(account_for('receivable'), revenue - share, 'Customer credited', cust(ret.customer_id))]
    if discount_acc:
        lines.append(C(discount_acc, share, 'Discount given back'))
    if cost > 0:
        lines += [D(account_for('inventory'), cost, 'Goods back in stock (at cost)'),
                  C(account_for('cogs'), cost, 'Cost reversed')]
    return post_entry(
        entry_date=_day(ret.sale_return_date), entry_type='sale', source_type='sale_return', source_id=ret.pk,
        description=f'Sale return #{ret.pk} - {ret.customer.name}', reference=ret.bill_no or f'SR-{ret.pk}',
        lines=lines, user=user, repost=repost, links={'sale': ret.sale} if ret.sale_id else None,
    )


def post_purchase_return(ret, user=None, repost=False):
    total = q2(ret.return_items.aggregate(t=Sum('total_amt'))['t'] or 0)
    if total <= 0:
        return None
    return post_entry(
        entry_date=_day(ret.purchase_return_date), entry_type='purchase', source_type='purchase_return',
        source_id=ret.pk, description=f'Purchase return #{ret.pk} - {ret.vendor.name}',
        reference=ret.bill_no or f'PR-{ret.pk}',
        lines=[D(account_for('payable'), total, 'Vendor credited', vend(ret.vendor_id)),
               C(account_for('inventory'), total, 'Stock returned to vendor')],
        user=user, repost=repost, links={'purchase': ret.purchase} if ret.purchase_id else None,
    )


def post_stock_adjustment(adj, user=None, repost=False):
    total = q2(adj.items.aggregate(t=Sum('total_value'))['t'] or 0)
    if total <= 0:
        return None
    if adj.adjustment_type == 'increase':
        lines = [D(account_for('inventory'), total, 'Stock found / added'),
                 C(account_for('stock_gain'), total, adj.reason)]
    else:
        lines = [D(account_for('stock_loss'), total, adj.reason),
                 C(account_for('inventory'), total, 'Stock written off')]
    return post_entry(
        entry_date=_day(adj.adjustment_date), entry_type='adjustment', source_type='stock_adjustment',
        source_id=adj.pk, description=f'Stock adjustment #{adj.pk} ({adj.adjustment_type}) - {adj.reason}',
        reference=f'ADJ-{adj.pk}', lines=lines, user=user, repost=repost,
    )


# ---------------------------------------------------------------------------
# Step 3b: opening stock
# ---------------------------------------------------------------------------
def inventory_figures():
    """(inventory account or None, balance in the ledger, value of the real stock batches)."""
    rule = PostingRule.objects.select_related('account').filter(key='inventory').first()
    if not rule:
        return None, Decimal('0.00'), Decimal('0.00')
    acc = rule.account
    agg = LedgerEntry.objects.filter(account=acc).aggregate(d=Sum('debit'), c=Sum('credit'))
    ledger = q2(acc.opening_balance) + q2(agg['d'] or 0) - q2(agg['c'] or 0)
    value = StockBatch.objects.filter(remaining_qty__gt=0).aggregate(t=Sum(ExpressionWrapper(
        F('remaining_qty') * F('price'), output_field=DecimalField(max_digits=18, decimal_places=2))))['t'] or 0
    return acc, ledger, q2(value)


def post_opening_stock(amount, entry_date, user=None):
    """Dr Inventory / Cr Opening Balance Equity. One entry only: running it again replaces it (reverse + new)."""
    amount = q2(amount)
    return post_entry(
        entry_date=entry_date, entry_type='adjustment', source_type='opening_stock', source_id=0,
        description='Opening stock (stock that was never bought through a posted purchase)', reference='OPENING-STOCK',
        lines=[D(account_for('inventory'), amount, 'Opening stock'),
               C(account_for('opening_equity'), amount, 'Opening balance equity')],
        user=user, repost=True,
    )


# register with the engine (backfill command and live signals read this table)
SOURCES.update({
    'sale_cogs': (Sale, post_sale_cogs),
    'sale_return': (SaleRetrn, post_sale_return),
    'purchase_return': (PurchaseRetrn, post_purchase_return),
    'stock_adjustment': (StockAdjustment, post_stock_adjustment),
})
