"""Audit Qa models."""
from django.db import models
from datetime import datetime
from datetime import date
from django.contrib.auth.models import User
import os

class AuditPlan(models.Model):
    """Audit plan template"""
    
    AUDIT_TYPES = [
        ('internal', '🔍 Internal Audit'),
        ('external', '📋 External Audit'),
        ('financial', '💰 Financial Audit'),
        ('compliance', '⚖️ Compliance Audit'),
        ('operational', '⚙️ Operational Audit'),
        ('it', '💻 IT Audit'),
        ('quality', '✅ Quality Audit'),
    ]
    
    AUDIT_STATUS = [
        ('draft', '📝 Draft'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    plan_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=AUDIT_STATUS, default='draft')
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Scope
    scope = models.TextField(help_text="Audit scope and objectives")
    criteria = models.TextField(help_text="Audit criteria")
    
    # Team
    lead_auditor = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, related_name='lead_audits')
    audit_team = models.ManyToManyField('Employee', blank=True, related_name='audit_team_member')
    
    # Department
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Finding
    findings_count = models.IntegerField(default=0)
    critical_findings = models.IntegerField(default=0)
    high_findings = models.IntegerField(default=0)
    medium_findings = models.IntegerField(default=0)
    low_findings = models.IntegerField(default=0)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_audits')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Audit Plans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.plan_no} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.plan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = AuditPlan.objects.filter(plan_no__startswith=f'AP-{year}').order_by('-plan_no').first()
            if last and last.plan_no:
                try:
                    last_num = int(last.plan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.plan_no = f'AP-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def get_progress(self):
        """Calculate audit progress"""
        if self.status in ['completed', 'cancelled']:
            return 100 if self.status == 'completed' else 0
        checklists = self.checklists.all()
        if checklists:
            completed = checklists.filter(is_completed=True).count()
            return int((completed / checklists.count()) * 100)
        return 0


class AuditChecklist(models.Model):
    """Audit checklist template"""
    
    CHECKLIST_TYPES = [
        ('compliance', '⚖️ Compliance'),
        ('financial', '💰 Financial'),
        ('operational', '⚙️ Operational'),
        ('it', '💻 IT'),
        ('quality', '✅ Quality'),
        ('hse', '🛡️ HSE'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='checklists')
    name = models.CharField(max_length=200)
    checklist_type = models.CharField(max_length=20, choices=CHECKLIST_TYPES)
    description = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.name}"
    
    def get_progress(self):
        items = self.items.all()
        if items:
            checked = items.filter(is_checked=True).count()
            return int((checked / items.count()) * 100)
        return 0


class AuditChecklistItem(models.Model):
    """Individual checklist items"""
    
    PRIORITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    checklist = models.ForeignKey(AuditChecklist, on_delete=models.CASCADE, related_name='items')
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['priority', 'id']
    
    def __str__(self):
        return f"{self.checklist.name} - {self.description[:50]}"


class AuditFinding(models.Model):
    """Audit findings"""
    
    SEVERITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    STATUS_CHOICES = [
        ('open', '📂 Open'),
        ('in_progress', '⚙️ In Progress'),
        ('resolved', '✅ Resolved'),
        ('accepted', '📋 Accepted'),
        ('rejected', '❌ Rejected'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='findings')
    checklist_item = models.ForeignKey(AuditChecklistItem, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Evidence
    evidence = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='audit_findings/', null=True, blank=True)
    
    # Recommendation
    recommendation = models.TextField()
    management_response = models.TextField(blank=True, null=True)
    
    # Dates
    found_date = models.DateField(auto_now_add=True)
    target_completion_date = models.DateField(null=True, blank=True)
    resolved_date = models.DateField(null=True, blank=True)
    
    # Assigned to
    assigned_to = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_findings')
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_findings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Audit Findings"
        ordering = ['-severity', '-created_at']
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.title} ({self.get_severity_display()})"
    
    def mark_resolved(self, user):
        self.status = 'resolved'
        self.resolved_date = date.today()
        self.save()


class AuditSchedule(models.Model):
    """Audit schedule"""
    
    SCHEDULE_STATUS = [
        ('scheduled', '📅 Scheduled'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
        ('postponed', '⏰ Postponed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='schedules')
    scheduled_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=SCHEDULE_STATUS, default='scheduled')
    attendees = models.ManyToManyField('Employee', blank=True, related_name='audit_attendees')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.scheduled_date}"


class AuditReport(models.Model):
    """Audit report"""
    
    audit_plan = models.OneToOneField(AuditPlan, on_delete=models.CASCADE, related_name='report')
    report_no = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    executive_summary = models.TextField()
    findings_summary = models.TextField()
    recommendations = models.TextField()
    conclusion = models.TextField()
    
    # Files
    pdf_file = models.FileField(upload_to='audit_reports/', null=True, blank=True)
    word_file = models.FileField(upload_to='audit_reports/', null=True, blank=True)
    
    # Approval
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_audit_reports')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_audit_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Audit Reports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.report_no} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.report_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = AuditReport.objects.filter(report_no__startswith=f'AR-{year}').order_by('-report_no').first()
            if last and last.report_no:
                try:
                    last_num = int(last.report_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.report_no = f'AR-{year}-{new_num}'
        super().save(*args, **kwargs)


class AuditTrail(models.Model):
    """Track all changes in the system"""
    
    ACTION_TYPES = [
        ('created', '📝 Created'),
        ('updated', '✏️ Updated'),
        ('deleted', '🗑️ Deleted'),
        ('viewed', '👁️ Viewed'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('submitted', '📤 Submitted'),
        ('completed', '🎯 Completed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    model_name = models.CharField(max_length=100)
    record_id = models.IntegerField()
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Audit Trails"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.action} - {self.model_name}"


class InternalControl(models.Model):
    """Internal controls register"""
    
    CONTROL_TYPES = [
        ('preventive', '🛡️ Preventive'),
        ('detective', '🔍 Detective'),
        ('corrective', '🔧 Corrective'),
    ]
    
    CONTROL_CATEGORIES = [
        ('financial', '💰 Financial'),
        ('operational', '⚙️ Operational'),
        ('compliance', '⚖️ Compliance'),
        ('it', '💻 IT'),
        ('fraud', '🚨 Fraud Prevention'),
    ]
    
    CONTROL_STATUS = [
        ('active', '✅ Active'),
        ('inactive', '❌ Inactive'),
        ('review', '📋 Under Review'),
        ('improved', '📈 Improved'),
    ]
    
    control_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField()
    control_type = models.CharField(max_length=20, choices=CONTROL_TYPES)
    category = models.CharField(max_length=20, choices=CONTROL_CATEGORIES)
    status = models.CharField(max_length=20, choices=CONTROL_STATUS, default='active')
    
    # Risk assessment
    risk_level = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    likelihood = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    impact = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    
    # Implementation
    implementation_date = models.DateField()
    review_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    
    # Responsible
    responsible_person = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, related_name='controls')
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Documents
    document = models.FileField(upload_to='internal_controls/', null=True, blank=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_controls')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Internal Controls"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.control_no} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.control_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = InternalControl.objects.filter(control_no__startswith=f'IC-{year}').order_by('-control_no').first()
            if last and last.control_no:
                try:
                    last_num = int(last.control_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.control_no = f'IC-{year}-{new_num}'
        super().save(*args, **kwargs)


class TestProject(models.Model):
    """Testing projects"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='test_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    class Meta:
        verbose_name_plural = "Test Projects"


class TestSuite(models.Model):
    """Test suites - group of test cases"""
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='suites')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"
    
    class Meta:
        verbose_name_plural = "Test Suites"


class TestCase(models.Model):
    """Individual test cases"""
    
    PRIORITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    TYPE_CHOICES = [
        ('functional', '✅ Functional'),
        ('integration', '🔗 Integration'),
        ('unit', '📦 Unit'),
        ('performance', '⚡ Performance'),
        ('security', '🔒 Security'),
        ('ui', '🎨 UI/UX'),
        ('api', '🔌 API'),
    ]
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('ready', '✅ Ready'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('failed', '❌ Failed'),
        ('passed', '✅ Passed'),
        ('blocked', '🚫 Blocked'),
    ]
    
    suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, related_name='cases')
    title = models.CharField(max_length=200)
    description = models.TextField()
    test_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='functional')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Test steps
    pre_conditions = models.TextField(blank=True, null=True)
    test_steps = models.JSONField(default=list, help_text="Steps to execute")
    expected_result = models.TextField()
    actual_result = models.TextField(blank=True, null=True)
    
    # Execution
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='executed_tests')
    executed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.DurationField(null=True, blank=True)
    
    # Automation
    is_automated = models.BooleanField(default=False)
    automation_script = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Test Cases"


class TestExecution(models.Model):
    """Test execution records"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('running', '⚙️ Running'),
        ('passed', '✅ Passed'),
        ('failed', '❌ Failed'),
        ('blocked', '🚫 Blocked'),
        ('skipped', '⏭️ Skipped'),
    ]
    
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='executions')
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    results = models.JSONField(default=dict)
    notes = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.test_case.title} - {self.get_status_display()}"
    
    class Meta:
        verbose_name_plural = "Test Executions"
        ordering = ['-started_at']


class Bug(models.Model):
    """Bug tracking"""
    
    SEVERITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('major', '🟠 Major'),
        ('minor', '🟡 Minor'),
        ('trivial', '🟢 Trivial'),
    ]
    
    STATUS_CHOICES = [
        ('new', '🆕 New'),
        ('assigned', '📋 Assigned'),
        ('in_progress', '⚙️ In Progress'),
        ('fixed', '🔧 Fixed'),
        ('verified', '✅ Verified'),
        ('closed', '✅ Closed'),
        ('reopened', '🔄 Reopened'),
        ('duplicate', '📋 Duplicate'),
        ('won_fix', '❌ Won\'t Fix'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='major')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    
    # Related
    test_case = models.ForeignKey(TestCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='bugs')
    module = models.CharField(max_length=100, blank=True, null=True)
    
    # Environment
    browser = models.CharField(max_length=50, blank=True, null=True)
    os = models.CharField(max_length=50, blank=True, null=True)
    device = models.CharField(max_length=50, blank=True, null=True)
    
    # Steps to reproduce
    steps_to_reproduce = models.TextField()
    actual_result = models.TextField()
    expected_result = models.TextField()
    
    # Attachments
    screenshot = models.ImageField(upload_to='bug_screenshots/', null=True, blank=True)
    attachment = models.FileField(upload_to='bug_attachments/', null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_bugs')
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_bugs')
    
    # Dates
    reported_at = models.DateTimeField(auto_now_add=True)
    fixed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"BUG-{self.id}: {self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Bugs"
        ordering = ['-reported_at']


class TestPlan(models.Model):
    """Test plans"""
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('review', '📋 Review'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
    ]
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=200)
    description = models.TextField()
    test_scope = models.TextField()
    test_strategy = models.TextField()
    resources = models.TextField(blank=True, null=True)
    schedule = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Test Plans"


class TestReport(models.Model):
    """Test reports"""
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='reports')
    name = models.CharField(max_length=200)
    description = models.TextField()
    
    # Metrics
    total_tests = models.IntegerField(default=0)
    passed_tests = models.IntegerField(default=0)
    failed_tests = models.IntegerField(default=0)
    blocked_tests = models.IntegerField(default=0)
    skipped_tests = models.IntegerField(default=0)
    
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Bugs
    total_bugs = models.IntegerField(default=0)
    critical_bugs = models.IntegerField(default=0)
    major_bugs = models.IntegerField(default=0)
    minor_bugs = models.IntegerField(default=0)
    
    # Files
    pdf_file = models.FileField(upload_to='test_reports/', null=True, blank=True)
    
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.generated_at.strftime('%d-%m-%Y')}"
    
    def calculate_metrics(self):
        total = self.total_tests
        if total > 0:
            self.pass_rate = (self.passed_tests / total) * 100
        return self.pass_rate
    
    class Meta:
        verbose_name_plural = "Test Reports"
        ordering = ['-generated_at']
