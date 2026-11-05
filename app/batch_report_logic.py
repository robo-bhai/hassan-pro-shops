"""Pure helpers for the Batch Sale Report (no Django import, so they can be tested anywhere).

A sale line (SaleItem) can take stock from several batches (6 from A + 4 from B).
SaleItemBatchUsage keeps that split; here we turn one batch's usage rows into report rows
where qty / amount / profit are only that batch's SHARE of the sale line.
"""
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

_CENT = Decimal('0.01')


def _money(value):
    return Decimal(value or 0).quantize(_CENT, rounding=ROUND_HALF_UP)


def share_of_line(usage_qty, line_qty):
    """Fraction of the sale line that came from this batch (0..1)."""
    if not line_qty or line_qty <= 0:
        return Decimal('0')
    ratio = Decimal(str(usage_qty)) / Decimal(str(line_qty))
    return min(max(ratio, Decimal('0')), Decimal('1'))


def build_batch_sale_rows(usages):
    """usages: iterable of SaleItemBatchUsage rows of ONE batch -> list of report rows."""
    rows = []
    for u in usages:
        item = u.sale_item
        ratio = share_of_line(u.qty, item.qty)
        cost = getattr(u, 'cost_price', None)
        if cost is not None and Decimal(cost) > 0 and item.price is not None:
            # Real per-batch profit: (price paid - THIS batch's cost) x qty taken from it.
            amount = _money(Decimal(item.price) * Decimal(str(u.qty)))
            profit = _money((Decimal(item.price) - Decimal(cost)) * Decimal(str(u.qty)))
        else:                                   # old rows without a cost: proportional share of the line
            amount = _money(Decimal(item.total_amt or 0) * ratio)
            profit = _money(Decimal(item.profit or 0) * ratio)
        rows.append(SimpleNamespace(
            id=item.pk, sale=item.sale, product=item.product, price=item.price,
            qty=u.qty, total_amt=amount, profit=profit, line_qty=item.qty,
        ))
    return rows


def summarize_batch_sale_rows(rows):
    """Totals + day-wise + customer-wise summaries in the shape the template already uses."""
    total_qty = 0.0
    total_sales = Decimal('0.00')
    total_profit = Decimal('0.00')
    daily, customers, order_ids = {}, {}, set()

    for r in rows:
        total_qty += r.qty
        total_sales += r.total_amt
        total_profit += r.profit
        order_ids.add(r.id)

        d = r.sale.sale_date.date() if hasattr(r.sale.sale_date, 'date') else r.sale.sale_date
        day = daily.setdefault(d, {'sale__sale_date__date': d, 'qty': 0.0,
                                   'amount': Decimal('0.00'), 'profit': Decimal('0.00')})
        day['qty'] += r.qty; day['amount'] += r.total_amt; day['profit'] += r.profit

        cust = r.sale.customer
        key = getattr(cust, 'pk', None)
        c = customers.setdefault(key, {
            'sale__customer__name': getattr(cust, 'name', ''),
            'sale__customer__customer_code': getattr(cust, 'customer_code', ''),
            'qty': 0.0, 'amount': Decimal('0.00'), 'profit': Decimal('0.00'), 'orders': 0})
        c['qty'] += r.qty; c['amount'] += r.total_amt; c['profit'] += r.profit; c['orders'] += 1

    return {
        'total_qty': total_qty, 'total_sales': total_sales, 'total_profit': total_profit,
        'total_orders': len(order_ids),
        'daily': sorted(daily.values(), key=lambda x: x['sale__sale_date__date'], reverse=True),
        'customers': sorted(customers.values(), key=lambda x: x['amount'], reverse=True),
    }
