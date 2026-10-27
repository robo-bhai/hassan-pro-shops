"""Frontend views: finance/budgets (split from the former expenses_budget.py)."""
from ...security.permissions import perm_required
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from ...models import CompanyInfo, Expense, Department, Project


@login_required
@perm_required('view_financials', 'manage_budget')
def expense_budget_list(request):
    """List all budgets"""
    
    budgets = ExpenseBudget.objects.select_related('category', 'department', 'project', 'approved_by').all()
    
    search = request.GET.get('search', '')
    if search:
        budgets = budgets.filter(
            Q(name__icontains=search) |
            Q(category__name__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        budgets = budgets.filter(status=status)
    
    # Calculate utilization
    for budget in budgets:
        budget.utilization = budget.budget_utilization_percent()
        budget.is_over = budget.is_over_budget()
        budget.expense_count = budget.expenses.count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budgets': budgets,
        'search': search,
        'status': status,
        'status_choices': ExpenseBudget.BUDGET_STATUS,
        'total_budgets': budgets.count(),
        'active_budgets': budgets.filter(status='active').count(),
        'over_budget': [b for b in budgets if b.is_over_budget()],
        'total_allocated': sum(b.allocated_amount for b in budgets),
        'total_used': sum(b.used_amount for b in budgets),
    }
    return render(request, 'expenses/budget_list.html', context)


@login_required
@perm_required('manage_budget')
def expense_budget_create(request):
    """Create new budget"""
    
    if request.method == 'POST':
        try:
            budget = ExpenseBudget.objects.create(
                name=request.POST.get('name'),
                category_id=request.POST.get('category'),
                budget_period=request.POST.get('budget_period'),
                period_start=request.POST.get('period_start'),
                period_end=request.POST.get('period_end'),
                allocated_amount=Decimal(request.POST.get('allocated_amount', 0)),
                status='draft',
                created_by=request.user,
                notes=request.POST.get('notes', '')
            )
            messages.success(request, f'✅ Budget "{budget.name}" created!')
            return redirect('expense_budget_detail', pk=budget.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_budget_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'budget_periods': ExpenseBudget.BUDGET_PERIODS,
    }
    return render(request, 'expenses/budget_create.html', context)


@login_required
@perm_required('view_financials', 'manage_budget')
def expense_budget_detail(request, pk):
    """Budget detail view"""
    
    budget = get_object_or_404(ExpenseBudget, pk=pk)
    expenses = budget.expenses.all().order_by('-expense_date')
    
    # Calculate budget utilization
    utilization = budget.budget_utilization_percent()
    is_over = budget.is_over_budget()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
        'expenses': expenses,
        'utilization': utilization,
        'is_over': is_over,
        'total_expenses': budget.used_amount,
        'remaining': budget.remaining_amount,
        'expense_count': expenses.count(),
    }
    return render(request, 'expenses/budget_detail.html', context)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_dashboard(request):
    """
    Professional Budget Dashboard
    Shows budget overview, utilization, and alerts
    """
    today = date.today()
    month_start = today.replace(day=1)
    
    # ========================================== #
    # 1. GET ACTIVE BUDGETS                     #
    # ========================================== #
    active_budgets = Budget.objects.filter(
        status='active',
        period_start__lte=today,
        period_end__gte=today
    ).select_related('department', 'project', 'category')
    
    # ========================================== #
    # 2. CALCULATE STATISTICS                   #
    # ========================================== #
    total_budgets = active_budgets.count()
    total_allocated = active_budgets.aggregate(
        total=Sum('allocated_amount')
    )['total'] or Decimal('0.00')
    
    total_used = active_budgets.aggregate(
        total=Sum('used_amount')
    )['total'] or Decimal('0.00')
    
    total_remaining = total_allocated - total_used
    utilization_percent = (total_used / total_allocated * 100) if total_allocated > 0 else 0
    
    # ========================================== #
    # 3. BUDGET ALERTS (Professional)           #
    # ========================================== #
    over_budget = []
    near_limit = []
    critical = []
    
    for budget in active_budgets:
        util = budget.utilization_percent()
        if util >= 95:
            critical.append(budget)
        elif util >= 80:
            near_limit.append(budget)
        
        if budget.is_over_budget():
            over_budget.append(budget)
    
    # ========================================== #
    # 4. DEPARTMENT WISE SUMMARY                #
    # ========================================== #
    department_summary = []
    departments = Department.objects.filter(is_active=True)
    
    for dept in departments:
        dept_budgets = active_budgets.filter(department=dept)
        if dept_budgets.exists():
            allocated = dept_budgets.aggregate(
                total=Sum('allocated_amount')
            )['total'] or Decimal('0.00')
            
            used = dept_budgets.aggregate(
                total=Sum('used_amount')
            )['total'] or Decimal('0.00')
            
            department_summary.append({
                'name': dept.name,
                'allocated': float(allocated),
                'used': float(used),
                'remaining': float(allocated - used),
                'utilization': float((used / allocated * 100) if allocated > 0 else 0),
                'budget_count': dept_budgets.count()
            })
    
    department_summary.sort(key=lambda x: x['utilization'], reverse=True)
    
    # ========================================== #
    # 5. TREND DATA (Last 6 Months)             #
    # ========================================== #
    trend_data = []
    for i in range(6):
        month_date = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        month_end = (month_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_budgets = Budget.objects.filter(
            period_start__lte=month_date,
            period_end__gte=month_end,
            status='active'
        )
        
        allocated = month_budgets.aggregate(
            total=Sum('allocated_amount')
        )['total'] or Decimal('0.00')
        
        used = month_budgets.aggregate(
            total=Sum('used_amount')
        )['total'] or Decimal('0.00')
        
        trend_data.append({
            'month': month_date.strftime('%b %Y'),
            'allocated': float(allocated),
            'used': float(used)
        })
    trend_data.reverse()
    
    # ========================================== #
    # 6. QUICK STATS                           #
    # ========================================== #
    quick_stats = {
        'total_budgets': total_budgets,
        'total_allocated': float(total_allocated),
        'total_used': float(total_used),
        'total_remaining': float(total_remaining),
        'utilization_percent': float(utilization_percent),
        'over_budget_count': len(over_budget),
        'near_limit_count': len(near_limit),
        'critical_count': len(critical),
        'active_budgets_count': active_budgets.count(),
    }
    
    # ========================================== #
    # 7. RECENT BUDGET ALERTS                   #
    # ========================================== #
    budget_alerts = []
    # Add custom alerts logic here
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'quick_stats': quick_stats,
        'active_budgets': active_budgets[:10],
        'department_summary': department_summary,
        'trend_data': json.dumps(trend_data),
        'budget_alerts': budget_alerts,
        'over_budget': over_budget[:5],
        'near_limit': near_limit[:5],
        'critical': critical[:5],
        'today': today,
        'month_start': month_start,
    }
    
    return render(request, 'budgets/dashboard.html', context)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_list(request):
    """List all budgets"""
    
    budgets = Budget.objects.select_related('department', 'project', 'category').all()
    
    # Filters
    search = request.GET.get('search', '')
    if search:
        budgets = budgets.filter(
            Q(name__icontains=search) |
            Q(budget_no__icontains=search) |
            Q(description__icontains=search)
        )
    
    budget_type = request.GET.get('type', '')
    if budget_type:
        budgets = budgets.filter(budget_type=budget_type)
    
    status = request.GET.get('status', '')
    if status:
        budgets = budgets.filter(status=status)
    
    department = request.GET.get('department', '')
    if department:
        budgets = budgets.filter(department_id=department)
    
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        budgets = budgets.filter(period_start__gte=from_date)
    if to_date:
        budgets = budgets.filter(period_end__lte=to_date)
    
    # Calculate utilization for each budget
    for budget in budgets:
        budget.utilization = budget.utilization_percent()
        budget.is_over = budget.is_over_budget()
        #budget.is_near = budget.is_near_limit()
    
    # Stats
    total_budgets = budgets.count()
    total_allocated = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    total_used = budgets.aggregate(total=Sum('used_amount'))['total'] or 0
    active_count = budgets.filter(status='active').count()
    over_budget_count = sum(1 for b in budgets if b.is_over_budget())
    
    paginator = Paginator(budgets, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'budgets': page_obj,
        'search': search,
        'budget_type': budget_type,
        'status': status,
        'department': department,
        'from_date': from_date,
        'to_date': to_date,
        'total_budgets': total_budgets,
        'total_allocated': total_allocated,
        'total_used': total_used,
        'active_count': active_count,
        'over_budget_count': over_budget_count,
        'budget_types': Budget.BUDGET_TYPES,
        'status_choices': Budget.BUDGET_STATUS,
        'departments': Department.objects.filter(is_active=True),
    }
    return render(request, 'budgets/list.html', context)


@login_required
@perm_required('manage_budget')
def budget_create(request):
    """Create new budget"""
    
    if request.method == 'POST':
        try:
            budget = Budget.objects.create(
                name=request.POST.get('name'),
                budget_type=request.POST.get('budget_type'),
                description=request.POST.get('description', ''),
                allocated_amount=Decimal(request.POST.get('allocated_amount', 0)),
                period_start=request.POST.get('period_start'),
                period_end=request.POST.get('period_end'),
                frequency=request.POST.get('frequency', 'monthly'),
                department_id=request.POST.get('department') or None,
                project_id=request.POST.get('project') or None,
                category_id=request.POST.get('category') or None,
                alert_threshold=Decimal(request.POST.get('alert_threshold', 80)),
                critical_threshold=Decimal(request.POST.get('critical_threshold', 95)),
                allow_rollover=request.POST.get('allow_rollover') == 'on',
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='draft'
            )
            
            # Add allocations
            category_ids = request.POST.getlist('category_ids[]')
            allocated_amounts = request.POST.getlist('allocated_amounts[]')
            
            for i, cat_id in enumerate(category_ids):
                if cat_id and Decimal(allocated_amounts[i]) > 0:
                    BudgetAllocation.objects.create(
                        budget=budget,
                        category_id=cat_id,
                        allocated_amount=Decimal(allocated_amounts[i])
                    )
            
            messages.success(request, f'✅ Budget "{budget.name}" created successfully!')
            return redirect('budget_detail', pk=budget.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('budget_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget_types': Budget.BUDGET_TYPES,
        'budget_frequencies': Budget.BUDGET_FREQUENCY,
        'departments': Department.objects.filter(is_active=True),
        'projects': Project.objects.filter(is_active=True),
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'today': date.today().strftime('%Y-%m-%d'),
        'next_month': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
    }
    return render(request, 'budgets/create.html', context)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_detail(request, pk):
    """Budget detail view"""
    
    budget = get_object_or_404(Budget, pk=pk)
    allocations = budget.allocations.all()
    transactions = budget.transactions.all().order_by('-performed_at')
    alerts = budget.alerts.all().order_by('-triggered_at')
    
    # ✅ Calculate utilization for each allocation
    from django.db.models import Sum
    from ...models import Expense
    
    for alloc in allocations:
        # Calculate used amount from expenses (including paid)
        used = Expense.objects.filter(
            category=alloc.category,
            budget=budget,
            status__in=['approved', 'paid'],
            expense_date__gte=budget.period_start,
            expense_date__lte=budget.period_end
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        alloc.used_amount = used
        alloc.utilization_percent = alloc.utilization_percent()
        alloc.is_over = alloc.used_amount > alloc.allocated_amount
    
    # Calculate budget metrics
    budget.calculate_used()  # ✅ This will update used amount
    budget.utilization = budget.utilization_percent()
    budget.is_over = budget.is_over_budget()
    budget.daily_allowance = budget.daily_allowance()
    budget.remaining_days = budget.remaining_days()
    budget.utilization_percent = budget.utilization_percent()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
        'allocations': allocations,
        'transactions': transactions,
        'alerts': alerts,
        'can_submit': budget.status == 'draft',
        'can_approve': budget.status == 'pending',
        'can_activate': budget.status == 'approved',
    }
    return render(request, 'budgets/detail.html', context)


@login_required
@perm_required('manage_budget')
def budget_edit(request, pk):
    """Edit budget"""
    
    budget = get_object_or_404(Budget, pk=pk)
    
    if budget.status not in ['draft', 'rejected']:
        messages.error(request, '❌ Only draft or rejected budgets can be edited!')
        return redirect('budget_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            budget.name = request.POST.get('name')
            budget.budget_type = request.POST.get('budget_type')
            budget.description = request.POST.get('description', '')
            budget.allocated_amount = Decimal(request.POST.get('allocated_amount', 0))
            budget.period_start = request.POST.get('period_start')
            budget.period_end = request.POST.get('period_end')
            budget.frequency = request.POST.get('frequency', 'monthly')
            budget.department_id = request.POST.get('department') or None
            budget.project_id = request.POST.get('project') or None
            budget.category_id = request.POST.get('category') or None
            budget.alert_threshold = Decimal(request.POST.get('alert_threshold', 80))
            budget.critical_threshold = Decimal(request.POST.get('critical_threshold', 95))
            budget.allow_rollover = request.POST.get('allow_rollover') == 'on'
            budget.notes = request.POST.get('notes', '')
            budget.save()
            
            # Update allocations
            budget.allocations.all().delete()
            
            category_ids = request.POST.getlist('category_ids[]')
            allocated_amounts = request.POST.getlist('allocated_amounts[]')
            
            for i, cat_id in enumerate(category_ids):
                if cat_id and Decimal(allocated_amounts[i]) > 0:
                    BudgetAllocation.objects.create(
                        budget=budget,
                        category_id=cat_id,
                        allocated_amount=Decimal(allocated_amounts[i])
                    )
            
            messages.success(request, f'✅ Budget "{budget.name}" updated!')
            return redirect('budget_detail', pk=budget.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('budget_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
        'budget_types': Budget.BUDGET_TYPES,
        'budget_frequencies': Budget.BUDGET_FREQUENCY,
        'departments': Department.objects.filter(is_active=True),
        'projects': Project.objects.filter(is_active=True),
        'categories': ExpenseCategory.objects.filter(is_active=True),
    }
    return render(request, 'budgets/edit.html', context)


@login_required
@perm_required('manage_budget')
def budget_delete(request, pk):
    """Delete budget"""
    
    budget = get_object_or_404(Budget, pk=pk)
    
    if budget.status not in ['draft', 'cancelled']:
        messages.error(request, '❌ Only draft or cancelled budgets can be deleted!')
        return redirect('budget_detail', pk=pk)
    
    if request.method == 'POST':
        name = budget.name
        budget.delete()
        messages.success(request, f'🗑️ Budget "{name}" deleted!')
        return redirect('budget_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
    }
    return render(request, 'budgets/delete.html', context)


@login_required
@perm_required('manage_budget')
def budget_submit(request, pk):
    """Submit budget for approval"""
    
    budget = get_object_or_404(Budget, pk=pk)
    
    if budget.status != 'draft':
        messages.error(request, '❌ Only draft budgets can be submitted!')
        return redirect('budget_detail', pk=pk)
    
    budget.submit(request.user)
    messages.success(request, f'📤 Budget "{budget.name}" submitted for approval!')
    return redirect('budget_detail', pk=pk)


@login_required
@perm_required('manage_budget')
def budget_approve(request, pk):
    """Approve budget"""
    
    budget = get_object_or_404(Budget, pk=pk)
    
    if budget.status != 'pending':
        messages.error(request, '❌ Only pending budgets can be approved!')
        return redirect('budget_detail', pk=pk)
    
    if request.method == 'POST':
        budget.approve(request.user)
        messages.success(request, f'✅ Budget "{budget.name}" approved!')
        return redirect('budget_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
    }
    return render(request, 'budgets/approve.html', context)


@login_required
@perm_required('manage_budget')
def budget_activate(request, pk):
    """Activate budget"""
    
    budget = get_object_or_404(Budget, pk=pk)
    
    if budget.status != 'approved':
        messages.error(request, '❌ Only approved budgets can be activated!')
        return redirect('budget_detail', pk=pk)
    
    budget.activate(request.user)
    messages.success(request, f'✅ Budget "{budget.name}" activated!')
    return redirect('budget_detail', pk=pk)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_report(request):
    """Budget reports"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    report_type = request.GET.get('report_type', 'summary')
    
    budgets = Budget.objects.filter(
        period_start__gte=from_date,
        period_end__lte=to_date
    )
    
    # Summary
    total_allocated = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    total_used = budgets.aggregate(total=Sum('used_amount'))['total'] or 0
    total_remaining = total_allocated - total_used
    
    # Department wise
    department_data = budgets.values('department__name').annotate(
        allocated=Sum('allocated_amount'),
        used=Sum('used_amount')
    ).order_by('-allocated')
    
    for dept in department_data:
        dept['remaining'] = dept['allocated'] - dept['used']
        dept['utilization'] = (dept['used'] / dept['allocated'] * 100) if dept['allocated'] > 0 else 0
    
    # Category wise
    category_data = budgets.values('category__name').annotate(
        allocated=Sum('allocated_amount'),
        used=Sum('used_amount')
    ).order_by('-allocated')
    
    for cat in category_data:
        cat['remaining'] = cat['allocated'] - cat['used']
        cat['utilization'] = (cat['used'] / cat['allocated'] * 100) if cat['allocated'] > 0 else 0
    
    # Monthly trend
    monthly_data = budgets.extra(
        select={'month': "strftime('%%Y-%%m', period_start)"}
    ).values('month').annotate(
        allocated=Sum('allocated_amount'),
        used=Sum('used_amount')
    ).order_by('month')
    
    for month in monthly_data:
        month['utilization'] = (month['used'] / month['allocated'] * 100) if month['allocated'] > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'report_type': report_type,
        'total_allocated': total_allocated,
        'total_used': total_used,
        'total_remaining': total_remaining,
        'total_utilization': (total_used / total_allocated * 100) if total_allocated > 0 else 0,
        'department_data': department_data,
        'category_data': category_data,
        'monthly_data': monthly_data,
        'budgets': budgets[:100],
        'count': budgets.count(),
    }
    return render(request, 'budgets/report.html', context)
