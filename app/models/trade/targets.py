"""Models: trade/targets (split from the former sales.py)."""
from django.db import models
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User

class SalesTarget(models.Model):
    TARGET_TYPES = [
        ('daily', '📅 Daily Target'),
        ('weekly', '📆 Weekly Target'),
        ('monthly', '📊 Monthly Target'),
        ('salesman', '👤 Salesman-wise'),
        ('product', '📦 Product-wise'),
    ]
    
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_amount = models.DecimalField(max_digits=15, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    salesman = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='targets')
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Bonus settings
    bonus_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    bonus_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_targets')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_target_type_display()}: Rs. {self.target_amount} ({self.start_date} to {self.end_date})"
    
    def current_progress(self):
        """Calculate current progress percentage"""
        from django.db.models import Sum
        from django.utils.timezone import now
        
        if self.target_type == 'daily':
            sales_today = Sale.objects.filter(
                sale_date__date=now().date()
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_today / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        elif self.target_type == 'monthly':
            sales_this_month = Sale.objects.filter(
                sale_date__month=now().month,
                sale_date__year=now().year
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_this_month / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        elif self.target_type == 'salesman' and self.salesman:
            sales_by_salesman = Sale.objects.filter(
                created_by=self.salesman,
                sale_date__date__gte=self.start_date,
                sale_date__date__lte=self.end_date
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_by_salesman / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        return 0
    
    def achieved_amount(self):
        from django.db.models import Sum
        from django.utils.timezone import now
        
        if self.target_type == 'daily':
            return Sale.objects.filter(
                sale_date__date=now().date()
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        elif self.target_type == 'monthly':
            return Sale.objects.filter(
                sale_date__month=now().month,
                sale_date__year=now().year
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        elif self.target_type == 'salesman' and self.salesman:
            return Sale.objects.filter(
                created_by=self.salesman,
                sale_date__date__gte=self.start_date,
                sale_date__date__lte=self.end_date
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        return 0
    
    def remaining_amount(self):
        return max(0, self.target_amount - self.achieved_amount())
    
    def days_remaining(self):
        from django.utils.timezone import now
        remaining = (self.end_date - now().date()).days
        return max(0, remaining)
    
    def daily_needed(self):
        days = self.days_remaining()
        if days > 0:
            return self.remaining_amount() / days
        return 0


class TargetProgress(models.Model):
    target = models.ForeignKey(SalesTarget, on_delete=models.CASCADE, related_name='progress_records')
    date = models.DateField(auto_now_add=True)
    achieved_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.target} - {self.date}: {self.percentage}%"
    
    def save(self, *args, **kwargs):
        if self.target.target_amount > 0:
            self.percentage = (self.achieved_amount / self.target.target_amount) * 100
        super().save(*args, **kwargs)
