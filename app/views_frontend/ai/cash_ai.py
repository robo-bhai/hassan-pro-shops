"""Frontend views: ai/cash_ai (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ...models import CashBalance, CompanyInfo, Expense
from ...ai.ai_cash_engine import AICashEngine


@login_required
@perm_required('use_ai', 'view_cash')
def ai_cash_dashboard(request):
    """AI Cash Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AICashAnalysis, AICashAlert, AICashHealthHistory
    
    # Run AI analysis if requested
    if request.GET.get('run') == 'true':
        try:
            engine = AICashEngine()
            results = engine.run_full_analysis()
            
            messages.success(
                request,
                f"🤖 AI Cash Analysis Complete! "
                f"Health Score: {results['health']['score']}/100 | "
                f"{results['alerts_created']} alerts created"
            )
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_cash_dashboard')
    
    # Get latest analysis
    latest_analysis = AICashAnalysis.objects.order_by('-created_at').first()
    
    # ==========================================
    # ✅ FIX: First get base queryset, then filter, THEN slice
    # ==========================================
    base_alerts = AICashAlert.objects.filter(is_resolved=False)
    
    # ✅ Stats from FULL queryset (before slicing)
    total_alerts = base_alerts.count()
    critical_alerts = base_alerts.filter(severity='critical').count()
    warning_alerts = base_alerts.filter(severity='warning').count()
    high_alerts = base_alerts.filter(severity='high').count()
    info_alerts = base_alerts.filter(severity='info').count()
    
    # ✅ Now slice for display (last 10)
    alerts = base_alerts.order_by('-created_at')[:10]
    
    # Health history (last 30 days)
    health_history = AICashHealthHistory.objects.order_by('-date')[:30]
    
    # Prepare chart data
    chart_labels = []
    chart_scores = []
    chart_balances = []
    
    for h in reversed(list(health_history)):
        chart_labels.append(h.date.strftime('%d-%b'))
        chart_scores.append(h.health_score)
        chart_balances.append(float(h.balance))
    
    import json
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'analysis': latest_analysis,
        'alerts': alerts,              # ✅ Sliced for display
        'total_alerts': total_alerts,  # ✅ From full queryset
        'critical_alerts': critical_alerts,
        'warning_alerts': warning_alerts,
        'high_alerts': high_alerts,
        'info_alerts': info_alerts,
        'chart_labels': json.dumps(chart_labels),
        'chart_scores': json.dumps(chart_scores),
        'chart_balances': json.dumps(chart_balances),
        'current_balance': CashBalance.get_balance(),
        'today': localdate(),
    }
    return render(request, 'ai/cash_dashboard.html', context)


@login_required
@perm_required('use_ai', 'view_cash')
def ai_cash_forecast(request):
    """Detailed Cash Forecast"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AICashAnalysis
    import json
    
    # Get latest or run new
    analysis = AICashAnalysis.objects.order_by('-created_at').first()
    
    if not analysis or request.GET.get('refresh') == 'true':
        engine = AICashEngine()
        results = engine.run_full_analysis()
        analysis = AICashAnalysis.objects.order_by('-created_at').first()
    
    # Prepare chart data
    forecast_30 = analysis.forecast_30_days if analysis else []
    
    chart_labels = [d['date'] for d in forecast_30]
    chart_data = [d['predicted_balance'] for d in forecast_30]
    chart_negative = [d['day'] if d['is_negative'] else None for d in forecast_30]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'analysis': analysis,
        'forecast_30': forecast_30,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'has_negative': any(d['is_negative'] for d in forecast_30),
    }
    return render(request, 'ai/cash_forecast.html', context)


@login_required
@perm_required('use_ai', 'view_cash')
def ai_cash_collections(request):
    """AI Collection Forecast"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    engine = AICashEngine()
    collections = engine.forecast_collections()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'collections': collections,
        'high_probability': collections['high_probability'],
        'medium_probability': collections['medium_probability'],
        'low_probability': collections['low_probability'],
        'total_outstanding': collections['total_outstanding'],
        'total_expected': collections['total_expected'],
    }
    return render(request, 'ai/cash_collections.html', context)


@login_required
@perm_required('use_ai', 'view_cash')
def ai_cash_alerts(request):
    """All Cash Alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AICashAlert
    
    alerts = AICashAlert.objects.all().order_by('-created_at')
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    alert_type = request.GET.get('type', '')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    # Stats
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'warning': alerts.filter(severity='warning').count(),
        'info': alerts.filter(severity='info').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts[:50],
        'stats': stats,
        'selected_severity': severity,
        'selected_type': alert_type,
        'selected_status': status,
        'alert_types': AICashAlert.ALERT_TYPES,
        'severity_levels': AICashAlert.SEVERITY_LEVELS,
    }
    return render(request, 'ai/cash_alerts.html', context)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def ai_cash_alert_resolve(request, pk):
    """Resolve a cash alert"""
    
    from ...models import AICashAlert
    alert = get_object_or_404(AICashAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_cash_alerts')


@login_required
@perm_required('use_ai', 'view_cash')
def ai_cash_health(request):
    """Cash Health Score Details"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AICashHealthHistory
    
    # Run new analysis
    engine = AICashEngine()
    health = engine.calculate_health_score()
    
    # History
    history = AICashHealthHistory.objects.order_by('-date')[:30]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'health': health,
        'history': history,
    }
    return render(request, 'ai/cash_health.html', context)


@login_required
@perm_required('use_ai', 'view_cash')
def cash_strategies_list(request):
    """List all cash investment strategies"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import CashInvestmentStrategy
    
    strategies = CashInvestmentStrategy.objects.all().order_by('-expected_profit')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        strategies = strategies.filter(status=status)
    
    strategy_type = request.GET.get('type', '')
    if strategy_type:
        strategies = strategies.filter(strategy_type=strategy_type)
    
    # Stats
    total = strategies.count()
    recommended = strategies.filter(status='recommended').count()
    approved = strategies.filter(status='approved').count()
    executing = strategies.filter(status='executing').count()
    completed = strategies.filter(status='completed').count()
    
    total_amount = strategies.aggregate(total=Sum('amount'))['total'] or 0
    total_expected_profit = strategies.aggregate(total=Sum('expected_profit'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'strategies': strategies,
        'total': total,
        'recommended': recommended,
        'approved': approved,
        'executing': executing,
        'completed': completed,
        'total_amount': total_amount,
        'total_expected_profit': total_expected_profit,
        'selected_status': status,
        'selected_type': strategy_type,
        'strategy_types': CashInvestmentStrategy.STRATEGY_TYPES,
        'status_choices': CashInvestmentStrategy.STATUS_CHOICES,
    }
    return render(request, 'ai/cash_strategies.html', context)


@login_required
@perm_required('use_ai', 'view_cash')
def cash_strategy_detail(request, pk):
    """View strategy details"""
    
    from ...models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'strategy': strategy,
    }
    return render(request, 'ai/cash_strategy_detail.html', context)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def cash_strategy_approve(request, pk):
    """Approve a cash strategy"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    strategy.approve(request.user)
    
    messages.success(request, f'✅ Strategy "{strategy.name}" approved!')
    return redirect('cash_strategies_list')


@login_required
@perm_required('manage_ai_ops')
@require_POST
def cash_strategy_execute(request, pk):
    """Start executing strategy"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    strategy.start_execution()
    
    messages.success(request, f'⚙️ Strategy "{strategy.name}" started!')
    return redirect('cash_strategies_list')


@login_required
@perm_required('manage_ai_ops')
def cash_strategy_complete(request, pk):
    """Complete a strategy with actual results"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    
    if request.method == 'POST':
        try:
            actual_profit = Decimal(request.POST.get('actual_profit', 0))
            actual_amount = Decimal(request.POST.get('actual_amount', 0))
            notes = request.POST.get('notes', '')
            
            strategy.complete(actual_profit, actual_amount)
            if notes:
                strategy.notes = notes
                strategy.save()
            
            actual_roi = strategy.calculate_actual_roi()
            messages.success(
                request,
                f'🎯 Strategy completed! Actual ROI: {actual_roi:.1f}%'
            )
            return redirect('cash_strategy_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {e}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'strategy': strategy,
    }
    return render(request, 'ai/cash_strategy_complete.html', context)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def cash_strategy_cancel(request, pk):
    """Cancel a strategy"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Only superuser can cancel strategies!')
        return redirect('cash_strategies_list')
    
    from ...models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    reason = request.POST.get('reason', '')
    strategy.cancel(reason)
    
    messages.success(request, f'❌ Strategy "{strategy.name}" cancelled!')
    return redirect('cash_strategies_list')


@login_required
@perm_required('use_ai', 'view_cash')
def strategy_allocations_list(request):
    """List all strategy allocation profiles"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import StrategyAllocation
    
    allocations = StrategyAllocation.objects.all().order_by('-is_active', '-updated_at')
    active_allocation = StrategyAllocation.get_active()
    
    # Add normalized + ROI data
    for allocation in allocations:
        allocation.normalized = allocation.get_normalized_percentages()
        allocation.avg_roi = allocation.get_average_roi()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'allocations': allocations,
        'active_allocation': active_allocation,
        'total_profiles': allocations.count(),
    }
    return render(request, 'strategy/allocations_list.html', context)


@login_required
@perm_required('manage_ai_ops')
def strategy_allocation_create(request):
    """Create new strategy allocation with Fast-Moving"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import StrategyAllocation
    
    templates = {
        'safe': {
            'name': '🟢 Safe Profile',
            'description': 'Low risk, steady returns',
            'bulk_purchase': 40, 'seasonal_stock': 20,
            'customer_credit': 0, 'vendor_advance': 15,
            'new_product': 0, 'fast_moving': 25,
            'bulk_purchase_roi': 25, 'seasonal_stock_roi': 35,
            'customer_credit_roi': 18, 'vendor_advance_roi': 28,
            'new_product_roi': 35, 'fast_moving_roi': 25,
        },
        'balanced': {
            'name': '🟡 Balanced Profile',
            'description': 'Recommended mix for most businesses',
            'bulk_purchase': 25, 'seasonal_stock': 20,
            'customer_credit': 15, 'vendor_advance': 10,
            'new_product': 10, 'fast_moving': 20,
            'bulk_purchase_roi': 25, 'seasonal_stock_roi': 35,
            'customer_credit_roi': 18, 'vendor_advance_roi': 28,
            'new_product_roi': 35, 'fast_moving_roi': 30,
        },
        'fast_moving': {
            'name': '⚡ Fast-Moving Focus',
            'description': 'Focus on fast-moving products',
            'bulk_purchase': 20, 'seasonal_stock': 10,
            'customer_credit': 5, 'vendor_advance': 10,
            'new_product': 5, 'fast_moving': 50,
            'bulk_purchase_roi': 25, 'seasonal_stock_roi': 35,
            'customer_credit_roi': 18, 'vendor_advance_roi': 28,
            'new_product_roi': 35, 'fast_moving_roi': 35,
        },
        'aggressive': {
            'name': '🔴 Aggressive Profile',
            'description': 'High risk, high reward',
            'bulk_purchase': 20, 'seasonal_stock': 25,
            'customer_credit': 10, 'vendor_advance': 5,
            'new_product': 25, 'fast_moving': 15,
            'bulk_purchase_roi': 30, 'seasonal_stock_roi': 40,
            'customer_credit_roi': 22, 'vendor_advance_roi': 30,
            'new_product_roi': 45, 'fast_moving_roi': 30,
        },
        'boom': {
            'name': '🔥 Boom Mode',
            'description': 'Maximum growth',
            'bulk_purchase': 10, 'seasonal_stock': 25,
            'customer_credit': 5, 'vendor_advance': 0,
            'new_product': 30, 'fast_moving': 30,
            'bulk_purchase_roi': 25, 'seasonal_stock_roi': 40,
            'customer_credit_roi': 20, 'vendor_advance_roi': 28,
            'new_product_roi': 50, 'fast_moving_roi': 35,
        },
        'retail': {
            'name': '🏪 Retail Shop',
            'description': 'Retail optimized',
            'bulk_purchase': 25, 'seasonal_stock': 20,
            'customer_credit': 10, 'vendor_advance': 15,
            'new_product': 5, 'fast_moving': 25,
            'bulk_purchase_roi': 28, 'seasonal_stock_roi': 38,
            'customer_credit_roi': 20, 'vendor_advance_roi': 25,
            'new_product_roi': 30, 'fast_moving_roi': 32,
        },
        'wholesale': {
            'name': '🏭 Wholesale Business',
            'description': 'Wholesale optimized',
            'bulk_purchase': 35, 'seasonal_stock': 15,
            'customer_credit': 20, 'vendor_advance': 10,
            'new_product': 5, 'fast_moving': 15,
            'bulk_purchase_roi': 22, 'seasonal_stock_roi': 30,
            'customer_credit_roi': 16, 'vendor_advance_roi': 25,
            'new_product_roi': 30, 'fast_moving_roi': 25,
        },
    }
    
    if request.method == 'POST':
        try:
            from decimal import Decimal
            
            # Allocation
            bulk = Decimal(request.POST.get('bulk_purchase', 25))
            seasonal = Decimal(request.POST.get('seasonal_stock', 20))
            credit = Decimal(request.POST.get('customer_credit', 15))
            advance = Decimal(request.POST.get('vendor_advance', 10))
            new_prod = Decimal(request.POST.get('new_product', 10))
            fast_moving = Decimal(request.POST.get('fast_moving', 20))
            
            # ROI
            bulk_roi = Decimal(request.POST.get('bulk_purchase_roi', 25))
            seasonal_roi = Decimal(request.POST.get('seasonal_stock_roi', 35))
            credit_roi = Decimal(request.POST.get('customer_credit_roi', 18))
            advance_roi = Decimal(request.POST.get('vendor_advance_roi', 28))
            new_roi = Decimal(request.POST.get('new_product_roi', 35))
            fast_roi = Decimal(request.POST.get('fast_moving_roi', 30))
            
            total = bulk + seasonal + credit + advance + new_prod + fast_moving
            
            if total <= 0:
                messages.error(request, '❌ Total must be greater than 0!')
                return redirect('strategy_allocation_create')
            
            allocation = StrategyAllocation.objects.create(
                profile_name=request.POST.get('profile_name'),
                profile_description=request.POST.get('profile_description', ''),
                bulk_purchase=bulk,
                seasonal_stock=seasonal,
                customer_credit=credit,
                vendor_advance=advance,
                new_product=new_prod,
                fast_moving=fast_moving,
                bulk_purchase_roi=bulk_roi,
                seasonal_stock_roi=seasonal_roi,
                customer_credit_roi=credit_roi,
                vendor_advance_roi=advance_roi,
                new_product_roi=new_roi,
                fast_moving_roi=fast_roi,
                is_active=request.POST.get('is_active') == 'on',
                created_by=request.user,
                updated_by=request.user,
            )
            
            messages.success(
                request,
                f'✅ Profile "{allocation.profile_name}" created! '
                f'Avg ROI: {allocation.get_average_roi()}%'
            )
            return redirect('strategy_allocations_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('strategy_allocation_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'templates': templates,
        'is_edit': False,
    }
    return render(request, 'strategy/allocation_form.html', context)


@login_required
@perm_required('manage_ai_ops')
def strategy_allocation_edit(request, pk):
    """Edit strategy allocation with Fast-Moving"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import StrategyAllocation
    
    allocation = get_object_or_404(StrategyAllocation, pk=pk)
    
    if request.method == 'POST':
        try:
            from decimal import Decimal
            
            # Allocation
            bulk = Decimal(request.POST.get('bulk_purchase', 25))
            seasonal = Decimal(request.POST.get('seasonal_stock', 20))
            credit = Decimal(request.POST.get('customer_credit', 15))
            advance = Decimal(request.POST.get('vendor_advance', 10))
            new_prod = Decimal(request.POST.get('new_product', 10))
            fast_moving = Decimal(request.POST.get('fast_moving', 20))
            
            # ROI
            bulk_roi = Decimal(request.POST.get('bulk_purchase_roi', 25))
            seasonal_roi = Decimal(request.POST.get('seasonal_stock_roi', 35))
            credit_roi = Decimal(request.POST.get('customer_credit_roi', 18))
            advance_roi = Decimal(request.POST.get('vendor_advance_roi', 28))
            new_roi = Decimal(request.POST.get('new_product_roi', 35))
            fast_roi = Decimal(request.POST.get('fast_moving_roi', 30))
            
            total = bulk + seasonal + credit + advance + new_prod + fast_moving
            
            if total <= 0:
                messages.error(request, '❌ Total must be greater than 0!')
                return redirect('strategy_allocation_edit', pk=pk)
            
            allocation.profile_name = request.POST.get('profile_name')
            allocation.profile_description = request.POST.get('profile_description', '')
            allocation.bulk_purchase = bulk
            allocation.seasonal_stock = seasonal
            allocation.customer_credit = credit
            allocation.vendor_advance = advance
            allocation.new_product = new_prod
            allocation.fast_moving = fast_moving
            allocation.bulk_purchase_roi = bulk_roi
            allocation.seasonal_stock_roi = seasonal_roi
            allocation.customer_credit_roi = credit_roi
            allocation.vendor_advance_roi = advance_roi
            allocation.new_product_roi = new_roi
            allocation.fast_moving_roi = fast_roi
            allocation.is_active = request.POST.get('is_active') == 'on'
            allocation.updated_by = request.user
            allocation.save()
            
            messages.success(
                request,
                f'✅ Profile "{allocation.profile_name}" updated! '
                f'Avg ROI: {allocation.get_average_roi()}%'
            )
            return redirect('strategy_allocations_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('strategy_allocation_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'allocation': allocation,
        'is_edit': True,
    }
    return render(request, 'strategy/allocation_form.html', context)


@login_required
@perm_required('manage_ai_ops')
def strategy_allocation_activate(request, pk):
    """Activate a strategy allocation"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import StrategyAllocation
    
    allocation = get_object_or_404(StrategyAllocation, pk=pk)
    
    if request.method == 'POST':
        StrategyAllocation.objects.exclude(pk=pk).update(is_active=False)
        allocation.is_active = True
        allocation.updated_by = request.user
        allocation.save()
        
        messages.success(
            request, 
            f'✅ Profile "{allocation.profile_name}" is now ACTIVE! '
            f'Avg ROI: {allocation.get_average_roi()}%'
        )
    
    return redirect('strategy_allocations_list')


@login_required
@perm_required('manage_ai_ops')
def strategy_allocation_delete(request, pk):
    """Delete a strategy allocation"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Only superuser can delete profiles!')
        return redirect('strategy_allocations_list')
    
    from ...models import StrategyAllocation
    
    allocation = get_object_or_404(StrategyAllocation, pk=pk)
    
    if allocation.is_active:
        messages.error(request, '❌ Cannot delete active profile! Activate another first.')
        return redirect('strategy_allocations_list')
    
    if request.method == 'POST':
        name = allocation.profile_name
        allocation.delete()
        messages.success(request, f'🗑️ Profile "{name}" deleted!')
    
    return redirect('strategy_allocations_list')


@login_required
@perm_required('manage_ai_ops')
def strategy_allocation_preview(request, pk):
    """Preview with Fast-Moving + Custom ROI"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    from ...models import StrategyAllocation
    
    allocation = get_object_or_404(StrategyAllocation, pk=pk)
    
    cash_balance = CashBalance.get_balance()
    allocation_dict = allocation.get_allocation_dict()
    roi_dict = allocation.get_roi_dict()
    
    raw = {
        'bulk_purchase': float(allocation.bulk_purchase),
        'seasonal_stock': float(allocation.seasonal_stock),
        'customer_credit': float(allocation.customer_credit),
        'vendor_advance': float(allocation.vendor_advance),
        'new_product': float(allocation.new_product),
        'fast_moving': float(allocation.fast_moving),
    }
    raw_total = sum(raw.values())
    
    normalized = allocation.get_normalized_percentages()
    
    preview = []
    
    # 6 Strategies
    strategies_config = [
        ('bulk_purchase', 'Bulk Purchase Discount', 'low', 4),
        ('seasonal_stock', 'Seasonal Stock', 'medium', 3),
        ('customer_credit', 'Customer Credit', 'medium', 3),
        ('vendor_advance', 'Vendor Advance', 'low', 2),
        ('new_product', 'New Product Line', 'high', 6),
        ('fast_moving', 'Fast-Moving Product', 'low', 1),
    ]
    
    for key, name, risk, timeline in strategies_config:
        if allocation_dict[key] > 0:
            amt = cash_balance * Decimal(str(allocation_dict[key]))
            roi = roi_dict[key]
            profit = amt * Decimal(str(roi / 100))
            preview.append({
                'name': name,
                'raw_percentage': raw[key],
                'normalized_percentage': normalized[key],
                'amount': float(amt),
                'roi': roi,
                'profit': float(profit),
                'risk': risk,
                'timeline': timeline,
            })
    
    total_profit = sum(p['profit'] for p in preview)
    
    return JsonResponse({
        'success': True,
        'cash_balance': float(cash_balance),
        'raw_total': raw_total,
        'raw_percentages': raw,
        'normalized': normalized,
        'roi_dict': roi_dict,
        'average_roi': allocation.get_average_roi(),
        'strategies': preview,
        'total_profit': total_profit,
        'total_roi': (total_profit / float(cash_balance) * 100) if cash_balance > 0 else 0,
    })


@login_required
@perm_required('use_ai', 'view_cash', post='manage_ai_ops')
def emergency_fund_dashboard(request):
    """Emergency Fund Dashboard"""
    
    from ...models import EmergencyFund, EmergencyFundTransaction, Expense
    
    # Fund nikalo
    fund = EmergencyFund.get_active_fund()
    
    # If it does not exist, create it
    if not fund:
        if request.method == 'POST':
            # Create new fund
            target = Decimal(request.POST.get('target_amount', 0))
            monthly = Decimal(request.POST.get('monthly_contribution', 0))
            
            fund = EmergencyFund.objects.create(
                name=request.POST.get('name', 'Emergency Fund'),
                fund_type=request.POST.get('fund_type', 'business'),
                description=request.POST.get('description', ''),
                target_amount=target,
                monthly_contribution=monthly,
                is_active=True,
                created_by=request.user,
            )
            
            messages.success(request, f'✅ Emergency Fund banaya gaya!')
            return redirect('emergency_fund_dashboard')
        
        # Show creation form
        # Monthly expense nikalo
        last_30 = date.today() - timedelta(days=30)
        monthly_expense = Expense.objects.filter(
            expense_date__gte=last_30,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('10000')
        
        context = {
            'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
            'fund': None,
            'suggested_target': monthly_expense * 3,
            'suggested_monthly': monthly_expense * Decimal('0.1'),
            'monthly_expense': monthly_expense,
            'fund_types': EmergencyFund.FUND_TYPES,
        }
        return render(request, 'ai/emergency_fund_create.html', context)
    
    # Transactions
    transactions = fund.transactions.all().order_by('-created_at')[:20]
    
    # Calculate stats
    monthly_expense = Decimal('0')
    last_30 = date.today() - timedelta(days=30)
    monthly_expense = Expense.objects.filter(
        expense_date__gte=last_30,
        status__in=['approved', 'paid']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'fund': fund,
        'transactions': transactions,
        'monthly_expense': monthly_expense,
        'months_covered': fund.months_covered,
        'progress': fund.progress_percent,
        'remaining': fund.remaining_amount,
        'months_remaining': fund.months_remaining,
        'is_completed': fund.is_completed,
    }
    return render(request, 'ai/emergency_fund_dashboard.html', context)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def emergency_fund_add(request):
    """Add money to the Emergency Fund"""
    
    from ...models import EmergencyFund, EmergencyFundTransaction
    
    fund_id = request.POST.get('fund_id')
    amount = Decimal(request.POST.get('amount', 0))
    description = request.POST.get('description', '')
    
    if amount <= 0:
        messages.error(request, '❌ Amount must be greater than 0')
        return redirect('emergency_fund_dashboard')
    
    try:
        with transaction.atomic():
            if fund_id:
                fund = EmergencyFund.objects.get(id=fund_id)
            else:
                fund = EmergencyFund.get_or_create_default()
            
            # Add money
            new_balance = fund.add_money(amount, request.user, description)
            
            # Transaction record
            EmergencyFundTransaction.objects.create(
                fund=fund,
                transaction_type='deposit',
                amount=amount,
                balance_after=new_balance,
                description=description,
                created_by=request.user,
            )
            
            messages.success(
                request, 
                f'✅ Rs. {amount:,.2f} added to the Emergency Fund!\n'
                f'💰 New Balance: Rs. {new_balance:,.2f}'
            )
    
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('emergency_fund_dashboard')


@login_required
@perm_required('manage_ai_ops')
@require_POST
def emergency_fund_withdraw(request):
    """Emergency Fund se paisa nikalo"""
    
    from ...models import EmergencyFund, EmergencyFundTransaction
    
    fund_id = request.POST.get('fund_id')
    amount = Decimal(request.POST.get('amount', 0))
    reason = request.POST.get('reason', '')
    
    if amount <= 0:
        messages.error(request, '❌ Amount must be greater than 0')
        return redirect('emergency_fund_dashboard')
    
    try:
        with transaction.atomic():
            fund = EmergencyFund.objects.get(id=fund_id)
            
            # Withdraw money
            new_balance = fund.withdraw_money(amount, request.user, reason)
            
            # Transaction record
            EmergencyFundTransaction.objects.create(
                fund=fund,
                transaction_type='withdraw',
                amount=amount,
                balance_after=new_balance,
                description=reason,
                created_by=request.user,
            )
            
            messages.success(
                request, 
                f'💸 Rs. {amount:,.2f} withdrawn from the Emergency Fund\n'
                f'💰 Remaining: Rs. {new_balance:,.2f}'
            )
    
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('emergency_fund_dashboard')


@login_required
@perm_required('manage_ai_ops')
def emergency_fund_settings(request):
    """Emergency Fund ki settings"""
    
    from ...models import EmergencyFund
    
    fund = EmergencyFund.get_active_fund()
    
    if request.method == 'POST':
        if fund:
            fund.name = request.POST.get('name', fund.name)
            fund.fund_type = request.POST.get('fund_type', fund.fund_type)
            fund.description = request.POST.get('description', '')
            fund.target_amount = Decimal(request.POST.get('target_amount', 0))
            fund.monthly_contribution = Decimal(request.POST.get('monthly_contribution', 0))
            fund.auto_deduct = request.POST.get('auto_deduct') == 'on'
            fund.save()
            
            messages.success(request, '✅ Settings updated!')
        else:
            # Create new
            fund = EmergencyFund.objects.create(
                name=request.POST.get('name', 'Emergency Fund'),
                fund_type=request.POST.get('fund_type', 'business'),
                description=request.POST.get('description', ''),
                target_amount=Decimal(request.POST.get('target_amount', 0)),
                monthly_contribution=Decimal(request.POST.get('monthly_contribution', 0)),
                auto_deduct=request.POST.get('auto_deduct') == 'on',
                is_active=True,
                created_by=request.user,
            )
            messages.success(request, '✅ Emergency Fund banaya gaya!')
        
        return redirect('emergency_fund_dashboard')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'fund': fund,
        'fund_types': EmergencyFund.FUND_TYPES,
    }
    return render(request, 'ai/emergency_fund_settings.html', context)


@login_required
@perm_required('use_ai', 'view_financials')
def business_ratios_dashboard(request):
    """CFO-Level Business Ratios Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can view ratios.')
        return redirect('dashboard')
    
    from ...business_ratios import BusinessRatios
    from datetime import datetime, timedelta
    
    # Date filters
    from_date_str = request.GET.get('from_date', (date.today() - timedelta(days=365)).strftime('%Y-%m-%d'))
    to_date_str = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    except:
        from_date = date.today() - timedelta(days=365)
        to_date = date.today()
    
    # Calculate ratios
    calculator = BusinessRatios()
    ratios = calculator.get_all_ratios(from_date, to_date)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'ratios': ratios,
        'from_date': from_date_str,
        'to_date': to_date_str,
        'today': date.today(),
    }
    return render(request, 'reports/business_ratios.html', context)
