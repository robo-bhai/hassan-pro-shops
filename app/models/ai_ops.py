"""Ai Ops models."""
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User

class AIInsight(models.Model):
    """AI-generated insights and findings"""
    
    INSIGHT_TYPES = [
        ('anomaly', '🔍 Anomaly Detection'),
        ('prediction', '🔮 Prediction'),
        ('recommendation', '💡 Recommendation'),
        ('risk', '⚠️ Risk Alert'),
        ('opportunity', '🎯 Opportunity'),
        ('optimization', '⚡ Optimization'),
    ]
    
    SEVERITY_LEVELS = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
        ('info', '🔵 Info'),
    ]
    
    CATEGORIES = [
        ('data_quality', '📊 Data Quality'),
        ('business', '💰 Business'),
        ('performance', '⚡ Performance'),
        ('security', '🔐 Security'),
        ('usability', '📱 Usability'),
        ('inventory', '📦 Inventory'),
        ('financial', '💵 Financial'),
        ('customer', '👥 Customer'),
        ('employee', '👔 Employee'),
    ]
    
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # AI Confidence (0-100%)
    confidence_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="AI confidence in this insight"
    )
    
    # Impact
    impact_score = models.IntegerField(
        default=0,
        help_text="Business impact score (0-100)"
    )
    
    # Data
    affected_records = models.IntegerField(default=0)
    affected_value = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Monetary value affected"
    )
    
    # Recommendations
    recommendation = models.TextField(blank=True, null=True)
    suggested_actions = models.JSONField(default=list, blank=True)
    fix_url = models.CharField(max_length=255, blank=True, null=True)
    
    # Data snapshot
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    # Status
    is_resolved = models.BooleanField(default=False)
    is_ignored = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='resolved_insights'
    )
    
    # Timestamps
    detected_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "🧠 AI Insights"
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['insight_type', 'severity']),
            models.Index(fields=['category', 'is_resolved']),
            models.Index(fields=['-detected_at']),
        ]
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info',
            'low': 'success',
            'info': 'secondary',
        }
        return colors.get(self.severity, 'secondary')
    
    @property
    def type_icon(self):
        icons = {
            'anomaly': '🔍',
            'prediction': '🔮',
            'recommendation': '💡',
            'risk': '⚠️',
            'opportunity': '🎯',
            'optimization': '⚡',
        }
        return icons.get(self.insight_type, '📊')


class AILearningData(models.Model):
    """Data for AI to learn from user actions"""
    
    insight = models.ForeignKey(
        AIInsight, 
        on_delete=models.CASCADE, 
        related_name='learning_data'
    )
    
    # User action
    ACTION_TYPES = [
        ('viewed', '👁️ Viewed'),
        ('accepted', '✅ Accepted'),
        ('rejected', '❌ Rejected'),
        ('ignored', '🔇 Ignored'),
        ('fixed', '🔧 Fixed'),
        ('deferred', '⏰ Deferred'),
    ]
    
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='ai_learning_actions'
    )
    feedback = models.TextField(blank=True, null=True)
    time_spent_seconds = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📚 AI Learning Data"
        ordering = ['-created_at']


class AIHealthScore(models.Model):
    """Daily AI health score of the system"""
    
    date = models.DateField(unique=True)
    
    # Overall score
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    
    # Category scores
    data_quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    business_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    security_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    usability_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    
    # Insights count
    total_insights = models.IntegerField(default=0)
    critical_count = models.IntegerField(default=0)
    high_count = models.IntegerField(default=0)
    medium_count = models.IntegerField(default=0)
    low_count = models.IntegerField(default=0)
    
    # Trends
    previous_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    trend = models.CharField(
        max_length=10, 
        choices=[('up', '⬆️'), ('down', '⬇️'), ('stable', '➡️')],
        default='stable'
    )
    
    # AI Recommendations
    top_recommendations = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 AI Health Scores"
        ordering = ['-date']
    
    def __str__(self):
        return f"Health Score - {self.date}: {self.overall_score}/100"


class AIAnomalyDetection(models.Model):
    """Anomalies detected by AI"""
    
    ANOMALY_TYPES = [
        ('spike', '📈 Sudden Spike'),
        ('drop', '📉 Sudden Drop'),
        ('pattern_break', '🔄 Pattern Break'),
        ('outlier', '🎯 Outlier'),
        ('unusual_behavior', '⚠️ Unusual Behavior'),
    ]
    
    anomaly_type = models.CharField(max_length=20, choices=ANOMALY_TYPES)
    metric_name = models.CharField(max_length=100, help_text="Which metric")
    expected_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    deviation_percent = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    description = models.TextField()
    data_points = models.JSONField(default=list, blank=True)
    
    # AI Confidence
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    detected_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "🔍 AI Anomalies"
        ordering = ['-detected_at']
    
    def __str__(self):
        return f"{self.get_anomaly_type_display()}: {self.metric_name}"


class AIPrediction(models.Model):
    """AI Predictions for business"""
    
    PREDICTION_TYPES = [
        ('sales', '📈 Sales'),
        ('demand', '📦 Demand'),
        ('cashflow', '💰 Cash Flow'),
        ('stockout', '⚠️ Stock Out'),
        ('payment', '💳 Payment'),
        ('churn', '🚫 Customer Churn'),
        ('growth', '📊 Growth'),
    ]
    
    prediction_type = models.CharField(max_length=20, choices=PREDICTION_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Prediction details
    target_date = models.DateField()
    predicted_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # Confidence
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    methodology = models.CharField(max_length=100, blank=True, null=True)
    
    # Data
    historical_data = models.JSONField(default=list, blank=True)
    prediction_data = models.JSONField(default=list, blank=True)
    
    # Related
    product = models.ForeignKey(
        'Product', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='predictions'
    )
    customer = models.ForeignKey(
        'Customer', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='predictions'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    is_accurate = models.BooleanField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "🔮 AI Predictions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_prediction_type_display()}: {self.title}"


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


class AIPurchaseAnalysis(models.Model):
    """AI Purchase Analysis - Store AI recommendations"""
    
    CONFIDENCE_LEVELS = [
        ('high', '🟢 High (85%+)'),
        ('medium', '🟡 Medium (60-85%)'),
        ('low', '🔴 Low (<60%)'),
    ]
    
    RISK_LEVELS = [
        ('safe', '✅ Safe'),
        ('warning', '⚠️ Warning'),
        ('danger', '🚨 Danger'),
    ]
    
    # Link to plan
    plan = models.ForeignKey(
        'MonthlyPurchasePlan',
        on_delete=models.CASCADE,
        related_name='ai_analysis',
        null=True,
        blank=True
    )
    
    # Product info
    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='purchase_ai_analyses'
    )
    warehouse = models.ForeignKey(
        'Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # ==========================================
    # AI SUGGESTIONS
    # ==========================================
    suggested_quantity = models.IntegerField(
        default=0,
        help_text="AI recommended purchase quantity"
    )
    min_quantity = models.IntegerField(default=0, help_text="Minimum safe quantity")
    max_quantity = models.IntegerField(default=0, help_text="Maximum safe quantity")
    
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="AI confidence 0-100%"
    )
    confidence_level = models.CharField(
        max_length=10,
        choices=CONFIDENCE_LEVELS,
        default='low'
    )
    
    # ==========================================
    # ANALYSIS DATA
    # ==========================================
    avg_daily_sales = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Average daily sales (last 90 days)"
    )
    current_stock = models.IntegerField(default=0)
    stock_coverage_days = models.IntegerField(
        default=0,
        help_text="How many days current stock will last"
    )
    sales_trend = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Sales trend % (+ or -)"
    )
    
    # ==========================================
    # RISK ANALYSIS
    # ==========================================
    risk_level = models.CharField(
        max_length=10,
        choices=RISK_LEVELS,
        default='safe'
    )
    risk_factors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of risk factors"
    )
    
    # ==========================================
    # FINANCIAL IMPACT
    # ==========================================
    estimated_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    cash_after_purchase = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    
    # ==========================================
    # AI EXPLANATIONS
    # ==========================================
    reasoning = models.JSONField(
        default=list,
        blank=True,
        help_text="Why AI suggested this"
    )
    warnings = models.JSONField(
        default=list,
        blank=True,
        help_text="Warnings and risks"
    )
    opportunities = models.JSONField(
        default=list,
        blank=True,
        help_text="Opportunities detected"
    )
    
    # ==========================================
    # USER DECISION
    # ==========================================
    user_accepted = models.BooleanField(null=True, blank=True)
    user_modified_quantity = models.IntegerField(null=True, blank=True)
    user_notes = models.TextField(blank=True, null=True)
    
    # ==========================================
    # TIMESTAMPS
    # ==========================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "🤖 AI Purchase Analyses"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['confidence_level']),
        ]
    
    def __str__(self):
        return f"AI Analysis - {self.product.name} ({self.confidence_score}%)"
    
    @property
    def confidence_color(self):
        """Get color for confidence level"""
        colors = {
            'high': 'success',
            'medium': 'warning',
            'low': 'danger'
        }
        return colors.get(self.confidence_level, 'secondary')
    
    @property
    def risk_color(self):
        """Get color for risk level"""
        colors = {
            'safe': 'success',
            'warning': 'warning',
            'danger': 'danger'
        }
        return colors.get(self.risk_level, 'secondary')
    
    @property
    def formatted_confidence(self):
        return f"{self.confidence_score:.1f}%"
    
    @property
    def formatted_cost(self):
        return f"Rs. {self.estimated_cost:,.2f}"


class AIPurchaseAccuracy(models.Model):
    """Track AI prediction accuracy over time"""
    
    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='ai_accuracy_records'
    )
    
    # Prediction
    predicted_quantity = models.IntegerField()
    prediction_date = models.DateField()
    prediction_confidence = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Actual result
    actual_sales = models.IntegerField(null=True, blank=True)
    evaluation_date = models.DateField(null=True, blank=True)
    
    # Accuracy
    accuracy_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    is_accurate = models.BooleanField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 AI Prediction Accuracy"
        ordering = ['-prediction_date']
    
    def __str__(self):
        return f"{self.product.name} - {self.prediction_date} - {self.accuracy_percentage or 'N/A'}%"


class AIPurchaseInsight(models.Model):
    """General AI insights for purchase planning"""
    
    INSIGHT_TYPES = [
        ('opportunity', '🎯 Opportunity'),
        ('warning', '⚠️ Warning'),
        ('risk', '🚨 Risk'),
        ('trend', '📈 Trend'),
        ('recommendation', '💡 Recommendation'),
    ]
    
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Related data
    affected_products = models.JSONField(default=list, blank=True)
    impact_score = models.IntegerField(default=0)
    
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "💡 AI Purchase Insights"
        ordering = ['-impact_score', '-created_at']
    
    def __str__(self):
        return f"[{self.get_insight_type_display()}] {self.title}"


class AICashAnalysis(models.Model):
    """AI Cash Flow Analysis - Store all predictions"""
    
    CONFIDENCE_LEVELS = [
        ('high', '🟢 High (85%+)'),
        ('medium', '🟡 Medium (60-85%)'),
        ('low', '🔴 Low (<60%)'),
    ]
    
    RISK_LEVELS = [
        ('safe', '✅ Safe'),
        ('warning', '⚠️ Warning'),
        ('critical', '🚨 Critical'),
        ('emergency', '🔥 Emergency'),
    ]
    
    analysis_date = models.DateField(default=now)
    analysis_type = models.CharField(
        max_length=20,
        choices=[
            ('daily', '📅 Daily Analysis'),
            ('weekly', '📆 Weekly Analysis'),
            ('monthly', '📊 Monthly Analysis'),
            ('forecast', '🔮 Forecast'),
            ('health', '❤️ Health Check'),
        ],
        default='daily'
    )
    
    # ==========================================
    # CURRENT STATE
    # ==========================================
    current_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    
    # ==========================================
    # FORECAST DATA (JSON)
    # ==========================================
    forecast_7_days = models.JSONField(
        default=list,
        blank=True,
        help_text="7-day balance forecast"
    )
    forecast_30_days = models.JSONField(
        default=list,
        blank=True,
        help_text="30-day balance forecast"
    )
    forecast_90_days = models.JSONField(
        default=list,
        blank=True,
        help_text="90-day balance forecast"
    )
    
    # ==========================================
    # PREDICTIONS
    # ==========================================
    predicted_daily_inflow = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    predicted_daily_outflow = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    
    days_until_shortage = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days until cash goes negative"
    )
    predicted_shortage_date = models.DateField(
        null=True,
        blank=True
    )
    predicted_shortage_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    
    # ==========================================
    # HEALTH SCORE
    # ==========================================
    health_score = models.IntegerField(
        default=100,
        help_text="0-100 cash health score"
    )
    liquidity_score = models.IntegerField(default=100)
    buffer_score = models.IntegerField(default=100)
    inflow_score = models.IntegerField(default=100)
    outflow_score = models.IntegerField(default=100)
    predictability_score = models.IntegerField(default=100)
    
    # ==========================================
    # RISK
    # ==========================================
    risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVELS,
        default='safe'
    )
    risk_factors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    
    # ==========================================
    # CONFIDENCE
    # ==========================================
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    confidence_level = models.CharField(
        max_length=10,
        choices=CONFIDENCE_LEVELS,
        default='low'
    )
    confidence_reasons = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🤖 AI Cash Analyses"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-analysis_date']),
            models.Index(fields=['risk_level']),
        ]
    
    def __str__(self):
        return f"Cash Analysis {self.analysis_date} - Score: {self.health_score}"
    
    @property
    def risk_color(self):
        colors = {
            'safe': 'success',
            'warning': 'warning',
            'critical': 'danger',
            'emergency': 'dark',
        }
        return colors.get(self.risk_level, 'secondary')
    
    @property
    def health_color(self):
        if self.health_score >= 80:
            return 'success'
        elif self.health_score >= 60:
            return 'warning'
        else:
            return 'danger'
    
    @property
    def health_label(self):
        if self.health_score >= 80:
            return '🟢 Excellent'
        elif self.health_score >= 60:
            return '🟡 Good'
        elif self.health_score >= 40:
            return '🟠 Moderate'
        else:
            return '🔴 Poor'


class AICashAlert(models.Model):
    """AI Cash Alerts - Warnings & Notifications"""
    
    ALERT_TYPES = [
        ('shortage', '🚨 Cash Shortage'),
        ('low_balance', '⚠️ Low Balance'),
        ('large_transaction', '💰 Large Transaction'),
        ('unusual_pattern', '🔍 Unusual Pattern'),
        ('fraud', '🚫 Fraud Suspected'),
        ('payment_due', '📅 Payment Due'),
        ('collection', '📥 Collection Reminder'),
        ('opportunity', '🎯 Opportunity'),
    ]
    
    SEVERITY_LEVELS = [
        ('info', '🔵 Info'),
        ('warning', '🟡 Warning'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='info')
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Related data
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    related_transaction = models.ForeignKey(
        'CashTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    # Actions
    suggested_action = models.TextField(blank=True, null=True)
    action_url = models.CharField(max_length=255, blank=True, null=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_cash_alerts'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "🚨 AI Cash Alerts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_resolved', '-created_at']),
            models.Index(fields=['severity']),
        ]
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {
            'info': 'info',
            'warning': 'warning',
            'high': 'orange',
            'critical': 'danger',
        }
        return colors.get(self.severity, 'secondary')


class AICashCollectionForecast(models.Model):
    """AI prediction of customer collections"""
    
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='ai_collection_forecasts'
    )
    
    outstanding_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    expected_collection = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0
    )
    collection_probability = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="0-100% probability"
    )
    expected_date = models.DateField(null=True, blank=True)
    
    reason = models.TextField(blank=True, null=True)
    
    is_collected = models.BooleanField(default=False)
    actual_collection = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    actual_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "📥 AI Collection Forecasts"
        ordering = ['-collection_probability']
    
    def __str__(self):
        return f"{self.customer.name} - {self.collection_probability}%"


class AICashHealthHistory(models.Model):
    """Track cash health over time"""
    
    date = models.DateField(unique=True)
    health_score = models.IntegerField(default=100)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    liquidity_score = models.IntegerField(default=100)
    buffer_score = models.IntegerField(default=100)
    inflow_score = models.IntegerField(default=100)
    outflow_score = models.IntegerField(default=100)
    predictability_score = models.IntegerField(default=100)
    
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "❤️ AI Cash Health History"
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.date} - {self.health_score}/100"


class AIShareholderScore(models.Model):
    """AI Score for each shareholder - 0 to 100"""
    
    RISK_LEVELS = [
        ('excellent', '🟢 Excellent'),
        ('good', '🟡 Good'),
        ('warning', '🟠 Warning'),
        ('critical', '🔴 Critical'),
    ]
    
    shareholder = models.OneToOneField(
        'Shareholder',
        on_delete=models.CASCADE,
        related_name='ai_score'
    )
    
    # Overall score
    overall_score = models.IntegerField(default=50)
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS, default='good')
    
    # Individual factor scores
    loyalty_score = models.IntegerField(default=50, help_text="0-100")
    financial_score = models.IntegerField(default=50)
    activity_score = models.IntegerField(default=50)
    growth_score = models.IntegerField(default=50)
    risk_score = models.IntegerField(default=50)
    
    # Detailed factors
    factors = models.JSONField(default=dict, blank=True)
    
    # Recommendations
    recommendations = models.JSONField(default=list, blank=True)
    
    # Metadata
    years_as_shareholder = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    total_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    activity_frequency = models.IntegerField(default=0, help_text="Activities per year")
    
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "⭐ AI Shareholder Scores"
        ordering = ['-overall_score']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.overall_score}/100"
    
    @property
    def score_color(self):
        colors = {
            'excellent': 'success',
            'good': 'info',
            'warning': 'warning',
            'critical': 'danger',
        }
        return colors.get(self.risk_level, 'secondary')
    
    @property
    def star_rating(self):
        """Convert score to 5-star rating"""
        if self.overall_score >= 90:
            return '⭐⭐⭐⭐⭐'
        elif self.overall_score >= 75:
            return '⭐⭐⭐⭐'
        elif self.overall_score >= 60:
            return '⭐⭐⭐'
        elif self.overall_score >= 40:
            return '⭐⭐'
        else:
            return '⭐'


class AIShareholderChurn(models.Model):
    """AI Churn Prediction for Shareholders"""
    
    RISK_LEVELS = [
        ('low', '🟢 Low Risk'),
        ('medium', '🟡 Medium Risk'),
        ('high', '🟠 High Risk'),
        ('critical', '🔴 Critical - About to Leave'),
    ]
    
    shareholder = models.OneToOneField(
        'Shareholder',
        on_delete=models.CASCADE,
        related_name='ai_churn_risk'
    )
    
    churn_probability = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="0-100% chance of leaving"
    )
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS, default='low')
    
    # Risk factors
    days_since_last_activity = models.IntegerField(default=0)
    days_since_last_deposit = models.IntegerField(default=0)
    withdrawal_requests_count = models.IntegerField(default=0)
    recent_deposits = models.IntegerField(default=0)
    
    # Analysis
    risk_factors = models.JSONField(default=list, blank=True)
    retention_actions = models.JSONField(default=list, blank=True)
    
    # Estimated value at risk
    investment_at_risk = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    is_contacted = models.BooleanField(default=False)
    contacted_at = models.DateTimeField(null=True, blank=True)
    contacted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacted_churn_shareholders'
    )
    retention_notes = models.TextField(blank=True, null=True)
    
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "🚨 AI Churn Predictions"
        ordering = ['-churn_probability']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.churn_probability}% churn risk"


class AIDividendRecommendation(models.Model):
    """AI Dividend Recommendations"""
    
    STATUS = [
        ('pending', '⏳ Pending'),
        ('accepted', '✅ Accepted'),
        ('rejected', '❌ Rejected'),
        ('used', '🎯 Used'),
    ]
    
    # Analysis period
    analysis_date = models.DateField(default=now)
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Recommendations
    recommended_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Recommended dividend % of profit"
    )
    recommended_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    
    # Analysis data
    total_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    min_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    max_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=70)
    
    # Reasoning
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reasoning = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    
    # Impact
    cash_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    buffer_days = models.IntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    applied_dividend_id = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "💰 AI Dividend Recommendations"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.recommended_percentage}% - Rs. {self.recommended_amount:,.0f}"


class AIShareholderAlert(models.Model):
    """AI Alerts for Shareholders"""
    
    ALERT_TYPES = [
        ('churn', '🚨 Churn Risk'),
        ('fraud', '🔒 Suspicious Activity'),
        ('opportunity', '🎯 Opportunity'),
        ('milestone', '🎉 Milestone'),
        ('communication', '📱 Communication Needed'),
        ('dividend', '💰 Dividend Related'),
        ('transfer', '🔄 Transfer Alert'),
    ]
    
    SEVERITY = [
        ('info', '🔵 Info'),
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder',
        on_delete=models.CASCADE,
        related_name='ai_alerts'
    )
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY, default='info')
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Action
    suggested_action = models.TextField(blank=True, null=True)
    action_url = models.CharField(max_length=255, blank=True, null=True)
    
    # Data
    amount_involved = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_shareholder_alerts'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🚨 AI Shareholder Alerts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.shareholder.name} - {self.title}"


class AIShareholderForecast(models.Model):
    """6-Month Forecast for Shareholder Module"""
    
    forecast_date = models.DateField(default=now)
    
    # Predictions
    total_shareholders = models.IntegerField(default=0)
    new_shareholders_expected = models.IntegerField(default=0)
    churn_expected = models.IntegerField(default=0)
    total_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_dividends = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Confidence
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Details
    monthly_forecast = models.JSONField(default=list, blank=True)
    risks = models.JSONField(default=list, blank=True)
    opportunities = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🔮 AI Shareholder Forecasts"
        ordering = ['-forecast_date']
    
    def __str__(self):
        return f"Forecast {self.forecast_date}"


class AIShareholderCommunication(models.Model):
    """AI-Generated Communications"""
    
    COMMUNICATION_TYPES = [
        ('retention', '🎯 Retention'),
        ('appreciation', '🙏 Appreciation'),
        ('bonus', '🎁 Bonus Offer'),
        ('announcement', '📢 Announcement'),
        ('dividend', '💰 Dividend Info'),
        ('custom', '📝 Custom'),
    ]
    
    CHANNELS = [
        ('whatsapp', '📱 WhatsApp'),
        ('email', '📧 Email'),
        ('sms', '💬 SMS'),
        ('call', '📞 Call Script'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder',
        on_delete=models.CASCADE,
        related_name='ai_communications'
    )
    
    communication_type = models.CharField(max_length=20, choices=COMMUNICATION_TYPES)
    channel = models.CharField(max_length=20, choices=CHANNELS, default='whatsapp')
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # AI context
    reason = models.TextField(blank=True, null=True)
    ai_generated = models.BooleanField(default=True)
    
    # Status
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    response = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📱 AI Communications"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.get_communication_type_display()}"


class AIBoardMember(models.Model):
    """Store all 6 AI Board Members' individual reports"""
    
    MEMBER_TYPES = [
        ('ceo', '👑 CEO - Chief Executive Officer'),
        ('cfo', '💰 CFO - Chief Financial Officer'),
        ('ca', '📊 CA - Chartered Accountant'),
        ('coo', '⚙️ COO - Chief Operating Officer'),
        ('cso', '🎯 CSO - Chief Strategy Officer'),
        ('csho', '👥 CSHO - Chief Shareholder Officer'),
    ]
    
    member_type = models.CharField(max_length=10, choices=MEMBER_TYPES)
    report_date = models.DateField(default=now)
    
    # ==========================================
    # HEALTH SCORE
    # ==========================================
    health_score = models.IntegerField(
        default=0,
        help_text="0-100 score"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('excellent', '🟢 Excellent'),
            ('good', '🟡 Good'),
            ('warning', '🟠 Warning'),
            ('critical', '🔴 Critical'),
        ],
        default='good'
    )
    
    # ==========================================
    # REPORT DATA
    # ==========================================
    summary = models.TextField(
        help_text="Executive summary of the report"
    )
    key_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Key metrics for this role"
    )
    findings = models.JSONField(
        default=list,
        blank=True,
        help_text="Detailed findings"
    )
    recommendations = models.JSONField(
        default=list,
        blank=True,
        help_text="Recommendations with priority"
    )
    warnings = models.JSONField(
        default=list,
        blank=True,
        help_text="Critical warnings"
    )
    opportunities = models.JSONField(
        default=list,
        blank=True,
        help_text="Growth opportunities"
    )
    
    # Financial impact
    potential_savings = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Money that can be saved"
    )
    potential_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Additional revenue possible"
    )
    
    # Metadata
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🏢 AI Board Members"
        ordering = ['-report_date', 'member_type']
        unique_together = ['member_type', 'report_date']
        indexes = [
            models.Index(fields=['-report_date']),
            models.Index(fields=['member_type']),
        ]
    
    def __str__(self):
        return f"{self.get_member_type_display()} - {self.report_date}"
    
    @property
    def status_color(self):
        colors = {
            'excellent': 'success',
            'good': 'info',
            'warning': 'warning',
            'critical': 'danger',
        }
        return colors.get(self.status, 'secondary')
    
    @property
    def emoji(self):
        emojis = {
            'ceo': '👑',
            'cfo': '💰',
            'ca': '📊',
            'coo': '⚙️',
            'cso': '🎯',
            'csho': '👥',
        }
        return emojis.get(self.member_type, '👤')


class AIBoardMeeting(models.Model):
    """Complete Board Meeting - All 7 members together with Cash Utilization"""
    
    meeting_date = models.DateField(default=now)
    title = models.CharField(
        max_length=255,
        default="Daily Board Meeting"
    )
    
    # ========================================== #
    # OVERALL HEALTH                             #
    # ========================================== #
    overall_health_score = models.IntegerField(
        default=0,
        help_text="Average of all 7 members"
    )
    overall_status = models.CharField(
        max_length=20,
        default='good'
    )
    
    # ========================================== #
    # INDIVIDUAL SCORES - 7 BOARD MEMBERS        #
    # ========================================== #
    ceo_score = models.IntegerField(default=0, help_text="CEO Score")
    cfo_score = models.IntegerField(default=0, help_text="CFO Score")
    ca_score = models.IntegerField(default=0, help_text="CA Score")
    coo_score = models.IntegerField(default=0, help_text="COO Score")
    cso_score = models.IntegerField(default=0, help_text="CSO Score")
    csho_score = models.IntegerField(default=0, help_text="CSHO Score")
    cso_tech_score = models.IntegerField(
        default=0,
        help_text="CSO Tech (IT/System) health score"
    )
    
    # ========================================== #
    # ✅ CASH UTILIZATION ANALYSIS               #
    # ========================================== #
    cfo_cash_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Total cash available in hand"
    )
    idle_cash = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Cash sitting idle (not invested)"
    )
    invested_cash = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Cash working in loans/investments"
    )
    utilization_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Cash utilization % (0-100)"
    )
    potential_cash_profit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Expected annual profit if idle cash invested"
    )
    
    # ========================================== #
    # UNIFIED RECOMMENDATIONS                    #
    # ========================================== #
    executive_summary = models.TextField(
        blank=True,
        help_text="Overall business summary"
    )
    
    top_priorities = models.JSONField(
        default=list,
        blank=True,
        help_text="Ranked priorities across all experts"
    )
    
    action_plan = models.JSONField(
        default=dict,
        blank=True,
        help_text="30/60/90 day action plan"
    )
    
    risks = models.JSONField(
        default=list,
        blank=True,
        help_text="Consolidated risks from all experts"
    )
    
    opportunities = models.JSONField(
        default=list,
        blank=True,
        help_text="Consolidated opportunities"
    )
    
    # ========================================== #
    # FINANCIAL IMPACT                           #
    # ========================================== #
    total_potential_savings = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    total_potential_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    net_impact = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    
    # ========================================== #
    # DECISIONS                                  #
    # ========================================== #
    critical_decisions = models.JSONField(
        default=list,
        blank=True,
        help_text="Decisions requiring CEO attention"
    )
    
    quick_wins = models.JSONField(
        default=list,
        blank=True,
        help_text="Quick wins (next 7 days)"
    )
    
    long_term_goals = models.JSONField(
        default=list,
        blank=True,
        help_text="6-12 month goals"
    )
    
    # ========================================== #
    # METADATA                                   #
    # ========================================== #
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    
    # ========================================== #
    # RELATIONSHIPS                              #
    # ========================================== #
    board_members = models.ManyToManyField(
        AIBoardMember,
        blank=True,
        related_name='meetings'
    )
    
    # ========================================== #
    # TIMESTAMPS                                 #
    # ========================================== #
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🏢 AI Board Meetings"
        ordering = ['-meeting_date', '-created_at']
        unique_together = ['meeting_date', 'title']
        indexes = [
            models.Index(fields=['-meeting_date']),
            models.Index(fields=['overall_status']),
        ]
    
    def __str__(self):
        return f"Board Meeting - {self.meeting_date} ({self.overall_health_score}/100)"
    
    # ========================================== #
    # PROPERTIES                                 #
    # ========================================== #
    @property
    def overall_status_color(self):
        """Get Bootstrap color for overall status"""
        colors = {
            'excellent': 'success',
            'good': 'info',
            'warning': 'warning',
            'critical': 'danger',
        }
        return colors.get(self.overall_status, 'secondary')
    
    @property
    def total_members(self):
        """Total number of board members (should be 7)"""
        return 7
    
    @property
    def average_score(self):
        """Calculate average score across all 7 members"""
        scores = [
            self.ceo_score,
            self.cfo_score,
            self.ca_score,
            self.coo_score,
            self.cso_score,
            self.csho_score,
            self.cso_tech_score,
        ]
        return sum(scores) / len(scores) if scores else 0
    
    @property
    def formatted_savings(self):
        """Formatted potential savings"""
        return f"Rs. {self.total_potential_savings:,.2f}"
    
    @property
    def formatted_revenue(self):
        """Formatted potential revenue"""
        return f"Rs. {self.total_potential_revenue:,.2f}"
    
    @property
    def formatted_impact(self):
        """Formatted net impact"""
        return f"Rs. {self.net_impact:,.2f}"
    
    # ========================================== #
    # ✅ CASH UTILIZATION PROPERTIES             #
    # ========================================== #
    @property
    def formatted_cash_balance(self):
        """Formatted cash balance"""
        return f"Rs. {self.cfo_cash_balance:,.2f}"
    
    @property
    def formatted_idle_cash(self):
        """Formatted idle cash"""
        return f"Rs. {self.idle_cash:,.2f}"
    
    @property
    def formatted_invested_cash(self):
        """Formatted invested cash"""
        return f"Rs. {self.invested_cash:,.2f}"
    
    @property
    def formatted_potential_profit(self):
        """Formatted potential profit"""
        return f"Rs. {self.potential_cash_profit:,.2f}"
    
    @property
    def utilization_status(self):
        """Get utilization status category"""
        rate = float(self.utilization_rate)
        if rate >= 70:
            return 'excellent'
        elif rate >= 50:
            return 'good'
        elif rate >= 30:
            return 'warning'
        return 'critical'
    
    @property
    def utilization_color(self):
        """Get Bootstrap color for utilization"""
        colors = {
            'excellent': 'success',
            'good': 'info',
            'warning': 'warning',
            'critical': 'danger',
        }
        return colors.get(self.utilization_status, 'secondary')
    
    @property
    def utilization_label(self):
        """Get utilization label text"""
        rate = float(self.utilization_rate)
        if rate >= 70:
            return '✅ Excellent'
        elif rate >= 50:
            return '🟢 Good'
        elif rate >= 30:
            return '🟡 Moderate'
        return '🔴 Low'
    
    @property
    def has_cash_opportunity(self):
        """Check if there's cash investment opportunity"""
        return self.idle_cash > 10000
    
    # ========================================== #
    # METHODS                                    #
    # ========================================== #
    def get_member_scores(self):
        """Get all member scores as dictionary"""
        return {
            'ceo': {'name': 'CEO', 'score': self.ceo_score, 'icon': '👑'},
            'cfo': {'name': 'CFO', 'score': self.cfo_score, 'icon': '💰'},
            'ca': {'name': 'CA', 'score': self.ca_score, 'icon': '📊'},
            'coo': {'name': 'COO', 'score': self.coo_score, 'icon': '⚙️'},
            'cso': {'name': 'CSO', 'score': self.cso_score, 'icon': '🎯'},
            'csho': {'name': 'CSHO', 'score': self.csho_score, 'icon': '👥'},
            'cso_tech': {'name': 'CSO Tech', 'score': self.cso_tech_score, 'icon': '💻'},
        }
    
    def recalculate_overall_score(self):
        """Recalculate overall score (average of all 7 members)"""
        self.overall_health_score = int(self.average_score)
        
        if self.overall_health_score >= 80:
            self.overall_status = 'excellent'
        elif self.overall_health_score >= 60:
            self.overall_status = 'good'
        elif self.overall_health_score >= 40:
            self.overall_status = 'warning'
        else:
            self.overall_status = 'critical'
        
        self.save(update_fields=['overall_health_score', 'overall_status'])
        return self.overall_health_score
    
    def calculate_utilization_rate(self):
        """Recalculate utilization rate"""
        total = self.cfo_cash_balance + self.invested_cash
        if total > 0:
            self.utilization_rate = (self.invested_cash / total) * 100
        else:
            self.utilization_rate = 0
        self.save(update_fields=['utilization_rate'])
        return self.utilization_rate


class AIBoardAlert(models.Model):
    """Critical alerts from Board Room"""
    
    SEVERITY_LEVELS = [
        ('info', '🔵 Info'),
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    ALERT_SOURCES = [
        ('ceo', '👑 CEO'),
        ('cfo', '💰 CFO'),
        ('ca', '📊 CA'),
        ('coo', '⚙️ COO'),
        ('cso', '🎯 CSO'),
        ('csho', '👥 CSHO'),
        ('board', '🏢 Board Room'),
    ]
    
    source = models.CharField(max_length=10, choices=ALERT_SOURCES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='info')
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Action
    suggested_action = models.TextField(blank=True, null=True)
    action_url = models.CharField(max_length=255, blank=True, null=True)
    
    # Data
    impact_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    data_snapshot = models.JSONField(default=dict, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_board_alerts'
    )
    
    # Link to meeting
    meeting = models.ForeignKey(
        AIBoardMeeting,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🚨 AI Board Alerts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_resolved', '-created_at']),
            models.Index(fields=['severity']),
            models.Index(fields=['source']),
        ]
    
    def __str__(self):
        return f"[{self.get_source_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {
            'info': 'info',
            'low': 'success',
            'medium': 'warning',
            'high': 'orange',
            'critical': 'danger',
        }
        return colors.get(self.severity, 'secondary')
    
    @property
    def source_emoji(self):
        emojis = {
            'ceo': '👑',
            'cfo': '💰',
            'ca': '📊',
            'coo': '⚙️',
            'cso': '🎯',
            'csho': '👥',
            'board': '🏢',
        }
        return emojis.get(self.source, '📌')


class AIBoardKPI(models.Model):
    """Board-level KPIs tracked over time"""
    
    date = models.DateField(default=now)
    
    # Financial KPIs
    revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Operations KPIs
    inventory_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    order_fulfillment = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    production_efficiency = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Customer KPIs
    active_customers = models.IntegerField(default=0)
    customer_satisfaction = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    customer_churn_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Shareholder KPIs
    total_shareholders = models.IntegerField(default=0)
    shareholder_satisfaction = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    dividend_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Overall
    overall_health = models.IntegerField(default=0)
    
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 AI Board KPIs"
        ordering = ['-date']
        unique_together = ['date']
    
    def __str__(self):
        return f"KPIs - {self.date} (Health: {self.overall_health})"


class AISystemHealth(models.Model):
    """Track system health metrics"""
    
    date = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of measurement"
    )
    
    # PERFORMANCE
    response_time_ms = models.IntegerField(
        default=0,
        help_text="Average response time in milliseconds"
    )
    uptime_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="System uptime %"
    )
    error_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Error rate %"
    )
    
    # DATABASE
    db_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Database size in MB"
    )
    db_query_time_ms = models.IntegerField(
        default=0,
        help_text="Average DB query time in ms"
    )
    
    # SERVER
    cpu_usage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="CPU usage %"
    )
    memory_usage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Memory usage %"
    )
    disk_usage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Disk usage %"
    )
    
    # USERS
    active_users = models.IntegerField(
        default=0,
        help_text="Currently active users"
    )
    peak_concurrent = models.IntegerField(
        default=0,
        help_text="Peak concurrent users"
    )
    
    # OVERALL
    health_score = models.IntegerField(
        default=100,
        help_text="Overall health 0-100"
    )
    
    class Meta:
        verbose_name_plural = "💻 System Health Records"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
        ]
    
    def __str__(self):
        return f"Health {self.health_score}/100 - {self.date}"
    
    @property
    def health_color(self):
        if self.health_score >= 80:
            return 'success'
        elif self.health_score >= 60:
            return 'info'
        elif self.health_score >= 40:
            return 'warning'
        else:
            return 'danger'


class AISecurityLog(models.Model):
    """Security events detection"""
    
    SEVERITY = [
        ('info', '🔵 Info'),
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    EVENT_TYPES = [
        ('login_fail', '🔒 Failed Login'),
        ('brute_force', '🚨 Brute Force'),
        ('sql_injection', '💉 SQL Injection'),
        ('unauthorized', '🚫 Unauthorized Access'),
        ('permission', '⚠️ Permission Violation'),
        ('data_access', '📊 Unusual Data Access'),
        ('api_abuse', '🔌 API Abuse'),
        ('suspicious_ip', '🌐 Suspicious IP'),
        ('password_change', '🔑 Password Change'),
        ('2fa_failed', '🔐 2FA Failed'),
    ]
    
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY,
        default='info'
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_logs'
    )
    
    # Status
    is_resolved = models.BooleanField(default=False)
    is_blocked = models.BooleanField(
        default=False,
        help_text="IP or user blocked"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_security_logs'
    )
    
    # Extra data
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional data"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🔐 Security Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['severity']),
            models.Index(fields=['event_type']),
            models.Index(fields=['is_resolved']),
        ]
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {
            'info': 'info',
            'low': 'success',
            'medium': 'warning',
            'high': 'orange',
            'critical': 'danger',
        }
        return colors.get(self.severity, 'secondary')


class AIPerformanceIssue(models.Model):
    """Performance issues detected"""
    
    ISSUE_TYPES = [
        ('slow_query', '🐌 Slow Query'),
        ('n_plus_1', '📊 N+1 Problem'),
        ('missing_index', '📇 Missing Index'),
        ('large_payload', '📦 Large Payload'),
        ('memory_leak', '💧 Memory Leak'),
        ('deadlock', '🔒 Database Deadlock'),
        ('slow_endpoint', '⏱️ Slow Endpoint'),
        ('high_memory', '💾 High Memory Usage'),
    ]
    
    STATUS_CHOICES = [
        ('new', '🆕 New'),
        ('investigating', '🔍 Investigating'),
        ('fixed', '✅ Fixed'),
        ('ignored', '🔇 Ignored'),
    ]
    
    issue_type = models.CharField(
        max_length=20,
        choices=ISSUE_TYPES
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new'
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    url_endpoint = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="API endpoint or URL affected"
    )
    
    # Metrics
    current_value = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Current measured value"
    )
    target_value = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Target/optimal value"
    )
    
    # Fix
    fix_suggested = models.TextField(
        blank=True,
        null=True,
        help_text="Suggested fix"
    )
    priority = models.IntegerField(
        default=5,
        help_text="Priority 1-10 (higher = more urgent)"
    )
    
    # Resolution
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_performance_issues'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "⚡ Performance Issues"
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['is_resolved', '-priority']),
            models.Index(fields=['issue_type']),
        ]
    
    def __str__(self):
        return f"[P{self.priority}] {self.title}"
    
    @property
    def priority_color(self):
        if self.priority >= 8:
            return 'danger'
        elif self.priority >= 6:
            return 'warning'
        elif self.priority >= 4:
            return 'info'
        else:
            return 'secondary'


class AIFeatureSuggestion(models.Model):
    """Feature suggestions from CSO Tech AI"""
    
    PRIORITY = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    STATUS = [
        ('pending', '⏳ Pending'),
        ('accepted', '✅ Accepted'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎉 Completed'),
        ('rejected', '❌ Rejected'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(
        help_text="What is this feature"
    )
    reason = models.TextField(
        help_text="Why this feature is needed"
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY,
        default='medium'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='pending'
    )
    
    # Impact
    expected_impact = models.TextField(
        blank=True,
        null=True,
        help_text="What benefit will it provide"
    )
    effort_hours = models.IntegerField(
        default=0,
        help_text="Estimated hours to build"
    )
    roi_score = models.IntegerField(
        default=0,
        help_text="ROI Score 0-100"
    )
    
    # Processing
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_features'
    )
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "💡 Feature Suggestions"
        ordering = ['-roi_score', '-created_at']
        indexes = [
            models.Index(fields=['status', '-roi_score']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"
    
    @property
    def priority_color(self):
        colors = {
            'low': 'success',
            'medium': 'info',
            'high': 'warning',
            'critical': 'danger',
        }
        return colors.get(self.priority, 'secondary')
    
    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'accepted': 'primary',
            'in_progress': 'info',
            'completed': 'success',
            'rejected': 'secondary',
        }
        return colors.get(self.status, 'secondary')
    
    def accept(self, user):
        """Accept the feature suggestion"""
        self.status = 'accepted'
        self.processed_at = now()
        self.processed_by = user
        self.save()
        return True
    
    def reject(self, user, reason=''):
        """Reject the feature suggestion"""
        self.status = 'rejected'
        self.processed_at = now()
        self.processed_by = user
        self.notes = reason
        self.save()
        return True
    
    def start_progress(self, user):
        """Mark as in progress"""
        self.status = 'in_progress'
        self.processed_at = now()
        self.processed_by = user
        self.save()
        return True
    
    def complete(self, user):
        """Mark as completed"""
        self.status = 'completed'
        self.processed_at = now()
        self.processed_by = user
        self.save()
        return True


class AIBugReport(models.Model):
    """Auto-captured bugs"""
    
    SEVERITY = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('critical', '🔴 Critical'),
    ]
    
    STATUS = [
        ('new', '🆕 New'),
        ('investigating', '🔍 Investigating'),
        ('fixed', '✅ Fixed'),
        ('closed', '🔒 Closed'),
        ('duplicate', '📋 Duplicate'),
        ('wont_fix', '❌ Won\'t Fix'),
    ]
    
    title = models.CharField(max_length=255)
    error_message = models.TextField(
        help_text="The error message"
    )
    stack_trace = models.TextField(
        blank=True,
        null=True,
        help_text="Full stack trace"
    )
    
    # Context
    url_endpoint = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Where the bug occurred"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bug_reports'
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="Browser/device info"
    )
    
    # Classification
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY,
        default='medium'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='new'
    )
    
    # Tracking
    frequency = models.IntegerField(
        default=1,
        help_text="How many times occurred"
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    # Analysis
    root_cause = models.TextField(
        blank=True,
        null=True,
        help_text="Root cause analysis"
    )
    fix_suggested = models.TextField(
        blank=True,
        null=True,
        help_text="Suggested fix"
    )
    
    # Resolution
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_bugs'
    )
    
    class Meta:
        verbose_name_plural = "🐛 Auto Bug Reports"
        ordering = ['-frequency', '-last_seen']
        indexes = [
            models.Index(fields=['status', '-frequency']),
            models.Index(fields=['severity']),
            models.Index(fields=['-last_seen']),
        ]
    
    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
    
    @property
    def severity_color(self):
        colors = {
            'low': 'success',
            'medium': 'warning',
            'high': 'orange',
            'critical': 'danger',
        }
        return colors.get(self.severity, 'secondary')
    
    @property
    def status_color(self):
        colors = {
            'new': 'danger',
            'investigating': 'warning',
            'fixed': 'success',
            'closed': 'secondary',
            'duplicate': 'info',
            'wont_fix': 'secondary',
        }
        return colors.get(self.status, 'secondary')
    
    @property
    def age_days(self):
        """Age in days"""
        delta = now() - self.first_seen
        return delta.days
    
    def fix(self, user):
        """Mark bug as fixed"""
        self.status = 'fixed'
        self.resolved_at = now()
        self.resolved_by = user
        self.save()
        return True
    
    def close(self, user):
        """Close the bug"""
        self.status = 'closed'
        self.resolved_at = now()
        self.resolved_by = user
        self.save()
        return True


class AICodeQuality(models.Model):
    """Track code quality metrics"""
    
    date = models.DateField(
        default=now,
        help_text="Date of measurement"
    )
    
    # Metrics
    total_files = models.IntegerField(default=0)
    total_lines = models.IntegerField(default=0)
    total_functions = models.IntegerField(default=0)
    
    # Quality
    test_coverage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Test coverage %"
    )
    duplicate_lines = models.IntegerField(
        default=0,
        help_text="Lines of duplicate code"
    )
    complex_functions = models.IntegerField(
        default=0,
        help_text="Functions with high complexity"
    )
    todo_count = models.IntegerField(
        default=0,
        help_text="Pending TODOs"
    )
    
    # Overall
    quality_score = models.IntegerField(
        default=100,
        help_text="Overall score 0-100"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📝 Code Quality Records"
        ordering = ['-date']
        unique_together = ['date']
    
    def __str__(self):
        return f"Code Quality {self.quality_score}/100 - {self.date}"


class AIIntegrationStatus(models.Model):
    """Track integration health"""
    
    INTEGRATION_TYPES = [
        ('whatsapp', '📱 WhatsApp'),
        ('email', '📧 Email'),
        ('sms', '💬 SMS'),
        ('payment', '💳 Payment Gateway'),
        ('bank', '🏦 Bank'),
        ('cloud', '☁️ Cloud Backup'),
        ('api', '🔌 External API'),
    ]
    
    STATUS_CHOICES = [
        ('operational', '✅ Operational'),
        ('degraded', '🟡 Degraded'),
        ('down', '🔴 Down'),
        ('unknown', '❓ Unknown'),
    ]
    
    integration_type = models.CharField(
        max_length=20,
        choices=INTEGRATION_TYPES
    )
    name = models.CharField(
        max_length=100,
        help_text="Integration name"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='operational'
    )
    
    # Performance
    response_time_ms = models.IntegerField(default=0)
    success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="Success rate %"
    )
    
    # Last check
    last_checked = models.DateTimeField(auto_now=True)
    last_error = models.TextField(blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🔗 Integration Status"
        ordering = ['integration_type', 'name']
        unique_together = ['integration_type', 'name']
    
    def __str__(self):
        return f"{self.get_integration_type_display()} - {self.name}: {self.get_status_display()}"
    
    @property
    def status_color(self):
        colors = {
            'operational': 'success',
            'degraded': 'warning',
            'down': 'danger',
            'unknown': 'secondary',
        }
        return colors.get(self.status, 'secondary')


class CashInvestmentStrategy(models.Model):
    """AI-recommended cash investment strategies"""
    
    STRATEGY_TYPES = [
        ('inventory', '📦 Inventory Investment'),
        ('customer_credit', '💳 Customer Credit'),
        ('shareholder_loan', '👥 Shareholder Loan'),
        ('bank_deposit', '🏦 Bank Deposit'),
        ('marketing', '📢 Marketing'),
        ('expansion', '🚀 Business Expansion'),
        ('vendor_advance', '📥 Vendor Advance'),
        ('other', '📋 Other'),
    ]
    
    RISK_LEVELS = [
        ('very_low', '🟢 Very Low'),
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🟠 High'),
        ('very_high', '🔴 Very High'),
    ]
    
    STATUS_CHOICES = [
        ('recommended', '💡 Recommended'),
        ('approved', '✅ Approved'),
        ('executing', '⚙️ Executing'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    strategy_type = models.CharField(max_length=20, choices=STRATEGY_TYPES)
    description = models.TextField()
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    expected_roi = models.DecimalField(max_digits=5, decimal_places=2)
    expected_profit = models.DecimalField(max_digits=15, decimal_places=2)
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS, default='medium')
    timeline_months = models.IntegerField(default=12)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='recommended')
    
    actual_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    recommended_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    ai_generated = models.BooleanField(default=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reasoning = models.JSONField(default=list, blank=True)
    
    meeting = models.ForeignKey(
        AIBoardMeeting, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cash_strategies'
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_cash_strategies'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_cash_strategies'
    )
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "💰 Cash Investment Strategies"
        ordering = ['-expected_profit', '-recommended_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['strategy_type']),
            models.Index(fields=['-expected_profit']),
        ]
    
    def __str__(self):
        return f"{self.name} - Rs. {self.amount:,.0f} @ {self.expected_roi}%"
    
    @property
    def risk_color(self):
        colors = {
            'very_low': 'success', 'low': 'success',
            'medium': 'warning', 'high': 'orange', 'very_high': 'danger',
        }
        return colors.get(self.risk_level, 'secondary')
    
    @property
    def status_color(self):
        colors = {
            'recommended': 'info', 'approved': 'primary',
            'executing': 'warning', 'completed': 'success', 'cancelled': 'secondary',
        }
        return colors.get(self.status, 'secondary')
    
    @property
    def roi_status(self):
        if not self.actual_amount or self.actual_amount == 0:
            return 'pending'
        actual_roi = float(self.actual_profit / self.actual_amount * 100)
        expected = float(self.expected_roi)
        if actual_roi >= expected:
            return 'exceeded'
        elif actual_roi >= expected * 0.8:
            return 'met'
        return 'below'
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def formatted_profit(self):
        return f"Rs. {self.expected_profit:,.2f}"
    
    def approve(self, user):
        self.status = 'approved'
        self.approved_at = now()
        self.approved_by = user
        self.save()
    
    def start_execution(self):
        self.status = 'executing'
        self.executed_at = now()
        self.save()
    
    def complete(self, actual_profit=0, actual_amount=0):
        self.status = 'completed'
        self.completed_at = now()
        self.actual_profit = Decimal(str(actual_profit))
        self.actual_amount = Decimal(str(actual_amount))
        self.save()
    
    def cancel(self, reason=''):
        self.status = 'cancelled'
        self.notes = f"{self.notes}\nCancelled: {reason}".strip()
        self.save()
    
    def calculate_actual_roi(self):
        if self.actual_amount > 0:
            return (self.actual_profit / self.actual_amount) * 100
        return Decimal('0')


class StrategyAllocation(models.Model):
    """
    Configure strategy allocation AND custom ROI
    ✅ 6 Strategies: Bulk, Seasonal, Credit, Advance, New Product, Fast-Moving
    ✅ No 100% restriction — auto-normalizes
    """
    
    # ========================================== #
    # ALLOCATION PERCENTAGES                     #
    # ========================================== #
    bulk_purchase = models.DecimalField(
        max_digits=5, decimal_places=2, default=25.00,
        verbose_name="📦 Bulk Purchase %",
    )
    seasonal_stock = models.DecimalField(
        max_digits=5, decimal_places=2, default=20.00,
        verbose_name="🌙 Seasonal Stock %",
    )
    customer_credit = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00,
        verbose_name="💳 Customer Credit %",
    )
    vendor_advance = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        verbose_name="📥 Vendor Advance %",
    )
    new_product = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        verbose_name="🚀 New Product %",
    )
    # ✅ NEW: Fast-Moving
    fast_moving = models.DecimalField(
        max_digits=5, decimal_places=2, default=20.00,
        verbose_name="⚡ Fast-Moving Product %",
        help_text="Percentage for Fast-Moving Products"
    )
    
    # ========================================== #
    # ROI FIELDS                                 #
    # ========================================== #
    bulk_purchase_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=25.00,
        verbose_name="📦 Bulk Purchase ROI %",
    )
    seasonal_stock_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=35.00,
        verbose_name="🌙 Seasonal Stock ROI %",
    )
    customer_credit_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=18.00,
        verbose_name="💳 Customer Credit ROI %",
    )
    vendor_advance_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=28.00,
        verbose_name="📥 Vendor Advance ROI %",
    )
    new_product_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=35.00,
        verbose_name="🚀 New Product ROI %",
    )
    # ✅ NEW: Fast-Moving ROI
    fast_moving_roi = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        verbose_name="⚡ Fast-Moving ROI %",
        help_text="Expected ROI for Fast-Moving Products (annual)"
    )
    
    # ========================================== #
    # PROFILE INFO                               #
    # ========================================== #
    profile_name = models.CharField(max_length=100, default='Default')
    profile_description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_allocations'
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_allocations'
    )
    
    class Meta:
        verbose_name_plural = "⚙️ Strategy Allocations"
        ordering = ['-is_active', '-updated_at']
    
    def __str__(self):
        status = "✅" if self.is_active else "⏸️"
        return f"{status} {self.profile_name} (Avg ROI: {self.get_average_roi()}%)"
    
    # ========================================== #
    # ALLOCATION METHODS                         #
    # ========================================== #
    def total_percentage(self):
        return (
            self.bulk_purchase + self.seasonal_stock +
            self.customer_credit + self.vendor_advance +
            self.new_product + self.fast_moving
        )
    
    def is_valid(self):
        return self.total_percentage() > 0
    
    def is_perfect_100(self):
        return abs(self.total_percentage() - Decimal('100.00')) < Decimal('0.01')
    
    def get_allocation_dict(self):
        """Auto-normalizes to 100%"""
        bulk = float(self.bulk_purchase)
        seasonal = float(self.seasonal_stock)
        credit = float(self.customer_credit)
        advance = float(self.vendor_advance)
        new = float(self.new_product)
        fast = float(self.fast_moving)
        
        total = bulk + seasonal + credit + advance + new + fast
        
        if total > 0:
            return {
                'bulk_purchase': bulk / total,
                'seasonal_stock': seasonal / total,
                'customer_credit': credit / total,
                'vendor_advance': advance / total,
                'new_product': new / total,
                'fast_moving': fast / total,
            }
        else:
            return {
                'bulk_purchase': 0.25, 'seasonal_stock': 0.20,
                'customer_credit': 0.15, 'vendor_advance': 0.10,
                'new_product': 0.10, 'fast_moving': 0.20,
            }
    
    def get_normalized_percentages(self):
        allocation = self.get_allocation_dict()
        return {
            'bulk_purchase': round(allocation['bulk_purchase'] * 100, 2),
            'seasonal_stock': round(allocation['seasonal_stock'] * 100, 2),
            'customer_credit': round(allocation['customer_credit'] * 100, 2),
            'vendor_advance': round(allocation['vendor_advance'] * 100, 2),
            'new_product': round(allocation['new_product'] * 100, 2),
            'fast_moving': round(allocation['fast_moving'] * 100, 2),
        }
    
    # ========================================== #
    # ROI METHODS                                #
    # ========================================== #
    def get_roi_dict(self):
        return {
            'bulk_purchase': float(self.bulk_purchase_roi),
            'seasonal_stock': float(self.seasonal_stock_roi),
            'customer_credit': float(self.customer_credit_roi),
            'vendor_advance': float(self.vendor_advance_roi),
            'new_product': float(self.new_product_roi),
            'fast_moving': float(self.fast_moving_roi),
        }
    
    def get_average_roi(self):
        allocation = self.get_allocation_dict()
        rois = self.get_roi_dict()
        
        avg_roi = (
            allocation['bulk_purchase'] * rois['bulk_purchase'] +
            allocation['seasonal_stock'] * rois['seasonal_stock'] +
            allocation['customer_credit'] * rois['customer_credit'] +
            allocation['vendor_advance'] * rois['vendor_advance'] +
            allocation['new_product'] * rois['new_product'] +
            allocation['fast_moving'] * rois['fast_moving']
        )
        return round(avg_roi, 2)
    
    def save(self, *args, **kwargs):
        if self.is_active:
            StrategyAllocation.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        allocation = cls.objects.filter(is_active=True).first()
        if not allocation:
            allocation = cls.objects.create(profile_name='Default', is_active=True)
        return allocation


class EmergencyFund(models.Model):
    """
    Emergency Fund - Bure waqt ke liye alag bachat
    
    Features:
    - Target amount set karo
    - Har mahine paisa jama karo
    - Progress track karo
    - Kitne mahine ka fund hai
    """
    
    FUND_TYPES = [
        ('personal', '👤 Personal Emergency'),
        ('business', '🏢 Business Emergency'),
        ('medical', '🏥 Medical Emergency'),
        ('family', '👨‍👩‍👧 Family Emergency'),
        ('other', '📋 Other'),
    ]
    
    # Basic Info
    name = models.CharField(
        max_length=200, 
        default='Emergency Fund',
        verbose_name="Fund Name"
    )
    fund_type = models.CharField(
        max_length=20,
        choices=FUND_TYPES,
        default='business',
        verbose_name="Fund Type"
    )
    description = models.TextField(
        blank=True, 
        null=True,
        verbose_name="Description"
    )
    
    # Amounts
    target_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        default=0,
        verbose_name="Target Amount",
        help_text="Kitna paisa chahiye (3-6 mahine ka kharcha)"
    )
    current_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        default=0,
        verbose_name="Current Amount",
        help_text="Kitna jama ho gaya"
    )
    monthly_contribution = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Monthly Contribution",
        help_text="Har mahine kitna rakhein"
    )
    
    # Settings
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active"
    )
    auto_deduct = models.BooleanField(
        default=False,
        verbose_name="Auto Deduct",
        help_text="Har mahine automatically katey"
    )
    
    # Dates
    start_date = models.DateField(
        default=now,
        verbose_name="Start Date"
    )
    target_date = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Target Date",
        help_text="Kab tak mukammal karna hai"
    )
    
    # System Fields
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_emergency_funds'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "🛡️ Emergency Funds"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name}: Rs. {self.current_amount:,.2f} / Rs. {self.target_amount:,.2f}"
    
    # ==========================================
    # PROPERTIES
    # ==========================================
    
    @property
    def progress_percent(self):
        """Kitna % mukammal hua"""
        if self.target_amount > 0:
            return float((self.current_amount / self.target_amount) * 100)
        return 0
    
    @property
    def remaining_amount(self):
        """Kitna paisa abhi bhi chahiye"""
        return max(0, self.target_amount - self.current_amount)
    
    @property
    def is_completed(self):
        """Kya fund mukammal hua"""
        return self.current_amount >= self.target_amount
    
    @property
    def months_covered(self):
        """Kitne mahine ka fund hai"""
        from . import Expense
        from datetime import date, timedelta
        
        last_30 = date.today() - timedelta(days=30)
        monthly_expense = Expense.objects.filter(
            expense_date__gte=last_30,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('1000')
        
        if monthly_expense > 0:
            return float(self.current_amount / monthly_expense)
        return 0
    
    @property
    def months_remaining(self):
        """Kitne mahine mein mukammal hoga"""
        if self.monthly_contribution > 0:
            return float(self.remaining_amount / self.monthly_contribution)
        return 0
    
    @property
    def status_badge(self):
        """Status badge"""
        months = self.months_covered
        
        if months >= 6:
            return '<span class="badge bg-success">🟢 Excellent (6+ mahine)</span>'
        elif months >= 3:
            return '<span class="badge bg-info">🔵 Good (3+ mahine)</span>'
        elif months >= 1:
            return '<span class="badge bg-warning text-dark">🟡 Moderate (1+ mahina)</span>'
        else:
            return '<span class="badge bg-danger">🔴 Critical (0 mahine)</span>'
    
    # ==========================================
    # METHODS
    # ==========================================
    
    def add_money(self, amount, user=None, description=""):
        """Fund mein paisa daalo"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount 0 se zyada hona chahiye")
        
        self.current_amount += amount
        self.save(update_fields=['current_amount', 'updated_at'])
        
        # CashTransaction record
        from . import CashTransaction
        CashTransaction.objects.create(
            amount=amount,
            transaction_type='withdraw',
            description=f"Emergency Fund: {self.name} - {description}",
            created_by=user,
        )
        
        return self.current_amount
    
    def withdraw_money(self, amount, user=None, reason=""):
        """Bure waqt mein paisa nikalo"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount 0 se zyada hona chahiye")
        
        if amount > self.current_amount:
            raise ValidationError(f"Sirf Rs. {self.current_amount} available hai")
        
        self.current_amount -= amount
        self.save(update_fields=['current_amount', 'updated_at'])
        
        # CashTransaction record
        from . import CashTransaction
        CashTransaction.objects.create(
            amount=amount,
            transaction_type='deposit',
            description=f"Emergency Withdrawal: {self.name} - {reason}",
            created_by=user,
        )
        
        return self.current_amount
    
    # ==========================================
    # CLASS METHODS
    # ==========================================
    
    @classmethod
    def get_active_fund(cls):
        """Active fund nikalo"""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_or_create_default(cls):
        """Default fund banao"""
        fund = cls.get_active_fund()
        
        if not fund:
            # Calculate target from monthly expense
            from . import Expense
            from datetime import date, timedelta
            
            last_30 = date.today() - timedelta(days=30)
            monthly = Expense.objects.filter(
                expense_date__gte=last_30,
                status__in=['approved', 'paid']
            ).aggregate(total=Sum('amount'))['total'] or Decimal('10000')
            
            fund = cls.objects.create(
                name='Emergency Fund',
                fund_type='business',
                target_amount=monthly * 3,
                monthly_contribution=monthly * Decimal('0.1'),  # 10%
                is_active=True,
            )
        
        return fund


class EmergencyFundTransaction(models.Model):
    """Emergency Fund ki transactions"""
    
    TRANSACTION_TYPES = [
        ('deposit', '💰 Deposit (Add)'),
        ('withdraw', '💸 Withdrawal (Remove)'),
        ('adjustment', '📝 Adjustment'),
    ]
    
    fund = models.ForeignKey(
        EmergencyFund,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )
    balance_after = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "🛡️ Emergency Fund Transactions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.fund.name}: {self.get_transaction_type_display()} - Rs. {self.amount}"
