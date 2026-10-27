"""Models: ai_bi/insights (split from the former ai_ops.py)."""
from django.db import models
from datetime import date
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
