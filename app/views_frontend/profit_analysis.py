"""Frontend views: profit analysis - item / customer / category / brand / month wise profit aur margin."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from ..models import Brand, Category, CompanyInfo, Customer, Product, SaleItem
from .. import store_access as _sa
from .. import store_exports as _ex

_PA_GROUPS = {
    # group: (id field, name field, label, drill-down group)
    'item': ('product_id', 'product__name', 'Item', 'customer'),
    'customer': ('sale__customer_id', 'sale__customer__name', 'Customer', 'item'),
    'category': ('product__category_id', 'product__category__name', 'Category', 'item'),
    'brand': ('product__brand_id', 'product__brand__name', 'Brand', 'item'),
    'month': (None, None, 'Month', None),
}
_PA_SORTS = {'profit': '-profit', 'margin': '-margin', 'revenue': '-revenue', 'qty': '-sold_qty', 'loss': 'profit'}
_MONEY = DecimalField(max_digits=20, decimal_places=2)


def _pa_date(value, default):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return default


def _pa_int(value):
    return int(value) if (value or '').isdigit() else None


@login_required
def profit_analysis(request):
    # store team members (who may have money hidden from them) cannot see profit
    if _sa.module_scope(request.user) is not None:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, 'Access denied! The profit report is not for the store team.')
        return redirect('dashboard')

    group = request.GET.get('group', 'item')
    if group not in _PA_GROUPS:
        group = 'item'
    sort = request.GET.get('sort', 'profit')
    if sort not in _PA_SORTS:
        sort = 'profit'
    d_to = _pa_date(request.GET.get('to'), date.today())
    d_from = _pa_date(request.GET.get('from'), d_to - timedelta(days=30))
    q = (request.GET.get('q') or '').strip()
    flt = {k: _pa_int(request.GET.get(k)) for k in ('customer', 'category', 'brand', 'product')}

    items = SaleItem.objects.filter(sale__sale_date__date__gte=d_from, sale__sale_date__date__lte=d_to)
    if flt['customer']:
        items = items.filter(sale__customer_id=flt['customer'])
    if flt['category']:
        items = items.filter(product__category_id=flt['category'])
    if flt['brand']:
        items = items.filter(product__brand_id=flt['brand'])
    if flt['product']:
        items = items.filter(product_id=flt['product'])

    idf, namef, label, drill = _PA_GROUPS[group]
    revenue = ExpressionWrapper(F('total_amt') - F('discount'), output_field=_MONEY)
    net_profit = ExpressionWrapper(F('profit') - F('discount'), output_field=_MONEY)

    if group == 'month':
        base = items.annotate(m=TruncMonth('sale__sale_date')).values('m')
    else:
        base = items.values(key=F(idf), label=F(namef))
        if q:
            base = base.filter(**{namef + '__icontains': q})
    agg = base.annotate(sold_qty=Sum('qty'), revenue=Sum(revenue), profit=Sum(net_profit),
                        bills=Count('sale', distinct=True))
    rows = list(agg)

    for r in rows:
        if group == 'month':
            r['key'], r['label'] = None, r['m'].strftime('%b %Y') if r['m'] else '-'
        r['label'] = r['label'] or '(none)'
        rev, prof = r['revenue'] or Decimal('0'), r['profit'] or Decimal('0')
        r['revenue'], r['profit'] = rev, prof
        r['cost'] = rev - prof
        r['margin'] = (prof / rev * 100) if rev else Decimal('0')
        r['drill'] = bool(drill and r['key'])
    key = _PA_SORTS[sort]
    if group == 'month':
        rows.sort(key=lambda r: r['m'] or date.min)
    else:
        rows.sort(key=lambda r: r[key.lstrip('-') if key.lstrip('-') != 'sold_qty' else 'sold_qty'] or 0,
                  reverse=key.startswith('-'))

    tot_rev = sum((r['revenue'] for r in rows), Decimal('0'))
    tot_prof = sum((r['profit'] for r in rows), Decimal('0'))
    tot_cost = tot_rev - tot_prof
    tot_qty = sum((r['sold_qty'] or 0 for r in rows), 0)
    tot_margin = (tot_prof / tot_rev * 100) if tot_rev else Decimal('0')

    fmt = request.GET.get('export', '')
    if fmt in ('xlsx', 'pdf', 'csv'):
        out = [[r['label'], r['bills'], round(r['sold_qty'] or 0, 3), float(r['revenue']), float(r['cost']),
                float(r['profit']), round(float(r['margin']), 2)] for r in rows]
        return _ex.export_response(
            fmt, f'profit_{group}_{d_from}_{d_to}', f'Profit by {label}',
            [label, 'Bills', 'Qty', 'Revenue', 'Cost', 'Profit', 'Margin %'], out,
            totals=['TOTAL', '', round(tot_qty, 3), float(tot_rev), float(tot_cost), float(tot_prof),
                    round(float(tot_margin), 2)],
            subtitle=f'{d_from} to {d_to}', number_cols=(1, 2, 3, 4, 5, 6))

    keep = {k: v for k, v in flt.items() if v}
    param = {'item': 'product', 'customer': 'customer', 'category': 'category', 'brand': 'brand'}.get(group, '')
    from urllib.parse import urlencode
    drill_qs = urlencode({'group': drill or 'item', 'from': d_from.isoformat(), 'to': d_to.isoformat(), 'sort': sort,
                          **{k: v for k, v in keep.items() if k != param}})
    context = {
        'company_name': (CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System'),
        'rows': rows, 'group': group, 'group_label': label, 'sort': sort, 'q': q,
        'groups': [(k, v[2]) for k, v in _PA_GROUPS.items()],
        'sorts': [('profit', 'Zyada profit'), ('margin', 'Zyada margin %'), ('revenue', 'Zyada sale'),
                  ('qty', 'More qty'), ('loss', 'Lowest profit / loss first')],
        'from': d_from.isoformat(), 'to': d_to.isoformat(), 'drill_group': drill, 'flt': keep,
        'drill_qs': drill_qs, 'drill_param': param,
        'tot': {'revenue': tot_rev, 'cost': tot_cost, 'profit': tot_prof, 'margin': tot_margin, 'qty': tot_qty,
                'loss_count': sum(1 for r in rows if r['profit'] < 0)},
        'categories': Category.objects.order_by('name'), 'brands': Brand.objects.order_by('name'),
        'customers': Customer.objects.filter(pk=flt['customer']) if flt['customer'] else [],
        'products': Product.objects.filter(pk=flt['product']) if flt['product'] else [],
        'sel': {k: (str(v) if v else '') for k, v in flt.items()},
    }
    return render(request, 'reports/profit_analysis.html', context)
