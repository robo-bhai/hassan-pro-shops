"""Frontend views: finance/expenses (split from the former expenses_budget.py)."""
from ...security.permissions import perm_required
from django.views.decorators.http import require_http_methods
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg
from decimal import Decimal
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ...models import CompanyInfo, Sale, Expense, Employee


@login_required
@perm_required('view_expenses')
def expense_dashboard(request):
    """Expense Dashboard with Budget Utilization"""
    
    from django.db.models import Sum, Count, Avg
    from datetime import date, timedelta
    from ...models import Expense, ExpenseCategory, Budget
    
    today = date.today()
    month_start = today.replace(day=1)
    
    # ========================================== #
    # EXPENSE STATS                              #
    # ========================================== #
    expenses = Expense.objects.all()
    
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_tax = expenses.aggregate(total=Sum('tax_amount'))['total'] or 0
    total_count = expenses.count()
    
    # Approved Expenses
    approved_expenses = expenses.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0
    approved_count = expenses.filter(status='approved').count()
    
    # Pending Expenses
    pending_expenses = expenses.filter(status__in=['submitted', 'review']).aggregate(total=Sum('amount'))['total'] or 0
    pending_count = expenses.filter(status__in=['submitted', 'review']).count()
    
    expense_count = expenses.count()
    
    # ========================================== #
    # ✅ BUDGET UTILIZATION                      #
    # ========================================== #
    budgets = Budget.objects.filter(
        status='active',
        period_start__lte=today,
        period_end__gte=today
    ).select_related('department', 'project')
    
    # Calculate utilization for each budget
    for budget in budgets:
        # ✅ FIX: Store the computed values as properties, not as function calls
        budget.utilization_percent = budget.utilization_percent()  # This is a method call - OK
        budget.is_over = budget.is_over_budget()  # This is a method call - OK
        #budget.is_near = budget.is_near_limit()   # This is a method call - OK (after your fix)
        #budget.is_critical = budget.is_critical() # This is a method call - OK (after your fix)
        budget.remaining_amount = budget.remaining_amount  # This is a field - NO parentheses!
    
    # ========================================== #
    # EXPENSES BY CATEGORY                      #
    # ========================================== #
    category_data = Expense.objects.filter(
        expense_date__gte=month_start
    ).values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Calculate percentage for each category
    total_category_amount = sum(item['total'] for item in category_data) or 1
    for item in category_data:
        item['percentage'] = (item['total'] / total_category_amount) * 100
    
    # ========================================== #
    # RECENT EXPENSES                           #
    # ========================================== #
    recent_expenses = Expense.objects.select_related(
        'category', 'budget', 'created_by'
    ).order_by('-created_at')[:10]
    
    # ========================================== #
    # MONTHLY EXPENSES TREND                    #
    # ========================================== #
    monthly_data = []
    for i in range(6):
        month_date = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        month_end = (month_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_expenses = Expense.objects.filter(
            expense_date__gte=month_date,
            expense_date__lte=month_end
        )
        
        total = month_expenses.aggregate(total=Sum('amount'))['total'] or 0
        count = month_expenses.count()
        avg = total / count if count > 0 else 0
        
        monthly_data.append({
            'month': month_date,
            'total': total,
            'count': count,
            'avg': avg,
        })
    monthly_data.reverse()
    
    # ========================================== #
    # CONTEXT                                   #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_expenses': total_expenses,
        'total_tax': total_tax,
        'total_count': total_count,
        'expense_count': expense_count,
        'approved_expenses': approved_expenses,
        'approved_count': approved_count,
        'pending_expenses': pending_expenses,
        'pending_count': pending_count,
        'budgets': budgets,  # ✅ For budget utilization table
        'category_data': category_data,
        'recent_expenses': recent_expenses,
        'monthly_data': monthly_data,
        'today': today,
        'month_start': month_start,
    }
    return render(request, 'expenses/dashboard.html', context)


@login_required
@perm_required('view_expenses')
def expense_list(request):
    """List all expenses with filters including budget"""
    
    expenses = Expense.objects.select_related('category', 'budget', 'vendor', 'created_by', 'approved_by').all()
    
    # Filters
    search = request.GET.get('search', '')
    if search:
        expenses = expenses.filter(
            Q(expense_no__icontains=search) |
            Q(description__icontains=search) |
            Q(vendor__name__icontains=search)
        )
    
    category = request.GET.get('category', '')
    if category:
        expenses = expenses.filter(category_id=category)
    
    # ✅ NEW: Budget Filter
    budget_id = request.GET.get('budget', '')
    if budget_id:
        expenses = expenses.filter(budget_id=budget_id)
    
    status = request.GET.get('status', '')
    if status:
        expenses = expenses.filter(status=status)
    
    payment_method = request.GET.get('payment_method', '')
    if payment_method:
        expenses = expenses.filter(payment_method=payment_method)
    
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        expenses = expenses.filter(expense_date__gte=from_date)
    if to_date:
        expenses = expenses.filter(expense_date__lte=to_date)
    
    # Statistics
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_tax = expenses.aggregate(total=Sum('tax_amount'))['total'] or 0
    total_with_tax = expenses.aggregate(total=Sum('total_amount'))['total'] or 0
    
    paginator = Paginator(expenses, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ✅ Get budgets for filter dropdown
    budgets = Budget.objects.filter(status='active')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'expenses': page_obj,
        'search': search,
        'category': category,
        'budget_id': budget_id,  # ✅ NEW
        'status': status,
        'payment_method': payment_method,
        'from_date': from_date,
        'to_date': to_date,
        'total_expenses': total_expenses,
        'total_tax': total_tax,
        'total_with_tax': total_with_tax,
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'budgets': budgets,  # ✅ NEW
        'status_choices': Expense.EXPENSE_STATUS,
        'payment_methods': Expense.PAYMENT_METHODS,
        'count': expenses.count(),
    }
    return render(request, 'expenses/list.html', context)


@login_required
@perm_required('manage_expenses')
def expense_create(request):
    """Create new expense with budget selection"""
    
    if request.method == 'POST':
        try:
            category_id = request.POST.get('category')
            budget_id = request.POST.get('budget')  # ✅ NEW: Budget ID
            description = request.POST.get('description')
            amount = Decimal(request.POST.get('amount', 0))
            expense_date = request.POST.get('expense_date')
            payment_method = request.POST.get('payment_method', 'cash')
            reference_no = request.POST.get('reference_no', '')
            vendor_id = request.POST.get('vendor') or None
            vendor_invoice_no = request.POST.get('vendor_invoice_no', '')
            tax_rate = Decimal(request.POST.get('tax_rate', 0))
            cost_center = request.POST.get('cost_center', '')
            is_recurring = request.POST.get('is_recurring') == 'on'
            recurring_frequency = request.POST.get('recurring_frequency', '')
            recurring_end_date = request.POST.get('recurring_end_date') or None
            notes = request.POST.get('notes', '')
            
            # Validate
            if not category_id or not description or amount <= 0:
                messages.error(request, 'Please fill all required fields!')
                return redirect('expense_create')
            
            # ✅ Get budget object if selected
            budget = None
            if budget_id:
                budget = get_object_or_404(Budget, id=budget_id)
            
            # Create expense
            expense = Expense.objects.create(
                category_id=category_id,
                budget=budget,  # ✅ NEW: Assign budget
                description=description,
                amount=amount,
                expense_date=expense_date,
                payment_method=payment_method,
                reference_no=reference_no,
                vendor_id=vendor_id,
                vendor_invoice_no=vendor_invoice_no,
                tax_rate=tax_rate,
                tax_amount=amount * (tax_rate / 100),
                cost_center=cost_center,
                is_recurring=is_recurring,
                recurring_frequency=recurring_frequency,
                recurring_end_date=recurring_end_date,
                notes=notes,
                created_by=request.user,
                status='draft'
            )
            
            # ✅ Update budget used amount
            if budget:
                budget.calculate_used()
            
            # Save receipt if uploaded
            if request.FILES.get('receipt'):
                expense.receipt = request.FILES['receipt']
                expense.save()
            
            if request.FILES.get('attachment'):
                expense.attachment = request.FILES['attachment']
                expense.save()
            
            # Create approval history
            ExpenseApprovalHistory.objects.create(
                expense=expense,
                action='submitted',
                performed_by=request.user,
                remarks="Expense created"
            )
            
            messages.success(request, f'✅ Expense #{expense.expense_no} created!')
            return redirect('expense_detail', pk=expense.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_create')
    
    # GET request - show form with budgets
    budgets = Budget.objects.filter(
        status='active',
        period_start__lte=date.today(),
        period_end__gte=date.today()
    ).select_related('department', 'project', 'category')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'payment_methods': Expense.PAYMENT_METHODS,
        'vendors': Vendor.objects.all(),
        'budgets': budgets,  # ✅ NEW: Pass budgets to template
        'recurring_frequencies': ExpenseBudget.BUDGET_PERIODS,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'expenses/create.html', context)


@login_required
@perm_required('view_expenses')
def expense_detail(request, pk):
    """View expense details"""
    
    expense = get_object_or_404(Expense, pk=pk)
    history = expense.approval_history.all()
    
    # Check permissions for actions
    can_approve = request.user.is_superuser or request.user.has_perm('app.can_approve_expenses')
    can_pay = request.user.is_superuser or request.user.has_perm('app.can_pay_expenses')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
        'history': history,
        'can_approve': can_approve,
        'can_pay': can_pay,
        'can_edit': expense.status in ['draft', 'rejected'],
        'can_submit': expense.status == 'draft',
        'can_delete': expense.status in ['draft', 'rejected'],
    }
    return render(request, 'expenses/detail.html', context)


@login_required
@perm_required('manage_expenses')
def expense_edit(request, pk):
    """Edit expense with budget selection"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status not in ['draft', 'rejected']:
        messages.error(request, '❌ Cannot edit approved or paid expenses!')
        return redirect('expense_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # ✅ Get budget from POST
            budget_id = request.POST.get('budget') or None
            
            expense.category_id = request.POST.get('category')
            expense.description = request.POST.get('description')
            expense.amount = Decimal(request.POST.get('amount', 0))
            expense.expense_date = request.POST.get('expense_date')
            expense.payment_method = request.POST.get('payment_method', 'cash')
            expense.reference_no = request.POST.get('reference_no', '')
            expense.vendor_id = request.POST.get('vendor') or None
            expense.vendor_invoice_no = request.POST.get('vendor_invoice_no', '')
            expense.tax_rate = Decimal(request.POST.get('tax_rate', 0))
            expense.tax_amount = expense.amount * (expense.tax_rate / 100)
            
            # ✅ Update budget
            old_budget = expense.budget
            expense.budget_id = budget_id  # ✅ NEW: Update budget
            expense.cost_center = request.POST.get('cost_center', '')
            expense.notes = request.POST.get('notes', '')
            expense.save()
            
            # ✅ Update both old and new budget used amounts
            if old_budget:
                old_budget.calculate_used()
            if expense.budget:
                expense.budget.calculate_used()
            
            # Save receipts
            if request.FILES.get('receipt'):
                expense.receipt = request.FILES['receipt']
                expense.save()
            
            if request.FILES.get('attachment'):
                expense.attachment = request.FILES['attachment']
                expense.save()
            
            messages.success(request, f'✅ Expense #{expense.expense_no} updated!')
            return redirect('expense_detail', pk=expense.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_edit', pk=pk)
    
    budgets = Budget.objects.filter(
        status='active',
        period_start__lte=date.today(),
        period_end__gte=date.today()
    ).select_related('department', 'project', 'category')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'payment_methods': Expense.PAYMENT_METHODS,
        'vendors': Vendor.objects.all(),
        'budgets': budgets,  # ✅ NEW: Pass budgets to template
    }
    return render(request, 'expenses/edit.html', context)


@login_required
@perm_required('manage_expenses')
def expense_submit(request, pk):
    """Submit expense for approval"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status != 'draft':
        messages.error(request, '❌ Only draft expenses can be submitted!')
        return redirect('expense_detail', pk=pk)
    
    expense.submit(request.user)
    ExpenseApprovalHistory.objects.create(
        expense=expense,
        action='submitted',
        performed_by=request.user,
        remarks="Submitted for approval"
    )
    
    messages.success(request, f'📤 Expense #{expense.expense_no} submitted for approval!')
    return redirect('expense_detail', pk=pk)


@login_required
@perm_required('manage_payments')
def expense_approve(request, pk):
    """Approve expense"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status not in ['submitted', 'review']:
        messages.error(request, '❌ This expense is not pending approval!')
        return redirect('expense_detail', pk=pk)
    
    if request.method == 'POST':
        remarks = request.POST.get('remarks', '')
        expense.approve(request.user)
        ExpenseApprovalHistory.objects.create(
            expense=expense,
            action='approved',
            performed_by=request.user,
            remarks=remarks
        )
        messages.success(request, f'✅ Expense #{expense.expense_no} approved!')
        return redirect('expense_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
    }
    return render(request, 'expenses/approve.html', context)


@login_required
@perm_required('manage_payments')
def expense_reject(request, pk):
    """Reject expense"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status not in ['submitted', 'review']:
        messages.error(request, '❌ This expense is not pending approval!')
        return redirect('expense_detail', pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        expense.reject(request.user, reason)
        ExpenseApprovalHistory.objects.create(
            expense=expense,
            action='rejected',
            performed_by=request.user,
            remarks=reason
        )
        messages.success(request, f'❌ Expense #{expense.expense_no} rejected!')
        return redirect('expense_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
    }
    return render(request, 'expenses/reject.html', context)


@login_required
@perm_required('manage_payments')
def expense_pay(request, pk):
    """Mark expense as paid"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status != 'approved':
        messages.error(request, '❌ Expense must be approved first!')
        return redirect('expense_detail', pk=pk)
    
    if request.method == 'POST':
        payment_date = request.POST.get('payment_date') or date.today()
        remarks = request.POST.get('remarks', '')
        
        expense.mark_paid(request.user, payment_date)
        ExpenseApprovalHistory.objects.create(
            expense=expense,
            action='paid',
            performed_by=request.user,
            remarks=remarks
        )
        messages.success(request, f'💰 Expense #{expense.expense_no} marked as paid!')
        return redirect('expense_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
    }
    return render(request, 'expenses/pay.html', context)


@login_required
@perm_required('manage_expenses')
def expense_delete(request, pk):
    """Delete expense"""
    
    expense = get_object_or_404(Expense, pk=pk)
    
    if expense.status not in ['draft', 'rejected']:
        messages.error(request, '❌ Only draft or rejected expenses can be deleted!')
        return redirect('expense_detail', pk=pk)
    
    if request.method == 'POST':
        expense_no = expense.expense_no
        expense.delete()
        messages.success(request, f'🗑️ Expense #{expense_no} deleted!')
        return redirect('expense_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'expense': expense,
    }
    return render(request, 'expenses/delete.html', context)


@login_required
@perm_required('view_expenses')
def expense_claim_list(request):
    """List all expense claims"""
    
    claims = ExpenseClaim.objects.select_related('employee', 'approved_by', 'submitted_by').all()
    
    search = request.GET.get('search', '')
    if search:
        claims = claims.filter(
            Q(claim_no__icontains=search) |
            Q(employee__name__icontains=search) |
            Q(title__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        claims = claims.filter(status=status)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'claims': claims,
        'search': search,
        'status': status,
        'status_choices': ExpenseClaim.CLAIM_STATUS,
        'total_claims': claims.count(),
        'pending_claims': claims.filter(status__in=['submitted', 'review']).count(),
        'approved_claims': claims.filter(status='approved').count(),
        'reimbursed_claims': claims.filter(status='reimbursed').count(),
        'total_amount': claims.aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    return render(request, 'expenses/claim_list.html', context)


@login_required
@perm_required('manage_expenses')
def expense_claim_create(request):
    """Create new expense claim"""
    
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee')
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            claim_date = request.POST.get('claim_date')
            notes = request.POST.get('notes', '')
            
            claim = ExpenseClaim.objects.create(
                employee_id=employee_id,
                title=title,
                description=description,
                claim_date=claim_date,
                status='draft',
                created_by=request.user,
                notes=notes
            )
            
            # Add expenses to claim
            expense_ids = request.POST.getlist('expense_ids[]')
            if expense_ids:
                claim.expenses.set(expense_ids)
                claim.save()
            
            messages.success(request, f'✅ Claim #{claim.claim_no} created!')
            return redirect('expense_claim_detail', pk=claim.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_claim_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employees': Employee.objects.filter(status='active'),
        'expenses': Expense.objects.filter(status='approved', claims__isnull=True),
    }
    return render(request, 'expenses/claim_create.html', context)


@login_required
@perm_required('view_expenses')
def expense_claim_detail(request, pk):
    """Claim detail view"""
    
    claim = get_object_or_404(ExpenseClaim, pk=pk)
    expenses = claim.expenses.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'claim': claim,
        'expenses': expenses,
        'total_expenses': claim.total_amount,
        'can_approve': request.user.is_superuser or request.user.has_perm('app.can_approve_claims'),
        'can_reimburse': request.user.is_superuser or request.user.has_perm('app.can_reimburse_claims'),
    }
    return render(request, 'expenses/claim_detail.html', context)


@login_required
@perm_required('view_expenses')
def expense_report(request):
    """Expense reports page"""
    
    report_type = request.GET.get('report_type', 'summary')
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    expenses = Expense.objects.filter(
        expense_date__gte=from_date,
        expense_date__lte=to_date
    )
    
    # Summary
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_tax = expenses.aggregate(total=Sum('tax_amount'))['total'] or 0
    total_expenses_with_tax = expenses.aggregate(total=Sum('total_amount'))['total'] or 0
    avg_expense = expenses.aggregate(avg=Avg('amount'))['avg'] or 0
    
    # Status breakdown
    status_breakdown = expenses.values('status').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('status')
    
    # Category wise
    category_data = expenses.values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Payment method wise
    payment_method_data = expenses.values('payment_method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Monthly trend
    monthly_data = expenses.extra(
        select={'month': "strftime('%%Y-%%m', expense_date)"}
    ).values('month').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('month')
    
    # Vendor wise
    vendor_data = expenses.values('vendor__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')[:10]
    
    # Department wise (if department exists)
    department_data = []
    if hasattr(Expense, 'department'):
        department_data = expenses.values('department__name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_type': report_type,
        'from_date': from_date,
        'to_date': to_date,
        'total_expenses': total_expenses,
        'total_tax': total_tax,
        'total_expenses_with_tax': total_expenses_with_tax,
        'avg_expense': avg_expense,
        'status_breakdown': status_breakdown,
        'category_data': category_data,
        'payment_method_data': payment_method_data,
        'monthly_data': monthly_data,
        'vendor_data': vendor_data,
        'department_data': department_data,
        'expenses': expenses[:100],
        'count': expenses.count(),
        'status_choices': Expense.EXPENSE_STATUS,
    }
    return render(request, 'expenses/report.html', context)


@login_required
@perm_required('manage_expenses')
@require_http_methods(["POST"])
def convert_sale_to_expense(request, pk):
    """Convert single sale to self expense with budget linking"""
    
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': False, 
            'message': 'Invalid request - AJAX required'
        }, status=400)
    
    try:
        sale = get_object_or_404(Sale, pk=pk)
        
        if sale.is_converted_to_expense:
            return JsonResponse({
                'success': False, 
                'message': 'Already converted to expense!'
            }, status=400)
        
        if sale.customer.customer_code != 'CUS-SELF' and sale.customer.name.lower() != 'self':
            return JsonResponse({
                'success': False, 
                'message': 'Only "Self" customer sales can be converted!'
            }, status=400)
        
        if not sale.saleitem_set.exists():
            return JsonResponse({
                'success': False, 
                'message': f'Sale #{sale.bill_no} has no items!'
            }, status=400)
        
        total = sale.total_amount()
        if total <= 0:
            return JsonResponse({
                'success': False, 
                'message': f'Sale #{sale.bill_no} total amount is 0!'
            }, status=400)
        
        # ✅ Get or create category
        category, _ = ExpenseCategory.objects.get_or_create(
            name='Self Sale / Personal Use',
            defaults={
                'category_type': 'operating',
                'is_active': True
            }
        )
        
        # ✅ NEW: Find active budget for this month
        today = date.today()
        month_start = today.replace(day=1)
        
        # Find active budget that includes this category
        budget = Budget.objects.filter(
            status='active',
            period_start__lte=today,
            period_end__gte=today,
            category=category  # ✅ Category match
        ).first()
        
        # ✅ If no budget with this category, try to find any active budget
        if not budget:
            budget = Budget.objects.filter(
                status='active',
                period_start__lte=today,
                period_end__gte=today
            ).first()
        
        # ✅ Create expense WITH budget
        expense = Expense.objects.create(
            category=category,
            budget=budget,  # ✅ NEW: Budget assigned!
            description=f"Self Sale - Bill #{sale.bill_no} - Converted from sale",
            amount=total,
            expense_date=today,
            payment_method='cash',
            created_by=request.user,
            status='approved'
        )
        
        # ✅ Update budget used amount
        if budget:
            budget.calculate_used()
        
        sale.is_converted_to_expense = True
        sale.save()
        
        budget_info = f" (Linked to: {budget.name})" if budget else " (No active budget found)"
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Sale #{sale.bill_no} converted to expense! Amount: Rs. {total:,.2f}{budget_info}'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e)
        }, status=500)


@login_required
@perm_required('manage_expenses')
@require_http_methods(["POST"])
def bulk_convert_to_expense(request):
    """Bulk convert multiple sales to self expense"""
    
    # Check if AJAX request
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': False, 
            'message': 'Invalid request - AJAX required'
        }, status=400)
    
    try:
        # Parse JSON body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False, 
                'message': f'Invalid JSON data: {str(e)}'
            }, status=400)
        
        sale_ids = data.get('sale_ids', [])
        
        if not sale_ids:
            return JsonResponse({
                'success': False, 
                'message': 'No sales selected!'
            }, status=400)
        
        # Get or create expense category
        category, _ = ExpenseCategory.objects.get_or_create(
            name='Self Sale / Personal Use',
            defaults={
                'category_type': 'operating',
                'is_active': True
            }
        )
        
        converted_count = 0
        skipped_count = 0
        total_amount = Decimal('0.00')
        errors = []
        
        with transaction.atomic():
            for sale_id in sale_ids:
                try:
                    sale = Sale.objects.get(pk=sale_id)
                    
                    # Skip if already converted
                    if sale.is_converted_to_expense:
                        skipped_count += 1
                        continue
                    
                    # Skip if customer is not "Self"
                    if sale.customer.customer_code != 'CUS-SELF' and sale.customer.name.lower() != 'self':
                        skipped_count += 1
                        continue
                    
                    # ✅ CHECK: Sale has items
                    if not sale.saleitem_set.exists():
                        errors.append(f"Sale #{sale.bill_no} has no items")
                        continue
                    
                    # ✅ CHECK: Total amount > 0
                    total = sale.total_amount()
                    if total <= 0:
                        errors.append(f"Sale #{sale.bill_no} total amount is 0")
                        continue
                    
                    # Create expense
                    Expense.objects.create(
                        category=category,
                        description=f"Self Sale - Bill #{sale.bill_no} - Bulk converted",
                        amount=total,
                        expense_date=date.today(),
                        payment_method='cash',
                        created_by=request.user,
                        status='approved'
                    )
                    
                    # Mark sale as converted
                    sale.is_converted_to_expense = True
                    sale.save()
                    
                    converted_count += 1
                    total_amount += total
                    
                except Sale.DoesNotExist:
                    errors.append(f"Sale ID {sale_id} not found")
                except Exception as e:
                    errors.append(str(e))
        
        # Build success message
        message = f'✅ {converted_count} sales converted to expense! Total amount: Rs. {total_amount:,.2f}'
        if skipped_count > 0:
            message += f' ⚠️ {skipped_count} sales skipped (already converted or not "Self" customer)'
        if errors:
            message += f' ❌ Errors: {", ".join(errors[:3])}'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'converted_count': converted_count,
            'skipped_count': skipped_count,
            'total_amount': float(total_amount)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e)
        }, status=500)
