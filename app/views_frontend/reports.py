"""Frontend views: reports."""
from django.utils.timezone import localdate
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper
from ..models import *
import json
import calendar
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Value, DecimalField
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.http import HttpResponse
from io import BytesIO
from ..models import CompanyInfo, Sale, Purchase, Expense, SalesTarget, Employee, SaleItem
from django.db.models.functions import TruncMonth, TruncWeek
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


@login_required
def range_report_view(request):
    """Range report page with date filters"""
    from datetime import date, timedelta
    
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    report_type = request.GET.get('report_type', 'sales')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        "title": "📊 Range Reports",
        "from_date": from_date,
        "to_date": to_date,
        "report_type": report_type,
    }
    
    if report_type == 'sales':
        sales = Sale.objects.filter(sale_date__date__gte=from_date_obj, sale_date__date__lte=to_date_obj)
        total_amount = sum(s.total_amount() for s in sales)
        total_profit = sum(s.total_profit() for s in sales)
        
        top_products = SaleItem.objects.filter(
            sale__sale_date__date__gte=from_date_obj,
            sale__sale_date__date__lte=to_date_obj
        ).values('product__name').annotate(
            total_qty=Sum('qty'),
            total_sales=Sum('total_amt')
        ).order_by('-total_sales')[:10]
        
        context['sales_data'] = {
            'count': sales.count(),
            'total_amount': total_amount,
            'total_profit': total_profit,
        }
        context['top_products'] = top_products
        
    elif report_type == 'purchases':
        purchases = Purchase.objects.filter(pur_date__date__gte=from_date_obj, pur_date__date__lte=to_date_obj)
        total_amount = sum(p.total_amount() for p in purchases)
        total_paid = sum(p.paid for p in purchases)
        
        context['purchase_data'] = {
            'count': purchases.count(),
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_outstanding': total_amount - total_paid,
        }
    
    elif report_type == 'daily':
        daily_data = []
        current = from_date_obj
        while current <= to_date_obj:
            day_sales = Sale.objects.filter(sale_date__date=current)
            day_purchases = Purchase.objects.filter(pur_date__date=current)
            daily_data.append({
                'date': current.strftime('%d-%b'),
                'sales': sum(s.total_amount() for s in day_sales),
                'purchases': sum(p.total_amount() for p in day_purchases),
                'profit': sum(s.total_profit() for s in day_sales),
            })
            current += timedelta(days=1)
        context['daily_data'] = daily_data
    
    return render(request, 'reports/range_report.html', context)


@login_required
def reports_dashboard(request):
    """Main Reports Dashboard - All reports in one place"""
    from django.db.models import Sum, Count, Q, F, Value, DecimalField
    from django.db.models.functions import Coalesce
    
    today = date.today()
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    
    # Current Month Stats
    current_month_sales = Sale.objects.filter(sale_date__date__gte=month_start).aggregate(
        total=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.0')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    
    current_month_purchases = Purchase.objects.filter(pur_date__date__gte=month_start).aggregate(
        total=Coalesce(
            Sum('purchaseitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.0')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    
    current_month_profit_agg = SaleItem.objects.filter(
        sale__sale_date__date__gte=month_start
    ).aggregate(
        profit=Coalesce(Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0'))),
        discount=Coalesce(
            Sum('sale__discount_value', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.0'))
        )
    )
    current_month_profit = current_month_profit_agg['profit'] - current_month_profit_agg['discount']
    
    # Last Month Stats
    last_month_sales = Sale.objects.filter(
        sale_date__date__gte=last_month_start,
        sale_date__date__lt=month_start
    ).aggregate(
        total=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.0'))
        )
    )['total']
    
    # Growth Percentage
    sales_growth = 0
    if last_month_sales > 0:
        sales_growth = float(((current_month_sales - last_month_sales) / last_month_sales) * 100)
    
    # ✅ FIX: Customer outstanding in ONE query
    customer_agg = Sale.objects.aggregate(
        total_amt=Coalesce(Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0'))),
        total_paid=Coalesce(Sum('paid', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0')))
    )
    total_customer_outstanding = customer_agg['total_amt'] - customer_agg['total_paid']
    
    # ✅ FIX: Vendor outstanding in ONE query
    vendor_agg = Purchase.objects.aggregate(
        total_amt=Coalesce(Sum('purchaseitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0'))),
        total_paid=Coalesce(Sum('paid', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0')))
    )
    opening_balance_total = Vendor.objects.aggregate(
        total=Coalesce(Sum('opening_balance', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0')))
    )['total']
    total_vendor_outstanding = (vendor_agg['total_amt'] - vendor_agg['total_paid']) + opening_balance_total
    
    # Low Stock Count
    low_stock_count = Inventory.objects.filter(
        stock__lt=F('product__low_stock_threshold')
    ).count()
    
    # Top 5 Products
    top_products = SaleItem.objects.filter(
        sale__sale_date__date__gte=month_start
    ).values('product__name').annotate(
        total_sales=Coalesce(Sum('total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0'))),
        total_qty=Coalesce(Sum('qty', output_field=DecimalField(max_digits=20, decimal_places=2)), Value(Decimal('0.0')))
    ).order_by('-total_sales')[:5]
    
    recent_sales = Sale.objects.select_related('customer').order_by('-sale_date')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'current_month_sales': current_month_sales,
        'current_month_purchases': current_month_purchases,
        'current_month_profit': current_month_profit,
        'sales_growth': sales_growth,
        'total_customer_outstanding': total_customer_outstanding,
        'total_vendor_outstanding': total_vendor_outstanding,
        'low_stock_count': low_stock_count,
        'top_products': top_products,
        'recent_sales': recent_sales,
        'today': today,
        'month_start': month_start,
    }
    return render(request, 'reports/dashboard.html', context)


@login_required
def business_health(request):
    """Business Health Dashboard - Key Indicators"""
    today = date.today()
    month_start = today.replace(day=1)
    
    # Sales & Profit
    sales_agg = Sale.objects.filter(sale_date__date__gte=month_start).aggregate(
        total_sales=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_profit=Coalesce(
            Sum('saleitem__profit', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_discount=Coalesce(
            Sum('discount_value', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )
    total_sales = sales_agg['total_sales']
    net_profit = sales_agg['total_profit'] - sales_agg['total_discount']
    
    profit_margin = float((net_profit / total_sales * 100)) if total_sales > 0 else 0
    
    # ✅ Customer outstanding in ONE query
    customer_agg = Sale.objects.aggregate(
        total_amt=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_paid=Coalesce(
            Sum('paid', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )
    total_customer_outstanding = customer_agg['total_amt'] - customer_agg['total_paid']
    outstanding_percentage = float((total_customer_outstanding / total_sales * 100)) if total_sales > 0 else 0
    
    # ✅ Inventory value with ExpressionWrapper
    inventory_value = Inventory.objects.aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F('stock') * F('product__price'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    
    cogs = total_sales
    inventory_turnover = float((cogs / inventory_value * 12)) if inventory_value > 0 else 0
    
    # Investment
    total_investment = Purchase.objects.filter(
        pur_date__date__gte=month_start
    ).aggregate(
        total=Coalesce(
            Sum('purchaseitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    roi = float((net_profit / total_investment * 100)) if total_investment > 0 else 0
    
    # Health Status
    health_status = []
    
    if profit_margin >= 15:
        health_status.append({'indicator': 'Profit Margin', 'value': f'{profit_margin:.1f}%', 'status': 'Excellent', 'color': 'success'})
    elif profit_margin >= 10:
        health_status.append({'indicator': 'Profit Margin', 'value': f'{profit_margin:.1f}%', 'status': 'Good', 'color': 'warning'})
    else:
        health_status.append({'indicator': 'Profit Margin', 'value': f'{profit_margin:.1f}%', 'status': 'Poor', 'color': 'danger'})
    
    if outstanding_percentage <= 20:
        health_status.append({'indicator': 'Outstanding', 'value': f'{outstanding_percentage:.1f}%', 'status': 'Excellent', 'color': 'success'})
    elif outstanding_percentage <= 40:
        health_status.append({'indicator': 'Outstanding', 'value': f'{outstanding_percentage:.1f}%', 'status': 'Average', 'color': 'warning'})
    else:
        health_status.append({'indicator': 'Outstanding', 'value': f'{outstanding_percentage:.1f}%', 'status': 'Poor', 'color': 'danger'})
    
    if inventory_turnover >= 12:
        health_status.append({'indicator': 'Inventory Turnover', 'value': f'{inventory_turnover:.1f}x', 'status': 'Excellent', 'color': 'success'})
    elif inventory_turnover >= 6:
        health_status.append({'indicator': 'Inventory Turnover', 'value': f'{inventory_turnover:.1f}x', 'status': 'Good', 'color': 'warning'})
    else:
        health_status.append({'indicator': 'Inventory Turnover', 'value': f'{inventory_turnover:.1f}x', 'status': 'Poor', 'color': 'danger'})
    
    if roi >= 20:
        health_status.append({'indicator': 'ROI', 'value': f'{roi:.1f}%', 'status': 'Excellent', 'color': 'success'})
    elif roi >= 10:
        health_status.append({'indicator': 'ROI', 'value': f'{roi:.1f}%', 'status': 'Good', 'color': 'warning'})
    else:
        health_status.append({'indicator': 'ROI', 'value': f'{roi:.1f}%', 'status': 'Poor', 'color': 'danger'})
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'profit_margin': profit_margin,
        'outstanding_percentage': outstanding_percentage,
        'inventory_turnover': inventory_turnover,
        'roi': roi,
        'total_sales': total_sales,
        'net_profit': net_profit,
        'total_customer_outstanding': total_customer_outstanding,
        'inventory_value': inventory_value,
        'health_status': health_status,
        'today': today,
    }
    return render(request, 'reports/business_health.html', context)


@login_required
def profit_loss_report(request):
    """Profit & Loss Report - FULLY FIXED"""
    from django.db.models import Sum, Value, DecimalField
    from django.db.models.functions import Coalesce
    
    # ✅ Date filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ✅ Sales (1 query)
    sales_agg = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).aggregate(
        total_sales=Coalesce(
            Sum('saleitem__total_amt'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_discount=Coalesce(
            Sum('discount_value'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
    )
    total_sales = sales_agg['total_sales']
    total_discount = sales_agg['total_discount']
    net_sales = total_sales - total_discount
    
    # ✅ Purchases (1 query)
    total_purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).aggregate(
        total=Coalesce(
            Sum('purchaseitem__total_amt'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    
    gross_profit = net_sales - total_purchases
    
    # ✅ Expenses (1 query)
    expenses_agg = Expense.objects.filter(
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj
    ).aggregate(
        total=Coalesce(
            Sum('amount'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )
    total_expenses = expenses_agg['total']
    
    # ✅ Salary expense (1 query)
    salary_expense = Expense.objects.filter(
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        category__name__iexact='salary'
    ).aggregate(
        total=Coalesce(
            Sum('amount'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )['total']
    
    net_profit = gross_profit - total_expenses
    profit_margin = float((net_profit / net_sales * 100)) if net_sales > 0 else 0
    
    # ✅ Monthly data (1 query with TruncMonth)
    from django.db.models.functions import TruncMonth
    monthly_qs = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Coalesce(
            Sum('saleitem__total_amt'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    ).order_by('month')
    
    monthly_data = []
    for item in monthly_qs:
        monthly_data.append({
            'month': item['month'].strftime('%b %Y') if item['month'] else '-',
            'sales': float(item['total'])
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_sales': total_sales,
        'total_discount': total_discount,
        'net_sales': net_sales,
        'total_purchases': total_purchases,
        'gross_profit': gross_profit,
        'total_expenses': total_expenses,
        'salary_expense': salary_expense,
        'net_profit': net_profit,
        'profit_margin': profit_margin,
        'monthly_data': json.dumps(monthly_data),
    }
    return render(request, 'reports/profit_loss.html', context)


@login_required
def cash_flow_report(request):
    """Cash Flow Statement"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    cash_in = Sale.objects.filter(sale_date__date__gte=from_date_obj, sale_date__date__lte=to_date_obj).aggregate(
        total=Sum('paid'))['total'] or Decimal('0.0')
    
    cash_out = Purchase.objects.filter(pur_date__date__gte=from_date_obj, pur_date__date__lte=to_date_obj).aggregate(
        total=Sum('paid'))['total'] or Decimal('0.0')
    
    total_expenses = Expense.objects.filter(expense_date__gte=from_date_obj, expense_date__lte=to_date_obj).aggregate(
        total=Sum('amount'))['total'] or Decimal('0.0')
    
    total_sales_received = cash_in
    purchase_payments = cash_out
    net_cash = cash_in - cash_out - total_expenses
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'cash_in': cash_in,
        'cash_out': cash_out,
        'total_expenses': total_expenses,
        'total_sales_received': total_sales_received,
        'purchase_payments': purchase_payments,
        'net_cash': net_cash,
    }
    return render(request, 'reports/cash_flow.html', context)


@login_required
def sales_summary_report(request):
    """Sales Summary Report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    sales = Sale.objects.select_related(
        'customer', 'warehouse', 'customer__group'
    ).prefetch_related(
        'saleitem_set__product'
    ).filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).order_by('sale_date')
    
    # ✅ FIX: Use Coalesce with output_field
    totals = sales.aggregate(
        total_amount=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_profit=Coalesce(
            Sum('saleitem__profit', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_paid=Coalesce(
            Sum('paid', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_count=Count('id', distinct=True),
        total_items=Count('saleitem__id', distinct=True),
    )
    
    total_amount = totals['total_amount']
    total_profit = totals['total_profit']
    total_paid = totals['total_paid']
    total_count = totals['total_count']
    total_items = totals['total_items']
    total_outstanding = total_amount - total_paid
    
    daily_data = []
    current = from_date_obj
    while current <= to_date_obj:
        day_sales = Sale.objects.filter(sale_date__date=current).aggregate(
            total=Coalesce(
                Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            )
        )['total']
        daily_data.append({
            'date': current.strftime('%d %b'),
            'amount': float(day_sales)
        })
        current += timedelta(days=1)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'sales': sales[:100],
        'total_amount': total_amount,
        'total_profit': total_profit,
        'total_paid': total_paid,
        'total_count': total_count,
        'total_items': total_items,
        'total_outstanding': total_outstanding,
        'avg_sale': total_amount / total_count if total_count > 0 else 0,
        'daily_data': json.dumps(daily_data),
    }
    return render(request, 'reports/sales_summary.html', context)


@login_required
def sales_forecast_report(request):
    """Sales Forecast based on historical data"""
    months = int(request.GET.get('months', 3))
    
    today = date.today()
    six_months_ago = today - timedelta(days=180)
    
    monthly_sales = Sale.objects.filter(
        sale_date__date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Sum('saleitem__total_amt')
    ).order_by('month')
    
    sales_list = list(monthly_sales)
    forecast = []
    
    if len(sales_list) >= 2:
        avg_growth = 0
        for i in range(1, len(sales_list)):
            if sales_list[i-1]['total']:
                growth = (sales_list[i]['total'] - sales_list[i-1]['total']) / sales_list[i-1]['total']
                avg_growth += growth
        avg_growth = avg_growth / (len(sales_list) - 1) if len(sales_list) > 1 else 0.1
        
        last_sale = sales_list[-1]['total'] or Decimal('100000')
        for i in range(1, months + 1):
            forecast_amount = last_sale * (1 + avg_growth) ** i
            forecast_date = today + timedelta(days=30 * i)
            forecast.append({
                'month': forecast_date.strftime('%B %Y'),
                'amount': forecast_amount,
                'growth': avg_growth * 100
            })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'historical_sales': list(monthly_sales),
        'forecast': forecast,
        'months': months,
    }
    return render(request, 'reports/sales_forecast.html', context)


@login_required
def profit_trend_report(request):
    """Profit trend over time"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=365)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    monthly_profit = SaleItem.objects.filter(
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).annotate(
        month=TruncMonth('sale__sale_date')
    ).values('month').annotate(
        sales=Sum('total_amt'),
        profit=Sum('profit'),
        discount=Sum('sale__discount_value')
    ).order_by('month')
    
    for item in monthly_profit:
        item['net_profit'] = (item['profit'] or 0) - (item['discount'] or 0)
        item['margin'] = (item['net_profit'] / item['sales'] * 100) if item['sales'] else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'monthly_profit': monthly_profit,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/profit_trend.html', context)


@login_required
def top_products_report(request):
    """Top Selling Products Report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    limit = int(request.GET.get('limit', 10))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    top_products = SaleItem.objects.filter(
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__id', 'product__name', 'product__serial_no'
    ).annotate(
        total_qty=Sum('qty'),
        total_sales=Sum('total_amt'),
        total_profit=Sum('profit')
    ).order_by('-total_sales')[:limit]
    
    max_sales = max([p['total_sales'] for p in top_products]) if top_products else 1
    for product in top_products:
        product['percentage'] = float(product['total_sales'] / max_sales * 100) if max_sales > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'top_products': top_products,
        'limit': limit,
    }
    return render(request, 'reports/top_products.html', context)


@login_required
def sales_by_hour_report(request):
    """Sales distribution by hour of day"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    hourly_sales = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).extra(
        {'hour': "strftime('%%H', sale_date)"}
    ).values('hour').annotate(
        total=Sum('saleitem__total_amt'),
        count=Count('id')
    ).order_by('hour')
    
    hours_data = []
    for h in range(24):
        hour_str = f"{h:02d}"
        found = False
        for hs in hourly_sales:
            if hs['hour'] == hour_str:
                hours_data.append({
                    'hour': h,
                    'total': hs['total'] or 0,
                    'count': hs['count']
                })
                found = True
                break
        if not found:
            hours_data.append({'hour': h, 'total': 0, 'count': 0})
    
    peak_hour = max(hours_data, key=lambda x: x['total']) if hours_data else None
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'hourly_sales': hours_data,
        'peak_hour': peak_hour,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/sales_by_hour.html', context)


@login_required
def sales_by_day_report(request):
    """Sales distribution by day of week"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    weekday_sales = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).extra(
        {'weekday': "strftime('%%w', sale_date)"}
    ).values('weekday').annotate(
        total=Sum('saleitem__total_amt'),
        count=Count('id')
    ).order_by('weekday')
    
    days_data = []
    for i, name in enumerate(weekday_names):
        sql_weekday = str(i + 1) if i < 6 else '0'
        found = False
        for ws in weekday_sales:
            if ws['weekday'] == sql_weekday:
                days_data.append({
                    'day': name,
                    'day_num': i,
                    'total': ws['total'] or 0,
                    'count': ws['count']
                })
                found = True
                break
        if not found:
            days_data.append({'day': name, 'day_num': i, 'total': 0, 'count': 0})
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'days_data': days_data,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/sales_by_day.html', context)


@login_required
def accounts_receivable_aging(request):
    """Accounts Receivable Aging Report"""
    today = date.today()
    
    aging_buckets = {'0-30': 0, '31-60': 0, '61-90': 0, '91+': 0}
    customer_details = []
    
    for customer in Customer.objects.all():
        balance = customer.adjusted_outstanding_balance()
        if balance > 0:
            oldest_sale = customer.sale_set.filter(
                outstanding_balance__gt=0
            ).order_by('sale_date').first()
            
            if oldest_sale:
                days_old = (today - oldest_sale.sale_date.date()).days
                
                if days_old <= 30:
                    bucket = '0-30'
                elif days_old <= 60:
                    bucket = '31-60'
                elif days_old <= 90:
                    bucket = '61-90'
                else:
                    bucket = '91+'
                
                aging_buckets[bucket] += balance
                
                customer_details.append({
                    'name': customer.name,
                    'code': customer.customer_code,
                    'balance': balance,
                    'days_old': days_old,
                    'bucket': bucket,
                    'oldest_date': oldest_sale.sale_date.date(),
                })
    
    customer_details.sort(key=lambda x: x['days_old'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'aging_buckets': aging_buckets,
        'customer_details': customer_details,
        'total_outstanding': sum(aging_buckets.values()),
    }
    return render(request, 'reports/accounts_receivable_aging.html', context)


@login_required
def inventory_status_report(request):
    """Inventory Status Report"""
    items = Inventory.objects.select_related('product', 'warehouse').order_by('product__name')
    
    total_products = items.count()
    total_stock_value = sum(item.stock_value() for item in items)
    low_stock_count = items.filter(stock__lt=F('product__low_stock_threshold')).count()
    out_of_stock = items.filter(stock=0).count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'inventory_items': items[:200],
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'low_stock_count': low_stock_count,
        'out_of_stock': out_of_stock,
    }
    return render(request, 'reports/inventory_status.html', context)


# ✅ NEW CODE
@login_required
def low_stock_report(request):
    low_stock_items = Inventory.objects.select_related(
        'product',
        'warehouse',
        'product__unit',
        'product__category',
        'product__brand'
    ).filter(
        stock__lt=F('product__low_stock_threshold')
    ).order_by('product__name')
    
    for item in low_stock_items:
        if item.product.low_stock_threshold > 0:
            item.stock_percent = (item.stock / item.product.low_stock_threshold) * 100
        else:
            item.stock_percent = 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'low_stock_items': low_stock_items,
        'total_low_stock': low_stock_items.count(),
    }
    return render(request, 'reports/low_stock.html', context)


@login_required
def inventory_aging_report(request):
    """Inventory Aging Report"""
    from decimal import Decimal
    
    warehouses = Warehouse.objects.all()
    aging_data = []
    total_value = Decimal('0.0')
    
    for warehouse in warehouses:
        batches = StockBatch.objects.filter(
            warehouse=warehouse,
            remaining_qty__gt=0
        ).order_by('id')
        
        for batch in batches:
            # ✅ FIX: float ko Decimal mein convert
            qty_decimal = Decimal(str(batch.remaining_qty))
            value = qty_decimal * batch.price
            total_value += value
            
            aging_data.append({
                'warehouse': warehouse.name,
                'product': batch.product.name,
                'quantity': batch.remaining_qty,
                'value': value,
                'price': batch.price,
            })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'aging_data': aging_data,
        'total_value': total_value,
    }
    return render(request, 'reports/inventory_aging.html', context)


@login_required
def stock_aging_report(request):
    """Stock Aging Report"""
    stock_data = []
    
    batches = StockBatch.objects.filter(remaining_qty__gt=0).select_related('product', 'warehouse')
    
    for batch in batches:
        value = batch.remaining_qty * batch.price
        stock_data.append({
            'warehouse': batch.warehouse.name,
            'product': batch.product.name,
            'quantity': batch.remaining_qty,
            'value': value,
            'price': batch.price,
        })
    
    total_value = sum(d['value'] for d in stock_data)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'stock_data': stock_data,
        'total_value': total_value,
    }
    return render(request, 'reports/stock_aging.html', context)


@login_required
def best_selling_categories_report(request):
    """Best selling categories"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    category_sales = SaleItem.objects.filter(
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__category__isnull=False
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum('total_amt'),
        total_qty=Sum('qty'),
        total_profit=Sum('profit')
    ).order_by('-total_sales')
    
    total_all = sum(c['total_sales'] for c in category_sales) or 1
    for cat in category_sales:
        cat['percentage'] = (cat['total_sales'] / total_all) * 100
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category_sales': category_sales,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/best_selling_categories.html', context)


@login_required
def yearly_comparison_report(request):
    """Year over year comparison"""
    year = int(request.GET.get('year', date.today().year))
    
    current_year_sales = Sale.objects.filter(
        sale_date__year=year
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Sum('saleitem__total_amt')
    ).order_by('month')
    
    previous_year_sales = Sale.objects.filter(
        sale_date__year=year-1
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Sum('saleitem__total_amt')
    ).order_by('month') if year > 2020 else []
    
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    comparison_data = []
    
    for i, month_name in enumerate(months):
        current = 0
        for cs in current_year_sales:
            if cs['month'] and cs['month'].month == i + 1:
                current = cs['total'] or 0
                break
        
        previous = 0
        for ps in previous_year_sales:
            if ps['month'] and ps['month'].month == i + 1:
                previous = ps['total'] or 0
                break
        
        growth = ((current - previous) / previous * 100) if previous > 0 else (100 if current > 0 else 0)
        
        comparison_data.append({
            'month': month_name,
            'current': current,
            'previous': previous,
            'growth': growth
        })
    
    total_current = sum(d['current'] for d in comparison_data)
    total_previous = sum(d['previous'] for d in comparison_data)
    overall_growth = ((total_current - total_previous) / total_previous * 100) if total_previous > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'comparison_data': comparison_data,
        'year': year,
        'total_current': total_current,
        'total_previous': total_previous,
        'overall_growth': overall_growth,
    }
    return render(request, 'reports/yearly_comparison.html', context)


@login_required
def monthly_comparison_report(request):
    """Month over month comparison"""
    year = int(request.GET.get('year', date.today().year))
    
    monthly_sales = Sale.objects.filter(
        sale_date__year=year
    ).annotate(
        month=TruncMonth('sale_date')
    ).values('month').annotate(
        total=Sum('saleitem__total_amt'),
        count=Count('id')
    ).order_by('month')
    
    months_data = []
    for month in range(1, 13):
        found = False
        for ms in monthly_sales:
            if ms['month'] and ms['month'].month == month:
                months_data.append({
                    'month': calendar.month_name[month],
                    'sales': ms['total'] or 0,
                    'count': ms['count']
                })
                found = True
                break
        if not found:
            months_data.append({
                'month': calendar.month_name[month],
                'sales': 0,
                'count': 0
            })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'months_data': months_data,
        'year': year,
    }
    return render(request, 'reports/monthly_comparison.html', context)


@login_required
def best_selling_brands_report(request):
    """Best selling brands"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    brand_sales = SaleItem.objects.filter(
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__brand__isnull=False
    ).values(
        'product__brand__name'
    ).annotate(
        total_sales=Sum('total_amt'),
        total_qty=Sum('qty'),
        total_profit=Sum('profit')
    ).order_by('-total_sales')
    
    total_all = sum(b['total_sales'] for b in brand_sales) or 1
    for brand in brand_sales:
        brand['percentage'] = (brand['total_sales'] / total_all) * 100
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'brand_sales': brand_sales,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/best_selling_brands.html', context)


@login_required
def sales_by_week_report(request):
    """Sales distribution by week number"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=180)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    weekly_sales = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).annotate(
        week=TruncWeek('sale_date')
    ).values('week').annotate(
        total=Sum('saleitem__total_amt'),
        count=Count('id')
    ).order_by('week')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'weekly_sales': weekly_sales,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/sales_by_week.html', context)


@login_required
def salesman_performance_report(request):
    """Salesman wise performance"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    salesmen = Employee.objects.filter(department='sales', status='active')
    salesman_data = []
    
    for salesman in salesmen:
        sales = Sale.objects.filter(
            created_by__email=salesman.email,
            sale_date__date__gte=from_date_obj,
            sale_date__date__lte=to_date_obj
        )
        
        total_sales = sum(s.total_amount() for s in sales)
        total_profit = sum(s.total_profit() for s in sales)
        sale_count = sales.count()
        
        target = SalesTarget.objects.filter(
            salesman__email=salesman.email,
            target_type='salesman',
            start_date__lte=to_date_obj,
            end_date__gte=from_date_obj
        ).first()
        
        target_amount = target.target_amount if target else total_sales
        achievement = (total_sales / target_amount * 100) if target_amount > 0 else 0
        
        salesman_data.append({
            'name': salesman.name,
            'employee_id': salesman.employee_id,
            'total_sales': total_sales,
            'total_profit': total_profit,
            'sale_count': sale_count,
            'target': target_amount,
            'achievement': achievement,
        })
    
    salesman_data.sort(key=lambda x: x['total_sales'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'salesman_data': salesman_data,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/salesman_performance.html', context)


@login_required
def sales_tax_summary(request):
    """Sales Tax Summary Report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    sales = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    )
    
    total_taxable = sum(s.total_amount() for s in sales)
    tax_rate = 16
    total_tax = total_taxable * (tax_rate / 100)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_taxable': total_taxable,
        'total_tax': total_tax,
        'tax_rate': tax_rate,
    }
    return render(request, 'reports/sales_tax_summary.html', context)


@login_required
def sales_return_analysis(request):
    """Sales Return Analysis Report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    returns = SaleRetrn.objects.filter(
        sale_return_date__date__gte=from_date_obj,
        sale_return_date__date__lte=to_date_obj
    )
    
    total_returns = 0
    return_reasons = {}
    
    for ret in returns:
        amount = sum(item.total_amt for item in ret.return_items.all())
        total_returns += amount
        
        if ret.return_reason not in return_reasons:
            return_reasons[ret.return_reason] = 0
        return_reasons[ret.return_reason] += amount
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_returns': total_returns,
        'return_reasons': return_reasons,
        'returns_count': returns.count(),
    }
    return render(request, 'reports/sales_return_analysis.html', context)


@login_required
def accounts_payable_aging(request):
    """Accounts Payable Aging Report"""
    today = date.today()
    
    aging_buckets = {'0-30': 0, '31-60': 0, '61-90': 0, '91+': 0}
    vendor_details = []
    
    for vendor in Vendor.objects.all():
        balance = vendor.outstanding_balance()
        if balance > 0:
            oldest_purchase = vendor.purchase_set.filter(
                outstanding_balance__gt=0
            ).order_by('pur_date').first()
            
            if oldest_purchase:
                days_old = (today - oldest_purchase.pur_date.date()).days
                
                if days_old <= 30:
                    bucket = '0-30'
                elif days_old <= 60:
                    bucket = '31-60'
                elif days_old <= 90:
                    bucket = '61-90'
                else:
                    bucket = '91+'
                
                aging_buckets[bucket] += balance
                
                vendor_details.append({
                    'name': vendor.name,
                    'code': vendor.vendor_code,
                    'balance': balance,
                    'days_old': days_old,
                    'bucket': bucket,
                    'oldest_date': oldest_purchase.pur_date.date(),
                })
    
    vendor_details.sort(key=lambda x: x['days_old'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'aging_buckets': aging_buckets,
        'vendor_details': vendor_details,
        'total_outstanding': sum(aging_buckets.values()),
    }
    return render(request, 'reports/accounts_payable_aging.html', context)


@login_required
def daily_summary_report(request):
    """Daily Summary Report"""
    date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    sales = Sale.objects.filter(sale_date__date=report_date)
    purchases = Purchase.objects.filter(pur_date__date=report_date)
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_purchases = sum(p.total_amount() for p in purchases)
    total_expenses = Expense.objects.filter(expense_date=report_date).aggregate(total=Sum('amount'))['total'] or 0
    
    net_income = total_sales - total_purchases - total_expenses
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_date': report_date,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_purchases': total_purchases,
        'total_expenses': total_expenses,
        'net_income': net_income,
        'sales_count': sales.count(),
        'purchases_count': purchases.count(),
    }
    return render(request, 'reports/daily_summary.html', context)


@login_required
def weekly_summary_report(request):
    """Weekly Summary Report"""
    week_num = int(request.GET.get('week', date.today().isocalendar()[1]))
    year = int(request.GET.get('year', date.today().year))
    
    start_date = datetime.strptime(f'{year}-W{week_num}-1', "%Y-W%W-%w").date()
    end_date = start_date + timedelta(days=6)
    
    sales = Sale.objects.filter(sale_date__date__gte=start_date, sale_date__date__lte=end_date)
    purchases = Purchase.objects.filter(pur_date__date__gte=start_date, pur_date__date__lte=end_date)
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_purchases = sum(p.total_amount() for p in purchases)
    
    daily_breakdown = []
    current = start_date
    while current <= end_date:
        day_sales = sales.filter(sale_date__date=current)
        daily_breakdown.append({
            'date': current,
            'sales': sum(s.total_amount() for s in day_sales),
            'count': day_sales.count()
        })
        current += timedelta(days=1)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'week_num': week_num,
        'year': year,
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_purchases': total_purchases,
        'daily_breakdown': daily_breakdown,
    }
    return render(request, 'reports/weekly_summary.html', context)


@login_required
def monthly_summary_report(request):
    """Monthly Summary Report"""
    year = int(request.GET.get('year', date.today().year))
    month = int(request.GET.get('month', date.today().month))
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    sales = Sale.objects.filter(sale_date__date__gte=start_date, sale_date__date__lte=end_date)
    purchases = Purchase.objects.filter(pur_date__date__gte=start_date, pur_date__date__lte=end_date)
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_purchases = sum(p.total_amount() for p in purchases)
    total_expenses = Expense.objects.filter(expense_date__gte=start_date, expense_date__lte=end_date).aggregate(total=Sum('amount'))['total'] or 0
    
    closing = MonthlyClosing.objects.filter(month=start_date).first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_purchases': total_purchases,
        'total_expenses': total_expenses,
        'closing': closing,
    }
    return render(request, 'reports/monthly_summary.html', context)


@login_required
def quarterly_summary_report(request):
    """Quarterly Summary Report"""
    year = int(request.GET.get('year', date.today().year))
    quarter = int(request.GET.get('quarter', ((date.today().month - 1) // 3) + 1))
    
    quarters = {
        1: {'months': [1, 2, 3], 'name': 'Q1 (Jan-Mar)'},
        2: {'months': [4, 5, 6], 'name': 'Q2 (Apr-Jun)'},
        3: {'months': [7, 8, 9], 'name': 'Q3 (Jul-Sep)'},
        4: {'months': [10, 11, 12], 'name': 'Q4 (Oct-Dec)'},
    }
    
    months = quarters[quarter]['months']
    start_date = date(year, months[0], 1)
    if months[-1] == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, months[-1] + 1, 1) - timedelta(days=1)
    
    sales = Sale.objects.filter(sale_date__date__gte=start_date, sale_date__date__lte=end_date)
    purchases = Purchase.objects.filter(pur_date__date__gte=start_date, pur_date__date__lte=end_date)
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_purchases = sum(p.total_amount() for p in purchases)
    
    monthly_breakdown = []
    for month in months:
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        month_sales = sales.filter(sale_date__date__gte=month_start, sale_date__date__lte=month_end)
        monthly_breakdown.append({
            'month': calendar.month_name[month],
            'sales': sum(s.total_amount() for s in month_sales),
            'count': month_sales.count()
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'year': year,
        'quarter': quarter,
        'quarter_name': quarters[quarter]['name'],
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_purchases': total_purchases,
        'monthly_breakdown': monthly_breakdown,
    }
    return render(request, 'reports/quarterly_summary.html', context)


@login_required
def yearly_summary_report(request):
    """Yearly Summary Report"""
    year = int(request.GET.get('year', date.today().year))
    
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    sales = Sale.objects.filter(sale_date__date__gte=start_date, sale_date__date__lte=end_date)
    purchases = Purchase.objects.filter(pur_date__date__gte=start_date, pur_date__date__lte=end_date)
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_purchases = sum(p.total_amount() for p in purchases)
    
    monthly_breakdown = []
    for month in range(1, 13):
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        month_sales = sales.filter(sale_date__date__gte=month_start, sale_date__date__lte=month_end)
        monthly_breakdown.append({
            'month': calendar.month_name[month],
            'sales': sum(s.total_amount() for s in month_sales),
            'profit': sum(s.total_profit() for s in month_sales),
            'count': month_sales.count()
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'year': year,
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_purchases': total_purchases,
        'monthly_breakdown': monthly_breakdown,
        'previous_year': year - 1,
        'next_year': year + 1,
    }
    return render(request, 'reports/yearly_summary.html', context)


@login_required
def export_report_excel(request, report_name):
    """Export any report to Excel"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report_name.replace('_', ' ').title()
    
    if report_name == 'sales_summary':
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        sales = Sale.objects.filter(sale_date__date__gte=from_date, sale_date__date__lte=to_date)
        
        headers = ['Bill No', 'Date', 'Customer', 'Amount', 'Discount', 'Paid', 'Outstanding', 'Profit']
        ws.append(headers)
        
        for sale in sales:
            ws.append([
                sale.bill_no,
                sale.sale_date.strftime('%d-%m-%Y'),
                sale.customer.name,
                float(sale.total_amount()),
                float(sale.discount_value),
                float(sale.paid),
                float(sale.outstanding_balance()),
                float(sale.total_profit())
            ])
    
    elif report_name == 'customer_outstanding':
        headers = ['Customer Code', 'Customer Name', 'Phone', 'Outstanding']
        ws.append(headers)
        
        for customer in Customer.objects.all():
            balance = customer.adjusted_outstanding_balance()
            if balance > 0:
                ws.append([
                    customer.customer_code or '-',
                    customer.name,
                    customer.contact_number or '-',
                    float(balance)
                ])
    
    elif report_name == 'low_stock':
        headers = ['Product', 'Current Stock', 'Threshold', 'Status']
        ws.append(headers)
        
        low_stock = Inventory.objects.filter(stock__lt=F('product__low_stock_threshold'))
        for item in low_stock:
            ws.append([
                item.product.name,
                item.stock,
                item.product.low_stock_threshold,
                'LOW STOCK!'
            ])
    
    elif report_name == 'top_products':
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        top = SaleItem.objects.filter(
            sale__sale_date__date__gte=from_date,
            sale__sale_date__date__lte=to_date
        ).values('product__name').annotate(
            total_qty=Sum('qty'),
            total_sales=Sum('total_amt')
        ).order_by('-total_sales')[:50]
        
        headers = ['Product', 'Quantity Sold', 'Total Sales']
        ws.append(headers)
        
        for item in top:
            ws.append([
                item['product__name'],
                float(item['total_qty']),
                float(item['total_sales'])
            ])
    
    elif report_name == 'customer_wise':
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        customers = Customer.objects.all()
        headers = ['Customer Code', 'Customer Name', 'Group', 'Total Sales', 'Total Profit', 'Sale Count', 'Outstanding']
        ws.append(headers)
        
        for customer in customers:
            sales = Sale.objects.filter(
                customer=customer,
                sale_date__date__gte=from_date,
                sale_date__date__lte=to_date
            )
            total_sales = sum(s.total_amount() for s in sales)
            if total_sales > 0:
                ws.append([
                    customer.customer_code or '-',
                    customer.name,
                    customer.group.name if customer.group else '-',
                    float(total_sales),
                    float(sum(s.total_profit() for s in sales)),
                    sales.count(),
                    float(customer.adjusted_outstanding_balance())
                ])
    
    # Style headers
    header_fill = PatternFill(start_color="1a1a2e", end_color="1a1a2e", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 40)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{report_name}_{date.today()}.xlsx"'
    wb.save(response)
    return response


@login_required
def sales_report(request):
    """
    Sales report with detailed filters
    ✅ OPTIMIZED: DB aggregation (was very heavy)
    """
    from django.db.models import Sum, Count, Q, F, Value, DecimalField
    from django.db.models.functions import Coalesce
    
    date_from = request.GET.get('date_from', (localdate() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', localdate().strftime('%Y-%m-%d'))
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    customer_id = request.GET.get('customer', '')
    warehouse_id = request.GET.get('warehouse', '')
    
    sales = Sale.objects.filter(
        sale_date__date__gte=date_from,
        sale_date__date__lte=date_to
    ).select_related(
        'customer', 'warehouse'
    ).prefetch_related(
        'saleitem_set', 'saleitem_set__product'
    )
    
    if search:
        sales = sales.filter(
            Q(bill_no__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__customer_code__icontains=search)
        )
    
    if customer_id:
        sales = sales.filter(customer_id=customer_id)
    
    if warehouse_id:
        sales = sales.filter(warehouse_id=warehouse_id)
    
    # ✅ Annotate for status filter
    sales = sales.annotate(
        annotated_total=Coalesce(
            Sum('saleitem__total_amt'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=15, decimal_places=2)
        ),
    )
    
    # Status filter AFTER annotation
    if status == 'paid':
        sales = sales.filter(paid__gte=F('annotated_total'))
    elif status == 'pending':
        sales = sales.filter(paid__lt=F('annotated_total'))
    
    # ✅ Single aggregate query
    totals = sales.aggregate(
        total_amount=Coalesce(Sum('saleitem__total_amt'), Value(Decimal('0.00'))),
        total_profit=Coalesce(Sum('saleitem__profit'), Value(Decimal('0.00'))),
        total_paid=Coalesce(Sum('paid'), Value(Decimal('0.00'))),
        total_subtotal=Coalesce(
            Sum(
                F('saleitem__qty') * F('saleitem__price'),
                output_field=DecimalField(max_digits=15, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        total_discount=Coalesce(Sum('discount_value'), Value(Decimal('0.00'))),
        total_items=Count('saleitem__id', distinct=True),
        count=Count('id', distinct=True),
    )
    
    total_amount = totals['total_amount']
    total_profit = totals['total_profit']
    total_paid = totals['total_paid']
    total_subtotal = totals['total_subtotal']
    total_discount = totals['total_discount']
    total_outstanding = total_amount - total_paid
    total_items = totals['total_items']
    count = totals['count']
    
    # PDF exports
    if request.GET.get('export') == 'pdf':
        return generate_sales_report_pdf(sales, date_from, date_to, total_amount, total_profit, total_paid, count)
    
    if request.GET.get('export') == 'products_pdf':
        return generate_products_detail_pdf(sales, date_from, date_to, total_amount, total_profit, count)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'sales': sales,
        'total_amount': total_amount,
        'total_profit': total_profit,
        'total_paid': total_paid,
        'total_subtotal': total_subtotal,
        'total_discount': total_discount,
        'total_outstanding': total_outstanding,
        'total_items': total_items,
        'count': count,
        'avg_sale': total_amount / count if count > 0 else 0,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
        'status': status,
        'selected_customer': customer_id,
        'selected_warehouse': warehouse_id,
        'customers': Customer.objects.all().order_by('name'),
        'warehouses': Warehouse.objects.all(),
    }
    return render(request, 'reports/sales_report.html', context)


def generate_sales_report_pdf(sales, date_from, date_to, total_amount, total_profit, total_paid, count):
    """Generate PDF for Sales Summary"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else 'ERP System'
    story.append(Paragraph(f"<b>{company_name}</b>", styles['Heading1']))
    story.append(Paragraph(f"Sales Report: {date_from} to {date_to}", styles['Heading2']))
    story.append(Paragraph(f"Total Sales: {count} | Amount: Rs. {total_amount:,.0f} | Profit: Rs. {total_profit:,.0f} | Paid: Rs. {total_paid:,.0f}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    data = [['Bill No', 'Date', 'Customer', 'Items', 'Total', 'Paid', 'Profit', 'Status']]
    for sale in sales:
        outstanding = sale.outstanding_balance()
        status = 'Paid' if outstanding <= 0 else 'Pending'
        data.append([
            sale.bill_no,
            sale.sale_date.strftime('%d-%m-%Y'),
            sale.customer.name[:22],
            str(sale.saleitem_set.count()),
            f"Rs. {sale.total_amount():,.0f}",
            f"Rs. {sale.paid:,.0f}",
            f"Rs. {sale.total_profit():,.0f}",
            status
        ])
    
    table = Table(data, colWidths=[90, 65, 140, 40, 80, 80, 80, 60])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f6fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Sales_Report_{date_from}_to_{date_to}.pdf"'
    return response


def generate_products_detail_pdf(sales, date_from, date_to, total_amount, total_profit, count):
    """Generate PDF for Products Sold Detail"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else 'ERP System'
    
    story.append(Paragraph(f"<b>{company_name}</b>", styles['Heading1']))
    story.append(Paragraph(f"Products Sold Detail: {date_from} to {date_to}", styles['Heading2']))
    
    total_items = sum(s.saleitem_set.count() for s in sales)
    story.append(Paragraph(f"Total Sales: {count} | Items: {total_items} | Amount: Rs. {total_amount:,.0f} | Profit: Rs. {total_profit:,.0f}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    data = [['Bill No', 'Date', 'Customer', 'Product', 'Qty', 'Price', 'Total', 'Profit']]
    
    grand_qty = 0
    grand_total = 0
    grand_profit = 0
    
    for sale in sales:
        for item in sale.saleitem_set.all():
            data.append([
                sale.bill_no,
                sale.sale_date.strftime('%d-%m-%Y'),
                sale.customer.name[:20],
                item.product.name[:30],
                f"{item.qty:,.2f}",
                f"Rs. {item.price:,.2f}",
                f"Rs. {item.total_amt:,.2f}",
                f"Rs. {item.profit:,.2f}",
            ])
            grand_qty += item.qty
            grand_total += item.total_amt
            grand_profit += item.profit
    
    data.append(['', '', '', 'GRAND TOTAL', f"{grand_qty:,.2f}", '', f"Rs. {grand_total:,.2f}", f"Rs. {grand_profit:,.2f}"])
    
    col_widths = [1.0*inch, 0.8*inch, 1.5*inch, 2.2*inch, 0.6*inch, 0.9*inch, 1.0*inch, 1.0*inch]
    
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -2), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f5f6fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 9),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#333333')),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Products_Detail_{date_from}_to_{date_to}.pdf"'
    return response


@login_required
def profit_loss(request):
    month = request.GET.get('month', localdate().strftime('%Y-%m'))
    month_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
    
    closing = MonthlyClosing.objects.filter(month=month_date).first()
    
    expenses = Expense.objects.filter(expense_date__year=month_date.year, expense_date__month=month_date.month).aggregate(
        total=Sum('amount'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'closing': closing,
        'expenses': expenses,
        'month': month,
        'net_profit': (closing.total_sale_profit() - expenses) if closing else 0,
    }
    return render(request, 'reports/profit_loss.html', context)


@login_required
def batch_sale_report(request, pk):
    """
    Batch se kitne ka sale hua — complete report
    """
    from django.db.models import Sum, Count
    from decimal import Decimal
    
    batch = get_object_or_404(StockBatch, pk=pk)
    
    # ✅ Is batch se saari sales
    sales_items = SaleItem.objects.filter(
        batches_used=batch
    ).select_related('sale', 'sale__customer', 'product').order_by('-sale__sale_date')
    
    # ✅ Statistics
    stats = sales_items.aggregate(
        total_qty=Sum('qty'),
        total_sales=Sum('total_amt'),
        total_profit=Sum('profit'),
        total_orders=Count('id', distinct=True),
    )
    
    total_qty = stats['total_qty'] or 0
    total_sales = stats['total_sales'] or Decimal('0.00')
    total_profit = stats['total_profit'] or Decimal('0.00')
    total_orders = stats['total_orders'] or 0
    
    # ✅ Total cost (batch se)
    total_cost = Decimal(str(total_qty)) * batch.price
    
    # ✅ Remaining
    remaining_qty = batch.remaining_qty
    remaining_value = Decimal(str(remaining_qty)) * batch.price
    
    # ✅ Batch summary
    batch_summary = {
        'original_qty': batch.qty,
        'sold_qty': total_qty,
        'remaining_qty': remaining_qty,
        'original_value': Decimal(str(batch.qty)) * batch.price,
        'sold_value': total_sales,
        'remaining_value': remaining_value,
        'total_profit': total_profit,
        'profit_margin': (total_profit / total_sales * 100) if total_sales > 0 else Decimal('0.00'),
    }
    
    # ✅ Daily summary
    daily_summary = sales_items.values(
        'sale__sale_date__date'
    ).annotate(
        qty=Sum('qty'),
        amount=Sum('total_amt'),
        profit=Sum('profit'),
    ).order_by('-sale__sale_date__date')
    
    # ✅ Customer-wise
    customer_summary = sales_items.values(
        'sale__customer__name',
        'sale__customer__customer_code'
    ).annotate(
        qty=Sum('qty'),
        amount=Sum('total_amt'),
        profit=Sum('profit'),
        orders=Count('id'),
    ).order_by('-amount')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'batch': batch,
        'sales_items': sales_items,
        'stats': stats,
        'batch_summary': batch_summary,
        'daily_summary': daily_summary,
        'customer_summary': customer_summary,
        'total_cost': total_cost,
    }
    return render(request, 'inventory/batch_sale_report.html', context)
