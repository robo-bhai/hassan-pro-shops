"""Models: people/discounts (split from the former shareholders.py)."""
from django.db import models
from datetime import date
from django.contrib.auth.models import User

class ShareholderDiscountProgram(models.Model):
    """Discount program for shareholders"""
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('tiered', 'Tiered Discount'),
    ]
    
    name = models.CharField(max_length=100)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=5, decimal_places=2, help_text="Discount % or fixed amount")
    
    min_shares_required = models.PositiveIntegerField(default=1)
    max_shares_required = models.PositiveIntegerField(null=True, blank=True)
    
    min_holding_period = models.IntegerField(default=0, help_text="Minimum months held")
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Product restrictions
    apply_to_all_products = models.BooleanField(default=True)
    products = models.ManyToManyField('Product', blank=True, related_name='discount_programs')
    categories = models.ManyToManyField('Category', blank=True, related_name='discount_programs')
    
    # Usage limits
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_per_shareholder = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    min_order_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher number = higher priority")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_discounts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Discount Programs"
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.discount_value}% off)"
    
    def get_discount_amount(self, shareholder, product=None, amount=0):
        """Calculate discount for shareholder"""
        if not self.is_active:
            return 0
        
        # Check share requirement
        shares = shareholder.total_shares()
        if shares < self.min_shares_required:
            return 0
        if self.max_shares_required and shares > self.max_shares_required:
            return 0
        
        # Check holding period
        if self.min_holding_period > 0:
            first_share = shareholder.shares.order_by('issue_date').first()
            if not first_share:
                return 0
            from datetime import date
            months_held = (date.today() - first_share.issue_date).days // 30
            if months_held < self.min_holding_period:
                return 0
        
        # Check product eligibility
        if not self.apply_to_all_products and product:
            if not self.products.filter(id=product.id).exists():
                if not self.categories.filter(id=product.category.id).exists():
                    return 0
        
        # Check min order
        if amount < self.min_order_amount:
            return 0
        
        # Check uses
        if self.max_uses > 0:
            uses = ShareholderDiscountUsage.objects.filter(program=self).count()
            if uses >= self.max_uses:
                return 0
        
        # Calculate discount
        if self.discount_type == 'percentage':
            return amount * (self.discount_value / 100)
        elif self.discount_type == 'fixed':
            return self.discount_value
        elif self.discount_type == 'tiered':
            # Tiered logic - can be customized
            if shares >= 1000:
                return amount * 0.15  # 15% for 1000+ shares
            elif shares >= 500:
                return amount * 0.10  # 10% for 500+ shares
            elif shares >= 100:
                return amount * 0.05   # 5% for 100+ shares
            else:
                return 0
        
        return 0


class ShareholderDiscountUsage(models.Model):
    """Track discount usage"""
    
    program = models.ForeignKey(ShareholderDiscountProgram, on_delete=models.CASCADE, related_name='usages')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='discount_usages')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, related_name='discount_usages')
    
    original_amount = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2)
    final_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    used_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Discount Usages"
        ordering = ['-used_at']
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.discount_amount:,.2f} off"
