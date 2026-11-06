"""Frontend views: expenses budget."""
from django.views.decorators.http import require_http_methods
from ..models import *
import json
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ..models import CompanyInfo, Sale, Expense, Employee, SaleItem, Department, Project
from django.db.models.functions import TruncMonth
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from openpyxl.utils import get_column_letter
from openpyxl.chart import PieChart, Reference


@login_required
def expense_dashboard(request):
    """Expense Dashboard with Budget Utilization"""
    
    from django.db.models import Sum, Count, Avg
    from datetime import date, timedelta
    from ..models import Expense, ExpenseCategory, Budget
    
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
def expense_category_list(request):
    """List all expense categories"""
    categories = ExpenseCategory.objects.filter(is_active=True)
    
    search = request.GET.get('search', '')
    if search:
        categories = categories.filter(name__icontains=search)
    
    category_type = request.GET.get('type', '')
    if category_type:
        categories = categories.filter(category_type=category_type)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': categories,
        'search': search,
        'category_type': category_type,
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'total_categories': categories.count(),
        'active_categories': categories.filter(is_active=True).count(),
    }
    return render(request, 'expenses/category_list.html', context)


@login_required
def expense_category_create(request):
    """Create new expense category from frontend"""
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            category_type = request.POST.get('category_type')
            parent_id = request.POST.get('parent') or None
            description = request.POST.get('description', '')
            is_active = request.POST.get('is_active') == 'on'
            
            if not name:
                messages.error(request, 'Category name is required!')
                return redirect('expense_category_create')
            
            # Check duplicate
            if ExpenseCategory.objects.filter(name__iexact=name).exists():
                messages.error(request, f'Category "{name}" already exists!')
                return redirect('expense_category_create')
            
            category = ExpenseCategory.objects.create(
                name=name,
                category_type=category_type,
                parent_id=parent_id,
                description=description,
                is_active=is_active
            )
            
            messages.success(request, f'✅ Category "{category.name}" created successfully!')
            return redirect('expense_category_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_category_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'parent_categories': ExpenseCategory.objects.filter(parent__isnull=True, is_active=True),
    }
    return render(request, 'expenses/category_create.html', context)


@login_required
def expense_category_edit(request, pk):
    """Edit expense category"""
    
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        try:
            category.name = request.POST.get('name', '').strip()
            category.category_type = request.POST.get('category_type')
            category.parent_id = request.POST.get('parent') or None
            category.description = request.POST.get('description', '')
            category.is_active = request.POST.get('is_active') == 'on'
            category.save()
            
            messages.success(request, f'✅ Category "{category.name}" updated!')
            return redirect('expense_category_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_category_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category': category,
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'parent_categories': ExpenseCategory.objects.filter(parent__isnull=True, is_active=True).exclude(pk=pk),
    }
    return render(request, 'expenses/category_edit.html', context)


@login_required
def expense_category_delete(request, pk):
    """Delete expense category"""
    
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'🗑️ Category "{name}" deleted!')
        return redirect('expense_category_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category': category,
    }
    return render(request, 'expenses/category_delete.html', context)


@login_required
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
def budget_detail(request, pk):
    """Budget detail view"""
    
    budget = get_object_or_404(Budget, pk=pk)
    allocations = budget.allocations.all()
    transactions = budget.transactions.all().order_by('-performed_at')
    alerts = budget.alerts.all().order_by('-triggered_at')
    
    # ✅ Calculate utilization for each allocation
    from django.db.models import Sum
    from ..models import Expense
    
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


@login_required
def department_list(request):
    """List all departments"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    departments = Department.objects.all().order_by('name')
    
    search = request.GET.get('search', '')
    if search:
        departments = departments.filter(name__icontains=search)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'departments': departments,
        'search': search,
    }
    return render(request, 'departments/list.html', context)


@login_required
def department_create(request):
    """Create new department"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Department name is required!')
            return redirect('department_create')
        
        department = Department.objects.create(
            name=name,
            code=code if code else name[:3].upper(),
            description=description,
            is_active=is_active
        )
        
        messages.success(request, f'✅ Department "{department.name}" created successfully!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'departments/create.html', context)


@login_required
def department_edit(request, pk):
    """Edit department"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        department.name = request.POST.get('name', '').strip()
        department.code = request.POST.get('code', '').strip()
        department.description = request.POST.get('description', '')
        department.is_active = request.POST.get('is_active') == 'on'
        department.save()
        
        messages.success(request, f'✅ Department "{department.name}" updated!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'department': department,
    }
    return render(request, 'departments/edit.html', context)


@login_required
def department_delete(request, pk):
    """Delete department"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can delete departments.')
        return redirect('department_list')
    
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        name = department.name
        department.delete()
        messages.success(request, f'🗑️ Department "{name}" deleted!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'department': department,
    }
    return render(request, 'departments/delete.html', context)


@login_required
def project_list(request):
    """List all projects"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    projects = Project.objects.select_related('department', 'manager').all().order_by('-start_date')
    
    search = request.GET.get('search', '')
    if search:
        projects = projects.filter(name__icontains=search)
    
    status = request.GET.get('status', '')
    if status:
        projects = projects.filter(status=status)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
        'search': search,
        'status': status,
    }
    return render(request, 'projects/list.html', context)


@login_required
def project_create(request):
    """Create new project"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        description = request.POST.get('description', '')
        department_id = request.POST.get('department')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        budget = request.POST.get('budget', 0)
        status = request.POST.get('status', 'active')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Project name is required!')
            return redirect('project_create')
        
        project = Project.objects.create(
            name=name,
            code=code if code else f'PRJ-{Project.objects.count() + 1:04d}',
            description=description,
            department_id=department_id if department_id else None,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            status=status,
            is_active=is_active
        )
        
        messages.success(request, f'✅ Project "{project.name}" created successfully!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'departments': Department.objects.filter(is_active=True),
    }
    return render(request, 'projects/create.html', context)


@login_required
def project_edit(request, pk):
    """Edit project"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    project = get_object_or_404(Project, pk=pk)
    
    if request.method == 'POST':
        project.name = request.POST.get('name', '').strip()
        project.code = request.POST.get('code', '').strip()
        project.description = request.POST.get('description', '')
        project.department_id = request.POST.get('department') if request.POST.get('department') else None
        project.start_date = request.POST.get('start_date')
        project.end_date = request.POST.get('end_date')
        project.budget = request.POST.get('budget', 0)
        project.status = request.POST.get('status', 'active')
        project.is_active = request.POST.get('is_active') == 'on'
        project.save()
        
        messages.success(request, f'✅ Project "{project.name}" updated!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'project': project,
        'departments': Department.objects.filter(is_active=True),
    }
    return render(request, 'projects/edit.html', context)


@login_required
def project_delete(request, pk):
    """Delete project"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can delete projects.')
        return redirect('project_list')
    
    project = get_object_or_404(Project, pk=pk)
    
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'🗑️ Project "{name}" deleted!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'project': project,
    }
    return render(request, 'projects/delete.html', context)


@login_required
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
def budget_goal_update_progress(request, pk):
    """Update goal progress manually"""
    goal = get_object_or_404(BudgetGoal, pk=pk)
    current_amount = Decimal(request.POST.get('current_amount', 0))
    goal.current_amount = current_amount
    goal.update_progress()
    
    messages.success(request, f'✅ Goal progress updated to {goal.progress:.1f}%')
    return redirect('budget_goal_detail', pk=goal.pk)


@login_required
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


@login_required
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
def self_expense_report(request):
    """
    Self Expense Report - Complete analytics for self expenses
    """
    
    # Get filter parameters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    category_id = request.GET.get('category', '')
    search_product = request.GET.get('search_product', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ========================================== #
    # 1. GET SELF EXPENSE CATEGORY              #
    # ========================================== #
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={
            'category_type': 'operating',
            'is_active': True
        }
    )
    
    # ========================================== #
    # 2. GET ALL SELF EXPENSES                  #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    # Filter by sub-category if selected
    if category_id:
        expenses = expenses.filter(category_id=category_id)
    
    # ========================================== #
    # 3. CALCULATE STATISTICS                   #
    # ========================================== #
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_count = expenses.count()
    total_tax = expenses.aggregate(total=Sum('tax_amount'))['total'] or Decimal('0.00')
    avg_expense = expenses.aggregate(avg=Avg('amount'))['avg'] or Decimal('0.00')
    
    # ========================================== #
    # 4. CATEGORY WISE BREAKDOWN                #
    # ========================================== #
    category_breakdown = expenses.values(
        'category__name'
    ).annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Calculate percentage
    total_all = sum(item['total'] for item in category_breakdown) or 1
    for item in category_breakdown:
        item['percentage'] = (item['total'] / total_all) * 100
    
    # ========================================== #
    # 5. MONTHLY TREND                          #
    # ========================================== #
    monthly_trend = expenses.annotate(
        month=TruncMonth('expense_date')
    ).values('month').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('month')
    
    # ========================================== #
    # 6. DAILY BREAKDOWN (Last 30 Days)        #
    # ========================================== #
    daily_data = []
    current = from_date_obj
    while current <= to_date_obj:
        day_expenses = expenses.filter(expense_date=current)
        daily_data.append({
            'date': current.strftime('%d-%b'),
            'amount': day_expenses.aggregate(total=Sum('amount'))['total'] or 0,
            'count': day_expenses.count()
        })
        current += timedelta(days=1)
    
    # ========================================== #
    # 7. SELF SALES (Converted)                 #
    # ========================================== #
    self_sales = Sale.objects.filter(
        is_converted_to_expense=True,
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).select_related('customer')
    
    total_self_sales = self_sales.aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0.00')
    self_sales_count = self_sales.count()
    
    # ========================================== #
    # 8. PRODUCT DETAILS (NEW)                  #
    # ========================================== #
    
    # Get all products used in self expenses
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__id',
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name',
        'product__price'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_profit=Sum('profit'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    # Search filter for products
    if search_product:
        product_details = product_details.filter(
            Q(product__name__icontains=search_product) |
            Q(product__serial_no__icontains=search_product) |
            Q(product__barcode__icontains=search_product)
        )
    
    # Calculate total product value
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # Top 5 products by amount
    top_products = product_details[:5]
    
    # Product category breakdown
    product_category = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__category__isnull=False
    ).values('product__category__name').annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('-total_amount')
    
    # Product brand breakdown
    product_brand = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__brand__isnull=False
    ).values('product__brand__name').annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('-total_amount')
    
    # Product monthly trend
    product_monthly = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).annotate(
        month=TruncMonth('sale__sale_date')
    ).values(
        'month',
        'product__name'
    ).annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('month', '-total_amount')
    
    # ========================================== #
    # 9. USER WISE SELF EXPENSES                #
    # ========================================== #
    user_wise = expenses.values('created_by__username').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # ========================================== #
    # 10. CHART DATA                            #
    # ========================================== #
    chart_labels = [d['date'] for d in daily_data]
    chart_amounts = [float(d['amount']) for d in daily_data]
    
    monthly_labels = [m['month'].strftime('%b %Y') for m in monthly_trend if m['month']]
    monthly_amounts = [float(m['total']) for m in monthly_trend]
    
    # Product chart data
    product_chart_labels = [p['product__name'][:20] for p in top_products]
    product_chart_amounts = [float(p['total_amount']) for p in top_products]
    
    # ========================================== #
    # 11. COMPARISON WITH PREVIOUS PERIOD       #
    # ========================================== #
    days_diff = (to_date_obj - from_date_obj).days
    prev_from = from_date_obj - timedelta(days=days_diff + 1)
    prev_to = to_date_obj - timedelta(days=days_diff + 1)
    
    prev_expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=prev_from,
        expense_date__lte=prev_to,
        status__in=['approved', 'paid']
    )
    prev_total = prev_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    growth_percent = 0
    if prev_total > 0:
        growth_percent = ((total_expenses - prev_total) / prev_total) * 100
    
    # ========================================== #
    # 12. PAGINATION FOR EXPENSES LIST          #
    # ========================================== #
    paginator = Paginator(expenses, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ========================================== #
    # 13. CONTEXT                               #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'expenses': page_obj,
        'from_date': from_date,
        'to_date': to_date,
        'total_expenses': total_expenses,
        'total_count': total_count,
        'total_tax': total_tax,
        'avg_expense': avg_expense,
        'category_breakdown': category_breakdown,
        'monthly_trend': monthly_trend,
        'daily_data': daily_data,
        'chart_labels': json.dumps(chart_labels),
        'chart_amounts': json.dumps(chart_amounts),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_amounts': json.dumps(monthly_amounts),
        'self_sales': self_sales[:20],
        'total_self_sales': total_self_sales,
        'self_sales_count': self_sales_count,
        'user_wise': user_wise,
        'prev_total': prev_total,
        'growth_percent': growth_percent,
        'category_id': category_id,
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'today': date.today(),
        # ✅ NEW: Product Details
        'product_details': product_details,
        'total_product_value': total_product_value,
        'top_products': top_products,
        'product_monthly': product_monthly,
        'product_category': product_category,
        'product_brand': product_brand,
        'total_products': product_details.count(),
        'search_product': search_product,
        'product_chart_labels': json.dumps(product_chart_labels),
        'product_chart_amounts': json.dumps(product_chart_amounts),
        'product_category_labels': json.dumps([cat['product__category__name'] for cat in product_category]),
        'product_category_amounts': json.dumps([float(cat['total_amount']) for cat in product_category]),
    }
    return render(request, 'reports/self_expense_report.html', context)


@login_required
def self_expense_report_pdf(request):
    """Generate PDF for Self Expense Report with Product Details"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={'category_type': 'operating', 'is_active': True}
    )
    
    # ========================================== #
    # GET EXPENSES                              #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # ========================================== #
    # GET PRODUCT DETAILS                       #
    # ========================================== #
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # ========================================== #
    # BUILD PDF                                 #
    # ========================================== #
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        topMargin=0.3*inch, 
        bottomMargin=0.3*inch,
        leftMargin=0.3*inch,
        rightMargin=0.3*inch
    )
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title Style
    title_style = ParagraphStyle(
        'Title', 
        parent=styles['Heading1'], 
        fontSize=16, 
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=3
    )
    
    # ========================================== #
    # HEADER                                    #
    # ========================================== #
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Self Expense Report", title_style))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # SUMMARY SECTION                           #
    # ========================================== #
    summary_data = [
        ['Metric', 'Value'],
        ['Total Self Expenses', f"Rs. {total_expenses:,.2f}"],
        ['Total Transactions', str(expenses.count())],
        ['Average Expense', f"Rs. {(total_expenses / expenses.count()):,.2f}" if expenses.count() > 0 else "Rs. 0.00"],
        ['Products Used', str(product_details.count())],
        ['Total Product Value', f"Rs. {total_product_value:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # PRODUCT DETAILS TABLE                     #
    # ========================================== #
    if product_details:
        story.append(Paragraph("<b>📦 Product Details</b>", styles['Heading3']))
        story.append(Spacer(1, 0.1*inch))
        
        product_data = [
            ['#', 'Product Name', 'Serial No', 'Barcode', 'Category', 'Brand', 'Qty', 'Unit', 'Total']
        ]
        
        for idx, product in enumerate(product_details, 1):
            product_data.append([
                str(idx),
                product['product__name'][:25] if product['product__name'] else '-',
                product['product__serial_no'] or '-',
                product['product__barcode'] or '-',
                product['product__category__name'] or '-',
                product['product__brand__name'] or '-',
                f"{product['total_qty']:,.0f}",
                product['product__unit__name'] or '-',
                f"Rs. {product['total_amount']:,.2f}",
            ])
        
        # Add total row
        product_data.append([
            '', '', '', '', '', '', '', 'TOTAL:',
            f"Rs. {total_product_value:,.2f}"
        ])
        
        product_table = Table(product_data, repeatRows=1)
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('FONTSIZE', (0, 1), (-1, -2), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fc')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (6, 1), (8, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(product_table)
        story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # EXPENSES TABLE                            #
    # ========================================== #
    story.append(Paragraph("<b>📋 Self Expenses List</b>", styles['Heading3']))
    story.append(Spacer(1, 0.1*inch))
    
    exp_data = [
        ['Date', 'Description', 'Category', 'Amount', 'Tax', 'Total', 'Created By', 'Status']
    ]
    
    for exp in expenses[:100]:  # Limit to 100 rows for PDF
        exp_data.append([
            exp.expense_date.strftime('%d-%m-%Y'),
            exp.description[:35],
            exp.category.name if exp.category else 'Self Expense',
            f"Rs. {exp.amount:,.2f}",
            f"Rs. {exp.tax_amount:,.2f}",
            f"Rs. {exp.total_amount:,.2f}",
            exp.created_by.username if exp.created_by else '-',
            exp.get_status_display()
        ])
    
    exp_table = Table(exp_data, repeatRows=1)
    exp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('ALIGN', (3, 1), (5, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(exp_table)
    
    # ========================================== #
    # FOOTER                                    #
    # ========================================== #
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "This is a computer generated report.",
        ParagraphStyle('Footer2', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Self_Expense_Report_{date.today()}.pdf"'
    return response


@login_required
def self_expense_export(request):
    """Export Self Expense Report to Excel with Product Details"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={'category_type': 'operating', 'is_active': True}
    )
    
    # ========================================== #
    # GET DATA                                  #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # ========================================== #
    # CREATE WORKBOOK                           #
    # ========================================== #
    wb = openpyxl.Workbook()
    
    # ========================================== #
    # SHEET 1: SUMMARY                          #
    # ========================================== #
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Header
    ws_summary.merge_cells('A1:C1')
    ws_summary['A1'] = company_name
    ws_summary['A1'].font = Font(bold=True, size=16)
    ws_summary['A1'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A2:C2')
    ws_summary['A2'] = "Self Expense Report"
    ws_summary['A2'].font = Font(bold=True, size=14)
    ws_summary['A2'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A3:C3')
    ws_summary['A3'] = f"Period: {from_date} to {to_date}"
    ws_summary['A3'].alignment = Alignment(horizontal='center')
    
    # Summary Data
    summary_data = [
        ['Metric', 'Value'],
        ['Total Self Expenses', float(total_expenses)],
        ['Total Transactions', expenses.count()],
        ['Average Expense', float(total_expenses / expenses.count()) if expenses.count() > 0 else 0],
        ['Products Used', product_details.count()],
        ['Total Product Value', float(total_product_value)],
    ]
    
    row = 5
    for data in summary_data:
        ws_summary.cell(row=row, column=1, value=data[0])
        ws_summary.cell(row=row, column=2, value=data[1])
        if row == 5:
            ws_summary.cell(row=row, column=1).font = Font(bold=True)
            ws_summary.cell(row=row, column=2).font = Font(bold=True)
        row += 1
    
    # Format numbers
    for r in range(6, 11):
        cell = ws_summary.cell(row=r, column=2)
        if isinstance(cell.value, (int, float)):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20
    
    # ========================================== #
    # SHEET 2: PRODUCT DETAILS                  #
    # ========================================== #
    ws_product = wb.create_sheet("Product Details")
    
    # Product Headers
    product_headers = ['#', 'Product Name', 'Serial No', 'Barcode', 'Category', 'Brand', 'Qty', 'Unit', 'Total Amount', 'Transactions']
    for col, header in enumerate(product_headers, 1):
        cell = ws_product.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Product Data
    for idx, product in enumerate(product_details, 1):
        row = idx + 1
        ws_product.cell(row=row, column=1, value=idx)
        ws_product.cell(row=row, column=2, value=product['product__name'] or '-')
        ws_product.cell(row=row, column=3, value=product['product__serial_no'] or '-')
        ws_product.cell(row=row, column=4, value=product['product__barcode'] or '-')
        ws_product.cell(row=row, column=5, value=product['product__category__name'] or '-')
        ws_product.cell(row=row, column=6, value=product['product__brand__name'] or '-')
        ws_product.cell(row=row, column=7, value=float(product['total_qty']))
        ws_product.cell(row=row, column=8, value=product['product__unit__name'] or '-')
        ws_product.cell(row=row, column=9, value=float(product['total_amount']))
        ws_product.cell(row=row, column=10, value=product['total_count'])
        
        # Format numbers
        ws_product.cell(row=row, column=7).number_format = '#,##0.00'
        ws_product.cell(row=row, column=9).number_format = '#,##0.00'
        ws_product.cell(row=row, column=7).alignment = Alignment(horizontal='right')
        ws_product.cell(row=row, column=9).alignment = Alignment(horizontal='right')
        ws_product.cell(row=row, column=10).alignment = Alignment(horizontal='center')
    
    # Product Total Row
    if product_details:
        total_row = len(product_details) + 2
        ws_product.cell(row=total_row, column=1, value="TOTAL")
        ws_product.cell(row=total_row, column=8, value="TOTAL:")
        ws_product.cell(row=total_row, column=9, value=float(total_product_value))
        ws_product.cell(row=total_row, column=10, value=product_details.count())
        
        for col in [1, 8, 9, 10]:
            cell = ws_product.cell(row=total_row, column=col)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="e8ecf4", end_color="e8ecf4", fill_type="solid")
        
        ws_product.cell(row=total_row, column=9).number_format = '#,##0.00'
        ws_product.cell(row=total_row, column=9).alignment = Alignment(horizontal='right')
    
    # Product Column Widths
    product_widths = [5, 35, 15, 18, 20, 15, 10, 10, 15, 12]
    for i, width in enumerate(product_widths, 1):
        ws_product.column_dimensions[get_column_letter(i)].width = width
    
    # ========================================== #
    # SHEET 3: EXPENSES                         #
    # ========================================== #
    ws_expenses = wb.create_sheet("Expenses")
    
    # Expense Headers
    expense_headers = ['Date', 'Description', 'Category', 'Amount', 'Tax', 'Total', 'Created By', 'Status']
    for col, header in enumerate(expense_headers, 1):
        cell = ws_expenses.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Expense Data
    for idx, exp in enumerate(expenses, 1):
        row = idx + 1
        ws_expenses.cell(row=row, column=1, value=exp.expense_date.strftime('%d-%m-%Y'))
        ws_expenses.cell(row=row, column=2, value=exp.description[:50])
        ws_expenses.cell(row=row, column=3, value=exp.category.name if exp.category else 'Self Expense')
        ws_expenses.cell(row=row, column=4, value=float(exp.amount))
        ws_expenses.cell(row=row, column=5, value=float(exp.tax_amount))
        ws_expenses.cell(row=row, column=6, value=float(exp.total_amount))
        ws_expenses.cell(row=row, column=7, value=exp.created_by.username if exp.created_by else 'System')
        ws_expenses.cell(row=row, column=8, value=exp.get_status_display())
        
        # Format numbers
        for col in [4, 5, 6]:
            cell = ws_expenses.cell(row=row, column=col)
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    # Expense Column Widths
    expense_widths = [12, 40, 20, 12, 12, 12, 15, 12]
    for i, width in enumerate(expense_widths, 1):
        ws_expenses.column_dimensions[get_column_letter(i)].width = width
    
    # ========================================== #
    # CREATE CHART (Product Category)           #
    # ========================================== #
    try:
        # Get product category data
        product_category = SaleItem.objects.filter(
            sale__is_converted_to_expense=True,
            sale__sale_date__date__gte=from_date_obj,
            sale__sale_date__date__lte=to_date_obj,
            product__category__isnull=False
        ).values('product__category__name').annotate(
            total_amount=Sum('total_amt')
        ).order_by('-total_amount')
        
        if product_category:
            # Create a new sheet for chart
            ws_chart = wb.create_sheet("Category Chart")
            
            # Add data
            ws_chart.cell(row=1, column=1, value="Category")
            ws_chart.cell(row=1, column=2, value="Amount")
            ws_chart.cell(row=1, column=1).font = Font(bold=True)
            ws_chart.cell(row=1, column=2).font = Font(bold=True)
            
            for idx, cat in enumerate(product_category, 1):
                ws_chart.cell(row=idx+1, column=1, value=cat['product__category__name'] or 'Uncategorized')
                ws_chart.cell(row=idx+1, column=2, value=float(cat['total_amount']))
                ws_chart.cell(row=idx+1, column=2).number_format = '#,##0.00'
            
            # Create Pie Chart
            chart = PieChart()
            data = Reference(ws_chart, min_col=2, min_row=1, max_row=len(product_category)+1)
            labels = Reference(ws_chart, min_col=1, min_row=2, max_row=len(product_category)+1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(labels)
            chart.title = "Product Category Breakdown"
            
            ws_chart.add_chart(chart, "D2")
            ws_chart.column_dimensions['A'].width = 25
            ws_chart.column_dimensions['B'].width = 15
    except Exception as e:
        # Chart creation failed, continue without chart
        pass
    
    # ========================================== #
    # RESPONSE                                  #
    # ========================================== #
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Self_Expense_Report_{date.today()}.xlsx"'
    wb.save(response)
    return response


@login_required
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
