"""Frontend views: ai/operations (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from ...models import CompanyInfo, Employee
from ...ai.ai_operations_engine import AIOperationsEngine


def can_manage_operations(user):
    """Check if user can manage operations"""
    if user.is_superuser:
        return True
    if user.groups.filter(name__in=['Owner', 'Store Manager', 'Operations Manager']).exists():
        return True
    return False


@login_required
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
@require_POST
def operation_plan_approve(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    plan.approve(request.user)
    messages.success(request, f'✅ Plan #{plan.plan_no} approved!')
    return redirect('operation_plan_detail', pk=pk)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def operation_plan_complete(request, pk):
    if not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    plan = get_object_or_404(BusinessOperationPlan, pk=pk)
    plan.complete(request.user)
    messages.success(request, f'🎯 Plan #{plan.plan_no} completed!')
    return redirect('operation_plan_detail', pk=pk)


@login_required
@perm_required('manage_ai_ops')
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
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
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
@perm_required('manage_ai_ops')
@require_POST
def checklist_complete(request, pk):
    item = get_object_or_404(DailyChecklist, pk=pk)
    item.complete(request.user)
    messages.success(request, f'✅ Completed: {item.title}')
    return redirect('checklist_today')


@login_required
@perm_required('use_ai', 'manage_ai_ops')
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
@perm_required('manage_ai_ops')
@require_POST
def alert_mark_read(request, pk):
    alert = get_object_or_404(OperationAlert, pk=pk)
    alert.is_read = True
    alert.save()
    return JsonResponse({'success': True})


@login_required
@perm_required('manage_ai_ops')
@require_POST
def alert_resolve(request, pk):
    alert = get_object_or_404(OperationAlert, pk=pk)
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    messages.success(request, '✅ Alert resolved!')
    return redirect('operation_alerts')
