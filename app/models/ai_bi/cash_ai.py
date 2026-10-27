"""Models: ai_bi/cash_ai (split from the former ai_ops.py)."""
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from .board import AIBoardMeeting

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
    Emergency Fund - separate savings for hard times
    
    Features:
    - Target amount set karo
    - Deposit money every month
    - Progress track karo
    - How many months the fund covers
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
        help_text="How much money is needed (3-6 months of expenses)"
    )
    current_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        default=0,
        verbose_name="Current Amount",
        help_text="How much has been saved"
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
        help_text="By when it should be completed"
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
        """How much money is still needed"""
        return max(0, self.target_amount - self.current_amount)
    
    @property
    def is_completed(self):
        """Is the fund complete"""
        return self.current_amount >= self.target_amount
    
    @property
    def months_covered(self):
        """How many months the fund covers"""
        from .. import Expense
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
        """In how many months it will be complete"""
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
        """Add money to the fund"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")
        
        self.current_amount += amount
        self.save(update_fields=['current_amount', 'updated_at'])
        
        # CashTransaction record
        from .. import CashTransaction
        CashTransaction.objects.create(
            amount=amount,
            transaction_type='withdraw',
            description=f"Emergency Fund: {self.name} - {description}",
            created_by=user,
        )
        
        return self.current_amount
    
    def withdraw_money(self, amount, user=None, reason=""):
        """Withdraw money in hard times"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")
        
        if amount > self.current_amount:
            raise ValidationError(f"Only Rs. {self.current_amount} is available")
        
        self.current_amount -= amount
        self.save(update_fields=['current_amount', 'updated_at'])
        
        # CashTransaction record
        from .. import CashTransaction
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
            from .. import Expense
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
