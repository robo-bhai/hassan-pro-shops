"""Budgeting models."""
from django.db import models
from decimal import Decimal
from datetime import datetime
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from ..system.core import Department, Project

class ExpenseCategory(models.Model):
    """Hierarchical expense categories"""
    
    CATEGORY_TYPES = [
        ('operating', 'Operating Expenses'),
        ('capital', 'Capital Expenses'),
        ('administrative', 'Administrative Expenses'),
        ('selling', 'Selling Expenses'),
        ('research', 'Research & Development'),
        ('other', 'Other Expenses'),
    ]
    
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, default='operating')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    code = models.CharField(max_length=20, unique=True, editable=False)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['category_type']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            last_cat = ExpenseCategory.objects.order_by('-id').first()
            if last_cat and last_cat.code:
                try:
                    last_num = int(last_cat.code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'EC-{new_num}'
        super().save(*args, **kwargs)
    
    def get_full_path(self):
        """Get full category path"""
        if self.parent:
            return f"{self.parent.get_full_path()} > {self.name}"
        return self.name
    
    def get_all_children(self):
        """Get all children categories recursively"""
        children = []
        for child in self.children.filter(is_active=True):
            children.append(child)
            children.extend(child.get_all_children())
        return children


class Budget(models.Model):
    """Main Budget Model"""
    
    BUDGET_TYPES = [
        ('department', '🏢 Department Budget'),
        ('project', '📋 Project Budget'),
        ('category', '📂 Category Budget'),
        ('annual', '📅 Annual Budget'),
        ('quarterly', '📊 Quarterly Budget'),
        ('monthly', '📆 Monthly Budget'),
        ('flexible', '🔄 Flexible Budget'),
    ]
    
    BUDGET_STATUS = [
        ('draft', '📝 Draft'),
        ('pending', '⏳ Pending Approval'),
        ('approved', '✅ Approved'),
        ('active', '✅ Active'),
        ('review', '📋 Under Review'),
        ('expired', '⏰ Expired'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    BUDGET_FREQUENCY = [
        ('one_time', 'One Time'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('half_yearly', 'Half Yearly'),
        ('yearly', 'Yearly'),
    ]
    
    # Basic Information
    budget_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    budget_type = models.CharField(max_length=20, choices=BUDGET_TYPES)
    description = models.TextField(blank=True, null=True)
    
    # Budget Details
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reserved_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Time Period
    period_start = models.DateField()
    period_end = models.DateField()
    frequency = models.CharField(max_length=20, choices=BUDGET_FREQUENCY, default='monthly')
    
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    
    # Status
    status = models.CharField(max_length=20, choices=BUDGET_STATUS, default='draft')
    
    # Alert Thresholds
    alert_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    critical_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=95)
    
    # Approval
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='approved_budget_items')
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='submitted_budget_items')
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # Rollover
    allow_rollover = models.BooleanField(default=False)
    rollover_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='created_budget_items')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Budgets"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['budget_no']),
            models.Index(fields=['budget_type']),
            models.Index(fields=['status']),
            models.Index(fields=['period_start', 'period_end']),
        ]
    
    def __str__(self):
        return f"{self.budget_no} - {self.name} (Rs. {self.allocated_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        from datetime import datetime
        if not self.budget_no:
            year = datetime.now().strftime('%Y')
            last_budget = Budget.objects.filter(budget_no__startswith=f'BDG-{year}').order_by('-budget_no').first()
            if last_budget and last_budget.budget_no:
                try:
                    last_num = int(last_budget.budget_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.budget_no = f'BDG-{year}-{new_num}'
        
        self.remaining_amount = self.allocated_amount - self.used_amount - self.reserved_amount
        super().save(*args, **kwargs)
    
    def calculate_used(self):
        """Calculate used amount from linked expenses"""
        from django.db.models import Sum
        from .. import Expense
        
        # ✅ INCLUDING PAID STATUS
        used = Expense.objects.filter(
            budget=self,
            status__in=['approved', 'paid'],
            expense_date__gte=self.period_start,
            expense_date__lte=self.period_end
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        self.used_amount = used
        self.remaining_amount = self.allocated_amount - used - self.reserved_amount
        self.save(update_fields=['used_amount', 'remaining_amount'])
        return used
    
    def utilization_percent(self):
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return 0
    
    def is_over_budget(self):
        return self.used_amount > self.allocated_amount
    
    def remaining_days(self):
        from datetime import date
        if self.period_end:
            return (self.period_end - date.today()).days
        return 0
    
    def daily_allowance(self):
        days = self.remaining_days()
        if days > 0 and self.remaining_amount > 0:
            return self.remaining_amount / days
        return 0
    
    def submit(self, user):
        from django.utils.timezone import now
        self.status = 'pending'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        from django.utils.timezone import now
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    def activate(self, user):
        self.status = 'active'
        self.save()
    
    def get_status_badge(self):
        colors = {
            'draft': 'secondary',
            'pending': 'warning',
            'approved': 'primary',
            'active': 'success',
            'review': 'info',
            'expired': 'danger',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'


class BudgetAllocation(models.Model):
    """Detailed budget allocation by sub-category"""
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='allocations')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.CASCADE, related_name='budget_allocations')
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Budget Allocations"
        unique_together = ['budget', 'category']
    
    def __str__(self):
        return f"{self.budget.name} - {self.category.name} (Rs. {self.allocated_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        self.remaining_amount = self.allocated_amount - self.used_amount
        super().save(*args, **kwargs)
    
    def utilization_percent(self):
        """Calculate utilization percentage for this allocation"""
        from decimal import Decimal
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return Decimal('0.00')


class BudgetTransaction(models.Model):
    """Track budget transactions"""
    
    TRANSACTION_TYPES = [
        ('allocation', '💰 Budget Allocated'),
        ('adjustment', '📝 Budget Adjusted'),
        ('transfer', '🔄 Budget Transferred'),
        ('expense', '📤 Expense Deducted'),
        ('reserve', '🔒 Budget Reserved'),
        ('release', '🔓 Budget Released'),
        ('rollover', '🔄 Budget Rollover'),
    ]
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField()
    expense = models.ForeignKey('Expense', on_delete=models.SET_NULL, null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Budget Transactions"
        ordering = ['-performed_at']
    
    def __str__(self):
        return f"{self.budget.budget_no} - {self.get_transaction_type_display()} (Rs. {self.amount:,.2f})"


class BudgetAlert(models.Model):
    """Budget alerts and notifications"""
    
    ALERT_TYPES = [
        ('warning', '⚠️ Warning'),
        ('critical', '🔴 Critical'),
        ('over_budget', '❌ Over Budget'),
        ('expiring', '⏰ Expiring'),
    ]
    
    ALERT_STATUS = [
        ('new', '🆕 New'),
        ('read', '📖 Read'),
        ('acknowledged', '✅ Acknowledged'),
        ('resolved', '✅ Resolved'),
    ]
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=ALERT_STATUS, default='new')
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='resolved_budget_alerts')
    
    class Meta:
        verbose_name_plural = "Budget Alerts"
        ordering = ['-triggered_at']
    
    def __str__(self):
        return f"{self.budget.budget_no} - {self.get_alert_type_display()}"
    
    def resolve(self, user):
        self.status = 'resolved'
        self.resolved_at = now()
        self.resolved_by = user
        self.save()


class BudgetForecast(models.Model):
    """Budget forecasting"""
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField()
    forecasted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Budget Forecasts"
        ordering = ['forecast_date']
    
    def __str__(self):
        return f"{self.budget.name} - {self.forecast_date.strftime('%B %Y')}"
    
    def calculate_variance(self):
        if self.forecasted_amount > 0:
            self.variance = self.actual_amount - self.forecasted_amount
            self.variance_percent = (self.variance / self.forecasted_amount) * 100
        return self.variance


class ExpenseBudget(models.Model):
    """Department/project wise budgets"""
    
    BUDGET_PERIODS = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('project', 'Project Based'),
    ]
    
    BUDGET_STATUS = [
        ('draft', '📝 Draft'),
        ('active', '✅ Active'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('expired', '⏰ Expired'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='budgets')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_budgets')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_budgets')
    
    budget_period = models.CharField(max_length=20, choices=BUDGET_PERIODS, default='monthly')
    period_start = models.DateField()
    period_end = models.DateField()
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=BUDGET_STATUS, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_budgets')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_budgets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expense Budgets"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'department']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.category.name}) - Rs. {self.allocated_amount:,.2f}"
    
    def calculate_used(self):
        """Calculate used amount from expenses"""
        used = Expense.objects.filter(
            category=self.category,
            expense_date__gte=self.period_start,
            expense_date__lte=self.period_end,
            status='approved'
        ).aggregate(total=Sum('amount'))['total'] or 0
        self.used_amount = used
        self.remaining_amount = self.allocated_amount - used
        self.save(update_fields=['used_amount', 'remaining_amount'])
        return used
    
    def is_over_budget(self):
        """Check if budget is exceeded"""
        return self.remaining_amount < 0
    
    def budget_utilization_percent(self):
        """Calculate budget utilization percentage"""
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return 0


class Expense(models.Model):
    """Main Expense Model with Professional Features"""
    
    EXPENSE_STATUS = [
        ('draft', '📝 Draft'),
        ('submitted', '📤 Submitted'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('paid', '💰 Paid'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', '💵 Cash'),
        ('bank_transfer', '🏦 Bank Transfer'),
        ('credit_card', '💳 Credit Card'),
        ('debit_card', '💳 Debit Card'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Payment'),
        ('other', '📋 Other'),
    ]
    
    # Basic Information
    expense_no = models.CharField(max_length=20, unique=True, editable=False)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='expenses')
    description = models.TextField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    expense_date = models.DateField()
    
    # Additional Details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    vendor_invoice_no = models.CharField(max_length=100, blank=True, null=True)
    
    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    
    # Budget & Cost Center
    budget = models.ForeignKey(Budget, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    cost_center = models.CharField(max_length=100, blank=True, null=True)
    
    # Approval
    status = models.CharField(max_length=20, choices=EXPENSE_STATUS, default='draft')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_expenses')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_expenses')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Payment
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='paid_expenses')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    
    # Documents
    receipt = models.FileField(upload_to='expenses/receipts/%Y/%m/', null=True, blank=True)
    attachment = models.FileField(upload_to='expenses/attachments/%Y/%m/', null=True, blank=True)
    
    # Recurring
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(max_length=20, choices=ExpenseBudget.BUDGET_PERIODS, null=True, blank=True)
    recurring_end_date = models.DateField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expenses"
        indexes = [
            models.Index(fields=['expense_no']),
            models.Index(fields=['category', 'expense_date']),
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
        ]
    
    def __str__(self):
        return f"{self.expense_no} - {self.description[:30]} (Rs. {self.amount:,.2f})"
    
    def save(self, *args, **kwargs):
        # Generate expense number
        if not self.expense_no:
            year = datetime.now().strftime('%Y%m')
            last_exp = Expense.objects.filter(expense_no__startswith=f'EXP-{year}').order_by('-expense_no').first()
            if last_exp and last_exp.expense_no:
                try:
                    last_num = int(last_exp.expense_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.expense_no = f'EXP-{year}-{new_num}'
        
        # Calculate total with tax
        self.total_amount = self.amount + self.tax_amount
        
        # Update budget if expense is approved
        if self.pk and self.status == 'approved':
            try:
                old_status = Expense.objects.get(pk=self.pk).status
                if old_status != 'approved' and self.budget:
                    self.budget.calculate_used()
            except Expense.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def submit(self, user):
        """Submit expense for approval"""
        self.status = 'submitted'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        """Approve expense"""
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Update budget
        if self.budget:
            self.budget.calculate_used()
    
    def reject(self, user, reason=""):
        """Reject expense"""
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejection_reason = reason
        self.save()
    
    def mark_paid(self, user, payment_date=None):
        """Mark expense as paid"""
        self.status = 'paid'
        self.paid_by = user
        self.paid_at = now()
        self.payment_date = payment_date or date.today()
        self.save()
        
        # Update cash balance
        if self.payment_method == 'cash':
            try:
                from .. import CashBalance
                CashBalance.update_balance(
                    amount=self.total_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Expense #{self.expense_no} - {self.description[:50]}"
                )
            except ImportError:
                pass
    
    def get_status_badge(self):
        """HTML badge for status"""
        colors = {
            'draft': 'secondary',
            'submitted': 'primary',
            'review': 'info',
            'approved': 'success',
            'rejected': 'danger',
            'paid': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def is_approved(self):
        return self.status in ['approved', 'paid']
    
    @property
    def is_pending(self):
        return self.status in ['draft', 'submitted', 'review']


class ExpenseApprovalHistory(models.Model):
    """Track approval history"""
    
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='approval_history')
    action = models.CharField(max_length=20, choices=[
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ])
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    remarks = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Approval History"
        ordering = ['-performed_at']
    
    def __str__(self):
        return f"{self.expense.expense_no} - {self.action} by {self.performed_by}"


class ExpenseClaim(models.Model):
    """Employee expense claims / reimbursement"""
    
    CLAIM_STATUS = [
        ('draft', '📝 Draft'),
        ('submitted', '📤 Submitted'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('reimbursed', '💰 Reimbursed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    claim_no = models.CharField(max_length=20, unique=True, editable=False)
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='expense_claims')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    claim_date = models.DateField(default=now)
    
    # Expenses linked to this claim
    expenses = models.ManyToManyField(Expense, related_name='claims', blank=True)
    
    # Approval
    status = models.CharField(max_length=20, choices=CLAIM_STATUS, default='draft')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_claims')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_claims')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Reimbursement
    reimbursed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reimbursed_claims')
    reimbursed_at = models.DateTimeField(null=True, blank=True)
    reimbursement_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_claims')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expense Claims"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.claim_no} - {self.employee.name} (Rs. {self.total_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.claim_no:
            year = datetime.now().strftime('%Y%m')
            last_claim = ExpenseClaim.objects.filter(claim_no__startswith=f'CLM-{year}').order_by('-claim_no').first()
            if last_claim and last_claim.claim_no:
                try:
                    last_num = int(last_claim.claim_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.claim_no = f'CLM-{year}-{new_num}'
        
        # Calculate total from expenses
        if self.pk:
            total = self.expenses.aggregate(total=Sum('total_amount'))['total'] or 0
            self.total_amount = total
        
        super().save(*args, **kwargs)
    
    def submit(self, user):
        """Submit claim for approval"""
        self.status = 'submitted'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        """Approve claim"""
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    def reject(self, user, reason=""):
        """Reject claim"""
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejection_reason = reason
        self.save()
    
    def mark_reimbursed(self, user, payment_method=None, reference_no=None):
        """Mark claim as reimbursed"""
        self.status = 'reimbursed'
        self.reimbursed_by = user
        self.reimbursed_at = now()
        self.reimbursement_date = date.today()
        if payment_method:
            self.payment_method = payment_method
        if reference_no:
            self.reference_no = reference_no
        self.save()


class ExpenseForecast(models.Model):
    """Expense forecasting"""
    
    month = models.DateField(unique=True)
    forecasted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Expense Forecasts"
        ordering = ['month']
    
    def __str__(self):
        return f"{self.month.strftime('%B %Y')} - Rs. {self.forecasted_amount:,.2f}"
    
    def calculate_variance(self):
        """Calculate variance between forecast and actual"""
        if self.forecasted_amount > 0:
            self.variance = self.actual_amount - self.forecasted_amount
            self.variance_percent = (self.variance / self.forecasted_amount) * 100
        else:
            self.variance = 0
            self.variance_percent = 0
        return self.variance


class BudgetGoal(models.Model):
    """Budget goals and targets"""
    
    GOAL_TYPES = [
        ('saving', '💰 Saving Goal'),
        ('spending', '💳 Spending Goal'),
        ('emergency', '🆘 Emergency Fund'),
        ('investment', '📈 Investment Goal'),
        ('debt', '💸 Debt Reduction'),
        ('purchase', '🛒 Big Purchase'),
    ]
    
    STATUS_CHOICES = [
        ('active', '✅ Active'),
        ('completed', '🎉 Completed'),
        ('cancelled', '❌ Cancelled'),
        ('expired', '⏰ Expired'),
    ]
    
    # Relationships
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='goals')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True, blank=True, 
                                  help_text="Leave empty for overall budget goal")
    
    # Goal Details
    name = models.CharField(max_length=200)
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPES, default='saving')
    description = models.TextField(blank=True, null=True)
    
    # Amounts
    target_amount = models.DecimalField(max_digits=15, decimal_places=2)
    current_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Budget Goals"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.progress:.1f}% ({self.get_status_display()})"
    
    def update_progress(self):
        """Update goal progress based on current amount"""
        from decimal import Decimal
        if self.target_amount > 0:
            self.progress = (self.current_amount / self.target_amount) * 100
            if self.progress >= 100:
                self.is_completed = True
                self.completed_at = now()
                self.status = 'completed'
        self.save()
    
    def get_status_badge(self):
        """Get HTML badge for status"""
        if self.status == 'completed':
            return '<span class="badge bg-success">✅ Completed</span>'
        elif self.progress >= 80:
            return '<span class="badge bg-warning text-dark">🟡 Almost Done</span>'
        elif self.progress >= 50:
            return '<span class="badge bg-info">🟢 In Progress</span>'
        else:
            return '<span class="badge bg-danger">🔴 Behind</span>'
    
    def days_remaining(self):
        """Days until goal deadline"""
        from datetime import date
        if self.end_date:
            days = (self.end_date - date.today()).days
            return max(0, days)
        return 0
    
    def daily_required(self):
        """Amount needed per day to achieve goal"""
        from decimal import Decimal
        days = self.days_remaining()
        remaining = self.target_amount - self.current_amount
        if days > 0 and remaining > 0:
            return remaining / days
        return Decimal('0.00')
    
    def progress_color(self):
        """Get color based on progress"""
        if self.progress >= 80:
            return 'success'
        elif self.progress >= 50:
            return 'warning'
        else:
            return 'danger'
    
    @classmethod
    def check_all_goals(cls):
        """Check all active goals and update progress"""
        goals = cls.objects.filter(status='active')
        for goal in goals:
            goal.update_progress()
        return goals.count()
