"""Models: ai_bi/purchase_ai (split from the former ai_ops.py)."""
from django.db import models

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
