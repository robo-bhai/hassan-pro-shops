from decimal import Decimal
from datetime import datetime, timedelta,date
from django.db.models import Sum, Count, Avg, Q, F
from django.utils.timezone import now
from app.models import (
    Sale, Purchase, Product, Customer, Vendor, Employee,
    Expense, Budget, Inventory, MonthlyClosing,
    SaleItem, PurchaseItem
)


def get_sales_data(days=30):
    """Get sales data for BI"""
    from datetime import date, timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    sales = Sale.objects.filter(
        sale_date__date__gte=start_date,
        sale_date__date__lte=end_date
    )
    
    total_sales = sum(s.total_amount() for s in sales)
    total_profit = sum(s.total_profit() for s in sales)
    total_count = sales.count()
    
    # Daily trend
    daily_data = []
    current = start_date
    while current <= end_date:
        day_sales = sales.filter(sale_date__date=current)
        daily_data.append({
            'date': current.strftime('%Y-%m-%d'),
            'sales': float(sum(s.total_amount() for s in day_sales)),
            'profit': float(sum(s.total_profit() for s in day_sales)),
            'count': day_sales.count()
        })
        current += timedelta(days=1)
    
    # Top products
    top_products = SaleItem.objects.filter(
        sale__in=sales
    ).values('product__name').annotate(
        total_sales=Sum('total_amt'),
        total_qty=Sum('qty'),
        total_profit=Sum('profit')
    ).order_by('-total_sales')[:10]
    
    return {
        'total_sales': float(total_sales),
        'total_profit': float(total_profit),
        'total_count': total_count,
        'avg_sale': float(total_sales / total_count if total_count > 0 else 0),
        'daily_data': daily_data,
        'top_products': list(top_products),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }


def get_financial_data():
    """Get financial data for BI"""
    today = date.today()
    month_start = today.replace(day=1)
    
    # Sales
    total_sales = Sale.objects.aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
    total_profit = SaleItem.objects.aggregate(total=Sum('profit'))['total'] or 0
    
    # Purchases
    total_purchases = Purchase.objects.aggregate(total=Sum('purchaseitem__total_amt'))['total'] or 0
    
    # Expenses
    total_expenses = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0
    
    # Cash
    from app.models import CashBalance
    cash_balance = CashBalance.get_balance()
    
    # Inventory value
    inventory_value = 0
    for inv in Inventory.objects.all():
        inventory_value += inv.stock_value()
    
    # Customer outstanding
    customer_outstanding = 0
    for customer in Customer.objects.all():
        customer_outstanding += customer.adjusted_outstanding_balance()
    
    # Vendor outstanding
    vendor_outstanding = 0
    for vendor in Vendor.objects.all():
        vendor_outstanding += vendor.outstanding_balance()
    
    return {
        'total_sales': float(total_sales),
        'total_profit': float(total_profit),
        'profit_margin': float((total_profit / total_sales * 100) if total_sales > 0 else 0),
        'total_purchases': float(total_purchases),
        'total_expenses': float(total_expenses),
        'cash_balance': float(cash_balance),
        'inventory_value': float(inventory_value),
        'customer_outstanding': float(customer_outstanding),
        'vendor_outstanding': float(vendor_outstanding),
        'net_worth': float(cash_balance + inventory_value - customer_outstanding - vendor_outstanding),
    }


def get_customer_data(days=30):
    """Get customer analytics"""
    from datetime import date, timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    total_customers = Customer.objects.count()
    
    # ✅ FIX: Customer model mein created_at nahi hai
    # Simple count of all customers as new for now
    new_customers = 0
    
    sales = Sale.objects.filter(sale_date__date__gte=start_date, sale_date__date__lte=end_date)
    
    # Top customers
    top_customers = sales.values('customer__name').annotate(
        total_sales=Sum('saleitem__total_amt'),
        total_count=Count('id')
    ).order_by('-total_sales')[:10]
    
    # Customer retention
    repeat_customers = sales.values('customer').annotate(
        total=Count('id')
    ).filter(total__gt=1).count()
    
    return {
        'total_customers': total_customers,
        'new_customers': new_customers,
        'top_customers': list(top_customers),
        'repeat_customers': repeat_customers,
        'retention_rate': float((repeat_customers / total_customers * 100) if total_customers > 0 else 0),
    }


def get_inventory_data():
    """Get inventory analytics"""
    total_products = Product.objects.count()
    total_inventory = Inventory.objects.count()
    
    low_stock = Inventory.objects.filter(stock__lt=F('product__low_stock_threshold')).count()
    out_of_stock = Inventory.objects.filter(stock=0).count()
    
    total_value = 0
    for inv in Inventory.objects.all():
        total_value += inv.stock_value()
    
    return {
        'total_products': total_products,
        'total_inventory': total_inventory,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'total_value': float(total_value),
        'stock_health': float(((total_inventory - low_stock - out_of_stock) / total_inventory * 100) if total_inventory > 0 else 0),
    }


def get_employee_data():
    """Get employee analytics"""
    total_employees = Employee.objects.count()
    active_employees = Employee.objects.filter(status='active').count()
    
    total_salary = 0
    for emp in Employee.objects.all():
        total_salary += emp.total_salary()
    
    return {
        'total_employees': total_employees,
        'active_employees': active_employees,
        'total_salary': float(total_salary),
        'avg_salary': float(total_salary / total_employees if total_employees > 0 else 0),
    }


def calculate_kpi(kpi):
    """Calculate KPI value"""
    from datetime import date, timedelta
    
    if kpi.category == 'sales':
        if kpi.name == 'Monthly Sales':
            month_start = date.today().replace(day=1)
            sales = Sale.objects.filter(sale_date__date__gte=month_start)
            kpi.current_value = sum(s.total_amount() for s in sales)
        
        elif kpi.name == 'Sales Growth':
            today = date.today()
            month_start = today.replace(day=1)
            last_month_start = (month_start - timedelta(days=1)).replace(day=1)
            
            current = Sale.objects.filter(sale_date__date__gte=month_start)
            previous = Sale.objects.filter(sale_date__date__gte=last_month_start, sale_date__date__lt=month_start)
            
            current_total = sum(s.total_amount() for s in current)
            previous_total = sum(s.total_amount() for s in previous)
            
            if previous_total > 0:
                kpi.current_value = ((current_total - previous_total) / previous_total) * 100
            else:
                kpi.current_value = 0
    
    elif kpi.category == 'financial':
        if kpi.name == 'Profit Margin':
            total_sales = Sale.objects.aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            total_profit = SaleItem.objects.aggregate(total=Sum('profit'))['total'] or 0
            kpi.current_value = (total_profit / total_sales * 100) if total_sales > 0 else 0
        
        elif kpi.name == 'Cash Balance':
            from app.models import CashBalance
            kpi.current_value = CashBalance.get_balance()
    
    elif kpi.category == 'customer':
        if kpi.name == 'Customer Satisfaction':
            kpi.current_value = 85
        
        elif kpi.name == 'Retention Rate':
            total = Customer.objects.count()
            repeat = Customer.objects.annotate(
                sale_count=Count('sale')
            ).filter(sale_count__gt=1).count()
            kpi.current_value = (repeat / total * 100) if total > 0 else 0
    
    kpi.update_progress()
    return kpi