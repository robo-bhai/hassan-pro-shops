"""Extra numbers for the main dashboard.

Shared numbers (cached 5 minutes): yesterday compare, 7 and 30 day sales, payment mix, returns, top customers,
cash balance. Per user numbers (not cached): the user's open shift.
A failure in any part never breaks the dashboard.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import localtime, now

from ...models import CashBalance, SaleItem, SalePayment, SaleRetrnItem

NOT_VOID = {'sale__returns__notes__startswith': 'VOID'}        # used with .exclude() on SaleItem
ZERO = Decimal('0.00')


def _series(today, days):
    start = today - timedelta(days=days - 1)
    rows = (SaleItem.objects.filter(sale__sale_date__date__gte=start, sale__sale_date__date__lte=today)
            .exclude(**NOT_VOID).values('sale__sale_date__date')
            .annotate(t=Coalesce(Sum('total_amt'), Value(ZERO))))
    by_day = {r['sale__sale_date__date']: float(r['t']) for r in rows}
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append({'label': d.strftime('%a') if days <= 7 else d.strftime('%d'), 'date': d.strftime('%d %b'),
                    'value': by_day.get(d, 0.0), 'today': d == today,
                    'show': days <= 7 or i % 5 == 4 or d == today})
    top = max([x['value'] for x in out] + [1.0])
    for x in out:
        x['pct'] = max(3, round(x['value'] * 100 / top)) if x['value'] > 0 else 3
    return out


def _shared(today):
    data = {'dash_week': [], 'dash_month': [], 'dash_week_total': 0, 'dash_month_total': 0, 'dash_yesterday': None,
            'dash_delta': None, 'dash_cash': None, 'dash_mix': [], 'dash_mix_total': 0, 'dash_returns_today': 0,
            'dash_returns_month': 0, 'dash_top_customers': [], 'dash_updated': localtime(now()).strftime('%I:%M %p').lstrip('0')}
    try:
        month = _series(today, 30)
        week = _series(today, 7)
        data['dash_week'], data['dash_month'] = week, month
        data['dash_week_total'] = round(sum(x['value'] for x in week), 2)
        data['dash_month_total'] = round(sum(x['value'] for x in month), 2)
        y, t = week[-2]['value'], week[-1]['value']
        data['dash_yesterday'] = y
        if y > 0:
            data['dash_delta'] = round((t - y) * 100 / y, 1)
    except Exception:
        pass
    try:                                                    # how today's money came in
        pays = (SalePayment.objects.filter(payment_date__date=today).exclude(sale__returns__notes__startswith='VOID')
                .values('method__name').annotate(t=Coalesce(Sum('amount'), Value(ZERO))))
        parts = {'cash': 0.0, 'bank': 0.0, 'other': 0.0}
        for p in pays:
            k = {'cash': 'cash', 'bank_transfer': 'bank'}.get(p['method__name'], 'other')
            parts[k] += float(p['t'])
        total = sum(parts.values())
        data['dash_mix_total'] = round(total, 2)
        if total > 0:
            names = {'cash': ('Cash', 'tone-green'), 'bank': ('Bank', 'tone-blue'), 'other': ('Other', 'tone-amber')}
            data['dash_mix'] = [{'name': names[k][0], 'tone': names[k][1], 'value': round(v, 2),
                                 'pct': round(v * 100 / total)} for k, v in parts.items() if v > 0]
    except Exception:
        pass
    try:                                                    # returns (a voided bill is not counted as a return)
        base = SaleRetrnItem.objects.exclude(sale_return__notes__startswith='VOID')
        data['dash_returns_today'] = float(base.filter(sale_return__sale_return_date__date=today)
                                           .aggregate(t=Coalesce(Sum('total_amt'), Value(ZERO)))['t'])
        data['dash_returns_month'] = float(base.filter(sale_return__sale_return_date__date__gte=today.replace(day=1))
                                           .aggregate(t=Coalesce(Sum('total_amt'), Value(ZERO)))['t'])
    except Exception:
        pass
    try:                                                    # best customers, last 30 days (walk-in is left out)
        rows = (SaleItem.objects.filter(sale__sale_date__date__gte=today - timedelta(days=29))
                .exclude(**NOT_VOID).exclude(sale__customer__customer_code='WALKIN')
                .values('sale__customer__name').annotate(t=Coalesce(Sum('total_amt'), Value(ZERO))).order_by('-t')[:5])
        rows = [{'name': r['sale__customer__name'], 'value': float(r['t'])} for r in rows]
        best = max([r['value'] for r in rows] + [1.0])
        for r in rows:
            r['pct'] = max(3, round(r['value'] * 100 / best))
        data['dash_top_customers'] = rows
    except Exception:
        pass
    try:
        data['dash_cash'] = float(CashBalance.get_balance())
    except Exception:
        pass
    return data


def dashboard_extras(today, user=None):
    key = f'dashboard_extra_{today}'
    data = cache.get(key)
    if data is None:
        data = _shared(today)
        cache.set(key, data, 300)
    data = dict(data)
    data['dash_shift'] = None
    if user is not None:
        try:
            from ..pos_sales.shift import compute_totals, open_shift_for
            s = open_shift_for(user)
            if s:
                t = compute_totals(s)
                data['dash_shift'] = {'id': s.pk, 'store': s.warehouse.name,
                                      'since': localtime(s.opened_at).strftime('%d %b %I:%M %p'),
                                      'drawer': float(t['expected_cash']), 'bills': t['sales_count'],
                                      'sales': float(t['total_sales'])}
        except Exception:
            pass
    return data
