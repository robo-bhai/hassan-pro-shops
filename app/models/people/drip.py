"""Models: people/drip (split from the former shareholders.py)."""
from django.db import models
from django.db import transaction
from datetime import datetime
from django.utils.timezone import now
from django.contrib.auth.models import User

class DividendReinvestmentPlan(models.Model):
    """DRIP settings per dividend"""
    
    DRIP_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('market', 'Market Price'),
    ]
    
    dividend = models.OneToOneField(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='drip',
        help_text="Dividend for which DRIP is available"
    )
    plan_name = models.CharField(
        max_length=200,
        default='Dividend Reinvestment Plan',
        help_text="Name of the DRIP plan"
    )
    
    discount_type = models.CharField(
        max_length=20, 
        choices=DISCOUNT_TYPES, 
        default='percentage'
    )
    discount_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Discount on share price (e.g., 5 for 5%)"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee per reinvestment"
    )
    
    min_shares = models.PositiveIntegerField(
        default=1,
        help_text="Minimum shares to reinvest"
    )
    max_shares = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maximum shares to reinvest (optional)"
    )
    
    start_date = models.DateField(
        help_text="Date when DRIP becomes available"
    )
    end_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when DRIP expires (optional)"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=DRIP_STATUS, 
        default='active'
    )
    is_auto_enroll = models.BooleanField(
        default=False,
        help_text="Auto-enroll all eligible shareholders"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Default DRIP for all dividends"
    )
    
    round_down_to_nearest = models.PositiveIntegerField(
        default=1,
        help_text="Round down shares to nearest integer"
    )
    fractional_shares_allowed = models.BooleanField(
        default=False,
        help_text="Allow fractional shares"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_drips'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Dividend Reinvestment Plans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP - {self.dividend.dividend_no} ({self.get_discount_type_display()})"
    
    def calculate_shares(self, dividend_amount, share_price):
        """Calculate number of shares to reinvest"""
        if self.discount_type == 'percentage':
            effective_price = share_price * (1 - self.discount_value / 100)
        elif self.discount_type == 'fixed':
            effective_price = share_price - self.discount_value
        else:
            effective_price = share_price
        
        amount_after_fee = dividend_amount - self.admin_fee
        
        if amount_after_fee <= 0:
            return 0
        
        shares = amount_after_fee / effective_price
        
        if not self.fractional_shares_allowed:
            shares = int(shares // self.round_down_to_nearest) * self.round_down_to_nearest
        
        if self.max_shares:
            shares = min(shares, self.max_shares)
        if self.min_shares and shares < self.min_shares:
            shares = 0
        
        return shares


class ShareholderDRIPEnrollment(models.Model):
    """Shareholder enrollment in DRIP"""
    
    ENROLLMENT_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='drip_enrollments'
    )
    drip = models.ForeignKey(
        DividendReinvestmentPlan, 
        on_delete=models.CASCADE, 
        related_name='enrollments'
    )
    
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=ENROLLMENT_STATUS, 
        default='active'
    )
    auto_reinvest = models.BooleanField(
        default=True,
        help_text="Auto-reinvest future dividends"
    )
    min_dividend_to_reinvest = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=500,
        help_text="Minimum dividend amount to trigger reinvestment"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_enrollments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Shareholder Enrollments"
        unique_together = ['shareholder', 'drip']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.drip.plan_name}"
    
    def is_eligible(self, dividend_amount):
        """Check if shareholder is eligible for reinvestment"""
        if self.status != 'active':
            return False
        if not self.auto_reinvest:
            return False
        if dividend_amount < self.min_dividend_to_reinvest:
            return False
        return True


class DRIPTransaction(models.Model):
    """DRIP transaction record"""
    
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    dividend_payment = models.ForeignKey(
        'DividendPayment', 
        on_delete=models.CASCADE, 
        related_name='drip_transactions'
    )
    enrollment = models.ForeignKey(
        ShareholderDRIPEnrollment, 
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    new_shares = models.ManyToManyField(
        'Share', 
        blank=True, 
        related_name='drip_transactions'
    )
    
    dividend_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Original dividend amount"
    )
    shares_purchased = models.PositiveIntegerField(
        default=0,
        help_text="Number of shares purchased"
    )
    purchase_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Price per share"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee deducted"
    )
    total_cost = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Total cost of reinvestment"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=TRANSACTION_STATUS, 
        default='pending'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    reference_no = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Transactions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP {self.reference_no} - {self.dividend_payment.shareholder.name}"
    
    def save(self, *args, **kwargs):
        if not self.reference_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.reference_no = f'DRIP-{timestamp}-{self.dividend_payment.id}'
        super().save(*args, **kwargs)
    
    def process(self):
        """Process the DRIP transaction"""
        from decimal import Decimal
        from django.db import transaction
        
        try:
            with transaction.atomic():
                drip = self.enrollment.drip
                share_price = SharePrice.objects.filter(is_active=True).first()
                
                if not share_price:
                    self.status = 'failed'
                    self.notes = "No active share price found"
                    self.save()
                    return False
                
                shares = drip.calculate_shares(
                    self.dividend_amount,
                    share_price.price
                )
                
                if shares <= 0:
                    self.status = 'failed'
                    self.notes = "Insufficient amount to purchase shares"
                    self.save()
                    return False
                
                shareholder = self.dividend_payment.shareholder
                
                new_share = Share.objects.create(
                    shareholder=shareholder,
                    quantity=shares,
                    purchase_price=share_price.price,
                    share_type='ordinary',
                    issue_date=now().date(),
                    created_by=self.created_by,
                    paid_from_shareholder_balance=False,
                    notes=f"DRIP purchase from dividend #{self.dividend_payment.dividend.dividend_no}"
                )
                
                new_share.certificate_number = f"DRIP-{new_share.id:06d}"
                new_share.certificate_issue_date = now().date()
                new_share.save()
                
                self.new_shares.add(new_share)
                self.shares_purchased = shares
                self.purchase_price = share_price.price
                self.total_cost = shares * share_price.price
                self.status = 'completed'
                self.completed_at = now()
                
                self.dividend_payment.status = 'paid'
                self.dividend_payment.payment_date = now()
                self.dividend_payment.payment_method = 'DRIP (Dividend Reinvestment)'
                self.dividend_payment.notes = f"Reinvested as {shares} shares via DRIP"
                self.dividend_payment.save()
                
                self.save()
                return True
                
        except Exception as e:
            self.status = 'failed'
            self.notes = str(e)
            self.save()
            return False
