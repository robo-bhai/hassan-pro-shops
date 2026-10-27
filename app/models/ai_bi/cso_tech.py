"""Models: ai_bi/cso_tech (split from the former ai_ops.py)."""
from django.db import models
from datetime import date
from django.utils.timezone import now
from django.contrib.auth.models import User

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
