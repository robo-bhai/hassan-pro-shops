"""Frontend views: purchase/monthly_plans (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from django.views.decorators.http import require_POST
from ...models import *
import logging
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from django.urls import reverse
from ...models import CashBalance, Shareholder, CompanyInfo, Product
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
logger = logging.getLogger(__name__)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders', post='manage_purchase_orders')
def monthly_purchase_planner(request):
    """
    Monthly Purchase & Investor Planner with AUTO-CALCULATE Purchase Qty
    
    Formula: Purchase Qty = Expected Sales Qty - Available Stock
    """
    
    # ========================================== #
    # ✅ PERMISSION CHECK                        #
    # ========================================== #
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can access this page.')
        return redirect('dashboard')
    
    # ========================================== #
    # ✅ GET SELECTED MONTH                      #
    # ========================================== #
    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    
    try:
        selected_month = datetime.strptime(month_str + '-01', '%Y-%m-%d').date()
    except:
        selected_month = date.today().replace(day=1)
        month_str = selected_month.strftime('%Y-%m')
    
    # ========================================== #
    # ✅ GET PLANS FOR SELECTED MONTH            #
    # ========================================== #
    plans_this_month = MonthlyPurchasePlan.objects.filter(
        month=selected_month,
        batch__isnull=True          # multi-product plan lines are shown separately
    ).order_by('-version')
    
    latest_plan = plans_this_month.filter(is_latest=True).first()
    
    # ========================================== #
    # ✅ GET WAREHOUSES                          #
    # ========================================== #
    warehouses = Warehouse.objects.all()
    
    # ========================================== #
    # ✅ SAFE CONVERSION FUNCTIONS               #
    # ========================================== #
    def safe_decimal(value, default='0.00'):
        """Safely convert value to Decimal"""
        try:
            if not value or str(value).strip() == '':
                return Decimal(default)
            cleaned = str(value).replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '').strip()
            if cleaned == '':
                return Decimal(default)
            return Decimal(cleaned)
        except:
            return Decimal(default)
    
    def safe_int(value, default=0):
        """Safely convert value to Integer"""
        try:
            if not value or str(value).strip() == '':
                return default
            return int(float(str(value).replace(',', '').replace(' ', '').strip()))
        except:
            return default
    
    def safe_float(value, default=0.0):
        """Safely convert value to Float"""
        try:
            if not value or str(value).strip() == '':
                return default
            return float(value)
        except:
            return default
    
    # ========================================== #
    # ✅ POST REQUEST HANDLING                   #
    # ========================================== #
    if request.method == 'POST':
        try:
            # ========================================== #
            # GET FORM DATA                              #
            # ========================================== #
            product_id = request.POST.get('product') or None
            warehouse_id = request.POST.get('warehouse') or None
            purchase_price = safe_decimal(request.POST.get('purchase_price_per_unit', 0))
            expected_sales_quantity = safe_int(request.POST.get('expected_sales_quantity', 0))
            expected_sales_amount = safe_decimal(request.POST.get('expected_sales_amount', 0))
            notes = request.POST.get('notes', '')
            action = request.POST.get('action', 'save')
            
            # ========================================== #
            # VALIDATION                                 #
            # ========================================== #
            if not product_id:
                messages.error(request, '❌ Please select a product!')
                return redirect(f'/monthly-planner/?month={month_str}')
            
            if not warehouse_id:
                messages.error(request, '❌ Please select a warehouse!')
                return redirect(f'/monthly-planner/?month={month_str}')
            
            if expected_sales_quantity <= 0:
                messages.error(request, '❌ Expected Sales Quantity must be greater than zero!')
                return redirect(f'/monthly-planner/?month={month_str}')
            
            if purchase_price <= 0:
                messages.error(request, '❌ Purchase price must be greater than zero!')
                return redirect(f'/monthly-planner/?month={month_str}')
            
            # ========================================== #
            # ✅ GET INVENTORY DATA (CRITICAL)           #
            # ========================================== #
            current_stock = 0
            available_stock = 0
            reserved_stock = 0
            
            if product_id and warehouse_id:
                inventory = Inventory.objects.filter(
                    product_id=product_id,
                    warehouse_id=warehouse_id
                ).first()
                if inventory:
                    current_stock = safe_float(inventory.stock)
                    reserved_stock = safe_float(inventory.reserved_stock)
                    available_stock = current_stock - reserved_stock
            
            # ========================================== #
            # ✅ AUTO-CALCULATE PURCHASE QUANTITY        #
            # ========================================== #
            # FORMULA: Purchase Qty = Expected Sales - Available Stock
            purchase_quantity = expected_sales_quantity - available_stock
            
            # Cannot be negative
            if purchase_quantity < 0:
                purchase_quantity = 0
            
            # Round to nearest whole number
            purchase_quantity = int(round(purchase_quantity))
            
            # ✅ Log the auto-calculation
            logger.info(
                f"Auto-calculated Purchase Qty: "
                f"Sale({expected_sales_quantity}) - Stock({available_stock}) = {purchase_quantity}"
            )
            
            # ========================================== #
            # ✅ CALCULATE EXISTING INVESTMENT           #
            # ========================================== #
            existing_investment = Decimal('0.00')
            for sh in Shareholder.objects.filter(status='active'):
                balance = sh.get_balance()
                if balance:
                    existing_investment += Decimal(str(balance))
            
            current_investors = Shareholder.objects.filter(status='active').count()
            
            # ========================================== #
            # ✅ ACTION: CREATE NEW VERSION              #
            # ========================================== #
            if action == 'create_new':
                # Mark all existing as not latest
                plans_this_month.update(is_latest=False)
                
                # Get next version number
                last_plan = plans_this_month.first()
                new_version = (last_plan.version + 1) if last_plan else 1
                
                # Create new plan
                plan = MonthlyPurchasePlan.objects.create(
                    month=selected_month,
                    version=new_version,
                    is_latest=True,
                    previous_plan=latest_plan,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    purchase_quantity=purchase_quantity,
                    purchase_price_per_unit=purchase_price,
                    expected_sales_quantity=expected_sales_quantity,
                    expected_sales_amount=expected_sales_amount,
                    current_stock=current_stock,
                    reserved_stock=reserved_stock,
                    available_stock=available_stock,
                    existing_investment=existing_investment,
                    current_investors=current_investors,
                    notes=notes,
                    created_by=request.user,
                    status='draft'
                )
                
                # Create history
                MonthlyPlanHistory.objects.create(
                    plan=plan,
                    action='created',
                    performed_by=request.user,
                    notes=f'New version v{new_version} created. '
                          f'Auto Qty: {expected_sales_quantity} - {available_stock} = {purchase_quantity}'
                )
                
                messages.success(
                    request, 
                    f'✅ New Plan v{new_version} created for {selected_month.strftime("%B %Y")}!\n'
                    f'📦 Auto-calculated Purchase Qty: {purchase_quantity} units'
                )
                
            # ========================================== #
            # ✅ ACTION: SAVE / UPDATE EXISTING          #
            # ========================================== #
            else:
                if latest_plan:
                    # Update existing plan
                    old_version = latest_plan.version
                    
                    latest_plan.product_id = product_id
                    latest_plan.warehouse_id = warehouse_id
                    latest_plan.purchase_quantity = purchase_quantity  # ✅ Auto-calculated
                    latest_plan.purchase_price_per_unit = purchase_price
                    latest_plan.expected_sales_quantity = expected_sales_quantity
                    latest_plan.expected_sales_amount = expected_sales_amount
                    latest_plan.current_stock = current_stock
                    latest_plan.reserved_stock = reserved_stock
                    latest_plan.available_stock = available_stock
                    latest_plan.existing_investment = existing_investment
                    latest_plan.current_investors = current_investors
                    latest_plan.notes = notes
                    latest_plan.save()
                    
                    # Create history
                    MonthlyPlanHistory.objects.create(
                        plan=latest_plan,
                        action='updated',
                        performed_by=request.user,
                        notes=f'Plan v{old_version} updated. '
                              f'Auto Qty: {expected_sales_quantity} - {available_stock} = {purchase_quantity}'
                    )
                    
                    messages.success(
                        request, 
                        f'✅ Plan v{old_version} updated for {selected_month.strftime("%B %Y")}!\n'
                        f'📦 Auto-calculated Purchase Qty: {purchase_quantity} units'
                    )
                else:
                    # Create first plan
                    plan = MonthlyPurchasePlan.objects.create(
                        month=selected_month,
                        version=1,
                        is_latest=True,
                        product_id=product_id,
                        warehouse_id=warehouse_id,
                        purchase_quantity=purchase_quantity,  # ✅ Auto-calculated
                        purchase_price_per_unit=purchase_price,
                        expected_sales_quantity=expected_sales_quantity,
                        expected_sales_amount=expected_sales_amount,
                        current_stock=current_stock,
                        reserved_stock=reserved_stock,
                        available_stock=available_stock,
                        existing_investment=existing_investment,
                        current_investors=current_investors,
                        notes=notes,
                        created_by=request.user,
                        status='draft'
                    )
                    
                    # Create history
                    MonthlyPlanHistory.objects.create(
                        plan=plan,
                        action='created',
                        performed_by=request.user,
                        notes=f'First plan created. '
                              f'Auto Qty: {expected_sales_quantity} - {available_stock} = {purchase_quantity}'
                    )
                    
                    messages.success(
                        request, 
                        f'✅ Plan v1 created for {selected_month.strftime("%B %Y")}!\n'
                        f'📦 Auto-calculated Purchase Qty: {purchase_quantity} units'
                    )
            
            return redirect(f'/monthly-planner/?month={month_str}')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            import traceback
            traceback.print_exc()
            return redirect(f'/monthly-planner/?month={month_str}')
    
    # ========================================== #
    # ✅ GET REQUEST - SHOW PAGE                 #
    # ========================================== #
    
    # Get all plans for history
    all_plans = MonthlyPurchasePlan.objects.select_related('batch').order_by('-month', '-version')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        all_plans = all_plans.filter(status=status_filter)
    
    paginator = Paginator(all_plans, 12)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Get products
    products = Product.objects.filter(is_active=True)
    
    # Calculate stats
    total_balance = Decimal('0.00')
    for sh in Shareholder.objects.filter(status='active'):
        balance = sh.get_balance()
        if balance:
            total_balance += Decimal(str(balance))
    
    total_plans = MonthlyPurchasePlan.objects.count()
    completed_plans = MonthlyPurchasePlan.objects.filter(status='completed').count()
    pending_plans = MonthlyPurchasePlan.objects.filter(
        status__in=['draft', 'approved', 'in_progress']
    ).count()
    
    # Multi-product plans of the selected month, each with its grand totals
    multi_plans = list(MonthlyPlanBatch.objects.filter(month=selected_month).select_related('warehouse'))
    for _b in multi_plans:
        _b.totals = _b.get_totals()
    
    # ========================================== #
    # ✅ CONTEXT                                 #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'latest_plan': latest_plan,
        'multi_plans': multi_plans,
        'plans_this_month': plans_this_month,
        'selected_month': selected_month,
        'month_str': month_str,
        'plans': page_obj,
        'page_obj': page_obj,
        'products': products,
        'warehouses': warehouses,
        'today': date.today(),
        'total_balance': total_balance,
        'total_investors': Shareholder.objects.filter(status='active').count(),
        'available_cash': CashBalance.get_balance(),
        'total_plans': total_plans,
        'completed_plans': completed_plans,
        'pending_plans': pending_plans,
        'status_filter': status_filter,
        'status_choices': MonthlyPurchasePlan.STATUS_CHOICES,
    }
    return render(request, 'shareholders/monthly_purchase_planner.html', context)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def check_stock_for_plan(request):
    """AJAX: Check stock for a plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        required_qty = float(request.GET.get('required_qty', 0))
        
        if not product_id or not warehouse_id:
            return JsonResponse({'success': False, 'message': 'Product and Warehouse required!'})
        
        # Get inventory
        inventory = Inventory.objects.filter(
            product_id=product_id,
            warehouse_id=warehouse_id
        ).first()
        
        if inventory:
            current_stock = inventory.stock
            reserved_stock = inventory.reserved_stock
            available_stock = inventory.stock - inventory.reserved_stock
        else:
            current_stock = 0
            reserved_stock = 0
            available_stock = 0
        
        # Calculate requirements
        stock_to_purchase = max(0, required_qty - available_stock)
        stock_after_purchase = available_stock + stock_to_purchase
        
        # Determine status
        if available_stock <= 0:
            status = 'out_of_stock'
            status_text = '❌ Out of Stock'
            status_color = 'danger'
        elif available_stock < (required_qty * 0.25):
            status = 'critical'
            status_text = '🔴 Critical'
            status_color = 'danger'
        elif available_stock < required_qty:
            status = 'low'
            status_text = '⚠️ Low Stock'
            status_color = 'warning'
        else:
            status = 'sufficient'
            status_text = '✅ Sufficient'
            status_color = 'success'
        
        return JsonResponse({
            'success': True,
            'current_stock': current_stock,
            'reserved_stock': reserved_stock,
            'available_stock': available_stock,
            'required_qty': required_qty,
            'stock_to_purchase': stock_to_purchase,
            'stock_after_purchase': stock_after_purchase,
            'status': status,
            'status_text': status_text,
            'status_color': status_color,
            'message': f'Available: {available_stock:.2f} | Required: {required_qty:.2f} | Purchase: {stock_to_purchase:.2f}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================================ #
# PLAN -> PURCHASE ORDER (one click, vendor picked automatically)  #
# ============================================================ #

def _plan_auto_vendor(product):
    """
    Pick the vendor for a product automatically.
    1) the vendor of the latest Purchase of this product
    2) the vendor of the latest (not cancelled) Purchase Order of this product
    3) the only vendor, if the system has just one
    Returns (vendor, source_text). vendor is None when nothing can be picked.
    """
    if not product:
        return None, ''
    item = (PurchaseItem.objects.filter(product=product)
            .select_related('purchase__vendor')
            .order_by('-purchase__pur_date', '-id').first())
    if item and item.purchase and item.purchase.vendor_id:
        return item.purchase.vendor, 'last purchase'
    po_item = (PurchaseOrderItem.objects.filter(product=product)
               .exclude(order__status='cancelled')
               .select_related('order__vendor')
               .order_by('-order__order_date', '-id').first())
    if po_item:
        return po_item.order.vendor, 'last purchase order'
    if Vendor.objects.count() == 1:
        return Vendor.objects.first(), 'only vendor'
    return None, ''


def _plan_po_problem(plan):
    """Why a Purchase Order cannot be made from this plan line (None = it can be made)."""
    if plan.status not in ['approved', 'in_progress']:
        return 'The plan must be approved first.'
    if plan.purchase_order_id:
        return f'A Purchase Order already exists: {plan.purchase_order.order_no}.'
    if plan.stock_to_purchase <= 0:
        return 'Stock is sufficient. No purchase is needed.'
    return None


def _create_po_from_plans(plans, vendor, user, note):
    """Make ONE Purchase Order (status pending) with one item per plan line and link each line to it."""
    po = PurchaseOrder.objects.create(
        vendor=vendor,
        warehouse=plans[0].warehouse,
        order_date=now(),
        status='pending',
        notes=note,
        created_by=user,
    )
    for plan in plans:
        PurchaseOrderItem.objects.create(
            order=po,
            product=plan.product,
            qty=plan.stock_to_purchase,
            price=plan.purchase_price_per_unit,
        )
        plan.purchase_order = po
        plan.save()
        MonthlyPlanHistory.objects.create(
            plan=plan,
            action='updated',
            performed_by=user,
            notes=f'Purchase Order {po.order_no} created (vendor: {vendor.name})'
        )
    return po


@login_required
@perm_required('manage_purchase_orders')
def generate_purchase_order_from_plan(request, pk):
    """Review page: choose or change the vendor, then create the Purchase Order from a Monthly Plan."""

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')

    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)

    problem = _plan_po_problem(plan)
    if problem:
        messages.warning(request, f'⚠️ {problem}')
        return redirect('monthly_plan_detail', pk=pk)

    if request.method == 'POST':
        vendor_id = request.POST.get('vendor') or ''
        vendor = Vendor.objects.filter(pk=vendor_id).first() if vendor_id.isdigit() else None
        if not vendor:
            messages.error(request, '❌ Please select a vendor!')
            return redirect('generate_purchase_order_from_plan', pk=pk)
        try:
            with transaction.atomic():
                po = _create_po_from_plans(
                    [plan], vendor, request.user,
                    f"Auto-generated from Monthly Plan {plan.plan_no}"
                )
            messages.success(request, f'✅ Purchase Order {po.order_no} generated!')
            return redirect('purchase_order_detail', pk=po.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('monthly_plan_detail', pk=pk)

    # GET request - show form (vendor is already selected when we can find it)
    auto_vendor, auto_source = _plan_auto_vendor(plan.product)
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'vendors': Vendor.objects.all().order_by('name'),
        'auto_vendor': auto_vendor,
        'auto_source': auto_source,
    }
    return render(request, 'shareholders/generate_po_from_plan.html', context)


@login_required
@perm_required('manage_purchase_orders')
@require_POST
def generate_po_quick(request, pk):
    """One click: create the Purchase Order from a Monthly Plan with the vendor picked automatically."""

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')

    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)

    problem = _plan_po_problem(plan)
    if problem:
        messages.warning(request, f'⚠️ {problem}')
        return redirect('monthly_plan_detail', pk=pk)

    vendor, source = _plan_auto_vendor(plan.product)
    if not vendor:
        messages.warning(request, '⚠️ No vendor could be found for this product. Please choose a vendor.')
        return redirect('generate_purchase_order_from_plan', pk=pk)

    try:
        with transaction.atomic():
            po = _create_po_from_plans(
                [plan], vendor, request.user,
                f"Auto-generated from Monthly Plan {plan.plan_no}"
            )
    except Exception as e:
        logger.exception('Quick PO from plan failed')
        messages.error(request, f'❌ Error: {str(e)}')
        return redirect('monthly_plan_detail', pk=pk)

    messages.success(request, f'✅ Purchase Order {po.order_no} created for {vendor.name} ({source}).')
    return redirect('purchase_order_detail', pk=po.pk)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def monthly_plan_detail(request, pk):
    """View complete plan details with history"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    history = plan.history.all().order_by('-performed_at')
    investor_balance, available_cash = _mp_money_context()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'history': history,
        'budget': _mp_budget(plan.total_purchase_amount, investor_balance, available_cash),
    }
    if plan.status in ['approved', 'in_progress'] and not plan.purchase_order_id and plan.stock_to_purchase > 0:
        context['po_vendor'], context['po_vendor_source'] = _plan_auto_vendor(plan.product)
    return render(request, 'shareholders/monthly_plan_detail.html', context)


@login_required
@perm_required('approve_purchases')
def monthly_plan_approve(request, pk):
    """Approve monthly plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    
    if plan.status != 'draft':
        messages.warning(request, '⚠️ Only draft plans can be approved!')
        return redirect('monthly_plan_detail', pk=pk)
    
    plan.approve(request.user)
    
    # Create history
    MonthlyPlanHistory.objects.create(
        plan=plan,
        action='approved',
        performed_by=request.user,
        notes='Plan approved'
    )
    
    messages.success(request, f'✅ Plan #{plan.plan_no} approved!')
    return redirect('monthly_plan_detail', pk=pk)


@login_required
@perm_required('approve_purchases')
def monthly_plan_complete(request, pk):
    """Mark plan as completed with actual data"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    
    # ✅ Check if plan is already completed
    if plan.status == 'completed':
        messages.info(request, f'✅ Plan #{plan.plan_no} is already completed!')
        return redirect('monthly_plan_detail', pk=pk)
    
    # ✅ Check if plan is cancelled
    if plan.status == 'cancelled':
        messages.error(request, '❌ Cannot complete a cancelled plan!')
        return redirect('monthly_plan_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # ✅ SAFE DECIMAL CONVERSION
            def safe_decimal(value, default='0.00'):
                try:
                    if not value or str(value).strip() == '':
                        return Decimal(default)
                    cleaned = str(value).replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '').strip()
                    if cleaned == '':
                        return Decimal(default)
                    return Decimal(cleaned)
                except:
                    return Decimal(default)
            
            def safe_int(value, default=0):
                try:
                    if not value or str(value).strip() == '':
                        return default
                    return int(float(str(value).replace(',', '').replace(' ', '').strip()))
                except:
                    return default
            
            # Get actual data with safe conversion
            plan.actual_purchase_quantity = safe_int(request.POST.get('actual_purchase_quantity', 0))
            plan.actual_purchase_amount = safe_decimal(request.POST.get('actual_purchase_amount', 0))
            plan.actual_sales_quantity = safe_int(request.POST.get('actual_sales_quantity', 0))
            plan.actual_sales_amount = safe_decimal(request.POST.get('actual_sales_amount', 0))
            plan.actual_profit = safe_decimal(request.POST.get('actual_profit', 0))
            plan.achievements = request.POST.get('achievements', '')
            plan.challenges = request.POST.get('challenges', '')
            plan.lessons_learned = request.POST.get('lessons_learned', '')
            
            # Mark complete
            plan.complete(request.user)
            
            # Create history
            MonthlyPlanHistory.objects.create(
                plan=plan,
                action='completed',
                performed_by=request.user,
                notes=f'Achievement: {plan.achievement_percentage:.1f}%'
            )
            
            messages.success(
                request, 
                f'✅ Plan #{plan.plan_no} completed! Achievement: {plan.achievement_percentage:.1f}%'
            )
            
            # ✅ Redirect to detail page (NOT complete page)
            return redirect('monthly_plan_detail', pk=pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('monthly_plan_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
    }
    return render(request, 'shareholders/monthly_plan_complete.html', context)


@login_required
@perm_required('approve_purchases')
def monthly_plan_cancel(request, pk):
    """Cancel monthly plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        plan.status = 'cancelled'
        plan.notes = f"{plan.notes}\nCancelled: {reason}".strip()
        plan.save()
        
        # Create history
        MonthlyPlanHistory.objects.create(
            plan=plan,
            action='cancelled',
            performed_by=request.user,
            notes=f'Reason: {reason}'
        )
        
        messages.success(request, f'❌ Plan #{plan.plan_no} cancelled!')
        return redirect('monthly_purchase_planner')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
    }
    return render(request, 'shareholders/monthly_plan_cancel.html', context)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def monthly_plan_report_pdf(request):
    """Generate PDF report for all monthly plans"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    
    plans = MonthlyPurchasePlan.objects.all().order_by('-month')
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Monthly Purchase Plans Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Table
    data = [['Month', 'Plan No', 'Product', 'Planned Qty', 'Actual Qty', 'Planned Amount', 'Actual Amount', 'Achievement %', 'Status']]
    
    for plan in plans:
        data.append([
            plan.month.strftime('%b %Y'),
            plan.plan_no,
            plan.product_name or '-',
            str(plan.purchase_quantity),
            str(plan.actual_purchase_quantity),
            f"Rs. {plan.total_purchase_amount:,.0f}",
            f"Rs. {plan.actual_purchase_amount:,.0f}",
            f"{plan.achievement_percentage:.1f}%",
            plan.get_status_display()
        ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
    ]))
    
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Monthly_Plans_Report.pdf"'
    return response


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def investor_requirement_api(request):
    """AJAX: Calculate investor requirements based on purchase plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        purchase_quantity = int(request.GET.get('purchase_quantity', 0))
        purchase_price = Decimal(request.GET.get('purchase_price', 0))
        
        # Total purchase amount
        total_purchase = Decimal(str(purchase_quantity)) * purchase_price
        
        # Existing investment
        existing_investment = Decimal('0.00')
        for sh in Shareholder.objects.filter(status='active'):
            existing_investment += sh.get_balance()
        
        current_investors = Shareholder.objects.filter(status='active').count()
        
        # Additional needed
        additional_needed = max(Decimal('0.00'), total_purchase - existing_investment)
        
        # Required investors (average Rs. 10,000)
        avg_investment = Decimal('10000')
        required_investors = int(total_purchase / avg_investment) if avg_investment > 0 else 0
        additional_investors = max(0, required_investors - current_investors)
        
        return JsonResponse({
            'success': True,
            'total_purchase': float(total_purchase),
            'existing_investment': float(existing_investment),
            'additional_needed': float(additional_needed),
            'current_investors': current_investors,
            'required_investors': required_investors,
            'additional_investors': additional_investors,
            'message': f'You need {additional_investors} more investors or Rs. {additional_needed:,.2f} more investment'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@perm_required('manage_purchase_orders')
def monthly_plan_edit(request, pk):
    """Edit Monthly Purchase Plan with Inventory"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    
    # ✅ Restrictions
    if plan.status == 'completed':
        messages.error(request, '❌ Cannot edit a completed plan!')
        return redirect('monthly_plan_detail', pk=pk)
    
    if plan.status == 'cancelled':
        messages.error(request, '❌ Cannot edit a cancelled plan!')
        return redirect('monthly_plan_detail', pk=pk)
    
    if not plan.is_latest:
        messages.error(request, '❌ Cannot edit an old version!')
        return redirect('monthly_plan_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # Safe conversion functions
            def safe_decimal(value, default='0.00'):
                try:
                    if not value or str(value).strip() == '':
                        return Decimal(default)
                    cleaned = str(value).replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '').strip()
                    if cleaned == '':
                        return Decimal(default)
                    return Decimal(cleaned)
                except:
                    return Decimal(default)
            
            def safe_int(value, default=0):
                try:
                    if not value or str(value).strip() == '':
                        return default
                    return int(float(str(value).replace(',', '').replace(' ', '').strip()))
                except:
                    return default
            
            # Get form data
            product_id = request.POST.get('product') or None
            warehouse_id = request.POST.get('warehouse') or None
            purchase_quantity = safe_int(request.POST.get('purchase_quantity', 0))
            purchase_price = safe_decimal(request.POST.get('purchase_price_per_unit', 0))
            expected_sales_quantity = safe_int(request.POST.get('expected_sales_quantity', 0))
            expected_sales_amount = safe_decimal(request.POST.get('expected_sales_amount', 0))
            notes = request.POST.get('notes', '')
            
            # Validation
            if not product_id or not warehouse_id:
                messages.error(request, '❌ Product and Warehouse required!')
                return redirect('monthly_plan_edit', pk=pk)
            
            # Get inventory data
            current_stock = 0
            available_stock = 0
            reserved_stock = 0
            
            if product_id and warehouse_id:
                inventory = Inventory.objects.filter(
                    product_id=product_id,
                    warehouse_id=warehouse_id
                ).first()
                if inventory:
                    current_stock = inventory.stock
                    reserved_stock = inventory.reserved_stock
                    available_stock = inventory.stock - inventory.reserved_stock
            
            # Update plan
            plan.product_id = product_id
            plan.warehouse_id = warehouse_id
            plan.purchase_quantity = purchase_quantity
            plan.purchase_price_per_unit = purchase_price
            plan.expected_sales_quantity = expected_sales_quantity
            plan.expected_sales_amount = expected_sales_amount
            plan.current_stock = current_stock
            plan.reserved_stock = reserved_stock
            plan.available_stock = available_stock
            plan.notes = notes
            plan.save()
            
            messages.success(request, f'✅ Plan updated!')
            return redirect('monthly_plan_detail', pk=pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('monthly_plan_edit', pk=pk)
    
    # GET request
    products = Product.objects.filter(is_active=True)
    warehouses = Warehouse.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'products': products,
        'warehouses': warehouses,
    }
    return render(request, 'shareholders/monthly_plan_edit.html', context)


@login_required
@perm_required('manage_purchase_orders')
def monthly_plan_delete(request, pk):
    """
    Delete Monthly Purchase Plan with Complete Restrictions
    """
    
    # ========================================== #
    # ✅ RESTRICTION 1: SUPERUSER ONLY          #
    # ========================================== #
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can delete plans.')
        return redirect('monthly_plan_detail', pk=pk)
    
    plan = get_object_or_404(MonthlyPurchasePlan, pk=pk)
    
    # ========================================== #
    # ✅ RESTRICTION 2: STATUS CHECK            #
    # ========================================== #
    if plan.status == 'completed':
        messages.error(request, '❌ Cannot delete a completed plan!')
        return redirect('monthly_plan_detail', pk=pk)
    
    if plan.status == 'approved':
        messages.error(request, '❌ Cannot delete an approved plan! Cancel it first.')
        return redirect('monthly_plan_detail', pk=pk)
    
    if plan.status == 'in_progress':
        messages.error(request, '❌ Cannot delete a plan in progress! Cancel it first.')
        return redirect('monthly_plan_detail', pk=pk)
    
    # ========================================== #
    # ✅ RESTRICTION 3: TRANSACTION CHECK       #
    # ========================================== #
    # If a purchase/sale is linked, do not delete
    # Example:
    # if plan.actual_purchase_quantity > 0 or plan.actual_sales_quantity > 0:
    #     messages.error(request, '❌ Cannot delete! Actual transactions exist for this plan.')
    #     return redirect('monthly_plan_detail', pk=pk)
    
    # ========================================== #
    # ✅ RESTRICTION 4: TIME LIMIT CHECK        #
    # ========================================== #
    from django.utils.timezone import now
    days_since_creation = (now().date() - plan.created_at.date()).days
    
    if days_since_creation > 30:
        messages.error(request, f'❌ Cannot delete! Plan is older than 30 days ({days_since_creation} days).')
        return redirect('monthly_plan_detail', pk=pk)
    
    # ========================================== #
    # DELETE CONFIRMATION                       #
    # ========================================== #
    if request.method == 'POST':
        plan_no = plan.plan_no
        month = plan.month
        
        # If this was the latest plan, mark previous as latest
        if plan.is_latest:
            previous = MonthlyPurchasePlan.objects.filter(
                month=month, batch=plan.batch
            ).exclude(pk=pk).order_by('-version').first()
            if previous:
                previous.is_latest = True
                previous.save()
        
        # Create history before delete
        MonthlyPlanHistory.objects.create(
            plan=plan,
            action='cancelled',
            performed_by=request.user,
            notes=f'Plan deleted by {request.user.username}'
        )
        
        plan.delete()
        messages.success(request, f'🗑️ Plan #{plan_no} deleted successfully!')
        return redirect('monthly_purchase_planner')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'days_since_creation': days_since_creation,
    }
    return render(request, 'shareholders/monthly_plan_delete.html', context)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def monthly_plan_history(request):
    """All Monthly Plans History"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get all plans
    plans = MonthlyPurchasePlan.objects.select_related('batch').order_by('-month', '-version')
    
    # Filters
    selected_month = request.GET.get('month', '')
    if selected_month:
        try:
            month_date = datetime.strptime(selected_month + '-01', '%Y-%m-%d').date()
            plans = plans.filter(month=month_date)
        except:
            pass
    
    selected_status = request.GET.get('status', '')
    if selected_status:
        plans = plans.filter(status=selected_status)
    
    search = request.GET.get('search', '')
    if search:
        plans = plans.filter(
            Q(plan_no__icontains=search) |
            Q(product_name__icontains=search)
        )
    
    # Stats
    total_plans = MonthlyPurchasePlan.objects.count()
    completed_count = MonthlyPurchasePlan.objects.filter(status='completed').count()
    approved_count = MonthlyPurchasePlan.objects.filter(status='approved').count()
    draft_count = MonthlyPurchasePlan.objects.filter(status='draft').count()
    in_progress_count = MonthlyPurchasePlan.objects.filter(status='in_progress').count()
    
    # Pagination
    paginator = Paginator(plans, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'plans': page_obj,
        'total_plans': total_plans,
        'completed_count': completed_count,
        'approved_count': approved_count,
        'draft_count': draft_count,
        'in_progress_count': in_progress_count,
        'selected_month': selected_month,
        'selected_status': selected_status,
        'search': search,
    }
    return render(request, 'shareholders/monthly_plan_history.html', context)


# ============================================================ #
# MULTI-PRODUCT MONTHLY PLAN                                   #
# One plan for a month with many products and one grand total. #
# Every line is a normal MonthlyPurchasePlan (linked by batch). #
# ============================================================ #

def _mp_safe_decimal(value, default='0'):
    try:
        cleaned = str(value if value is not None else '').replace(',', '').replace(' ', '').replace('Rs.', '').strip()
        return Decimal(cleaned) if cleaned else Decimal(default)
    except Exception:
        return Decimal(default)


def _mp_safe_int(value, default=0):
    try:
        cleaned = str(value if value is not None else '').replace(',', '').replace(' ', '').strip()
        return int(float(cleaned)) if cleaned else default
    except Exception:
        return default


def _mp_money_context():
    """Investor balance + available cash (used to compare with the grand total)."""
    investor_balance = Decimal('0.00')
    for sh in Shareholder.objects.filter(status='active'):
        bal = sh.get_balance()
        if bal:
            investor_balance += Decimal(str(bal))
    return investor_balance, CashBalance.get_balance()


def _mp_budget(plan_amount, investor_balance, available_cash):
    """
    Budget vs Plan: compare a plan amount with the investor balance and the available cash.

    Budget limit = investor balance + available cash.
      level 'ok'   : plan is inside the investor balance
      level 'warn' : plan is above the investor balance (available cash will be needed)
      level 'over' : plan is above the limit  -> red warning
    (The same rules are repeated in budgetUpdate() in monthly_plan_multi_form.html.)
    """
    def D(v):
        try:
            return max(Decimal('0'), Decimal(str(v or 0)))
        except Exception:
            return Decimal('0')

    plan, inv, cash = D(plan_amount), D(investor_balance), D(available_cash)
    limit = inv + cash

    if plan <= 0:
        level = 'empty'
    elif plan <= inv:
        level = 'ok'
    elif plan <= limit:
        level = 'warn'
    else:
        level = 'over'

    def pct(a, b, cap=None):
        if b > 0:
            v = float(a / b * 100)
        else:
            v = 100.0 if a > 0 else 0.0
        return min(v, cap) if cap else v

    fill_pct = 0.0 if plan <= 0 else pct(plan, limit, 100)
    marker_pct = pct(inv, limit, 100) if limit > 0 else 0.0
    inv_pct, cash_pct = pct(plan, inv), pct(plan, cash)

    over_by = plan - limit if plan > limit else Decimal('0')
    above_inv = plan - inv if plan > inv else Decimal('0')
    left = limit - plan if plan <= limit else Decimal('0')

    def rs(v):
        return f'Rs. {v:,.0f}'

    if level == 'empty':
        badge, message = 'No plan yet', 'Add products to see how the plan compares with your budget.'
    elif level == 'ok':
        badge = 'Within budget'
        message = f'The plan is inside the investor balance. {rs(inv - plan)} of investor balance will be left.'
    elif level == 'warn':
        badge = 'Uses cash'
        message = (f'The plan is {rs(above_inv)} more than the investor balance. '
                   f'Available cash will be needed for the rest.')
    else:
        badge = 'OVER BUDGET'
        message = (f'OVER BUDGET by {rs(over_by)}! The plan is more than the investor balance '
                   f'and available cash together.')

    return {
        'plan': plan, 'investor': inv, 'cash': cash, 'limit': limit,
        'level': level, 'badge': badge, 'message': message,
        'fill_pct': fill_pct, 'marker_pct': marker_pct,
        'inv_pct': inv_pct, 'cash_pct': cash_pct,
        'inv_width': min(inv_pct, 100.0), 'cash_width': min(cash_pct, 100.0),
        'over_by': over_by, 'above_investor': above_inv,
        'left_label': 'Over by' if level == 'over' else 'Left in budget',
        'left_value': over_by if level == 'over' else left,
    }


@login_required
@perm_required('manage_purchase_orders')
def monthly_plan_multi_create(request):
    """Create a multi-product plan: many products in one monthly plan, with a grand total."""

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can access this page.')
        return redirect('dashboard')

    month_str = request.GET.get('month') or request.POST.get('month') or date.today().strftime('%Y-%m')
    try:
        selected_month = datetime.strptime(month_str[:7] + '-01', '%Y-%m-%d').date()
    except ValueError:
        selected_month = date.today().replace(day=1)
    month_str = selected_month.strftime('%Y-%m')

    warehouses = Warehouse.objects.all().order_by('name')
    posted_rows = []
    posted = {'warehouse': '', 'title': '', 'notes': ''}

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse') or ''
        title = (request.POST.get('title') or '').strip()[:200]
        notes = (request.POST.get('notes') or '').strip()
        posted = {'warehouse': warehouse_id, 'title': title, 'notes': notes}

        product_ids = request.POST.getlist('product')
        sale_qtys = request.POST.getlist('sale_qty')
        unit_prices = request.POST.getlist('unit_price')
        sell_prices = request.POST.getlist('sell_price')

        errors = []
        lines = []
        seen = set()
        warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id.isdigit() else None
        if not warehouse:
            errors.append('Please select a warehouse!')

        for i, pid in enumerate(product_ids):
            sale_raw = sale_qtys[i] if i < len(sale_qtys) else ''
            price_raw = unit_prices[i] if i < len(unit_prices) else ''
            sell_raw = sell_prices[i] if i < len(sell_prices) else ''
            posted_rows.append({'product': pid, 'sale_qty': sale_raw, 'unit_price': price_raw, 'sell_price': sell_raw})
            if not pid:
                continue                      # empty row, ignore
            row_no = i + 1
            if not pid.isdigit():
                errors.append(f'Row {row_no}: invalid product.')
                continue
            if pid in seen:
                errors.append(f'Row {row_no}: the same product is added twice.')
                continue
            seen.add(pid)
            qty = _mp_safe_int(sale_raw)
            price = _mp_safe_decimal(price_raw)
            sell = _mp_safe_decimal(sell_raw)
            if qty <= 0:
                errors.append(f'Row {row_no}: Sale Qty must be greater than zero.')
            if price <= 0:
                errors.append(f'Row {row_no}: Unit price must be greater than zero.')
            if sell < 0:
                errors.append(f'Row {row_no}: Selling price cannot be negative.')
            lines.append((pid, qty, price, sell))

        if not lines:
            errors.append('Add at least one product.')

        products_by_id = {str(pr.pk): pr for pr in Product.objects.filter(pk__in=[l[0] for l in lines])}
        for pid, qty, price, sell in lines:
            if pid not in products_by_id:
                errors.append('One of the selected products was not found.')
                break

        if not errors:
            try:
                with transaction.atomic():
                    batch = MonthlyPlanBatch.objects.create(
                        month=selected_month,
                        warehouse=warehouse,
                        title=title,
                        notes=notes,
                        created_by=request.user,
                    )
                    stock_map = {
                        str(inv.product_id): inv
                        for inv in Inventory.objects.filter(warehouse=warehouse, product_id__in=[l[0] for l in lines])
                    }
                    investors = Shareholder.objects.filter(status='active').count()
                    for pid, qty, price, sell in lines:
                        inv = stock_map.get(pid)
                        current = float(inv.stock) if inv else 0.0
                        reserved = float(inv.reserved_stock) if inv else 0.0
                        available = current - reserved
                        # Purchase Qty = Sale Qty - Available Stock (never below zero)
                        buy_qty = max(0, int(round(qty - available)))
                        plan = MonthlyPurchasePlan.objects.create(
                            month=selected_month,
                            version=1,
                            is_latest=True,
                            batch=batch,
                            product_id=pid,
                            warehouse=warehouse,
                            purchase_quantity=buy_qty,
                            purchase_price_per_unit=price,
                            expected_sales_quantity=qty,
                            expected_sales_amount=Decimal(qty) * sell,
                            current_stock=current,
                            reserved_stock=reserved,
                            available_stock=available,
                            existing_investment=Decimal('0.00'),   # funding is checked on the grand total
                            current_investors=investors,
                            notes=notes,
                            created_by=request.user,
                            status='draft',
                        )
                        MonthlyPlanHistory.objects.create(
                            plan=plan,
                            action='created',
                            performed_by=request.user,
                            notes=f'Created in multi-product plan {batch.batch_no}. '
                                  f'Auto Qty: {qty} - {available:g} = {buy_qty}'
                        )
                totals = batch.get_totals()
                messages.success(
                    request,
                    f'✅ Multi-product plan {batch.batch_no} created for {selected_month.strftime("%B %Y")}: '
                    f'{totals["products"]} products, grand total Rs. {totals["purchase_amount"]:,.2f}'
                )
                _inv, _cash = _mp_money_context()
                _b = _mp_budget(totals['purchase_amount'], _inv, _cash)
                if _b['level'] == 'over':
                    messages.warning(request, f'⚠️ {_b["message"]}')
                return redirect('monthly_plan_multi_detail', pk=batch.pk)
            except Exception as e:
                logger.exception('Multi-product plan create failed')
                errors.append(f'Could not save the plan: {e}')

        for err in errors:
            messages.error(request, f'❌ {err}')

    investor_balance, available_cash = _mp_money_context()
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': _mp_budget(0, investor_balance, available_cash),
        'selected_month': selected_month,
        'month_str': month_str,
        'warehouses': warehouses,
        'products': list(Product.objects.filter(is_active=True).order_by('name').values('id', 'name')),
        'posted': posted,
        'posted_rows': posted_rows,
        'investor_balance': investor_balance,
        'available_cash': available_cash,
    }
    return render(request, 'shareholders/monthly_plan_multi_form.html', context)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def monthly_plan_multi_product_info(request):
    """AJAX: stock, cost price and selling price of one product (used by the multi-product form)."""

    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})

    product_id = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    product = Product.objects.filter(pk=product_id).first() if (product_id or '').isdigit() else None
    if not product:
        return JsonResponse({'success': False, 'message': 'Product not found.'})

    available = 0.0
    if warehouse_id:
        inv = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first() if warehouse_id.isdigit() else None
        if inv:
            available = float(inv.stock) - float(inv.reserved_stock)

    cost = float(product.price or 0)
    last_batch = StockBatch.objects.filter(product=product).order_by('-id').first()
    if cost <= 0 and last_batch:
        cost = float(last_batch.price)
    sell_batch = StockBatch.objects.filter(product=product, selling_price__gt=0).order_by('-id').first()
    selling = float(sell_batch.selling_price) if sell_batch else 0.0

    return JsonResponse({
        'success': True,
        'available_stock': available,
        'cost_price': cost,
        'selling_price': selling,
    })


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def monthly_plan_multi_detail(request, pk):
    """One multi-product plan: all its products and the grand total at the bottom."""

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')

    batch = get_object_or_404(MonthlyPlanBatch.objects.select_related('warehouse', 'created_by'), pk=pk)
    lines = list(batch.lines.select_related('product', 'warehouse', 'purchase_order').order_by('id'))
    totals = batch.get_totals()
    investor_balance, available_cash = _mp_money_context()

    po_ready = po_no_vendor = 0
    for l in lines:
        l.po_vendor, l.po_source = None, ''
        if l.purchase_order_id or _plan_po_problem(l):
            continue                                  # already has a PO / not ready / no purchase needed
        l.po_vendor, l.po_source = _plan_auto_vendor(l.product)
        if l.po_vendor:
            po_ready += 1
        else:
            po_no_vendor += 1

    grand = totals['purchase_amount']
    context = {
        'po_ready': po_ready,
        'po_no_vendor': po_no_vendor,
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'batch': batch,
        'lines': lines,
        'totals': totals,
        'expected_gap': totals['sales_amount'] - grand,
        'investor_balance': investor_balance,
        'available_cash': available_cash,
        'budget': _mp_budget(grand, investor_balance, available_cash),
        'funding_gap': max(Decimal('0.00'), grand - investor_balance),
        'draft_count': sum(1 for l in lines if l.status == 'draft'),
        'can_delete': request.user.is_superuser and all(l.status == 'draft' and not l.purchase_order_id for l in lines),
    }
    return render(request, 'shareholders/monthly_plan_multi_detail.html', context)


@login_required
@perm_required('approve_purchases')
@require_POST
def monthly_plan_multi_approve(request, pk):
    """Approve every draft line of a multi-product plan in one click."""

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')

    batch = get_object_or_404(MonthlyPlanBatch, pk=pk)
    count = 0
    with transaction.atomic():
        for plan in batch.lines.filter(status='draft'):
            plan.approve(request.user)
            MonthlyPlanHistory.objects.create(
                plan=plan,
                action='approved',
                performed_by=request.user,
                notes=f'Approved with multi-product plan {batch.batch_no}'
            )
            count += 1

    if count:
        messages.success(request, f'✅ {count} product line(s) of {batch.batch_no} approved!')
        _inv, _cash = _mp_money_context()
        _b = _mp_budget(batch.get_totals()['purchase_amount'], _inv, _cash)
        if _b['level'] == 'over':
            messages.warning(request, f'⚠️ {_b["message"]}')
    else:
        messages.warning(request, '⚠️ There are no draft lines to approve.')
    return redirect('monthly_plan_multi_detail', pk=pk)


@login_required
@perm_required('manage_purchase_orders')
@require_POST
def monthly_plan_multi_delete(request, pk):
    """Delete a multi-product plan (superuser only, and only while every line is still a draft)."""

    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can delete plans.')
        return redirect('monthly_plan_multi_detail', pk=pk)

    batch = get_object_or_404(MonthlyPlanBatch, pk=pk)
    lines = list(batch.lines.all())
    if any(l.status != 'draft' or l.purchase_order_id for l in lines):
        messages.error(request, '❌ Cannot delete! Some lines are already approved or have a Purchase Order.')
        return redirect('monthly_plan_multi_detail', pk=pk)

    batch_no = batch.batch_no
    month = batch.month.strftime('%Y-%m')
    with transaction.atomic():
        batch.delete()            # its draft lines (and their history) are deleted with it
    messages.success(request, f'🗑️ Multi-product plan {batch_no} deleted.')
    return redirect(f"{reverse('monthly_purchase_planner')}?month={month}")


@login_required
@perm_required('manage_purchase_orders')
@require_POST
def monthly_plan_multi_generate_po(request, pk):
    """
    One click: Purchase Orders for a multi-product plan.
    Ready lines are grouped by their auto-picked vendor, so each vendor gets ONE Purchase Order
    with all of its products.
    """

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')

    batch = get_object_or_404(MonthlyPlanBatch, pk=pk)

    groups = {}                 # (vendor_id, warehouse_id) -> {'vendor':..., 'lines': [...]}
    no_vendor, not_ready = [], 0
    for plan in batch.lines.select_related('product', 'warehouse', 'purchase_order').order_by('id'):
        if plan.purchase_order_id or _plan_po_problem(plan):
            not_ready += 1
            continue
        vendor, _src = _plan_auto_vendor(plan.product)
        if not vendor:
            no_vendor.append(plan.product_name or str(plan.product))
            continue
        groups.setdefault((vendor.pk, plan.warehouse_id), {'vendor': vendor, 'lines': []})['lines'].append(plan)

    if not groups:
        if no_vendor:
            messages.warning(request, '⚠️ No vendor found for: ' + ', '.join(no_vendor) +
                             '. Open each product line and choose a vendor.')
        else:
            messages.info(request, 'ℹ️ There is nothing to order. Lines must be approved, without a PO, and need stock.')
        return redirect('monthly_plan_multi_detail', pk=pk)

    made = []
    try:
        with transaction.atomic():
            for g in groups.values():
                po = _create_po_from_plans(
                    g['lines'], g['vendor'], request.user,
                    f"Auto-generated from multi-product plan {batch.batch_no}"
                )
                made.append(f'{po.order_no} ({g["vendor"].name}, {len(g["lines"])} item(s))')
    except Exception as e:
        logger.exception('Multi-product PO generation failed')
        messages.error(request, f'❌ Error: {str(e)}. No Purchase Order was created.')
        return redirect('monthly_plan_multi_detail', pk=pk)

    messages.success(request, f'✅ {len(made)} Purchase Order(s) created: ' + '; '.join(made))
    if no_vendor:
        messages.warning(request, '⚠️ No vendor found for: ' + ', '.join(no_vendor) +
                         '. Open each of these lines and choose a vendor.')
    return redirect('monthly_plan_multi_detail', pk=pk)
