"""Agri Edition: rules shared by the sale screens, POS and the agri pages.

Nothing here posts to the ledger. It only reads sales / returns, or writes the plain
harvest_due_date / harvest_note fields with queryset.update().
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .calc import ZERO, credit_decision, credit_mode, parse_date

MONEY = DecimalField(max_digits=18, decimal_places=2)


def unpaid_sales():
    """Sales with an unpaid balance (items total - discount - paid); multi-item bills are not double counted."""
    from ..models import Sale, SaleItem
    items_sq = (SaleItem.objects.filter(sale=OuterRef('pk')).order_by().values('sale')
                .annotate(t=Sum('total_amt')).values('t'))
    return (Sale.objects.select_related('customer')
            .annotate(items_total=Coalesce(Subquery(items_sq, output_field=MONEY),
                                           Value(ZERO), output_field=MONEY))
            .annotate(balance=ExpressionWrapper(F('items_total') - F('discount_value') - F('paid'),
                                                output_field=MONEY))
            .filter(balance__gt=0))


def returns_by_customer(customer_id=None):
    from ..models import SaleRetrnItem
    qs = SaleRetrnItem.objects.order_by()
    if customer_id is not None:
        qs = qs.filter(sale_return__customer_id=customer_id)
    rows = qs.values('sale_return__customer').annotate(t=Sum('total_amt'))
    return {r['sale_return__customer']: (r['t'] or ZERO) for r in rows}


def customer_outstanding(customer_id):
    """Unpaid balance of one customer after sale returns (never below zero)."""
    total = unpaid_sales().filter(customer_id=customer_id).aggregate(t=Sum('balance'))['t'] or ZERO
    total -= returns_by_customer(customer_id).get(customer_id, ZERO)
    return max(total, ZERO)


def check_credit_limit(customer, new_credit, can_override=False):
    """Call before a sale is saved. Raises ValueError (message in Roman Urdu) when the sale must stop.

    Returns a warning text (or '') when the sale may go on.
    System setting `agri_credit_limit_mode`: block (default) / warn / off.
    Managers (can_override=True) are warned, not stopped.
    """
    from ..models import SystemSetting
    if customer is None or not getattr(customer, 'credit_limit', None):
        return ''
    new_credit = Decimal(str(new_credit or 0))
    if new_credit <= 0:
        return ''
    mode = credit_mode(SystemSetting.get_value('agri_credit_limit_mode', 'block'))
    action, msg = credit_decision(customer.credit_limit, customer_outstanding(customer.pk), new_credit, mode)
    if action == 'block':
        if can_override:
            return msg + ' (Manager ki ijazat se.)'
        raise ValueError('%s ka %s Manager se approve karwayen ya pehle kuch raqam wasool karein.'
                         % (customer.name, msg))
    return msg if action == 'warn' else ''


def apply_harvest_due(sale, raw_date, note=''):
    """Save the promised repayment (harvest) date on a sale. Returns False when the date text is wrong."""
    from ..models import Sale
    ok, due = parse_date(raw_date)
    if not ok:
        return False
    if due is None and not note:
        return True
    Sale.objects.filter(pk=sale.pk).update(harvest_due_date=due, harvest_note=(note or '')[:200])
    return True
