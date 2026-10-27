"""
Main dashboard update. Run from the project folder:  python patch_dashboard.py
Safe to run twice. Makes app/views_frontend/dashboard.py.bak_dash first.

What it fixes in dashboard.py:
 1. The discount was added once PER ITEM of each bill, so today's / this month's profit was too low
    for bills with more than one item and a discount. It is now added once per bill.
 2. Voided bills are left out of sales, profit, top products and recent sales.
 3. The "Top products" bars never showed (the bar width was never calculated). Now it is.
 4. Adds yesterday compare, the 7-day sales chart and the cash balance (from dashboard_extras.py).
 5. Quick action names lose their emoji (the new design shows icons).
"""
import re, shutil, sys

P = 'app/views_frontend/dashboard.py'
s = open(P, encoding='utf-8').read()
if 'dashboard_extras' in s:
    print('dashboard.py is already updated. Nothing to do.')
    sys.exit(0)

PAIRS = [("        today_stats = Sale.objects.filter(sale_date__date=today).aggregate(\n            total_sales=Coalesce(\n                Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),\n                Value(Decimal('0.00'))\n            ),\n            sales_count=Count('id', distinct=True),\n            total_discount=Coalesce(\n                Sum('discount_value'),\n                Value(Decimal('0.00'))\n            )\n        )\n", "        _today_sales = Sale.objects.filter(sale_date__date=today).exclude(returns__notes__startswith='VOID')\n        today_stats = _today_sales.aggregate(\n            total_sales=Coalesce(\n                Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),\n                Value(Decimal('0.00'))\n            ),\n            sales_count=Count('id', distinct=True),\n        )\n        # The discount is summed on its own. Summed together with the items it was counted once per item.\n        today_stats['total_discount'] = _today_sales.aggregate(\n            d=Coalesce(Sum('discount_value'), Value(Decimal('0.00'))))['d']\n"), ('        today_profit_raw = SaleItem.objects.filter(\n            sale__sale_date__date=today\n        ).aggregate(', "        today_profit_raw = SaleItem.objects.filter(\n            sale__sale_date__date=today\n        ).exclude(sale__returns__notes__startswith='VOID').aggregate("), ("        monthly_stats = Sale.objects.filter(\n            sale_date__date__gte=month_start\n        ).aggregate(\n            total_sales=Coalesce(Sum('saleitem__total_amt'), Value(Decimal('0.00'))),\n            total_discount=Coalesce(Sum('discount_value'), Value(Decimal('0.00')))\n        )\n", "        _month_sales = Sale.objects.filter(sale_date__date__gte=month_start).exclude(returns__notes__startswith='VOID')\n        monthly_stats = _month_sales.aggregate(\n            total_sales=Coalesce(Sum('saleitem__total_amt'), Value(Decimal('0.00'))),\n        )\n        monthly_stats['total_discount'] = _month_sales.aggregate(\n            d=Coalesce(Sum('discount_value'), Value(Decimal('0.00'))))['d']\n"), ('        monthly_profit_raw = SaleItem.objects.filter(\n            sale__sale_date__date__gte=month_start\n        ).aggregate(', "        monthly_profit_raw = SaleItem.objects.filter(\n            sale__sale_date__date__gte=month_start\n        ).exclude(sale__returns__notes__startswith='VOID').aggregate("), ('        top_products = list(SaleItem.objects.filter(\n            sale__sale_date__date__gte=month_ago\n        ).values(', "        top_products = list(SaleItem.objects.filter(\n            sale__sale_date__date__gte=month_ago\n        ).exclude(sale__returns__notes__startswith='VOID').values("), ("        ).order_by('-total_sales')[:8])\n", '        ).order_by(\'-total_sales\')[:8])\n        _best = max([float(p[\'total_sales\']) for p in top_products] + [1.0])\n        for p in top_products:                      # width of the bar in the "Top products" card\n            p[\'sales_percent\'] = max(3, round(float(p[\'total_sales\']) * 100 / _best))\n'), ("        recent_sales = list(Sale.objects.select_related(\n            'customer', 'warehouse', 'created_by'\n        ).annotate(", "        recent_sales = list(Sale.objects.select_related(\n            'customer', 'warehouse', 'created_by'\n        ).exclude(returns__notes__startswith='VOID').annotate("), ('    context = {\n        **base_stats,\n', '    try:\n        from .dashboard_extras import dashboard_extras\n        _extras = dashboard_extras(today)\n    except Exception:\n        _extras = {}\n    context = {\n        **base_stats,\n        **_extras,\n')]

for old, new in PAIRS:
    if s.count(old) != 1:
        sys.exit('Could not find the expected code in dashboard.py (it may have been edited):\n' + old[:120] +
                 '\nNothing was changed.')
shutil.copy(P, P + '.bak_dash')
for old, new in PAIRS:
    s = s.replace(old, new)

def strip_emoji(m):
    return m.group(1)
s = re.sub(r"('name': ')[^A-Za-z0-9']+(?=[A-Za-z])", strip_emoji, s)
open(P, 'w', encoding='utf-8').write(s)
print('Done. Backup: ' + P + '.bak_dash')
