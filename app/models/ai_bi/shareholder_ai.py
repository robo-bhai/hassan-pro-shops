"""Models: ai_bi/shareholder_ai (split from the former ai_ops.py)."""
from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User

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
