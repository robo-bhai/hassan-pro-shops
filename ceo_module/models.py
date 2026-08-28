from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import JSONField
import uuid
from datetime import timedelta, date


class ExecutiveProfile(models.Model):
    """CEO/Executive Profile with enterprise features"""
    
    EXECUTIVE_TYPES = [
        ('ceo', 'Chief Executive Officer'),
        ('cfo', 'Chief Financial Officer'),
        ('coo', 'Chief Operating Officer'),
        ('cto', 'Chief Technology Officer'),
        ('cmo', 'Chief Marketing Officer'),
        ('chairman', 'Chairman'),
        ('board_member', 'Board Member'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='executive_profile')
    executive_type = models.CharField(max_length=20, choices=EXECUTIVE_TYPES, default='ceo')
    
    # Professional Info
    executive_id = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=100, default='Chief Executive Officer')
    department = models.CharField(max_length=100, default='Executive Office')
    join_date = models.DateField(auto_now_add=True)
    
    # Contact
    office_phone = models.CharField(max_length=20, blank=True)
    mobile_phone = models.CharField(max_length=20, blank=True)
    personal_email = models.EmailField()
    assistant_email = models.EmailField(blank=True, null=True)
    assistant_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Security & Permissions
    security_clearance_level = models.IntegerField(default=5, choices=[(i, f'Level {i}') for i in range(1, 11)])
    mfa_enabled = models.BooleanField(default=False)
    session_timeout_minutes = models.IntegerField(default=30)
    
    # Notification Channels
    email_alerts = models.BooleanField(default=True)
    whatsapp_alerts = models.BooleanField(default=False)
    slack_webhook = models.URLField(blank=True, null=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Executive Profiles"
    
    def __str__(self):
        return f"{self.get_executive_type_display()}: {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.executive_id:
            prefix = self.executive_type.upper()
            last = ExecutiveProfile.objects.filter(executive_id__startswith=prefix).order_by('-id').first()
            if last:
                try:
                    num = int(last.executive_id.split('-')[1]) + 1
                except:
                    num = 1
            else:
                num = 1
            self.executive_id = f"{prefix}-{num:04d}"
        super().save(*args, **kwargs)


class ExecutiveAuditLog(models.Model):
    """Complete audit trail for executive actions"""
    
    ACTION_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('view', 'View Data'),
        ('export', 'Export Report'),
        ('approve', 'Approval'),
        ('reject', 'Rejection'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('settings', 'Settings Change'),
    ]
    
    executive = models.ForeignKey(ExecutiveProfile, on_delete=models.CASCADE, related_name='audit_logs')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    affected_model = models.CharField(max_length=100, blank=True, null=True)
    affected_id = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Executive Audit Logs"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.executive.executive_id} - {self.action_type} - {self.timestamp}"


class RealTimeMetric(models.Model):
    """Real-time business metrics"""
    
    METRIC_TYPES = [
        ('revenue_today', 'Today\'s Revenue'),
        ('revenue_this_month', 'Month-to-Date Revenue'),
        ('profit_today', 'Today\'s Profit'),
        ('profit_margin', 'Profit Margin %'),
        ('avg_order_value', 'Average Order Value'),
        ('cash_flow', 'Cash Flow'),
        ('inventory_turnover', 'Inventory Turnover'),
        ('outstanding_receivables', 'Outstanding Receivables'),
    ]
    
    metric_type = models.CharField(max_length=30, choices=METRIC_TYPES, unique=True)
    current_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    previous_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    percentage_change = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    trend = models.CharField(max_length=10, choices=[('up', '↑ Up'), ('down', '↓ Down'), ('stable', '→ Stable')], default='stable')
    last_updated = models.DateTimeField(auto_now=True)
    historical_data = JSONField(default=list)
    
    class Meta:
        verbose_name_plural = "Real-time Metrics"
    
    def __str__(self):
        return f"{self.get_metric_type_display()}: {self.current_value}"


class StrategicObjective(models.Model):
    """OKR (Objectives and Key Results)"""
    
    QUARTER_CHOICES = [
        ('Q1', 'Q1 (Jan-Mar)'),
        ('Q2', 'Q2 (Apr-Jun)'),
        ('Q3', 'Q3 (Jul-Sep)'),
        ('Q4', 'Q4 (Oct-Dec)'),
    ]
    
    PRIORITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('at_risk', 'At Risk'),
        ('on_track', 'On Track'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    objective = models.TextField()
    description = models.TextField(blank=True, null=True)
    quarter = models.CharField(max_length=2, choices=QUARTER_CHOICES)
    year = models.IntegerField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    owner = models.ForeignKey(ExecutiveProfile, on_delete=models.SET_NULL, null=True, related_name='owned_objectives')
    
    start_date = models.DateField()
    target_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    estimated_revenue_impact = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    estimated_cost_saving = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Strategic Objectives"
        ordering = ['-year', 'quarter', '-priority']
    
    def __str__(self):
        return f"{self.quarter} {self.year}: {self.objective[:50]}"
    
    def days_remaining(self):
        if self.target_date and self.status != 'completed':
            return (self.target_date - date.today()).days
        return 0


class KeyResult(models.Model):
    """Key Results for OKRs"""
    
    objective = models.ForeignKey(StrategicObjective, on_delete=models.CASCADE, related_name='key_results')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    target_value = models.DecimalField(max_digits=20, decimal_places=2)
    current_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    unit = models.CharField(max_length=50, default='%')
    
    start_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    
    status = models.CharField(max_length=20, choices=StrategicObjective.STATUS_CHOICES, default='in_progress')
    last_update = models.DateTimeField(auto_now=True)
    update_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Key Results"
    
    def __str__(self):
        return f"{self.title} - {self.progress_percentage()}%"
    
    def progress_percentage(self):
        target_diff = self.target_value - self.start_value
        current_diff = self.current_value - self.start_value
        if target_diff > 0:
            return (current_diff / target_diff) * 100
        return 0 if self.current_value >= self.target_value else 0


class RiskAssessment(models.Model):
    """Enterprise risk management"""
    
    RISK_CATEGORIES = [
        ('financial', 'Financial Risk'),
        ('operational', 'Operational Risk'),
        ('strategic', 'Strategic Risk'),
        ('compliance', 'Compliance Risk'),
        ('reputational', 'Reputational Risk'),
        ('cybersecurity', 'Cybersecurity Risk'),
        ('market', 'Market Risk'),
    ]
    
    RISK_LEVELS = [
        ('critical', 'Critical (Immediate Action)'),
        ('high', 'High (Urgent)'),
        ('medium', 'Medium (Monitor)'),
        ('low', 'Low (Acceptable)'),
    ]
    
    RISK_STATUS = [
        ('identified', 'Identified'),
        ('analyzing', 'Under Analysis'),
        ('mitigating', 'Mitigation in Progress'),
        ('monitoring', 'Monitoring'),
        ('resolved', 'Resolved'),
        ('accepted', 'Accepted'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=RISK_CATEGORIES)
    
    likelihood = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    impact = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    risk_score = models.IntegerField(editable=False, default=0)
    
    mitigation_strategy = models.TextField()
    mitigation_owner = models.ForeignKey(ExecutiveProfile, on_delete=models.SET_NULL, null=True, related_name='owned_risks')
    mitigation_deadline = models.DateField()
    
    potential_financial_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    mitigation_cost = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=RISK_STATUS, default='identified')
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS, editable=False, default='low')
    
    identified_by = models.ForeignKey(ExecutiveProfile, on_delete=models.SET_NULL, null=True, related_name='identified_risks')
    identified_date = models.DateTimeField(auto_now_add=True)
    last_review = models.DateTimeField(auto_now=True)
    next_review = models.DateField()
    
    class Meta:
        verbose_name_plural = "Risk Assessments"
    
    def __str__(self):
        return f"{self.get_risk_level_display()}: {self.title}"
    
    def save(self, *args, **kwargs):
        self.risk_score = self.likelihood * self.impact
        if self.risk_score >= 20:
            self.risk_level = 'critical'
        elif self.risk_score >= 15:
            self.risk_level = 'high'
        elif self.risk_score >= 8:
            self.risk_level = 'medium'
        else:
            self.risk_level = 'low'
        super().save(*args, **kwargs)


class ExecutiveMeeting(models.Model):
    """Board and executive meeting management"""
    
    MEETING_TYPES = [
        ('board', 'Board Meeting'),
        ('executive', 'Executive Committee'),
        ('strategy', 'Strategy Session'),
        ('review', 'Quarterly Review'),
        ('emergency', 'Emergency Meeting'),
    ]
    
    title = models.CharField(max_length=200)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES)
    meeting_date = models.DateTimeField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    location = models.CharField(max_length=200, blank=True)
    virtual_link = models.URLField(blank=True, null=True)
    
    agenda = models.TextField()
    minutes = models.TextField(blank=True, null=True)
    decisions = models.TextField(blank=True, null=True)
    action_items = models.TextField(blank=True, null=True)
    
    chairperson = models.ForeignKey(ExecutiveProfile, on_delete=models.SET_NULL, null=True, related_name='chaired_meetings')
    attendees = models.ManyToManyField(ExecutiveProfile, blank=True, related_name='meetings')
    
    status = models.CharField(max_length=20, default='scheduled',
                             choices=[('scheduled', 'Scheduled'), ('in_progress', 'In Progress'), 
                                     ('completed', 'Completed'), ('cancelled', 'Cancelled')])
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Executive Meetings"
        ordering = ['-meeting_date']
    
    def __str__(self):
        return f"{self.get_meeting_type_display()}: {self.title}"


class ExecutiveBriefing(models.Model):
    """Daily/Weekly executive briefing reports"""
    
    BRIEFING_TYPES = [
        ('daily', 'Daily Briefing'),
        ('weekly', 'Weekly Briefing'),
        ('monthly', 'Monthly Briefing'),
    ]
    
    executive = models.ForeignKey(ExecutiveProfile, on_delete=models.CASCADE, related_name='briefings')
    briefing_type = models.CharField(max_length=10, choices=BRIEFING_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    
    executive_summary = models.TextField()
    key_metrics = JSONField(default=dict)
    achievements = models.TextField()
    challenges = models.TextField()
    upcoming_priorities = models.TextField()
    
    pdf_report = models.FileField(upload_to='briefings/', blank=True, null=True)
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(ExecutiveProfile, on_delete=models.SET_NULL, null=True, related_name='created_briefings')
    
    class Meta:
        verbose_name_plural = "Executive Briefings"
        ordering = ['-period_start']
    
    def __str__(self):
        return f"{self.get_briefing_type_display()} - {self.period_start}"