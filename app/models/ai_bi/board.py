"""Models: ai_bi/board (split from the former ai_ops.py)."""
from django.db import models
from datetime import date
from django.utils.timezone import now
from django.contrib.auth.models import User

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
