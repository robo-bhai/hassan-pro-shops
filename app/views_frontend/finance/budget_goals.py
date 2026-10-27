"""Frontend views: finance/budget_goals (split from the former expenses_budget.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from datetime import date
from django.contrib import messages
from ...models import CompanyInfo


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_goals(request, pk):
    """View all goals for a budget"""
    budget = get_object_or_404(Budget, pk=pk)
    goals = budget.goals.all()
    
    # Update progress for all goals
    for goal in goals:
        goal.update_progress()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
        'goals': goals,
        'active_goals': goals.filter(status='active').count(),
        'completed_goals': goals.filter(status='completed').count(),
        'total_goals': goals.count(),
    }
    return render(request, 'budgets/goals/list.html', context)


@login_required
@perm_required('manage_budget')
def budget_goal_create(request, pk):
    """Create a new goal for a budget"""
    budget = get_object_or_404(Budget, pk=pk)
    
    if request.method == 'POST':
        try:
            goal = BudgetGoal.objects.create(
                budget=budget,
                category_id=request.POST.get('category') or None,
                name=request.POST.get('name'),
                goal_type=request.POST.get('goal_type'),
                description=request.POST.get('description', ''),
                target_amount=Decimal(request.POST.get('target_amount', 0)),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                created_by=request.user
            )
            
            messages.success(request, f'✅ Goal "{goal.name}" created successfully!')
            return redirect('budget_goals', pk=budget.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('budget_goal_create', pk=budget.pk)
    
    categories = ExpenseCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'budget': budget,
        'categories': categories,
        'goal_types': BudgetGoal.GOAL_TYPES,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'budgets/goals/create.html', context)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_goal_detail(request, pk):
    """View goal details"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    goal.update_progress()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'goal': goal,
    }
    return render(request, 'budgets/goals/detail.html', context)


@login_required
@perm_required('manage_budget')
def budget_goal_edit(request, pk):
    """Edit a goal"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    
    if request.method == 'POST':
        try:
            goal.name = request.POST.get('name')
            goal.goal_type = request.POST.get('goal_type')
            goal.description = request.POST.get('description', '')
            goal.target_amount = Decimal(request.POST.get('target_amount', 0))
            goal.start_date = request.POST.get('start_date')
            goal.end_date = request.POST.get('end_date')
            goal.category_id = request.POST.get('category') or None
            goal.save()
            
            messages.success(request, f'✅ Goal "{goal.name}" updated!')
            return redirect('budget_goal_detail', pk=goal.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('budget_goal_edit', pk=goal.pk)
    
    categories = ExpenseCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'goal': goal,
        'categories': categories,
        'goal_types': BudgetGoal.GOAL_TYPES,
    }
    return render(request, 'budgets/goals/edit.html', context)


@login_required
@perm_required('manage_budget')
def budget_goal_delete(request, pk):
    """Delete a goal"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    budget_pk = goal.budget.pk
    
    if request.method == 'POST':
        goal_name = goal.name
        goal.delete()
        messages.success(request, f'🗑️ Goal "{goal_name}" deleted!')
        return redirect('budget_goals', pk=budget_pk)
    
    return redirect('budget_goals', pk=budget_pk)


@login_required
@perm_required('manage_budget')
def budget_goal_update_progress(request, pk):
    """Update goal progress manually"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    current_amount = Decimal(request.POST.get('current_amount', 0))
    goal.current_amount = current_amount
    goal.update_progress()
    
    messages.success(request, f'✅ Goal progress updated to {goal.progress:.1f}%')
    return redirect('budget_goal_detail', pk=goal.pk)


@login_required
@perm_required('view_financials', 'manage_budget')
def budget_goal_comparison(request, pk):
    """Compare goal progress with previous goals"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    goal.update_progress()
    
    # Get previous goals
    previous_goals = goal.get_previous_goals(5)
    
    # Calculate trends
    trends = {
        'progress_trend': 'up',
        'speed_trend': 'faster',
        'projected_completion': goal.projected_completion_date(),
    }
    
    if previous_goals.exists():
        first_prev = previous_goals.first()
        if goal.progress > first_prev.progress:
            trends['progress_trend'] = 'up'
        elif goal.progress < first_prev.progress:
            trends['progress_trend'] = 'down'
        else:
            trends['progress_trend'] = 'same'
        
        if goal.achievement_rate() > first_prev.achievement_rate():
            trends['speed_trend'] = 'faster'
        elif goal.achievement_rate() < first_prev.achievement_rate():
            trends['speed_trend'] = 'slower'
        else:
            trends['speed_trend'] = 'same'
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'goal': goal,
        'previous_goals': previous_goals,
        'trends': trends,
        'has_previous': previous_goals.exists(),
        'total_previous': previous_goals.count(),
        'achievement_rate': goal.achievement_rate(),
        'projected_date': goal.projected_completion_date(),
    }
    return render(request, 'budgets/goals/comparison.html', context)
