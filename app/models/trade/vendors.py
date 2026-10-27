"""Models: trade/vendors (split from the former purchasing.py)."""
from django.db import models
from decimal import Decimal
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

class VendorGroup(models.Model):
    name = models.CharField(max_length=20, unique=True)
    description = models.TextField(null=True, blank=True)

    def total_outstanding_balance(self):
        return sum(vendor.outstanding_balance() for vendor in self.vendors.all())
    
    class Meta:
        verbose_name_plural = '3.1 Vendor Groups'

    def __str__(self):
        return self.name


# Vendor model to store vendor details
class Vendor(models.Model):
    vendor_code = models.CharField(
        max_length=50, 
        unique=True, 
        null=True,          # ✅ Temporarily allow null for the migration
        blank=True,         # ✅ Temporarily allow blank in the form
        verbose_name=_("Vendor Code"),
        help_text="Enter unique vendor code manually (e.g., VEN-001, SUP-001)"
    )
    name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    group = models.ForeignKey('VendorGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name='vendors')
    
    # ✅ NEW: Opening balance field (Previous outstanding before system)
    opening_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00'),
        verbose_name="Opening Balance",
        help_text="Previous outstanding balance before using this system"
    )

    class Meta:
        verbose_name_plural = '3. Vendor'
        indexes = [
            models.Index(fields=['vendor_code']),
            models.Index(fields=['name']),
            models.Index(fields=['group']),
        ]

    def __str__(self):
        if self.vendor_code:
            return f"{self.vendor_code} - {self.name}"
        return self.name

    def outstanding_balance(self):
        """Calculate total outstanding including opening balance"""
        totals = self.purchase_set.aggregate(
            total_amount=Sum('purchaseitem__total_amt'),
            total_paid=Sum('paid')
        )
        total_purchases = totals['total_amount'] or Decimal('0.0')
        total_paid = totals['total_paid'] or Decimal('0.0')
        purchase_returns = self.purchaseretrn_set.aggregate(
            total_return=Sum('return_items__total_amt')
        )['total_return'] or Decimal('0.0')
        
        # ✅ Include opening balance
        return self.opening_balance + total_purchases - total_paid - purchase_returns

    def save(self, *args, **kwargs):
        # ✅ If vendor_code is empty, auto-generate it
        if not self.vendor_code:
            last_vendor = Vendor.objects.exclude(
                vendor_code__isnull=True
            ).exclude(
                vendor_code=''
            ).order_by('-id').first()
            
            if last_vendor and last_vendor.vendor_code and last_vendor.vendor_code.startswith('VEN-'):
                try:
                    last_num = int(last_vendor.vendor_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            
            self.vendor_code = f'VEN-{new_num}'
        
        super().save(*args, **kwargs)


class VendorPayment(models.Model):
    """Vendor payment record - Separate from SalePayment"""
    
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='payments')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateTimeField(default=now)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Vendor Payments"
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['vendor', 'payment_date']),
            models.Index(fields=['purchase']),
        ]
    
    def __str__(self):
        return f"{self.vendor.name} - Rs. {self.amount:,.2f} - {self.payment_date.strftime('%d-%m-%Y')}"
