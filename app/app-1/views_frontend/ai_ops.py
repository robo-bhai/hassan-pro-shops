"""Frontend views: ai ops."""
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST
from ..models import *
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ..models import CashBalance, Shareholder, CompanyInfo, Expense, Employee, Product, AIInsight, AIHealthScore, AIAnomalyDetection, AIPrediction
from ..ai_engine import AIEngine
from ..ai_operations_engine import AIOperationsEngine
from ..chatbot_engine import BusinessChatbot
from ..ai_purchase_planner import AIPurchasePlanner
from ..ai_cash_engine import AICashEngine
from ..ai_shareholder_engine import AIShareholderEngine
from ..ai_board_room import AIBoardRoom
from ..ai_cso_tech import AICSOTechEngine
import logging

logger = logging.getLogger(__name__)


@login_required
def risk_assessment_api(request):
    """API: Calculate risk assessment for a purchase"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        from ..risk_calculator import RiskCalculator
        
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        sale_qty = int(request.GET.get('sale_qty', 0))
        purchase_qty = int(request.GET.get('purchase_qty', 0))
        unit_price = Decimal(request.GET.get('unit_price', 0))
        
        if not product_id or not warehouse_id:
            return JsonResponse({'success': False, 'message': 'Product and Warehouse required!'})
        
        if purchase_qty <= 0:
            return JsonResponse({
                'success': True,
                'score': 0,
                'category': 'NO PURCHASE NEEDED',
                'color': 'success',
                'factors': {},
                'alerts': [],
                'positives': ['Stock sufficient - no purchase needed'],
                'recommendation': {
                    'action': 'SKIP',
                    'title': '✅ NO PURCHASE NEEDED',
                    'message': 'Available stock kaafi hai. Kuch kharidne ki zaroorat nahi.',
                    'suggested_qty': 0,
                    'steps': ['Stock sufficient hai', 'Monitor karte raho'],
                },
            })
        
        product = get_object_or_404(Product, pk=product_id)
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Calculate risk
        calculator = RiskCalculator(
            product=product,
            warehouse=warehouse,
            sale_qty=sale_qty,
            purchase_qty=purchase_qty,
            unit_price=unit_price,
        )
        
        result = calculator.calculate()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Risk assessment error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e),
        })


@login_required
def ai_dashboard(request):
    """AI Self-Diagnostic Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can access AI Dashboard.')
        return redirect('dashboard')
    
    # Run AI analysis on-demand
    run_analysis = request.GET.get('run', 'false') == 'true'
    
    if run_analysis:
        with transaction.atomic():
            engine = AIEngine()
            result = engine.run_full_analysis()
            
            # Save health score
            today = now().date()
            health_score, created = AIHealthScore.objects.get_or_create(
                date=today,
                defaults={
                    'overall_score': result['health_score'],
                }
            )
            
            if not created:
                health_score.overall_score = result['health_score']
                health_score.save()
            
            messages.success(
                request, 
                f"🤖 AI Analysis complete! "
                f"{result['insights_count']} new insights. "
                f"Health Score: {result['health_score']}/100"
            )
    
    # Get all insights
    insights = AIInsight.objects.filter(is_ignored=False).order_by('-detected_at')
    
    # Stats
    total_insights = insights.count()
    critical_count = insights.filter(severity='critical', is_resolved=False).count()
    high_count = insights.filter(severity='high', is_resolved=False).count()
    medium_count = insights.filter(severity='medium', is_resolved=False).count()
    low_count = insights.filter(severity='low', is_resolved=False).count()
    
    # Category breakdown
    categories = insights.values('category').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Health score
    latest_score = AIHealthScore.objects.order_by('-date').first()
    
    # Anomalies
    anomalies = AIAnomalyDetection.objects.filter(
        is_resolved=False
    ).order_by('-detected_at')[:10]
    
    # Predictions
    predictions = AIPrediction.objects.order_by('-created_at')[:10]
    
    # Filter by category
    category_filter = request.GET.get('category', '')
    if category_filter:
        insights = insights.filter(category=category_filter)
    
    # Filter by severity
    severity_filter = request.GET.get('severity', '')
    if severity_filter:
        insights = insights.filter(severity=severity_filter)
    
    # Pagination
    paginator = Paginator(insights, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'insights': page_obj,
        'total_insights': total_insights,
        'critical_count': critical_count,
        'high_count': high_count,
        'medium_count': medium_count,
        'low_count': low_count,
        'categories': categories,
        'latest_score': latest_score,
        'anomalies': anomalies,
        'predictions': predictions,
        'category_filter': category_filter,
        'severity_filter': severity_filter,
        'insight_categories': AIInsight.CATEGORIES,
        'severity_levels': AIInsight.SEVERITY_LEVELS,
    }
    return render(request, 'ai/dashboard.html', context)


@login_required
def ai_run_analysis(request):
    """Run AI analysis via AJAX"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        engine = AIEngine()
        result = engine.run_full_analysis()
        
        return JsonResponse({
            'success': True,
            'insights_count': result['insights_count'],
            'health_score': result['health_score'],
            'message': f"✅ Analysis complete! {result['insights_count']} new insights found."
        })
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def ai_insight_detail(request, pk):
    """View AI insight detail"""
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    # Track view
    if request.user.is_authenticated:
        from ..models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='viewed',
            user=request.user,
        )
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'insight': insight,
    }
    return render(request, 'ai/insight_detail.html', context)


@login_required
def ai_resolve_insight(request, pk):
    """Mark insight as resolved"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    if request.method == 'POST':
        insight.is_resolved = True
        insight.resolved_at = now()
        insight.resolved_by = request.user
        insight.save()
        
        # Track action
        from ..models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='fixed',
            user=request.user,
        )
        
        messages.success(request, f'✅ Insight marked as resolved!')
    
    return redirect('ai_dashboard')


@login_required
def ai_ignore_insight(request, pk):
    """Ignore an insight"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    if request.method == 'POST':
        insight.is_ignored = True
        insight.save()
        
        # Track action
        from ..models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='ignored',
            user=request.user,
        )
        
        messages.success(request, f'🔇 Insight ignored!')
    
    return redirect('ai_dashboard')


def can_manage_operations(user):
    """Check if user can manage operations"""
    if user.is_superuser:
        return True
    if user.groups.filter(name__in=['Owner', 'Store Manager', 'Operations Manager']).exists():
        return True
    return False


@login_required
def operations_dashboard(request):
    """Main Business Operations Dashboard with AI"""
    
    today = localdate()
    
    # Run AI analysis if requested
    if request.GET.get('run_ai') == 'true':
        try:
            engine = AIOperationsEngine()
            result = engine.run_full_analysis()
            messages.success(
                request,
                f"🤖 AI Analysis Complete! "
                f"{result['insights_created']} insights, "
                f"{result['alerts_created']} alerts, "
                f"Health Score: {result['health_score']}/100"
            )
        except Exception as e:
            messages.error(request, f"❌ AI Error: {str(e)}")
        return redirect('operations_dashboard')
    
    # Today's tasks
    today_tasks = OperationTask.objects.filter(
        due_date__date=today
    ).select_related('assigned_to', 'plan').order_by('priority')[:10]
    
    # Overdue tasks
    overdue_tasks = OperationTask.objects.filter(
        due_date__lt=now(),
        status__in=['pending', 'in_progress']
    ).select_related('assigned_to', 'plan').order_by('due_date')[:10]
    
    # Active plans
    active_plans = BusinessOperationPlan.objects.filter(
        status__in=['active', 'in_progress'],
        end_date__gte=today
    ).order_by('end_date')[:5]
    
    # KPIs
    kpis = OperationsKPI.objects.filter(is_active=True)[:8]
    kpi_summary = {
        'total': OperationsKPI.objects.filter(is_active=True).count(),
        'on_track': OperationsKPI.objects.filter(status='on_track').count(),
        'warning': OperationsKPI.objects.filter(status='warning').count(),
        'critical': OperationsKPI.objects.filter(status='critical').count(),
        'achieved': OperationsKPI.objects.filter(status='achieved').count(),
    }
    
    # Department stats
    department_stats = []
    for dept_code, dept_name in BusinessOperationPlan.DEPARTMENTS:
        dept_tasks = OperationTask.objects.filter(plan__department=dept_code)
        total = dept_tasks.count()
        completed = dept_tasks.filter(status='completed').count()
        department_stats.append({
            'code': dept_code,
            'name': dept_name,
            'total': total,
            'completed': completed,
            'pending': total - completed,
            'percent': (completed / total * 100) if total > 0 else 0,
        })
    
    # AI Insights
    ai_insights = AIOperationsInsight.objects.filter(
        is_resolved=False, is_ignored=False
    ).order_by('-detected_at')[:5]
    
    # AI Task Suggestions
    ai_suggestions = AITaskSuggestion.objects.filter(
        status='pending'
    ).order_by('-generated_at')[:5]
    
    # Alerts
    recent_alerts = OperationAlert.objects.filter(
        is_resolved=False
    ).order_by('-created_at')[:10]
    
    # Checklist
    today_checklist = DailyChecklist.objects.filter(date=today).order_by('department', 'order')
    checklist_stats = {
        'total': today_checklist.count(),
        'completed': today_checklist.filter(is_completed=True).count(),
    }
    checklist_stats['pending'] = checklist_stats['total'] - checklist_stats['completed']
    checklist_stats['percent'] = (
        (checklist_stats['completed'] / checklist_stats['total'] * 100)
        if checklist_stats['total'] > 0 else 0
    )
    
    # Weekly trend
    weekly_labels = []
    weekly_completed = []
    weekly_created = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        weekly_labels.append(day.strftime('%a'))
        weekly_created.append(OperationTask.objects.filter(created_at__date=day).count())
        weekly_completed.append(OperationTask.objects.filter(completed_at__date=day).count())
    
    # Quick stats
    quick_stats = {
        'total_tasks': OperationTask.objects.count(),
        'pending_tasks': OperationTask.objects.filter(status='pending').count(),
        'in_progress_tasks': OperationTask.objects.filter(status='in_progress').count(),
        'completed_tasks': OperationTask.objects.filter(status='completed').count(),
        'overdue_tasks': overdue_tasks.count(),
        'total_plans': BusinessOperationPlan.objects.count(),
        'active_plans': active_plans.count(),
        'ai_insights': AIOperationsInsight.objects.filter(is_resolved=False).count(),
        'ai_suggestions': AITaskSuggestion.objects.filter(status='pending').count(),
    }
    
    # Calculate current health score
    try:
        engine = AIOperationsEngine()
        health_score = engine.calculate_health_score()
    except:
        health_score = 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'today': today,
        'today_tasks': today_tasks,
        'overdue_tasks': overdue_tasks,
        'active_plans': active_plans,
        'kpis': kpis,
        'kpi_summary': kpi_summary,
        'department_stats': department_stats,
        'ai_insights': ai_insights,
        'ai_suggestions': ai_suggestions,
        'recent_alerts': recent_alerts,
        'today_checklist': today_checklist,
        'checklist_stats': checklist_stats,
        'quick_stats': quick_stats,
        'health_score': health_score,
        'weekly_labels': json.dumps(weekly_labels),
        'weekly_completed': json.dumps(weekly_completed),
        'weekly_created': json.dumps(weekly_created),
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/dashboard.html', context)


@login_required
def ai_insights_list(request):
    """View all AI insights"""
    
    insights = AIOperationsInsight.objects.filter(is_ignored=False).order_by('-detected_at')
    
    # Filters
    insight_type = request.GET.get('type', '')
    if insight_type:
        insights = insights.filter(insight_type=insight_type)
    
    severity = request.GET.get('severity', '')
    if severity:
        insights = insights.filter(severity=severity)
    
    status = request.GET.get('status', '')
    if status == 'resolved':
        insights = insights.filter(is_resolved=True)
    elif status == 'unresolved':
        insights = insights.filter(is_resolved=False)
    
    # Stats
    stats = {
        'total': insights.count(),
        'critical': insights.filter(severity='critical', is_resolved=False).count(),
        'high': insights.filter(severity='high', is_resolved=False).count(),
        'medium': insights.filter(severity='medium', is_resolved=False).count(),
        'low': insights.filter(severity='low', is_resolved=False).count(),
    }
    
    paginator = Paginator(insights, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'insights': page_obj,
        'stats': stats,
        'insight_types': AIOperationsInsight.INSIGHT_TYPES,
        'severities': AIOperationsInsight.SEVERITY,
        'selected_type': insight_type,
        'selected_severity': severity,
        'selected_status': status,
    }
    return render(request, 'operations/ai_insights.html', context)


@login_required
@require_POST
def ai_insight_resolve(request, pk):
    """Mark AI insight as resolved"""
    insight = get_object_or_404(AIOperationsInsight, pk=pk)
    insight.is_resolved = True
    insight.resolved_at = now()
    insight.resolved_by = request.user
    insight.save()
    
    messages.success(request, '✅ Insight resolved!')
    return redirect('ai_insights_list')


@login_required
@require_POST
def ai_insight_ignore(request, pk):
    """Ignore AI insight"""
    insight = get_object_or_404(AIOperationsInsight, pk=pk)
    insight.is_ignored = True
    insight.save()
    
    messages.success(request, '🔇 Insight ignored!')
    return redirect('ai_insights_list')


@login_required
def ai_task_suggestions(request):
    """View AI task suggestions"""
    
    suggestions = AITaskSuggestion.objects.filter(
        status='pending'
    ).order_by('-generated_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suggestions': suggestions,
        'total': suggestions.count(),
    }
    return render(request, 'operations/ai_suggestions.html', context)


@login_required
def ai_suggestion_accept(request, pk):
    """Accept AI suggestion and create task"""
    
    suggestion = get_object_or_404(AITaskSuggestion, pk=pk)
    
    if request.method == 'POST':
        try:
            # Get or create a default plan
            plan, _ = BusinessOperationPlan.objects.get_or_create(
                title=f"AI Suggested Tasks - {localdate()}",
                defaults={
                    'description': 'Tasks created from AI suggestions',
                    'plan_type': 'daily',
                    'department': suggestion.department,
                    'start_date': localdate(),
                    'end_date': localdate() + timedelta(days=7),
                    'created_by': request.user,
                    'status': 'active',
                }
            )
            
            # Create task
            task = OperationTask.objects.create(
                plan=plan,
                title=suggestion.title,
                description=suggestion.description,
                priority=suggestion.suggested_priority,
                assigned_to=suggestion.suggested_assignee,
                assigned_by=request.user,
                due_date=now() + timedelta(days=1),
                notes=f"Created from AI suggestion. Reason: {suggestion.reason}",
                created_by=request.user,
                ai_suggested=True,
            )
            
            suggestion.status = 'accepted'
            suggestion.created_task = task
            suggestion.processed_at = now()
            suggestion.processed_by = request.user
            suggestion.save()
            
            messages.success(request, f'✅ Task created: {task.task_no}')
            return redirect('task_detail', pk=task.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('ai_task_suggestions')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suggestion': suggestion,
    }
    return render(request, 'operations/ai_suggestion_accept.html', context)


@login_required
@require_POST
def ai_suggestion_reject(request, pk):
    """Reject AI suggestion"""
    suggestion = get_object_or_404(AITaskSuggestion, pk=pk)
    suggestion.status = 'rejected'
    suggestion.processed_at = now()
    suggestion.processed_by = request.user
    suggestion.save()
    
    messages.success(request, '❌ Suggestion rejected!')
    return redirect('ai_task_suggestions')


@login_required
def operation_plan_list(request):
    """List all operation plans"""
    
    plans = BusinessOperationPlan.objects.select_related(
        'assigned_to', 'created_by', 'approved_by'
    ).all().order_by('-start_date')
    
    plan_type = request.GET.get('type', '')
    if plan_type:
        plans = plans.filter(plan_type=plan_type)
    
    department = request.GET.get('department', '')
    if department:
        plans = plans.filter(department=department)
    
    status = request.GET.get('status', '')
    if status:
        plans = plans.filter(status=status)
    
    search = request.GET.get('search', '')
    if search:
        plans = plans.filter(Q(plan_no__icontains=search) | Q(title__icontains=search))
    
    paginator = Paginator(plans, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'plans': page_obj,
        'total_plans': plans.count(),
        'active_count': plans.filter(status='active').count(),
        'completed_count': plans.filter(status='completed').count(),
        'draft_count': plans.filter(status='draft').count(),
        'plan_types': BusinessOperationPlan.PLAN_TYPES,
        'departments': BusinessOperationPlan.DEPARTMENTS,
        'status_choices': BusinessOperationPlan.STATUS_CHOICES,
        'priority_choices': BusinessOperationPlan.PRIORITY_CHOICES,
        'selected_type': plan_type,
        'selected_department': department,
        'selected_status': status,
        'search': search,
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/plan_list.html', context)


@login_required
def operation_plan_create(request):
    """Create a new operation plan"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('operation_plan_list')
    
    if request.method == 'POST':
        try:
            plan = BusinessOperationPlan.objects.create(
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                plan_type=request.POST.get('plan_type'),
                department=request.POST.get('department'),
                priority=request.POST.get('priority', 'medium'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                goal_description=request.POST.get('goal_description', ''),
                target_value=Decimal(request.POST.get('target_value', 0) or 0),
                target_unit=request.POST.get('target_unit', ''),
                assigned_to_id=request.POST.get('assigned_to') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='draft',
            )
            
            team_ids = request.POST.getlist('assigned_team[]')
            if team_ids:
                plan.assigned_team.set(team_ids)
            
            messages.success(request, f'✅ Plan #{plan.plan_no} created!')
            return redirect('operation_plan_detail', pk=plan.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('operation_plan_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employees': Employee.objects.filter(status='active'),
        'plan_types': BusinessOperationPlan.PLAN_TYPES,
        'departments': BusinessOperationPlan.DEPARTMENTS,
        'priority_choices': BusinessOperationPlan.PRIORITY_CHOICES,
        'today': localdate().strftime('%Y-%m-%d'),
        'next_week': (localdate() + timedelta(days=7)).strftime('%Y-%m-%d'),
        'is_edit': False,
    }
    return render(request, 'operations/plan_form.html', context)


@login_required
def operation_plan_detail(request, pk):
    """View plan details"""
    
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    tasks = plan.tasks.select_related('assigned_to').order_by('priority', 'due_date')
    
    task_stats = {
        'total': tasks.count(),
        'pending': tasks.filter(status='pending').count(),
        'in_progress': tasks.filter(status='in_progress').count(),
        'completed': tasks.filter(status='completed').count(),
        'overdue': sum(1 for t in tasks if t.is_overdue()),
    }
    
    plan.update_progress()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'tasks': tasks,
        'task_stats': task_stats,
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/plan_detail.html', context)


@login_required
def operation_plan_edit(request, pk):
    """Edit an operation plan"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('operation_plan_list')
    
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    
    if plan.status == 'completed':
        messages.error(request, '❌ Cannot edit completed plan!')
        return redirect('operation_plan_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            plan.title = request.POST.get('title')
            plan.description = request.POST.get('description', '')
            plan.plan_type = request.POST.get('plan_type')
            plan.department = request.POST.get('department')
            plan.priority = request.POST.get('priority', 'medium')
            plan.start_date = request.POST.get('start_date')
            plan.end_date = request.POST.get('end_date')
            plan.goal_description = request.POST.get('goal_description', '')
            plan.target_value = Decimal(request.POST.get('target_value', 0) or 0)
            plan.target_unit = request.POST.get('target_unit', '')
            plan.actual_value = Decimal(request.POST.get('actual_value', 0) or 0)
            plan.assigned_to_id = request.POST.get('assigned_to') or None
            plan.notes = request.POST.get('notes', '')
            plan.save()
            
            plan.assigned_team.clear()
            team_ids = request.POST.getlist('assigned_team[]')
            if team_ids:
                plan.assigned_team.set(team_ids)
            
            messages.success(request, '✅ Plan updated!')
            return redirect('operation_plan_detail', pk=plan.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('operation_plan_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'employees': Employee.objects.filter(status='active'),
        'plan_types': BusinessOperationPlan.PLAN_TYPES,
        'departments': BusinessOperationPlan.DEPARTMENTS,
        'priority_choices': BusinessOperationPlan.PRIORITY_CHOICES,
        'is_edit': True,
    }
    return render(request, 'operations/plan_form.html', context)


@login_required
@require_POST
def operation_plan_approve(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    plan.approve(request.user)
    messages.success(request, f'✅ Plan #{plan.plan_no} approved!')
    return redirect('operation_plan_detail', pk=pk)


@login_required
@require_POST
def operation_plan_complete(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    plan.complete(request.user)
    messages.success(request, f'🎯 Plan #{plan.plan_no} completed!')
    return redirect('operation_plan_detail', pk=pk)


@login_required
@require_POST
def operation_plan_delete(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    plan_no = plan.plan_no
    plan.delete()
    messages.success(request, f'🗑️ Plan #{plan_no} deleted!')
    return redirect('operation_plan_list')


@login_required
def task_list(request):
    """List all tasks"""
    
    tasks = OperationTask.objects.select_related(
        'assigned_to', 'plan', 'created_by'
    ).order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        tasks = tasks.filter(status=status)
    
    priority = request.GET.get('priority', '')
    if priority:
        tasks = tasks.filter(priority=priority)
    
    assigned_to = request.GET.get('assigned_to', '')
    if assigned_to:
        tasks = tasks.filter(assigned_to_id=assigned_to)
    
    search = request.GET.get('search', '')
    if search:
        tasks = tasks.filter(Q(task_no__icontains=search) | Q(title__icontains=search))
    
    stats = {
        'total': tasks.count(),
        'pending': tasks.filter(status='pending').count(),
        'in_progress': tasks.filter(status='in_progress').count(),
        'completed': tasks.filter(status='completed').count(),
        'overdue': sum(1 for t in tasks if t.is_overdue()),
    }
    
    paginator = Paginator(tasks, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'tasks': page_obj,
        'stats': stats,
        'employees': Employee.objects.filter(status='active'),
        'status_choices': OperationTask.STATUS_CHOICES,
        'priority_choices': OperationTask.PRIORITY_CHOICES,
        'selected_status': status,
        'selected_priority': priority,
        'selected_assigned_to': assigned_to,
        'search': search,
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/task_list.html', context)


@login_required
def task_create(request):
    """Create a new task"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('task_list')
    
    plan_id = request.GET.get('plan')
    pre_plan = None
    if plan_id:
        try:
            pre_plan = BusinessOperationPlan.objects.get(pk=plan_id)
        except:
            pass
    
    if request.method == 'POST':
        try:
            task = OperationTask.objects.create(
                plan_id=request.POST.get('plan'),
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                priority=request.POST.get('priority', 'medium'),
                assigned_to_id=request.POST.get('assigned_to') or None,
                assigned_by=request.user,
                due_date=request.POST.get('due_date'),
                estimated_hours=Decimal(request.POST.get('estimated_hours', 0) or 0),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            
            messages.success(request, f'✅ Task #{task.task_no} created!')
            return redirect('task_detail', pk=task.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('task_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'pre_plan': pre_plan,
        'plans': BusinessOperationPlan.objects.filter(status__in=['active', 'in_progress']),
        'employees': Employee.objects.filter(status='active'),
        'priority_choices': OperationTask.PRIORITY_CHOICES,
        'tomorrow': (localdate() + timedelta(days=1)).strftime('%Y-%m-%dT10:00'),
        'is_edit': False,
    }
    return render(request, 'operations/task_form.html', context)


@login_required
def task_detail(request, pk):
    """View task details"""
    task = get_object_or_404(OperationTask, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'task': task,
        'is_overdue': task.is_overdue(),
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/task_detail.html', context)


@login_required
def task_edit(request, pk):
    """Edit task"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('task_list')
    
    task = get_object_or_404(OperationTask, pk=pk)
    
    if request.method == 'POST':
        try:
            task.plan_id = request.POST.get('plan')
            task.title = request.POST.get('title')
            task.description = request.POST.get('description', '')
            task.priority = request.POST.get('priority', 'medium')
            task.assigned_to_id = request.POST.get('assigned_to') or None
            task.due_date = request.POST.get('due_date')
            task.estimated_hours = Decimal(request.POST.get('estimated_hours', 0) or 0)
            task.notes = request.POST.get('notes', '')
            task.save()
            
            messages.success(request, '✅ Task updated!')
            return redirect('task_detail', pk=task.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('task_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'task': task,
        'plans': BusinessOperationPlan.objects.filter(status__in=['active', 'in_progress']),
        'employees': Employee.objects.filter(status='active'),
        'priority_choices': OperationTask.PRIORITY_CHOICES,
        'is_edit': True,
    }
    return render(request, 'operations/task_form.html', context)


@login_required
@require_POST
def task_start(request, pk):
    task = get_object_or_404(OperationTask, pk=pk)
    task.mark_started(request.user)
    messages.success(request, f'⚙️ Task started: {task.title}')
    return redirect('task_detail', pk=pk)


@login_required
def task_complete(request, pk):
    """Mark task as completed"""
    
    task = get_object_or_404(OperationTask, pk=pk)
    
    if request.method == 'POST':
        hours = request.POST.get('actual_hours')
        if hours:
            hours = Decimal(hours)
        task.mark_completed(request.user, hours)
        messages.success(request, f'✅ Task completed: {task.title}')
        return redirect('task_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'task': task,
    }
    return render(request, 'operations/task_complete.html', context)


@login_required
@require_POST
def task_delete(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    task = get_object_or_404(OperationTask, pk=pk)
    task_no = task.task_no
    task.delete()
    messages.success(request, f'🗑️ Task #{task_no} deleted!')
    return JsonResponse({'success': True})


@login_required
def my_tasks(request):
    """Show current user's tasks"""
    
    employee = Employee.objects.filter(email=request.user.email).first()
    
    if employee:
        tasks = OperationTask.objects.filter(assigned_to=employee).select_related('plan').order_by('priority', 'due_date')
    else:
        tasks = OperationTask.objects.none()
    
    today = localdate()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
        'pending': tasks.filter(status='pending'),
        'in_progress': tasks.filter(status='in_progress'),
        'overdue': tasks.filter(due_date__lt=now()).exclude(status__in=['completed', 'cancelled']),
        'today_tasks': tasks.filter(due_date__date=today).exclude(status__in=['completed', 'cancelled']),
        'completed': tasks.filter(status='completed').order_by('-completed_at')[:10],
        'total': tasks.count(),
    }
    return render(request, 'operations/my_tasks.html', context)


@login_required
def kpi_list(request):
    """List all KPIs"""
    
    kpis = OperationsKPI.objects.all().order_by('category', 'name')
    
    category = request.GET.get('category', '')
    if category:
        kpis = kpis.filter(category=category)
    
    status = request.GET.get('status', '')
    if status:
        kpis = kpis.filter(status=status)
    
    stats = {
        'total': kpis.count(),
        'on_track': kpis.filter(status='on_track').count(),
        'warning': kpis.filter(status='warning').count(),
        'critical': kpis.filter(status='critical').count(),
        'achieved': kpis.filter(status='achieved').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'kpis': kpis,
        'stats': stats,
        'categories': OperationsKPI.KPI_CATEGORIES,
        'status_choices': OperationsKPI.KPI_STATUS,
        'selected_category': category,
        'selected_status': status,
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/kpi_list.html', context)


@login_required
def kpi_create(request):
    """Create new KPI"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('kpi_list')
    
    if request.method == 'POST':
        try:
            kpi = OperationsKPI.objects.create(
                name=request.POST.get('name'),
                category=request.POST.get('category'),
                description=request.POST.get('description', ''),
                unit=request.POST.get('unit', '%'),
                target_value=Decimal(request.POST.get('target_value', 0) or 0),
                current_value=Decimal(request.POST.get('current_value', 0) or 0),
                warning_threshold=Decimal(request.POST.get('warning_threshold', 70) or 70),
                critical_threshold=Decimal(request.POST.get('critical_threshold', 50) or 50),
                period_start=request.POST.get('period_start'),
                period_end=request.POST.get('period_end'),
                created_by=request.user,
                is_active=request.POST.get('is_active') == 'on',
            )
            kpi.update_status()
            messages.success(request, f'✅ KPI "{kpi.name}" created!')
            return redirect('kpi_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('kpi_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': OperationsKPI.KPI_CATEGORIES,
        'today': localdate().strftime('%Y-%m-%d'),
        'month_end': (localdate().replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1),
        'is_edit': False,
    }
    return render(request, 'operations/kpi_form.html', context)


@login_required
def kpi_edit(request, pk):
    """Edit KPI"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('kpi_list')
    
    kpi = get_object_or_404(OperationsKPI, pk=pk)
    
    if request.method == 'POST':
        try:
            kpi.name = request.POST.get('name')
            kpi.category = request.POST.get('category')
            kpi.description = request.POST.get('description', '')
            kpi.unit = request.POST.get('unit', '%')
            kpi.target_value = Decimal(request.POST.get('target_value', 0) or 0)
            kpi.current_value = Decimal(request.POST.get('current_value', 0) or 0)
            kpi.warning_threshold = Decimal(request.POST.get('warning_threshold', 70) or 70)
            kpi.critical_threshold = Decimal(request.POST.get('critical_threshold', 50) or 50)
            kpi.period_start = request.POST.get('period_start')
            kpi.period_end = request.POST.get('period_end')
            kpi.is_active = request.POST.get('is_active') == 'on'
            kpi.update_status()
            messages.success(request, '✅ KPI updated!')
            return redirect('kpi_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('kpi_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'kpi': kpi,
        'categories': OperationsKPI.KPI_CATEGORIES,
        'is_edit': True,
    }
    return render(request, 'operations/kpi_form.html', context)


@login_required
@require_POST
def kpi_delete(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    kpi = get_object_or_404(OperationsKPI, pk=pk)
    kpi.delete()
    messages.success(request, '🗑️ KPI deleted!')
    return redirect('kpi_list')


@login_required
def checklist_today(request):
    """Today's checklist"""
    
    today = localdate()
    department = request.GET.get('department', '')
    
    checklist = DailyChecklist.objects.filter(date=today)
    if department:
        checklist = checklist.filter(department=department)
    checklist = checklist.order_by('department', 'order')
    
    total = checklist.count()
    completed = checklist.filter(is_completed=True).count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'checklist': checklist,
        'today': today,
        'stats': {
            'total': total,
            'completed': completed,
            'pending': total - completed,
            'percent': (completed / total * 100) if total > 0 else 0,
        },
        'departments': BusinessOperationPlan.DEPARTMENTS,
        'selected_department': department,
        'can_manage': can_manage_operations(request.user),
    }
    return render(request, 'operations/checklist_today.html', context)


@login_required
def checklist_create(request):
    """Create new checklist item"""
    
    if not can_manage_operations(request.user):
        messages.error(request, 'Access denied!')
        return redirect('checklist_today')
    
    if request.method == 'POST':
        try:
            DailyChecklist.objects.create(
                date=request.POST.get('date'),
                department=request.POST.get('department'),
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                order=int(request.POST.get('order', 0) or 0),
                is_mandatory=request.POST.get('is_mandatory') == 'on',
            )
            messages.success(request, '✅ Checklist item created!')
            return redirect('checklist_today')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('checklist_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'departments': BusinessOperationPlan.DEPARTMENTS,
        'today': localdate().strftime('%Y-%m-%d'),
    }
    return render(request, 'operations/checklist_form.html', context)


@login_required
@require_POST
def checklist_complete(request, pk):
    item = get_object_or_404(DailyChecklist, pk=pk)
    item.complete(request.user)
    messages.success(request, f'✅ Completed: {item.title}')
    return redirect('checklist_today')


@login_required
def operation_alerts(request):
    """View all alerts"""
    
    alerts = OperationAlert.objects.all().order_by('-created_at')
    
    status_filter = request.GET.get('status', '')
    if status_filter == 'unread':
        alerts = alerts.filter(is_read=False)
    elif status_filter == 'unresolved':
        alerts = alerts.filter(is_resolved=False)
    elif status_filter == 'ai':
        alerts = alerts.filter(ai_generated=True)
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    stats = {
        'total': alerts.count(),
        'unread': alerts.filter(is_read=False).count(),
        'unresolved': alerts.filter(is_resolved=False).count(),
        'critical': alerts.filter(severity='critical').count(),
        'ai_generated': alerts.filter(ai_generated=True).count(),
    }
    
    paginator = Paginator(alerts, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'alerts': page_obj,
        'stats': stats,
        'severity_choices': OperationAlert.SEVERITY,
        'selected_status': status_filter,
        'selected_severity': severity,
    }
    return render(request, 'operations/alerts.html', context)


@login_required
@require_POST
def alert_mark_read(request, pk):
    alert = get_object_or_404(OperationAlert, pk=pk)
    alert.is_read = True
    alert.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def alert_resolve(request, pk):
    alert = get_object_or_404(OperationAlert, pk=pk)
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    messages.success(request, '✅ Alert resolved!')
    return redirect('operation_alerts')


@login_required
def run_ai_analysis(request):
    """Run AI analysis via AJAX"""
    
    if not request.user.is_superuser and not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        engine = AIOperationsEngine()
        result = engine.run_full_analysis()
        
        return JsonResponse({
            'success': True,
            'insights_created': result['insights_created'],
            'alerts_created': result['alerts_created'],
            'task_suggestions': result['task_suggestions'],
            'health_score': result['health_score'],
            'details': result['details'],
            'message': f"✅ AI Analysis Complete! Health: {result['health_score']}/100"
        })
    except Exception as e:
        logger.error(f"AI Analysis Error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def chatbot_api(request):
    """Chatbot API - Handles all queries"""
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        
        if not question:
            return JsonResponse({
                'success': False,
                'message': 'Question required'
            })
        
        # Get response from chatbot
        chatbot = BusinessChatbot(user=request.user)
        answer = chatbot.get_response(question)
        
        return JsonResponse({
            'success': True,
            'answer': answer,
            'question': question,
            'timestamp': now().isoformat(),
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON'
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Chatbot error: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Server error'
        })


@login_required
def announce_alerts_api(request):
    """API: Get alerts that need voice announcement"""
    
    try:
        alerts = []
        
        # ==========================================
        # 1. LOW STOCK ALERTS
        # ==========================================
        low_stock_items = Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).select_related('product')[:5]
        
        for item in low_stock_items:
            alerts.append({
                'id': f'lowstock_{item.id}',
                'type': 'low_stock',
                'product_name': item.product.name,
                'units': int(item.stock),
                'priority': 'high',
                'severity': 'warning',
            })
        
        # ==========================================
        # 2. OVERDUE TASKS
        # ==========================================
        try:
            from ..models import OperationTask
            from django.utils.timezone import now
            
            overdue_count = OperationTask.objects.filter(
                due_date__lt=now(),
                status__in=['pending', 'in_progress']
            ).count()
            
            if overdue_count > 0:
                alerts.append({
                    'id': f'overdue_{overdue_count}',
                    'type': 'overdue_task',
                    'count': overdue_count,
                    'priority': 'critical',
                    'severity': 'danger',
                })
        except:
            pass
        
        # ==========================================
        # 3. EMI DUE TODAY
        # ==========================================
        try:
            from ..models import SaleInstallment
            from django.utils.timezone import now
            
            today = now().date()
            
            due_emis = SaleInstallment.objects.filter(
                status__in=['pending', 'partial'],
                next_due_date=today
            ).select_related('sale__customer')[:3]
            
            for inst in due_emis:
                alerts.append({
                    'id': f'emi_{inst.id}',
                    'type': 'emi_due',
                    'customer_name': inst.sale.customer.name,
                    'amount': float(inst.remaining_amount()),
                    'priority': 'medium',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 4. LOW CASH BALANCE
        # ==========================================
        try:
            balance = CashBalance.get_balance()
            
            if balance < 10000:  # Rs. 10,000 se kam
                alerts.append({
                    'id': f'cash_low_{int(balance)}',
                    'type': 'cash_low',
                    'balance': float(balance),
                    'priority': 'high',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 5. OVERDUE PAYMENTS (Customer)
        # ==========================================
        try:
            from ..models import Customer
            
            overdue_customers = []
            for customer in Customer.objects.all()[:100]:
                balance = customer.adjusted_outstanding_balance()
                if balance > 50000:  # Rs. 50,000 se zyada
                    overdue_customers.append(customer)
                    if len(overdue_customers) >= 3:
                        break
            
            for customer in overdue_customers:
                alerts.append({
                    'id': f'payment_{customer.id}',
                    'type': 'payment_overdue',
                    'customer_name': customer.name,
                    'amount': float(customer.adjusted_outstanding_balance()),
                    'priority': 'medium',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 6. NEW WHATSAPP MESSAGES
        # ==========================================
        try:
            from ..models import Notification
            
            new_whatsapp = Notification.objects.filter(
                Q(user=request.user) | Q(user__isnull=True),
                category='whatsapp',
                is_read=False
            ).count()
            
            if new_whatsapp > 0:
                alerts.append({
                    'id': f'whatsapp_{new_whatsapp}',
                    'type': 'whatsapp',
                    'count': new_whatsapp,
                    'priority': 'low',
                    'severity': 'info',
                })
        except:
            pass
        
        # Return top 5 alerts by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        alerts.sort(key=lambda x: priority_order.get(x.get('priority', 'medium'), 2))
        
        return JsonResponse({
            'success': True,
            'alerts': alerts[:5],
            'total': len(alerts),
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Announce alerts error: {e}")
        return JsonResponse({
            'success': False,
            'alerts': [],
            'error': str(e),
        })


@login_required
def voice_announcement_settings(request):
    """Voice Announcement Settings Page"""
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_title': '🔊 Voice Announcement Settings',
    }
    return render(request, 'settings/voice_announcement.html', context)


@login_required
def ai_purchase_analysis(request):
    """API: Get AI analysis for a product"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'message': 'Product ID required'
            })
        
        product = get_object_or_404(Product, pk=product_id)
        warehouse = None
        
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Run AI analysis
        planner = AIPurchasePlanner(product, warehouse)
        result = planner.analyze()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"AI analysis API error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def ai_bulk_analysis(request):
    """API: Get AI analysis for multiple products"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        warehouse_id = request.GET.get('warehouse_id')
        warehouse = None
        
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Get products with sales activity
        from django.db.models import Sum
        from datetime import timedelta
        
        last_90 = localdate() - timedelta(days=90)
        
        active_products = Product.objects.filter(
            is_active=True,
            saleitem__sale__sale_date__date__gte=last_90
        ).distinct()[:20]
        
        results = []
        for product in active_products:
            try:
                planner = AIPurchasePlanner(product, warehouse)
                result = planner.analyze()
                
                if result['success']:
                    results.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'suggested_quantity': result['suggested_quantity'],
                        'confidence_score': result['confidence_score'],
                        'confidence_level': result['confidence_level'],
                        'risk_level': result['risk_level'],
                        'estimated_cost': result['estimated_cost'],
                        'is_urgent': result.get('is_urgent', False),
                        'current_stock': result['current_stock'],
                        'stock_coverage_days': result['stock_coverage_days'],
                    })
            except Exception as e:
                logger.warning(f"Failed for {product.name}: {e}")
                continue
        
        # Sort by urgency and confidence
        results.sort(
            key=lambda x: (
                not x['is_urgent'],
                -x['confidence_score'],
                -x['estimated_cost']
            )
        )
        
        return JsonResponse({
            'success': True,
            'analyses': results,
            'total': len(results),
        })
        
    except Exception as e:
        logger.error(f"Bulk analysis error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def ai_purchase_planner_dashboard(request):
    """AI Purchase Planner Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIPurchaseAnalysis, AIPurchaseInsight
    
    # Recent analyses
    recent_analyses = AIPurchaseAnalysis.objects.select_related(
        'product', 'warehouse'
    ).order_by('-created_at')[:20]
    
    # ✅ FIX: Python-level filter instead of JSON contains
    all_analyses = AIPurchaseAnalysis.objects.filter(
        user_accepted__isnull=True
    ).select_related('product', 'warehouse').order_by('-created_at')[:50]
    
    urgent_items = []
    for analysis in all_analyses:
        # Python mein check karo
        risk_factors = analysis.risk_factors or []
        if 'urgent' in risk_factors or analysis.risk_level == 'danger':
            urgent_items.append(analysis)
            if len(urgent_items) >= 10:
                break
    
    # Stats
    stats = {
        'total_analyses': AIPurchaseAnalysis.objects.count(),
        'high_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='high'
        ).count(),
        'medium_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='medium'
        ).count(),
        'low_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='low'
        ).count(),
        'danger_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='danger'
        ).count(),
        'warning_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='warning'
        ).count(),
        'safe_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='safe'
        ).count(),
    }
    
    # Insights
    insights = AIPurchaseInsight.objects.filter(
        is_resolved=False
    ).order_by('-impact_score')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'recent_analyses': recent_analyses,
        'urgent_items': urgent_items,
        'stats': stats,
        'insights': insights,
        'now': now(),
    }
    return render(request, 'ai/purchase_planner_dashboard.html', context)


@login_required
def ai_accept_suggestion(request, pk):
    """Accept AI suggestion and apply to plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        import json
        data = json.loads(request.body)
        
        analysis = get_object_or_404(AIPurchaseAnalysis, pk=pk)
        modified_qty = data.get('quantity')
        
        analysis.user_accepted = True
        analysis.user_modified_quantity = modified_qty
        analysis.user_notes = data.get('notes', '')
        analysis.save()
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Suggestion accepted! Quantity: {modified_qty or analysis.suggested_quantity}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def ai_reject_suggestion(request, pk):
    """Reject AI suggestion"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    analysis = get_object_or_404(AIPurchaseAnalysis, pk=pk)
    analysis.user_accepted = False
    analysis.save()
    
    return JsonResponse({'success': True, 'message': '❌ Suggestion rejected'})


@login_required
def ai_cash_dashboard(request):
    """AI Cash Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AICashAnalysis, AICashAlert, AICashHealthHistory
    
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
def ai_cash_forecast(request):
    """Detailed Cash Forecast"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AICashAnalysis
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
def ai_cash_alerts(request):
    """All Cash Alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AICashAlert
    
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
@require_POST
def ai_cash_alert_resolve(request, pk):
    """Resolve a cash alert"""
    
    from ..models import AICashAlert
    alert = get_object_or_404(AICashAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_cash_alerts')


@login_required
def ai_cash_health(request):
    """Cash Health Score Details"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AICashHealthHistory
    
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
def ai_shareholder_dashboard(request):
    """AI Shareholder Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import (
        AIShareholderScore, AIShareholderChurn,
        AIDividendRecommendation, AIShareholderAlert,
        AIShareholderForecast
    )
    
    # Run analysis if requested
    if request.GET.get('run') == 'true':
        try:
            engine = AIShareholderEngine()
            results = engine.run_full_analysis()
            
            messages.success(
                request,
                f"🤖 AI Analysis Complete! "
                f"Scored: {results['scores_calculated']} | "
                f"Churn: {results['churn_predictions']} | "
                f"Fraud: {results['fraud_alerts']}"
            )
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_shareholder_dashboard')
    
    # Get data
    top_shareholders = AIShareholderScore.objects.select_related(
        'shareholder'
    ).order_by('-overall_score')[:10]
    
    at_risk_shareholders = AIShareholderChurn.objects.select_related(
        'shareholder'
    ).filter(
        risk_level__in=['high', 'critical']
    ).order_by('-churn_probability')[:10]
    
    recent_alerts = AIShareholderAlert.objects.select_related(
        'shareholder'
    ).filter(
        is_resolved=False
    ).order_by('-created_at')[:10]
    
    dividend_recommendation = AIDividendRecommendation.objects.filter(
        status='pending'
    ).order_by('-created_at').first()
    
    forecast = AIShareholderForecast.objects.order_by('-forecast_date').first()
    
    # Stats
    total_shareholders = Shareholder.objects.filter(status='active').count()
    scored_shareholders = AIShareholderScore.objects.count()
    critical_risk = AIShareholderChurn.objects.filter(
        risk_level='critical'
    ).count()
    investment_at_risk = AIShareholderChurn.objects.filter(
        risk_level__in=['high', 'critical']
    ).aggregate(
        total=Sum('investment_at_risk')
    )['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'top_shareholders': top_shareholders,
        'at_risk_shareholders': at_risk_shareholders,
        'recent_alerts': recent_alerts,
        'dividend_recommendation': dividend_recommendation,
        'forecast': forecast,
        'total_shareholders': total_shareholders,
        'scored_shareholders': scored_shareholders,
        'critical_risk': critical_risk,
        'investment_at_risk': investment_at_risk,
        'total_alerts': recent_alerts.count(),
    }
    return render(request, 'ai/shareholder_dashboard.html', context)


@login_required
def ai_shareholder_scores(request):
    """View all shareholder scores"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIShareholderScore
    
    scores = AIShareholderScore.objects.select_related('shareholder').all()
    
    # Filter
    risk_level = request.GET.get('level', '')
    if risk_level:
        scores = scores.filter(risk_level=risk_level)
    
    # Stats
    stats = {
        'total': scores.count(),
        'excellent': scores.filter(risk_level='excellent').count(),
        'good': scores.filter(risk_level='good').count(),
        'warning': scores.filter(risk_level='warning').count(),
        'critical': scores.filter(risk_level='critical').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'scores': scores,
        'stats': stats,
        'selected_level': risk_level,
    }
    return render(request, 'ai/shareholder_scores.html', context)


@login_required
def ai_shareholder_churn(request):
    """View churn predictions"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIShareholderChurn
    
    churn_data = AIShareholderChurn.objects.select_related('shareholder').all()
    
    risk_level = request.GET.get('level', '')
    if risk_level:
        churn_data = churn_data.filter(risk_level=risk_level)
    
    stats = {
        'total': churn_data.count(),
        'low': churn_data.filter(risk_level='low').count(),
        'medium': churn_data.filter(risk_level='medium').count(),
        'high': churn_data.filter(risk_level='high').count(),
        'critical': churn_data.filter(risk_level='critical').count(),
        'at_risk_amount': churn_data.filter(
            risk_level__in=['high', 'critical']
        ).aggregate(total=Sum('investment_at_risk'))['total'] or 0,
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'churn_data': churn_data,
        'stats': stats,
        'selected_level': risk_level,
    }
    return render(request, 'ai/shareholder_churn.html', context)


@login_required
def ai_dividend_recommendation(request):
    """View dividend recommendations"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIDividendRecommendation
    
    # Get latest recommendation
    recommendations = AIDividendRecommendation.objects.all().order_by('-created_at')
    latest = recommendations.first()
    
    # Generate new if requested
    if request.GET.get('generate') == 'true':
        engine = AIShareholderEngine()
        new_rec = engine.recommend_dividend()
        
        if new_rec:
            messages.success(request, f"✅ New recommendation: {new_rec.recommended_percentage}%")
        else:
            messages.warning(request, "⚠️ Cannot generate recommendation (no profit)")
        
        return redirect('ai_dividend_recommendation')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'recommendations': recommendations,
        'latest': latest,
    }
    return render(request, 'ai/dividend_recommendation.html', context)


@login_required
def ai_shareholder_alerts(request):
    """View all shareholder AI alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIShareholderAlert
    
    alerts = AIShareholderAlert.objects.select_related('shareholder').all()
    
    alert_type = request.GET.get('type', '')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'medium': alerts.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts,
        'stats': stats,
        'selected_type': alert_type,
        'selected_severity': severity,
        'selected_status': status,
        'alert_types': AIShareholderAlert.ALERT_TYPES,
        'severity_levels': AIShareholderAlert.SEVERITY,
    }
    return render(request, 'ai/shareholder_alerts.html', context)


@login_required
def ai_shareholder_forecast(request):
    """6-Month Shareholder Forecast"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIShareholderForecast
    import json
    
    forecast = AIShareholderForecast.objects.order_by('-forecast_date').first()
    
    if request.GET.get('generate') == 'true':
        engine = AIShareholderEngine()
        forecast = engine.generate_forecast()
        messages.success(request, "✅ New forecast generated!")
        return redirect('ai_shareholder_forecast')
    
    # Chart data
    chart_labels = []
    chart_values = []
    
    if forecast and forecast.monthly_forecast:
        for m in forecast.monthly_forecast:
            chart_labels.append(m['month'])
            chart_values.append(m['expected_shareholders'])
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'forecast': forecast,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
    }
    return render(request, 'ai/shareholder_forecast.html', context)


@login_required
@require_POST
def ai_shareholder_alert_resolve(request, pk):
    """Resolve a shareholder alert"""
    
    from ..models import AIShareholderAlert
    alert = get_object_or_404(AIShareholderAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_shareholder_alerts')


@login_required
def ai_board_room_dashboard(request):
    """Main AI Board Room Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBoardMeeting, AIBoardMember, AIBoardAlert, AIBoardKPI
    
    # Run meeting if requested
    if request.GET.get('run') == 'true':
        try:
            board = AIBoardRoom()
            results = board.run_full_board_meeting()
            
            if results['success']:
                messages.success(
                    request,
                    f"🏢 Board Meeting Complete! "
                    f"Health: {results['overall_health']}/100 | "
                    f"Alerts: {results['alerts_created']} | "
                    f"Impact: Rs. {results['total_savings'] + results['total_revenue']:,.0f}"
                )
            else:
                messages.error(request, f"❌ Error: {results.get('error', 'Unknown')}")
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_board_room_dashboard')
    
    # Get latest meeting
    latest_meeting = AIBoardMeeting.objects.order_by('-meeting_date', '-created_at').first()
    
    # Get all members for latest
    if latest_meeting:
        members = latest_meeting.board_members.all().order_by('member_type')
    else:
        members = []
    
    # ==========================================
    # ✅ FIX: Base queryset PEHLE banao
    # ==========================================
    base_alerts = AIBoardAlert.objects.filter(is_resolved=False)
    
    # ✅ Stats from FULL queryset (slice se PEHLE)
    total_alerts = base_alerts.count()
    critical_alerts = base_alerts.filter(severity='critical').count()
    high_alerts = base_alerts.filter(severity='high').count()
    medium_alerts = base_alerts.filter(severity='medium').count()
    
    # ✅ Ab slice karo display ke liye
    alerts = base_alerts.order_by('-created_at')[:15]
    
    # KPI history
    kpis = AIBoardKPI.objects.order_by('-date')[:30]
    
    # Chart data
    kpi_labels = [k.date.strftime('%d-%b') for k in reversed(list(kpis))]
    kpi_health = [k.overall_health for k in reversed(list(kpis))]
    kpi_revenue = [float(k.revenue) for k in reversed(list(kpis))]
    
    # Stats
    stats = {
        'total_meetings': AIBoardMeeting.objects.count(),
        'active_alerts': total_alerts,       # ✅ From base
        'critical_alerts': critical_alerts,  # ✅ From base
        'high_alerts': high_alerts,          # ✅ From base
        'medium_alerts': medium_alerts,      # ✅ From base
        'total_savings': AIBoardMeeting.objects.aggregate(
            total=Sum('total_potential_savings')
        )['total'] or 0,
        'total_revenue': AIBoardMeeting.objects.aggregate(
            total=Sum('total_potential_revenue')
        )['total'] or 0,
    }
    
    import json
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': latest_meeting,
        'members': members,
        'alerts': alerts,                # ✅ Sliced list for display
        'stats': stats,
        'kpi_labels': json.dumps(kpi_labels),
        'kpi_health': json.dumps(kpi_health),
        'kpi_revenue': json.dumps(kpi_revenue),
        'today': localdate(),
    }
    return render(request, 'ai/board_room_dashboard.html', context)


@login_required
def ai_board_member_detail(request, member_type):
    """View individual board member report"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBoardMember
    
    # Get latest report for this member
    member = AIBoardMember.objects.filter(
        member_type=member_type
    ).order_by('-report_date', '-created_at').first()
    
    if not member:
        messages.warning(request, f"No report found for {member_type}. Run board meeting first.")
        return redirect('ai_board_room_dashboard')
    
    # History
    history = AIBoardMember.objects.filter(
        member_type=member_type
    ).order_by('-report_date')[:30]
    
    import json
    chart_labels = [h.report_date.strftime('%d-%b') for h in reversed(list(history))]
    chart_scores = [h.health_score for h in reversed(list(history))]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'member': member,
        'history': history,
        'chart_labels': json.dumps(chart_labels),
        'chart_scores': json.dumps(chart_scores),
    }
    return render(request, 'ai/board_member_detail.html', context)


@login_required
def ai_board_meetings_list(request):
    """List all board meetings"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBoardMeeting
    
    meetings = AIBoardMeeting.objects.order_by('-meeting_date', '-created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meetings': meetings,
    }
    return render(request, 'ai/board_meetings_list.html', context)


@login_required
def ai_board_meeting_detail(request, pk):
    """View detailed board meeting"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBoardMeeting
    
    meeting = get_object_or_404(AIBoardMeeting, pk=pk)
    members = meeting.board_members.all().order_by('member_type')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': meeting,
        'members': members,
    }
    return render(request, 'ai/board_meeting_detail.html', context)


@login_required
def ai_board_alerts(request):
    """View all board alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBoardAlert
    
    alerts = AIBoardAlert.objects.all().order_by('-created_at')
    
    # Filters
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    source = request.GET.get('source', '')
    if source:
        alerts = alerts.filter(source=source)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'medium': alerts.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts,
        'stats': stats,
        'selected_severity': severity,
        'selected_source': source,
        'selected_status': status,
    }
    return render(request, 'ai/board_alerts.html', context)


@login_required
@require_POST
def ai_board_alert_resolve(request, pk):
    """Resolve a board alert"""
    
    from ..models import AIBoardAlert
    alert = get_object_or_404(AIBoardAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_board_alerts')


@login_required
def ai_cso_tech_dashboard(request):
    """CSO Tech Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import (
        AIBugReport, AIPerformanceIssue, AIFeatureSuggestion,
        AISystemHealth, AISecurityLog
    )
    
    # Run analysis if requested
    if request.GET.get('run') == 'true':
        try:
            engine = AICSOTechEngine()
            report = engine.run_full_analysis()
            
            messages.success(
                request,
                f"💻 CSO Tech Analysis Complete! "
                f"Health: {report['health_score']}/100 | "
                f"Warnings: {len(report['warnings'])}"
            )
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_cso_tech_dashboard')
    
    # Get latest system health
    latest_health = AISystemHealth.objects.order_by('-date').first()
    
    # Stats
    active_bugs = AIBugReport.objects.filter(status__in=['new', 'investigating'])
    performance_issues = AIPerformanceIssue.objects.filter(is_resolved=False)
    pending_features = AIFeatureSuggestion.objects.filter(status='pending')
    security_alerts = AISecurityLog.objects.filter(is_resolved=False)
    
    stats = {
        'system_health': latest_health.health_score if latest_health else 100,
        'active_bugs': active_bugs.count(),
        'critical_bugs': active_bugs.filter(severity='critical').count(),
        'performance_issues': performance_issues.count(),
        'pending_features': pending_features.count(),
        'security_alerts': security_alerts.count(),
    }
    
    # Recent items
    recent_bugs = active_bugs.order_by('-frequency')[:5]
    recent_issues = performance_issues.order_by('-priority')[:5]
    recent_features = pending_features.order_by('-roi_score')[:5]
    recent_security = security_alerts.order_by('-created_at')[:5]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'stats': stats,
        'latest_health': latest_health,
        'recent_bugs': recent_bugs,
        'recent_issues': recent_issues,
        'recent_features': recent_features,
        'recent_security': recent_security,
    }
    return render(request, 'ai/cso_tech_dashboard.html', context)


@login_required
def ai_cso_tech_security(request):
    """Security Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AISecurityLog
    
    alerts = AISecurityLog.objects.all().order_by('-created_at')
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    # Stats - BEFORE slice
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'medium': alerts.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts[:50],
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_security.html', context)


@login_required
def ai_cso_tech_performance(request):
    """Performance Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIPerformanceIssue, AISystemHealth
    
    issues = AIPerformanceIssue.objects.all().order_by('-priority', '-created_at')
    health_records = AISystemHealth.objects.order_by('-date')[:30]
    
    # Stats
    stats = {
        'total_issues': issues.count(),
        'unresolved': issues.filter(is_resolved=False).count(),
        'critical': issues.filter(priority__gte=8, is_resolved=False).count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'issues': issues,
        'health_records': health_records,
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_performance.html', context)


@login_required
def ai_cso_tech_bugs(request):
    """Bugs Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIBugReport
    
    bugs = AIBugReport.objects.all().order_by('-frequency', '-last_seen')
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        bugs = bugs.filter(status__in=['new', 'investigating'])
    elif status == 'fixed':
        bugs = bugs.filter(status__in=['fixed', 'closed'])
    
    # Stats BEFORE slice
    stats = {
        'total': bugs.count(),
        'critical': bugs.filter(severity='critical').count(),
        'high': bugs.filter(severity='high').count(),
        'medium': bugs.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'bugs': bugs[:50],
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_bugs.html', context)


@login_required
def ai_cso_tech_features(request):
    """Feature Suggestions Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AIFeatureSuggestion
    
    features = AIFeatureSuggestion.objects.all().order_by('-roi_score', '-created_at')
    
    status = request.GET.get('status', 'pending')
    if status:
        features = features.filter(status=status)
    
    stats = {
        'total': features.count(),
        'pending': features.filter(status='pending').count(),
        'in_progress': features.filter(status='in_progress').count(),
        'completed': features.filter(status='completed').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'features': features,
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_features.html', context)


@login_required
def ai_cso_tech_system(request):
    """System Health Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import AISystemHealth
    import json
    
    health_records = AISystemHealth.objects.order_by('-date')[:60]
    
    # Chart data
    labels = [h.date.strftime('%d-%b %H:%M') for h in reversed(list(health_records))]
    scores = [h.health_score for h in reversed(list(health_records))]
    memory = [float(h.memory_usage) for h in reversed(list(health_records))]
    disk = [float(h.disk_usage) for h in reversed(list(health_records))]
    
    # Latest
    latest = health_records.first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'latest': latest,
        'records': health_records,
        'chart_labels': json.dumps(labels),
        'chart_scores': json.dumps(scores),
        'chart_memory': json.dumps(memory),
        'chart_disk': json.dumps(disk),
    }
    return render(request, 'ai/cso_tech_system.html', context)


@login_required
def cash_strategies_list(request):
    """List all cash investment strategies"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import CashInvestmentStrategy
    
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
def cash_strategy_detail(request, pk):
    """View strategy details"""
    
    from ..models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'strategy': strategy,
    }
    return render(request, 'ai/cash_strategy_detail.html', context)


@login_required
@require_POST
def cash_strategy_approve(request, pk):
    """Approve a cash strategy"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    strategy.approve(request.user)
    
    messages.success(request, f'✅ Strategy "{strategy.name}" approved!')
    return redirect('cash_strategies_list')


@login_required
@require_POST
def cash_strategy_execute(request, pk):
    """Start executing strategy"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    strategy.start_execution()
    
    messages.success(request, f'⚙️ Strategy "{strategy.name}" started!')
    return redirect('cash_strategies_list')


@login_required
def cash_strategy_complete(request, pk):
    """Complete a strategy with actual results"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import CashInvestmentStrategy
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
@require_POST
def cash_strategy_cancel(request, pk):
    """Cancel a strategy"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Only superuser can cancel strategies!')
        return redirect('cash_strategies_list')
    
    from ..models import CashInvestmentStrategy
    strategy = get_object_or_404(CashInvestmentStrategy, pk=pk)
    reason = request.POST.get('reason', '')
    strategy.cancel(reason)
    
    messages.success(request, f'❌ Strategy "{strategy.name}" cancelled!')
    return redirect('cash_strategies_list')


@login_required
def strategy_allocations_list(request):
    """List all strategy allocation profiles"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import StrategyAllocation
    
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
def strategy_allocation_create(request):
    """Create new strategy allocation with Fast-Moving"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import StrategyAllocation
    
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
def strategy_allocation_edit(request, pk):
    """Edit strategy allocation with Fast-Moving"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import StrategyAllocation
    
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
def strategy_allocation_activate(request, pk):
    """Activate a strategy allocation"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ..models import StrategyAllocation
    
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
def strategy_allocation_delete(request, pk):
    """Delete a strategy allocation"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Only superuser can delete profiles!')
        return redirect('strategy_allocations_list')
    
    from ..models import StrategyAllocation
    
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
def strategy_allocation_preview(request, pk):
    """Preview with Fast-Moving + Custom ROI"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    from ..models import StrategyAllocation
    
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
def emergency_fund_dashboard(request):
    """Emergency Fund Dashboard"""
    
    from ..models import EmergencyFund, EmergencyFundTransaction, Expense
    
    # Fund nikalo
    fund = EmergencyFund.get_active_fund()
    
    # Agar nahi hai to banao
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
@require_POST
def emergency_fund_add(request):
    """Emergency Fund mein paisa daalo"""
    
    from ..models import EmergencyFund, EmergencyFundTransaction
    
    fund_id = request.POST.get('fund_id')
    amount = Decimal(request.POST.get('amount', 0))
    description = request.POST.get('description', '')
    
    if amount <= 0:
        messages.error(request, '❌ Amount 0 se zyada hona chahiye')
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
                f'✅ Rs. {amount:,.2f} Emergency Fund mein add ho gaya!\n'
                f'💰 New Balance: Rs. {new_balance:,.2f}'
            )
    
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('emergency_fund_dashboard')


@login_required
@require_POST
def emergency_fund_withdraw(request):
    """Emergency Fund se paisa nikalo"""
    
    from ..models import EmergencyFund, EmergencyFundTransaction
    
    fund_id = request.POST.get('fund_id')
    amount = Decimal(request.POST.get('amount', 0))
    reason = request.POST.get('reason', '')
    
    if amount <= 0:
        messages.error(request, '❌ Amount 0 se zyada hona chahiye')
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
                f'💸 Rs. {amount:,.2f} Emergency Fund se nikala gaya\n'
                f'💰 Remaining: Rs. {new_balance:,.2f}'
            )
    
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('emergency_fund_dashboard')


@login_required
def emergency_fund_settings(request):
    """Emergency Fund ki settings"""
    
    from ..models import EmergencyFund
    
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
            
            messages.success(request, '✅ Settings update ho gayi!')
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
def business_ratios_dashboard(request):
    """CFO-Level Business Ratios Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can view ratios.')
        return redirect('dashboard')
    
    from ..business_ratios import BusinessRatios
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
