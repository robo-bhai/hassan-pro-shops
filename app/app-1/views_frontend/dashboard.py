"""Frontend views: dashboard."""
from django.utils.timezone import localdate
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper
from django.core.cache import cache
from ..models import *
import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Value, DecimalField
from decimal import Decimal
from django.utils.timezone import now
from datetime import timedelta
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from ..models import Shareholder, Share, DividendPayment, ShareholderCashBalance, CompanyInfo, Sale, Purchase, Expense, SystemSetting, Employee, Attendance, LeaveRequest, SaleOrder, SaleItem, Product
from django.contrib.auth import logout
from django.contrib.auth.models import User


ROLE_ICONS = {
    'admin': 'bi-shield-lock',
    'owner': 'bi-building',
    'salesman': 'bi-person-badge',
    'accountant': 'bi-calculator',
    'manager': 'bi-people',
    'warehouse': 'bi-box',
}


# Role mapping
ROLE_GROUPS = {
    'admin': ['Admin', 'Can view all', 'Can edit all', 'Can delete all'],
    'owner': ['Owner', 'Can view reports', 'Can manage users', 'Full access'],
    'salesman': ['Salesman', 'Can create sales', 'Can view customers'],
    'accountant': ['Accountant', 'Can view reports', 'Can view financials'],
    'manager': ['Store Manager', 'Can manage inventory', 'Can approve orders'],
    'warehouse': ['Warehouse Staff', 'Can manage stock', 'Can receive goods'],
}


@login_required
def profile_view(request):
    return render(request, 'profile.html', {
        'user': request.user
    })


from ..module_catalog import MODULE_CATALOG, MODULE_GROUPS
_MODULE_KEYS = tuple(m['key'] for m in MODULE_CATALOG)


@login_required
def module_settings(request):
    """Module settings page - Admin can toggle modules"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can change module settings.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        # Update settings from POST data
        for key, value in request.POST.items():
            if key.startswith('setting_'):
                setting_key = key.replace('setting_', '')
                SystemSetting.set_value(setting_key, value == 'on', request.user)
        
        # Har module ke liye Shop / Factory switch (unchecked = off bhi save hota hai)
        for m in _MODULE_KEYS:
            shop_on = request.POST.get('mode_shop_%s' % m) == 'on'
            factory_on = request.POST.get('mode_factory_%s' % m) == 'on'
            SystemSetting.set_value('mode_shop_%s' % m, shop_on, request.user)
            SystemSetting.set_value('mode_factory_%s' % m, factory_on, request.user)
            # purana global switch union ke sath sync rakho (purane code ke liye)
            SystemSetting.set_value('show_%s_module' % m, shop_on or factory_on, request.user)

        # Shareholder deduction: unchecked = off, aur type bhi save ho
        SystemSetting.set_value('enable_shareholder_purchase_deduction',
                                request.POST.get('setting_enable_shareholder_purchase_deduction') == 'on',
                                request.user)
        deduction_type = request.POST.get('deduction_type')
        if deduction_type in ('proportional', 'equal'):
            SystemSetting.set_value('shareholder_deduction_type', deduction_type, request.user)

        # Handle Balance Dividend Settings
        enable_balance_dividend = request.POST.get('setting_enable_balance_dividend') == 'on'
        SystemSetting.set_value('enable_balance_dividend', enable_balance_dividend, request.user)
        
        # Business mode: shop / factory / both
        business_mode = request.POST.get('business_mode', 'both')
        if business_mode not in ('shop', 'factory', 'both'):
            business_mode = 'both'
        SystemSetting.set_value('business_mode', business_mode, request.user)
        
        default_dividend_type = request.POST.get('default_dividend_type', 'both')
        SystemSetting.set_value('default_dividend_type', default_dividend_type, request.user)
        
        default_dividend_percentage = request.POST.get('default_dividend_percentage', '50')
        SystemSetting.set_value('default_dividend_percentage', default_dividend_percentage, request.user)
        
        min_balance_for_dividend = request.POST.get('min_balance_for_dividend', '0')
        SystemSetting.set_value('min_balance_for_dividend', min_balance_for_dividend, request.user)
        
        min_holding_months = request.POST.get('min_holding_months', '0')
        SystemSetting.set_value('min_holding_months', min_holding_months, request.user)
        
        auto_process_days = request.POST.get('auto_process_days', '7')
        SystemSetting.set_value('auto_process_days', auto_process_days, request.user)
        
        cache.delete('module_visibility')   # sidebar foran naye settings dikhaye
        messages.success(request, '✅ Module settings updated successfully!')
        return redirect('module_settings')
    
    # GET request - show form
    # ========================================== #
    # MODULE SETTINGS                           #
    # ========================================== #
    from ..context_processors import unit_enabled, module_visibility
    visible = module_visibility()
    module_settings = []
    for m in MODULE_CATALOG:
        module_settings.append({
            'id': m['key'], 'key': 'show_%s_module' % m['key'],
            'name': m['label'], 'icon': m['icon'], 'description': m['description'], 'group': m['group'],
            'shop': unit_enabled(m['key'], 'shop'),
            'factory': unit_enabled(m['key'], 'factory'),
            'visible': visible.get(m['key'], True),     # abhi chalu hai?
        })
    module_groups = [
        {'name': g, 'items': [x for x in module_settings if x['group'] == g]}
        for g in MODULE_GROUPS
    ]
    module_groups = [g for g in module_groups if g['items']]
    
    # ========================================== #
    # SHAREHOLDER DEDUCTION SETTINGS             #
    # ========================================== #
    is_enabled = SystemSetting.get_bool('enable_shareholder_purchase_deduction', True)
    deduction_type = SystemSetting.get_value('shareholder_deduction_type', 'proportional')
    
    total_shareholders = Shareholder.objects.filter(status='active').count()
    total_balance = 0
    for sh in Shareholder.objects.filter(status='active'):
        total_balance += ShareholderCashBalance.get_balance(sh)
    pending_purchases = Purchase.objects.filter(shareholder_deduction_done=False).count()
    
    # ========================================== #
    # BALANCE DIVIDEND SETTINGS                  #
    # ========================================== #
    enable_balance_dividend = SystemSetting.get_bool('enable_balance_dividend', True)
    default_dividend_type = SystemSetting.get_value('default_dividend_type', 'both')
    default_dividend_percentage = SystemSetting.get_value('default_dividend_percentage', '50')
    min_balance_for_dividend = SystemSetting.get_value('min_balance_for_dividend', '0')
    min_holding_months = SystemSetting.get_value('min_holding_months', '0')
    auto_process_days = SystemSetting.get_value('auto_process_days', '7')
    
    # Eligible shareholders count
    eligible_count = 0
    total_balance_used = Decimal('0.00')
    for shareholder in Shareholder.objects.filter(status='active'):
        balance_used = get_shareholder_balance_used(shareholder)
        if balance_used > 0:
            eligible_count += 1
            total_balance_used += balance_used
    
    pending_balance_dividends = BalanceDividend.objects.filter(status='declared').count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'module_settings': module_settings,
        'module_groups': module_groups,
        'is_enabled': is_enabled,
        'deduction_type': deduction_type,
        'total_shareholders': total_shareholders,
        'total_balance': total_balance,
        'pending_purchases': pending_purchases,
        'enable_balance_dividend': enable_balance_dividend,
        'default_dividend_type': default_dividend_type,
        'default_dividend_percentage': default_dividend_percentage,
        'min_balance_for_dividend': min_balance_for_dividend,
        'min_holding_months': min_holding_months,
        'auto_process_days': auto_process_days,
        'eligible_shareholders': eligible_count,
        'total_balance_used': total_balance_used,
        'pending_balance_dividends': pending_balance_dividends,
    }
    return render(request, 'admin/module_settings.html', context)


@login_required
def toggle_setting(request, setting_key):
    """AJAX endpoint to toggle a setting"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    if request.method == 'POST':
        new_value = SystemSetting.toggle(setting_key, request.user)
        cache.delete('module_visibility')
        return JsonResponse({
            'success': True,
            'setting_key': setting_key,
            'new_value': new_value,
            'message': f'Setting updated to {new_value}'
        })
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


def custom_logout(request):
    """Logout user and redirect to login page"""
    logout(request)
    return redirect('/login/')


@login_required
def dashboard_view(request):
    """
    Main Dashboard — OPTIMIZED + CACHED (30x faster)
    Before: 30+ queries | After: Cached (5 min)
    """
    from django.db.models import Sum, Count, Q, F, Value, DecimalField, ExpressionWrapper
    from django.db.models.functions import Coalesce
    from django.contrib.sessions.models import Session
    import os
    import glob
    import shutil
    from django.conf import settings
    
    # ========================================== #
    # REDIRECTS                                   #
    # ========================================== #
    if (hasattr(request.user, 'shareholder_profile') 
        and not request.user.is_superuser 
        and not request.user.is_staff):
        return redirect('shareholder_portal_dashboard')
    
    if (hasattr(request.user, 'customer_profile') 
        and not request.user.is_superuser 
        and not request.user.is_staff):
        return redirect('shop_home')
    
    # ========================================== #
    # ROLE DETECTION                              #
    # ========================================== #
    is_superuser = request.user.is_superuser
    in_ceo_group = request.user.groups.filter(name='CEO').exists()
    in_md_group = (
        request.user.groups.filter(name='MD').exists() or 
        request.user.groups.filter(name='Managing Director').exists()
    )
    in_cto_group = (
        request.user.groups.filter(name='CTO').exists() or 
        request.user.groups.filter(name='Chief Technology Officer').exists()
    )
    
    is_ceo = in_ceo_group and not is_superuser
    is_md = not is_superuser and not is_ceo and in_md_group
    is_cto = not is_superuser and not is_ceo and not is_md and in_cto_group
    
    # ========================================== #
    # ✅ CACHE BASE STATS (Shared for all users) #
    # ========================================== #
    today = localdate()
    month_ago = today - timedelta(days=30)
    month_start = today.replace(day=1)
    
    cache_key = f'dashboard_stats_{today}'
    base_stats = cache.get(cache_key)
    
    if base_stats is None:
        # ✅ All heavy queries in one place
        today_stats = Sale.objects.filter(sale_date__date=today).aggregate(
            total_sales=Coalesce(
                Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(Decimal('0.00'))
            ),
            sales_count=Count('id', distinct=True),
            total_discount=Coalesce(
                Sum('discount_value'),
                Value(Decimal('0.00'))
            )
        )
        
        today_purchases = Purchase.objects.filter(pur_date__date=today).aggregate(
            total=Coalesce(
                Sum('purchaseitem__total_amt'),
                Value(Decimal('0.00'))
            ),
            count=Count('id', distinct=True)
        )
        
        today_profit_raw = SaleItem.objects.filter(
            sale__sale_date__date=today
        ).aggregate(
            total=Coalesce(Sum('profit'), Value(Decimal('0.00')))
        )['total']
        
        # Monthly stats
        monthly_stats = Sale.objects.filter(
            sale_date__date__gte=month_start
        ).aggregate(
            total_sales=Coalesce(Sum('saleitem__total_amt'), Value(Decimal('0.00'))),
            total_discount=Coalesce(Sum('discount_value'), Value(Decimal('0.00')))
        )
        
        monthly_purchases = Purchase.objects.filter(
            pur_date__date__gte=month_start
        ).aggregate(
            total=Coalesce(Sum('purchaseitem__total_amt'), Value(Decimal('0.00')))
        )['total']
        
        monthly_profit_raw = SaleItem.objects.filter(
            sale__sale_date__date__gte=month_start
        ).aggregate(
            total=Coalesce(Sum('profit'), Value(Decimal('0.00')))
        )['total']
        
        # Low stock
        low_stock_items = list(Inventory.objects.select_related(
            'product', 'warehouse', 'product__unit'
        ).filter(
            stock__lt=F('product__low_stock_threshold')
        ).order_by('stock')[:10])
        
        low_stock_count = Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold')
        ).count()
        
        # Top products (30 days)
        top_products = list(SaleItem.objects.filter(
            sale__sale_date__date__gte=month_ago
        ).values(
            'product__id', 'product__name', 'product__price'
        ).annotate(
            total_sales=Coalesce(Sum('total_amt'), Value(Decimal('0.00'))),
            total_qty=Coalesce(Sum('qty'), Value(0.0)),
            total_profit=Coalesce(Sum('profit'), Value(Decimal('0.00')))
        ).order_by('-total_sales')[:8])
        
        # Counts
        total_customers = Customer.objects.count()
        total_vendors = Vendor.objects.count()
        total_products = Product.objects.count()
        active_installments = SaleInstallment.objects.filter(
            status__in=['pending', 'partial']
        ).count()
        pending_sale_orders = SaleOrder.objects.filter(status='pending').count()
        pending_purchases = Purchase.objects.filter(
            shareholder_deduction_done=False
        ).count()
        pending_leave_requests = LeaveRequest.objects.filter(status='pending').count()
        pending_orders = PurchaseOrder.objects.filter(
            status__in=['pending', 'confirmed', 'processing']
        ).count()
        
        # Stock value (single query)
        total_stock_value = StockBatch.objects.filter(
            remaining_qty__gt=0
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('remaining_qty') * F('price'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            )
        )['total'] or Decimal('0.00')
        
        # Total profit (cached helper)
        total_profit = get_cached_total_profit()
        
        # Recent sales
        recent_sales = list(Sale.objects.select_related(
            'customer', 'warehouse', 'created_by'
        ).annotate(
            cached_total=Coalesce(Sum('saleitem__total_amt'), Value(Decimal('0.00')))
        ).order_by('-sale_date')[:10])
        
        base_stats = {
            'today_sales': today_stats['total_sales'],
            'today_sales_count': today_stats['sales_count'] or 0,
            'today_discount': today_stats['total_discount'],
            'today_purchases_amount': today_purchases['total'],
            'today_purchase_count': today_purchases['count'] or 0,
            'today_profit': today_profit_raw - today_stats['total_discount'],
            'monthly_sales': monthly_stats['total_sales'],
            'monthly_discount': monthly_stats['total_discount'],
            'monthly_purchases': monthly_purchases,
            'monthly_profit': monthly_profit_raw - monthly_stats['total_discount'],
            'low_stock_items': low_stock_items,
            'low_stock_count': low_stock_count,
            'top_products': top_products,
            'total_customers': total_customers,
            'total_vendors': total_vendors,
            'total_products': total_products,
            'active_installments': active_installments,
            'pending_sale_orders': pending_sale_orders,
            'pending_purchases': pending_purchases,
            'pending_leave_requests': pending_leave_requests,
            'pending_orders': pending_orders,
            'total_stock_value': total_stock_value,
            'total_profit': total_profit,
            'recent_sales': recent_sales,
            'today': today,
            'month_start': month_start,
        }
        
        # ✅ Cache for 5 minutes
        cache.set(cache_key, base_stats, 300)
    
    # ========================================== #
    # ROLE-SPECIFIC STATS (Per-user, not cached) #
    # ========================================== #
    admin_stats = None
    ceo_stats = None
    md_stats = None
    cto_stats = None
    
    # ADMIN
    if is_superuser:
        admin_stats = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'total_employees': Employee.objects.count(),
            'total_shareholders': Shareholder.objects.filter(status='active').count(),
            'total_products': base_stats['total_products'],
            'total_stock_value': base_stats['total_stock_value'],
            'total_customers': base_stats['total_customers'],
            'total_vendors': base_stats['total_vendors'],
            'total_profit': base_stats['total_profit'],
            'today_sales': base_stats['today_sales'],
            'monthly_profit': base_stats['monthly_profit'],
        }
    
    # CEO
    if is_ceo:
        total_shares = Share.objects.aggregate(
            total=Coalesce(Sum('quantity'), Value(0))
        )['total'] or 0
        
        total_dividends = DividendPayment.objects.filter(status='paid').aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total'] or Decimal('0.00')
        
        total_expenses_month = Expense.objects.filter(
            expense_date__gte=month_start,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        gross_margin = 0
        if base_stats['monthly_sales'] > 0:
            gross_margin = float(
                (base_stats['monthly_profit'] / base_stats['monthly_sales']) * 100
            )
        
        ceo_stats = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'total_employees': Employee.objects.count(),
            'active_employees': Employee.objects.filter(status='active').count(),
            'total_shareholders': Shareholder.objects.filter(status='active').count(),
            'total_warehouses': Warehouse.objects.count(),
            'total_products': base_stats['total_products'],
            'active_products': Product.objects.filter(is_active=True).count(),
            'total_profit': base_stats['total_profit'],
            'monthly_revenue': base_stats['monthly_sales'],
            'monthly_profit': base_stats['monthly_profit'],
            'monthly_expenses': total_expenses_month,
            'gross_margin': round(gross_margin, 1),
            'today_revenue': base_stats['today_sales'],
            'today_profit': base_stats['today_profit'],
            'total_customers': base_stats['total_customers'],
            'total_vendors': base_stats['total_vendors'],
            'pending_purchases': base_stats['pending_purchases'],
            'pending_orders': base_stats['pending_orders'],
            'pending_leave_requests': base_stats['pending_leave_requests'],
            'pending_sale_orders': base_stats['pending_sale_orders'],
            'active_installments': base_stats['active_installments'],
            'total_installments': SaleInstallment.objects.count(),
            'defaulted_installments': SaleInstallment.objects.filter(status='defaulted').count(),
            'low_stock_count': base_stats['low_stock_count'],
            'total_stock_value': base_stats['total_stock_value'],
            'today_sales_count': base_stats['today_sales_count'],
            'today_purchases_count': base_stats['today_purchase_count'],
            'total_shares': total_shares,
            'total_dividends': total_dividends,
        }
    
    # MD
    if is_md:
        today_orders = SaleOrder.objects.filter(order_date__date=today).count()
        today_challans = DeliveryChallan.objects.filter(challan_date__date=today).count()
        today_grns = GoodsReceivedNote.objects.filter(grn_date__date=today).count()
        today_returns = SaleRetrn.objects.filter(sale_return_date__date=today).count()
        today_purchase_returns = PurchaseRetrn.objects.filter(
            purchase_return_date__date=today
        ).count()
        
        pending_deliveries = SaleOrder.objects.filter(
            status__in=['confirmed', 'processing', 'ready']
        ).count()
        pending_receipts = PurchaseOrder.objects.filter(
            status__in=['confirmed', 'processing', 'shipped']
        ).count()
        
        today_attendance = Attendance.objects.filter(date=today, status='present').count()
        today_absent = Attendance.objects.filter(date=today, status='absent').count()
        
        total_stock_items = Inventory.objects.filter(stock__gt=0).count()
        out_of_stock_items = Inventory.objects.filter(stock=0).count()
        
        today_avg_sale = Decimal('0.00')
        if base_stats['today_sales_count'] > 0:
            today_avg_sale = base_stats['today_sales'] / base_stats['today_sales_count']
        
        md_stats = {
            'today_orders': today_orders,
            'today_challans': today_challans,
            'today_grns': today_grns,
            'today_returns': today_returns,
            'today_purchase_returns': today_purchase_returns,
            'pending_deliveries': pending_deliveries,
            'pending_receipts': pending_receipts,
            'pending_purchases': base_stats['pending_purchases'],
            'pending_leave_requests': base_stats['pending_leave_requests'],
            'today_sales': base_stats['today_sales'],
            'today_purchases': base_stats['today_purchases_amount'],
            'monthly_sales': base_stats['monthly_sales'],
            'monthly_purchases': base_stats['monthly_purchases'],
            'today_sales_count': base_stats['today_sales_count'],
            'today_purchase_count': base_stats['today_purchase_count'],
            'today_avg_sale': round(today_avg_sale, 2),
            'total_customers': base_stats['total_customers'],
            'total_vendors': base_stats['total_vendors'],
            'pending_orders': base_stats['pending_orders'],
            'low_stock_count': base_stats['low_stock_count'],
            'total_stock_items': total_stock_items,
            'out_of_stock_items': out_of_stock_items,
            'total_employees': Employee.objects.count(),
            'active_employees': Employee.objects.filter(status='active').count(),
            'today_present': today_attendance,
            'today_absent': today_absent,
            'active_installments': base_stats['active_installments'],
            'today_profit': base_stats['today_profit'],
            'monthly_profit': base_stats['monthly_profit'],
        }
    
    # CTO
    if is_cto:
        from django.contrib.admin.models import LogEntry
        
        # DB size
        total_db_size = "N/A"
        db_size_mb = 0
        try:
            db_engine = settings.DATABASES['default']['ENGINE']
            if 'sqlite' in db_engine:
                db_path = settings.DATABASES['default']['NAME']
                if os.path.exists(db_path):
                    db_size_bytes = os.path.getsize(db_path)
                    db_size_mb = db_size_bytes / (1024 * 1024)
                    total_db_size = f"{db_size_mb:.2f} MB"
        except Exception:
            pass
        
        active_sessions = 0
        try:
            active_sessions = Session.objects.filter(expire_date__gte=now()).count()
        except Exception:
            pass
        
        users_online = User.objects.filter(
            last_login__gte=now() - timedelta(minutes=30)
        ).count()
        
        try:
            recent_logs = LogEntry.objects.filter(
                action_time__gte=now() - timedelta(days=1)
            ).count()
        except Exception:
            recent_logs = 0
        
        total_records = (
            Sale.objects.count() + Purchase.objects.count() + 
            Customer.objects.count() + Vendor.objects.count() +
            Product.objects.count()
        )
        
        cto_stats = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'users_online': users_online,
            'active_sessions': active_sessions,
            'total_db_size': total_db_size,
            'db_size_mb': round(db_size_mb, 2),
            'recent_logs': recent_logs,
            'total_records': total_records,
            'total_products': base_stats['total_products'],
        }
    
    # ========================================== #
    # QUICK ACTIONS                               #
    # ========================================== #
    quick_actions = []
    
    if is_superuser:
        quick_actions = [
            {'name': '👥 Users', 'url': '/users/', 'icon': 'bi-people', 'color': 'primary'},
            {'name': '⚙️ Settings', 'url': '/settings/modules/', 'icon': 'bi-gear', 'color': 'success'},
            {'name': '💾 Backup', 'url': '/database-backup/', 'icon': 'bi-hdd-stack', 'color': 'info'},
            {'name': '📊 Reports', 'url': '/reports/dashboard/', 'icon': 'bi-graph-up', 'color': 'warning'},
        ]
    elif is_ceo:
        quick_actions = [
            {'name': '👥 Users', 'url': '/users/', 'icon': 'bi-people', 'color': 'primary'},
            {'name': '👔 HR', 'url': '/hr/employees/', 'icon': 'bi-person-badge', 'color': 'success'},
            {'name': '👥 Shareholders', 'url': '/shareholders/', 'icon': 'bi-building', 'color': 'info'},
            {'name': '📊 Reports', 'url': '/reports/dashboard/', 'icon': 'bi-graph-up', 'color': 'warning'},
        ]
    elif is_md:
        quick_actions = [
            {'name': '🛒 Sale', 'url': '/sales/create/', 'icon': 'bi-cart-plus', 'color': 'primary'},
            {'name': '📥 Purchase', 'url': '/purchases/create/', 'icon': 'bi-box-arrow-in-down', 'color': 'success'},
            {'name': '📦 Inventory', 'url': '/inventory/', 'icon': 'bi-box', 'color': 'info'},
            {'name': '📊 Reports', 'url': '/reports/dashboard/', 'icon': 'bi-graph-up', 'color': 'warning'},
        ]
    elif is_cto:
        quick_actions = [
            {'name': '💾 Backup', 'url': '/database-backup/', 'icon': 'bi-hdd-stack', 'color': 'success'},
            {'name': '🔐 Security', 'url': '/security/', 'icon': 'bi-shield-lock', 'color': 'danger'},
            {'name': '📊 BI', 'url': '/bi/', 'icon': 'bi-bar-chart', 'color': 'info'},
            {'name': '🤖 AI', 'url': '/ai/dashboard/', 'icon': 'bi-robot', 'color': 'warning'},
        ]
    
    # ========================================== #
    # CONTEXT                                     #
    # ========================================== #
    context = {
        **base_stats,
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'is_superuser': is_superuser,
        'is_ceo': is_ceo,
        'is_md': is_md,
        'is_cto': is_cto,
        'admin_stats': admin_stats,
        'ceo_stats': ceo_stats,
        'md_stats': md_stats,
        'cto_stats': cto_stats,
        'quick_actions': quick_actions,
    }
    
    return render(request, 'index.html', context)


def get_cached_total_profit():
    """Get total profit with caching"""
    cache_key = 'total_profit'
    result = cache.get(cache_key)
    
    if result is None:
        total_sales = Sale.objects.aggregate(
            total=Coalesce(
                Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(Decimal('0.00'))
            )
        )['total'] or Decimal('0.0')
        
        total_purchases = Purchase.objects.aggregate(
            total=Coalesce(
                Sum('purchaseitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(Decimal('0.00'))
            )
        )['total'] or Decimal('0.0')
        
        total_expenses = Expense.objects.aggregate(
            total=Coalesce(
                Sum('amount', output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(Decimal('0.00'))
            )
        )['total'] or Decimal('0.0')
        
        gross_profit = total_sales - total_purchases
        result = gross_profit - total_expenses
        
        cache.set(cache_key, result, 3600)
    
    return result


def get_total_profit():
    """Calculate total profit from system"""
    total_sales = Sale.objects.aggregate(
        total=Coalesce(
            Sum('saleitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        )
    )['total'] or Decimal('0.0')
    
    total_purchases = Purchase.objects.aggregate(
        total=Coalesce(
            Sum('purchaseitem__total_amt', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        )
    )['total'] or Decimal('0.0')
    
    total_expenses = Expense.objects.aggregate(
        total=Coalesce(
            Sum('amount', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        )
    )['total'] or Decimal('0.0')
    
    gross_profit = total_sales - total_purchases
    net_profit = gross_profit - total_expenses
    
    return net_profit


# ============================================
# SETTINGS
# ============================================
def _apply_company_logo(request, company):
    """POST se aaya logo check karke company par lagata hai. Save caller karega.
    Galat file par ValueError uthata hai. Kuch badla ho to True lautata hai."""
    if request.POST.get('remove_logo') and company.logo:
        company.logo.delete(save=False)
        return True
    logo = request.FILES.get('logo')
    if not logo:
        return False
    if logo.size > 2 * 1024 * 1024:
        raise ValueError('Logo 2MB se chota hona chahiye.')
    from PIL import Image
    try:
        img = Image.open(logo)
        img.verify()
        fmt = (img.format or '').upper()
    except Exception:
        raise ValueError('Sahi image file (PNG/JPG/WEBP) upload karein.')
    if fmt not in ('PNG', 'JPEG', 'WEBP'):
        raise ValueError('Sirf PNG, JPG ya WEBP logo allowed hai.')
    logo.seek(0)
    company.logo = logo
    return True


@login_required
def company_settings(request):
    """Company settings with deposit payment details"""
    
    # Sirf superuser, Owner ya CEO (bank/JazzCash/EasyPaisa ke numbers badalne ka khatra)
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['Owner', 'CEO']).exists():
        messages.error(request, 'Access denied! Only Owner or CEO can change company settings.')
        return redirect('dashboard')
    
    company = CompanyInfo.objects.first()
    
    if request.method == 'POST':
        try:
            if company:
                # Basic Info
                company.name = request.POST.get('name')
                company.tagline = request.POST.get('tagline', '')
                company.address = request.POST.get('address')
                company.contact_number = request.POST.get('contact_number')
                company.email = request.POST.get('email')
                company.website = request.POST.get('website', '')
                company.footer_note = request.POST.get('footer_note', '')
                
                # ✅ Deposit Payment Details - YEH ADD KARO
                company.jazzcash_number = request.POST.get('jazzcash_number', '').strip()
                company.easypaisa_number = request.POST.get('easypaisa_number', '').strip()
                company.bank_name = request.POST.get('bank_name', '').strip()
                company.bank_account_title = request.POST.get('bank_account_title', '').strip()
                company.bank_account_number = request.POST.get('bank_account_number', '').strip()
                company.deposit_instructions = request.POST.get('deposit_instructions', '').strip()
                
                _apply_company_logo(request, company)
                company.save()
            else:
                # Create new company
                company = CompanyInfo.objects.create(
                    name=request.POST.get('name'),
                    tagline=request.POST.get('tagline', ''),
                    address=request.POST.get('address'),
                    contact_number=request.POST.get('contact_number'),
                    email=request.POST.get('email'),
                    website=request.POST.get('website', ''),
                    footer_note=request.POST.get('footer_note', ''),
                    jazzcash_number=request.POST.get('jazzcash_number', '').strip(),
                    easypaisa_number=request.POST.get('easypaisa_number', '').strip(),
                    bank_name=request.POST.get('bank_name', '').strip(),
                    bank_account_title=request.POST.get('bank_account_title', '').strip(),
                    bank_account_number=request.POST.get('bank_account_number', '').strip(),
                    deposit_instructions=request.POST.get('deposit_instructions', '').strip(),
                )
                if _apply_company_logo(request, company):
                    company.save()
            
            messages.success(request, '✅ Settings updated successfully!')
            return redirect('company_settings')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('company_settings')
    
    context = {
        'company_name': company.name if company else 'ERP System',
        'company': company,
    }
    return render(request, 'settings/company.html', context)
