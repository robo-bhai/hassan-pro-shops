"""Models: ai_bi/operations (split from the former ai_ops.py)."""
from django.db import models
from datetime import date
from django.utils.timezone import now
from django.contrib.auth.models import User

class BusinessOperationPlan(models.Model):
    """
    Main Business Operation Plan - Daily/Weekly/Monthly/Yearly
    """
    
    PLAN_TYPES = [
        ('daily', '📅 Daily Plan'),
        ('weekly', '📆 Weekly Plan'),
        ('monthly', '📊 Monthly Plan'),
        ('quarterly', '🎯 Quarterly Plan'),
        ('yearly', '🏆 Yearly Plan'),
    ]
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('active', '✅ Active'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
        ('on_hold', '⏸️ On Hold'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    DEPARTMENTS = [
        ('sales', '🛒 Sales'),
        ('purchase', '📥 Purchase'),
        ('inventory', '📦 Inventory'),
        ('accounts', '💰 Accounts'),
        ('hr', '👔 HR'),
        ('production', '🏭 Production'),
        ('service', '🛠️ Service'),
        ('marketing', '📢 Marketing'),
        ('admin', '⚙️ Admin'),
    ]
    
    plan_no = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    department = models.CharField(max_length=20, choices=DEPARTMENTS)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    goal_description = models.TextField(blank=True, null=True)
    target_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    target_unit = models.CharField(max_length=50, blank=True, null=True)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    achievement_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    assigned_to = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='operation_plans'
    )
    assigned_team = models.ManyToManyField(
        'Employee', blank=True, related_name='team_operation_plans'
    )
    
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_operation_plans'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_operation_plans'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    # AI Fields
    ai_recommendation = models.TextField(blank=True, null=True)
    ai_risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ai_last_analyzed = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "📋 Business Operation Plans"
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['plan_no']),
            models.Index(fields=['plan_type', 'status']),
            models.Index(fields=['department']),
            models.Index(fields=['start_date', 'end_date']),
        ]
    
    def __str__(self):
        return f"{self.plan_no} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.plan_no:
            last_plan = BusinessOperationPlan.objects.order_by('-id').first()
            if last_plan and last_plan.plan_no:
                try:
                    last_num = int(last_plan.plan_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.plan_no = f'BOP-{new_num}'
        
        if self.target_value > 0:
            self.achievement_percent = (self.actual_value / self.target_value) * 100
            if self.achievement_percent > 100:
                self.achievement_percent = 100
        
        super().save(*args, **kwargs)
    
    def update_progress(self):
        total_tasks = self.tasks.count()
        if total_tasks > 0:
            completed = self.tasks.filter(status='completed').count()
            self.progress_percent = (completed / total_tasks) * 100
            self.save(update_fields=['progress_percent'])
        return self.progress_percent
    
    def approve(self, user):
        self.status = 'active'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    def complete(self, user):
        self.status = 'completed'
        self.completed_at = now()
        self.save()
    
    @property
    def status_badge(self):
        colors = {
            'draft': 'secondary', 'active': 'primary', 'in_progress': 'warning',
            'completed': 'success', 'cancelled': 'danger', 'on_hold': 'info',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def priority_badge(self):
        colors = {'low': 'success', 'medium': 'info', 'high': 'warning', 'critical': 'danger'}
        return f'<span class="badge bg-{colors.get(self.priority, "secondary")}">{self.get_priority_display()}</span>'


class OperationTask(models.Model):
    """Individual tasks under a Business Operation Plan"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
        ('blocked', '🚫 Blocked'),
        ('cancelled', '❌ Cancelled'),
        ('deferred', '⏰ Deferred'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('urgent', '🔴 Urgent'),
    ]
    
    task_no = models.CharField(max_length=20, unique=True, editable=False)
    plan = models.ForeignKey(
        BusinessOperationPlan, on_delete=models.CASCADE,
        related_name='tasks'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    assigned_to = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='operation_tasks'
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='assigned_operation_tasks'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    due_date = models.DateTimeField()
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    depends_on = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='blocking_tasks')
    
    attachment = models.FileField(upload_to='task_attachments/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    # AI Fields
    ai_priority_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ai_suggested = models.BooleanField(default=False)
    ai_notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_operation_tasks'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "✅ Operation Tasks"
        ordering = ['priority', 'due_date']
        indexes = [
            models.Index(fields=['task_no']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.task_no} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.task_no:
            last_task = OperationTask.objects.order_by('-id').first()
            if last_task and last_task.task_no:
                try:
                    last_num = int(last_task.task_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.task_no = f'TASK-{new_num}'
        
        super().save(*args, **kwargs)
    
    def mark_started(self, user):
        self.status = 'in_progress'
        self.started_at = now()
        self.save()
    
    def mark_completed(self, user, hours=None):
        self.status = 'completed'
        self.completed_at = now()
        self.progress_percent = 100
        if hours:
            self.actual_hours = hours
        self.save()
        self.plan.update_progress()
    
    def is_overdue(self):
        return self.status not in ['completed', 'cancelled'] and self.due_date < now()
    
    @property
    def days_left(self):
        if self.due_date:
            delta = (self.due_date.date() - date.today()).days
            return max(0, delta)
        return 0
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'secondary', 'in_progress': 'warning', 'completed': 'success',
            'blocked': 'danger', 'cancelled': 'dark', 'deferred': 'info',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'


class DailyChecklist(models.Model):
    """Daily operational checklist items"""
    
    date = models.DateField()
    department = models.CharField(max_length=20, choices=BusinessOperationPlan.DEPARTMENTS)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    
    is_completed = models.BooleanField(default=False)
    is_mandatory = models.BooleanField(default=True)
    completed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_checklist_items'
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📋 Daily Checklists"
        ordering = ['date', 'department', 'order']
        indexes = [
            models.Index(fields=['date', 'department']),
            models.Index(fields=['is_completed']),
        ]
    
    def __str__(self):
        return f"{self.date} - {self.title}"
    
    def complete(self, user):
        self.is_completed = True
        self.completed_by = user
        self.completed_at = now()
        self.save()


class OperationsKPI(models.Model):
    """Key Performance Indicators for operations"""
    
    KPI_CATEGORIES = [
        ('sales', '🛒 Sales'), ('purchase', '📥 Purchase'),
        ('inventory', '📦 Inventory'), ('financial', '💰 Financial'),
        ('customer', '👥 Customer'), ('employee', '👔 Employee'),
        ('operational', '⚙️ Operational'),
    ]
    
    KPI_STATUS = [
        ('on_track', '✅ On Track'), ('warning', '⚠️ Warning'),
        ('critical', '🔴 Critical'), ('achieved', '🎉 Achieved'),
    ]
    
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=KPI_CATEGORIES)
    description = models.TextField(blank=True, null=True)
    unit = models.CharField(max_length=50, default='%')
    
    target_value = models.DecimalField(max_digits=15, decimal_places=2)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    warning_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=70)
    critical_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    
    status = models.CharField(max_length=20, choices=KPI_STATUS, default='on_track')
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    period_start = models.DateField()
    period_end = models.DateField()
    
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # AI Fields
    ai_prediction = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    ai_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ai_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "📊 Operations KPIs"
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"
    
    def update_status(self):
        if self.target_value > 0:
            self.progress_percent = (self.current_value / self.target_value) * 100
            
            if self.progress_percent >= 100:
                self.status = 'achieved'
            elif self.progress_percent >= self.warning_threshold:
                self.status = 'on_track'
            elif self.progress_percent >= self.critical_threshold:
                self.status = 'warning'
            else:
                self.status = 'critical'
        
        self.save(update_fields=['progress_percent', 'status'])
    
    @property
    def status_badge(self):
        colors = {
            'on_track': 'success', 'warning': 'warning',
            'critical': 'danger', 'achieved': 'primary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'


class OperationAlert(models.Model):
    """Alerts and notifications for operations"""
    
    ALERT_TYPES = [
        ('task_overdue', '⏰ Task Overdue'),
        ('plan_deadline', '📅 Plan Deadline'),
        ('kpi_warning', '⚠️ KPI Warning'),
        ('kpi_critical', '🔴 KPI Critical'),
        ('stock_alert', '📦 Stock Alert'),
        ('payment_due', '💰 Payment Due'),
        ('ai_alert', '🤖 AI Alert'),
        ('custom', '📌 Custom Alert'),
    ]
    
    SEVERITY = [
        ('low', '🟢 Low'), ('medium', '🟡 Medium'),
        ('high', '🟠 High'), ('critical', '🔴 Critical'),
    ]
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY, default='medium')
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    task = models.ForeignKey(OperationTask, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    plan = models.ForeignKey(BusinessOperationPlan, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    kpi = models.ForeignKey(OperationsKPI, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_operation_alerts')
    
    for_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='operation_alerts')
    
    # AI Fields
    ai_generated = models.BooleanField(default=False)
    ai_recommendation = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🚨 Operation Alerts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.title}"


class AIOperationsInsight(models.Model):
    """AI-generated insights for operations"""
    
    INSIGHT_TYPES = [
        ('prediction', '🔮 Prediction'),
        ('recommendation', '💡 Recommendation'),
        ('anomaly', '🔍 Anomaly'),
        ('opportunity', '🎯 Opportunity'),
        ('risk', '⚠️ Risk'),
        ('optimization', '⚡ Optimization'),
    ]
    
    SEVERITY = [
        ('low', '🟢 Low'), ('medium', '🟡 Medium'),
        ('high', '🟠 High'), ('critical', '🔴 Critical'),
    ]
    
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY, default='medium')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    impact_score = models.IntegerField(default=0)
    
    affected_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    recommendation = models.TextField(blank=True, null=True)
    suggested_actions = models.JSONField(default=list, blank=True)
    
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    is_resolved = models.BooleanField(default=False)
    is_ignored = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_ai_insights')
    
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🤖 AI Operations Insights"
        ordering = ['-detected_at']
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {'critical': 'danger', 'high': 'warning', 'medium': 'info', 'low': 'success'}
        return colors.get(self.severity, 'secondary')


class OperationsReport(models.Model):
    """Saved operations reports"""
    
    REPORT_TYPES = [
        ('daily', '📅 Daily Report'),
        ('weekly', '📆 Weekly Report'),
        ('monthly', '📊 Monthly Report'),
        ('department', '🏢 Department Report'),
        ('employee', '👤 Employee Report'),
        ('kpi', '📈 KPI Report'),
        ('ai', '🤖 AI Report'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    department = models.CharField(max_length=20, blank=True, null=True)
    
    report_data = models.JSONField(default=dict)
    ai_summary = models.TextField(blank=True, null=True)
    
    pdf_file = models.FileField(upload_to='operations_reports/', null=True, blank=True)
    
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📄 Operations Reports"
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.period_start} to {self.period_end}"


class AITaskSuggestion(models.Model):
    """AI-generated task suggestions"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('accepted', '✅ Accepted'),
        ('rejected', '❌ Rejected'),
        ('expired', '⏰ Expired'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    department = models.CharField(max_length=20, choices=BusinessOperationPlan.DEPARTMENTS)
    suggested_priority = models.CharField(max_length=10, choices=OperationTask.PRIORITY_CHOICES, default='medium')
    
    suggested_assignee = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_suggested_tasks'
    )
    
    reason = models.TextField(help_text="Why AI is suggesting this task")
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Link to created task if accepted
    created_task = models.ForeignKey(
        OperationTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_ai_suggestion'
    )
    
    generated_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "🤖 AI Task Suggestions"
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"AI Suggestion: {self.title}"
