"""Admin: budgeting models."""
from ..models import *
from django.contrib import admin
from django.utils.timezone import now
from django.utils.html import format_html
from ..models import ExpenseCategory, ExpenseBudget, Expense, ExpenseApprovalHistory, ExpenseClaim, ExpenseForecast, Budget, BudgetAllocation, BudgetTransaction, BudgetAlert, BudgetForecast


@admin.register(ExpenseCategory, site=admin.site)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category_type', 'parent', 'is_active')
    list_filter = ('category_type', 'is_active')
    search_fields = ('name', 'code', 'description')
    list_editable = ('is_active',)
    readonly_fields = ('code',)


@admin.register(ExpenseBudget, site=admin.site)
class ExpenseBudgetAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'department', 'project', 'budget_period', 
                    'period_start', 'period_end', 'allocated_amount', 'used_amount', 
                    'remaining_amount', 'status')
    list_filter = ('status', 'budget_period', 'category', 'department')
    search_fields = ('name', 'category__name', 'department__name')
    list_editable = ('status',)
    readonly_fields = ('used_amount', 'remaining_amount')
    
    actions = ['activate_budgets', 'approve_budgets', 'expire_budgets']
    
    def activate_budgets(self, request, queryset):
        count = queryset.update(status='active')
        self.message_user(request, f"✅ {count} budgets activated")
    activate_budgets.short_description = "✅ Activate Selected Budgets"
    
    def approve_budgets(self, request, queryset):
        count = queryset.update(status='approved', approved_by=request.user, approved_at=now())
        self.message_user(request, f"✅ {count} budgets approved")
    approve_budgets.short_description = "✅ Approve Selected Budgets"
    
    def expire_budgets(self, request, queryset):
        count = queryset.update(status='expired')
        self.message_user(request, f"⏰ {count} budgets expired")
    expire_budgets.short_description = "⏰ Expire Selected Budgets"


class ExpenseApprovalHistoryInline(admin.TabularInline):
    model = ExpenseApprovalHistory
    fields = ('action', 'performed_by', 'remarks', 'performed_at')
    readonly_fields = ('performed_at',)
    extra = 0
    can_delete = False


@admin.register(Expense, site=admin.site)
class ExpenseAdmin(admin.ModelAdmin):
    # ✅ NO 'date' FIELD ANYWHERE
    list_display = (
        'expense_no',
        'description',
        'category',
        'amount',
        'expense_date',
        'status_display',
        'payment_method',
        'created_by'
    )
    
    list_filter = (
        'status',
        'category',
        'payment_method',
        'expense_date',
        'department'
    )
    
    search_fields = ('expense_no', 'description', 'reference_no', 'vendor__name')
    
    # ✅ NO list_editable - removed completely
    # list_editable = ()  # Empty
    
    inlines = [ExpenseApprovalHistoryInline]
    readonly_fields = ('expense_no', 'total_amount', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Expense Information', {
            'fields': ('expense_no', 'category', 'description', 'amount', 'expense_date')
        }),
        ('Payment Details', {
            'fields': ('payment_method', 'reference_no', 'vendor', 'vendor_invoice_no')
        }),
        ('Tax', {
            'fields': ('tax_rate', 'tax_amount', 'total_amount')
        }),
        ('Budget & Cost Center', {
            'fields': ('budget', 'department', 'project', 'cost_center')
        }),
        ('Approval', {
            'fields': ('status', 'submitted_by', 'submitted_at', 'approved_by', 
                      'approved_at', 'rejection_reason')
        }),
        ('Payment', {
            'fields': ('paid_by', 'paid_at', 'payment_date')
        }),
        ('Documents', {
            'fields': ('receipt', 'attachment')
        }),
        ('Recurring', {
            'fields': ('is_recurring', 'recurring_frequency', 'recurring_end_date'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': ('created_by', 'created_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    def status_display(self, obj):
        return format_html(obj.get_status_badge())
    status_display.short_description = "Status"
    
    actions = ['submit_expenses', 'approve_expenses', 'reject_expenses', 'mark_paid']
    
    def submit_expenses(self, request, queryset):
        count = 0
        for expense in queryset.filter(status='draft'):
            expense.submit(request.user)
            count += 1
        self.message_user(request, f"📤 {count} expenses submitted")
    submit_expenses.short_description = "📤 Submit Selected Expenses"
    
    def approve_expenses(self, request, queryset):
        count = 0
        for expense in queryset.filter(status='submitted'):
            expense.approve(request.user)
            count += 1
        self.message_user(request, f"✅ {count} expenses approved")
    approve_expenses.short_description = "✅ Approve Selected Expenses"
    
    def reject_expenses(self, request, queryset):
        count = 0
        for expense in queryset.filter(status__in=['submitted', 'review']):
            expense.reject(request.user, "Rejected via bulk action")
            count += 1
        self.message_user(request, f"❌ {count} expenses rejected")
    reject_expenses.short_description = "❌ Reject Selected Expenses"
    
    def mark_paid(self, request, queryset):
        count = 0
        for expense in queryset.filter(status='approved'):
            expense.mark_paid(request.user)
            count += 1
        self.message_user(request, f"💰 {count} expenses marked as paid")
    mark_paid.short_description = "💰 Mark as Paid"


@admin.register(ExpenseClaim, site=admin.site)
class ExpenseClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_no', 'employee', 'title', 'total_amount', 'claim_date', 'status')
    list_filter = ('status', 'claim_date', 'employee')
    search_fields = ('claim_no', 'employee__name', 'title')
    list_editable = ('status',)
    filter_horizontal = ('expenses',)
    readonly_fields = ('claim_no', 'total_amount')
    
    actions = ['approve_claims', 'reject_claims', 'mark_reimbursed']
    
    def approve_claims(self, request, queryset):
        count = queryset.update(status='approved', approved_by=request.user, approved_at=now())
        self.message_user(request, f"✅ {count} claims approved")
    approve_claims.short_description = "✅ Approve Selected Claims"
    
    def reject_claims(self, request, queryset):
        count = queryset.update(status='rejected', approved_by=request.user, approved_at=now())
        self.message_user(request, f"❌ {count} claims rejected")
    reject_claims.short_description = "❌ Reject Selected Claims"
    
    def mark_reimbursed(self, request, queryset):
        count = queryset.update(status='reimbursed', reimbursed_by=request.user, reimbursed_at=now())
        self.message_user(request, f"💰 {count} claims marked as reimbursed")
    mark_reimbursed.short_description = "💰 Mark as Reimbursed"


@admin.register(ExpenseForecast, site=admin.site)
class ExpenseForecastAdmin(admin.ModelAdmin):
    list_display = ('month', 'forecasted_amount', 'actual_amount', 'variance', 'variance_percent')
    list_filter = ('month',)
    search_fields = ('notes',)
    readonly_fields = ('variance', 'variance_percent')


class BudgetAllocationInline(admin.TabularInline):
    model = BudgetAllocation
    fields = ('category', 'allocated_amount', 'used_amount', 'remaining_amount')
    readonly_fields = ('used_amount', 'remaining_amount')
    extra = 1


class BudgetTransactionInline(admin.TabularInline):
    model = BudgetTransaction
    fields = ('transaction_type', 'amount', 'balance_after', 'description')
    readonly_fields = ('balance_after', 'performed_at')
    extra = 0
    can_delete = False


@admin.register(Budget, site=admin.site)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('budget_no', 'name', 'budget_type', 'department', 'project', 
                    'allocated_amount', 'used_amount', 'remaining_amount', 
                    'utilization_display', 'status_display', 'period_end')
    list_filter = ('budget_type', 'status', 'frequency', 'department')
    search_fields = ('budget_no', 'name', 'description')
    inlines = [BudgetAllocationInline, BudgetTransactionInline]
    
    fieldsets = (
        ('Budget Information', {
            'fields': ('budget_no', 'name', 'budget_type', 'description')
        }),
        ('Amounts', {
            'fields': ('allocated_amount', 'used_amount', 'remaining_amount', 'reserved_amount')
        }),
        ('Period', {
            'fields': ('period_start', 'period_end', 'frequency')
        }),
        ('Links', {
            'fields': ('department', 'project', 'category')
        }),
        ('Status', {
            'fields': ('status', 'alert_threshold', 'critical_threshold', 
                      'approved_by', 'approved_at', 'submitted_by', 'submitted_at')
        }),
        ('Settings', {
            'fields': ('allow_rollover', 'rollover_from')
        }),
        ('System', {
            'fields': ('created_by', 'created_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('budget_no', 'used_amount', 'remaining_amount', 'created_at', 'updated_at')
    
    def utilization_display(self, obj):
        percent = obj.utilization_percent()
        if percent >= obj.critical_threshold:
            color = 'red'
        elif percent >= obj.alert_threshold:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color, percent
        )
    utilization_display.short_description = "Utilization"
    
    def status_display(self, obj):
        return format_html(obj.get_status_badge())
    status_display.short_description = "Status"
    
    actions = ['approve_budgets', 'activate_budgets', 'submit_budgets']
    
    def submit_budgets(self, request, queryset):
        for budget in queryset.filter(status='draft'):
            budget.submit(request.user)
        self.message_user(request, f"📤 {queryset.count()} budgets submitted")
    submit_budgets.short_description = "📤 Submit for Approval"
    
    def approve_budgets(self, request, queryset):
        for budget in queryset.filter(status='pending'):
            budget.approve(request.user)
        self.message_user(request, f"✅ {queryset.count()} budgets approved")
    approve_budgets.short_description = "✅ Approve Selected Budgets"
    
    def activate_budgets(self, request, queryset):
        for budget in queryset.filter(status='approved'):
            budget.activate(request.user)
        self.message_user(request, f"✅ {queryset.count()} budgets activated")
    activate_budgets.short_description = "✅ Activate Selected Budgets"


@admin.register(BudgetAlert, site=admin.site)
class BudgetAlertAdmin(admin.ModelAdmin):
    list_display = ('budget', 'alert_type', 'message', 'status', 'triggered_at')
    list_filter = ('alert_type', 'status')
    search_fields = ('budget__name', 'message')
    list_editable = ('status',)
    
    actions = ['resolve_alerts']
    
    def resolve_alerts(self, request, queryset):
        for alert in queryset.filter(status__in=['new', 'read']):
            alert.resolve(request.user)
        self.message_user(request, f"✅ {queryset.count()} alerts resolved")
    resolve_alerts.short_description = "✅ Resolve Selected Alerts"


@admin.register(BudgetForecast, site=admin.site)
class BudgetForecastAdmin(admin.ModelAdmin):
    list_display = ('budget', 'forecast_date', 'forecasted_amount', 'actual_amount', 
                    'variance', 'variance_percent', 'confidence_level')
    list_filter = ('forecast_date',)
    search_fields = ('budget__name',)
