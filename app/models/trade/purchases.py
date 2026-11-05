"""Models: trade/purchases (split from the former purchasing.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from django.utils.timezone import now
from django.utils.timezone import localdate
from django.db.models import Sum
from django.contrib.auth.models import User
import logging
from ..inventory.catalog import Product, Warehouse
from .vendors import Vendor
logger = logging.getLogger(__name__)

class Purchase(models.Model):
    """
    Purchase Model - Complete with Shareholder Proportional Deduction
    """
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='purchases'
    )
    bill_no = models.CharField(max_length=10, null=True, blank=True)
    waiting_for_bill = models.BooleanField(default=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    pur_date = models.DateTimeField(default=now)
    previous_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.0'), 
        editable=False
    )
    paid = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        editable=False
    )
    monthly_purchase = models.ForeignKey(
        'MonthlyClosing', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='purchases', 
        editable=False
    )
    
    # ========================================== #
    # PAYMENT FIELDS                            #
    # ========================================== #
    PAYMENT_TYPES = [
        ('credit', '📋 Credit'),
        ('cash', '💵 Cash'),
        ('mixed', '🔄 Mixed (Cash + Credit)'),
    ]
    payment_type = models.CharField(
        max_length=10, 
        choices=PAYMENT_TYPES, 
        default='credit'
    )
    
    cash_used = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Kitni cash use ki?"
    )
    
    # ========================================== #
    # SHAREHOLDER DEDUCTION FIELDS              #
    # ========================================== #
    shareholder_deduction_done = models.BooleanField(
        default=False,
        verbose_name="Shareholder Deduction Done",
        help_text="Has this purchase been deducted from shareholders?"
    )
    shareholder_deduction_data = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name="Deduction Data",
        help_text="Store deduction details for each shareholder"
    )
    shareholder_deduction_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Deduction Date",
        help_text="When was the deduction processed?"
    )
    shareholder_deduction_type = models.CharField(
        max_length=20,
        choices=[
            ('equal', 'Equal Division'),
            ('proportional', 'Proportional by Balance'),
            ('skip', 'Skip Deduction'),
        ],
        default='proportional',
        verbose_name="Deduction Type",
        help_text="How to distribute the purchase amount among shareholders"
    )

    class Meta:
        verbose_name_plural = '4. Purchase'
        indexes = [
            models.Index(fields=['vendor', 'pur_date']),
            models.Index(fields=['bill_no']),
            models.Index(fields=['warehouse']),
            models.Index(fields=['shareholder_deduction_done']),
        ]

    def __str__(self):
        return f"Purchase Bill No. {self.bill_no} - {self.vendor.name} on {self.pur_date}"

    # ========================================== #
    # AMOUNT CALCULATIONS                       #
    # ========================================== #
    
    def total_amount(self):
        """Calculates the total amount for all items in this purchase."""
        return sum(Decimal(item.qty) * item.price for item in self.purchaseitem_set.all())

    def outstanding_balance(self):
        """Outstanding balance for this purchase."""
        return self.total_amount() - self.paid

    def outstanding_with_previous(self):
        """Outstanding balance including previous balance."""
        return self.outstanding_balance() + self.previous_balance

    def bill_status(self):
        """Display status for admin."""
        return "Bill Pending" if self.waiting_for_bill else f"Bill No. {self.bill_no}"
    bill_status.short_description = 'Bill No'

    # ========================================== #
    # SHAREHOLDER DEDUCTION METHODS             #
    # ========================================== #
    
    def process_shareholder_deduction(self, user=None):
        """
        ✅ Process shareholder deduction based on configured type
        Returns: (success, result_data)
        """
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.shareholder_deduction_done:
            return False, "Deduction already processed for this purchase"
        
        # Get deduction type from setting or purchase
        deduction_type = self.shareholder_deduction_type
        if deduction_type == 'skip':
            return False, "Deduction skipped for this purchase"
        
        # Get system setting override
        system_type = SystemSetting.get_value('shareholder_deduction_type', 'proportional')
        if system_type in ['equal', 'proportional']:
            deduction_type = system_type
        
        try:
            with transaction.atomic():
                if deduction_type == 'equal':
                    success, result = Shareholder.deduct_purchase_equally(
                        purchase_amount=self.total_amount(),
                        purchase_obj=self,
                        user=user or self.created_by
                    )
                else:  # proportional (default)
                    success, result = Shareholder.deduct_purchase_proportionally_by_balance(
                        purchase_amount=self.total_amount(),
                        purchase_obj=self,
                        user=user or self.created_by
                    )
                
                if success:
                    self.shareholder_deduction_done = True
                    self.shareholder_deduction_data = result
                    self.shareholder_deduction_date = now()
                    self.shareholder_deduction_type = deduction_type
                    
                    # Save without triggering recursion
                    Purchase.objects.filter(pk=self.pk).update(
                        shareholder_deduction_done=True,
                        shareholder_deduction_data=result,
                        shareholder_deduction_date=now(),
                        shareholder_deduction_type=deduction_type
                    )
                    
                    return True, result
                else:
                    return False, result
                    
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Shareholder deduction failed for purchase {self.pk}: {e}")
            return False, str(e)
    
    def get_deduction_summary(self):
        """Get formatted deduction summary for display"""
        if not self.shareholder_deduction_done:
            return None
        
        data = self.shareholder_deduction_data
        if not data:
            return None
        
        return {
            'total_shareholders': data.get('total_shareholders', 0),
            'total_balance': data.get('total_balance', 0),
            'total_amount': data.get('total_amount', 0),
            'deducted_from': data.get('deducted_from', []),
            'failed': data.get('failed', []),
            'skipped': data.get('skipped', []),
            'deduction_type': self.shareholder_deduction_type,
            'date': self.shareholder_deduction_date,
        }

    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def clean(self):
        """Custom validation for conditional bill_no requirement."""
        if not self.waiting_for_bill and not self.bill_no:
            raise ValidationError({'bill_no': 'Bill number is required when the purchase is not waiting for a bill.'})
        if self.waiting_for_bill and self.bill_no:
            raise ValidationError({'bill_no': 'Bill number should not be provided if waiting for a bill.'})

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Override save to handle shareholder deduction"""
        
        # Set created_by
        if not self.pk and not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        # Set default warehouse
        if not self.warehouse:
            from django.conf import settings as _settings
            if getattr(_settings, 'PURCHASE_REQUIRE_WAREHOUSE', False):
                raise ValidationError("Selecting a Store (warehouse) is required, so the stock goes into the right store.")
            self.warehouse = Warehouse.objects.first()
        
        # Set monthly closing
        purchase_month = self.pur_date.replace(day=1)
        monthly_closing, created = MonthlyClosing.objects.get_or_create(month=purchase_month)
        
        if monthly_closing and monthly_closing.locked:
            raise ValidationError(
                f"Cannot add or modify purchases for {purchase_month.strftime('%B %Y')} "
                f"as the month is locked."
            )
        
        self.monthly_purchase = monthly_closing
        
        # Handle bill_no
        if self.bill_no:
            self.waiting_for_bill = False
        
        # Set previous balance for new purchases
        if not self.pk:
            previous_balance = self.vendor.purchase_set.aggregate(
                outstanding=Sum('purchaseitem__total_amt') - Sum('paid')
            )['outstanding'] or Decimal('0.0')
            self.previous_balance = previous_balance
            
            if not self.created_by:
                self.created_by = User.objects.first()
        
        # ✅ Save the purchase first
        super().save(*args, **kwargs)
        
        # ✅ Process shareholder deduction for new purchases
        if not self.pk and SystemSetting.get_bool('enable_shareholder_purchase_deduction', True):
            # Use celery or background task if available, else process directly
            try:
                success, result = self.process_shareholder_deduction()
                if not success:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Shareholder deduction failed for purchase {self.pk}: {result}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Shareholder deduction error for purchase {self.pk}: {e}")


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))

    # [agri-edition:pi-fields]
    batch_no = models.CharField(max_length=50, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = '4.1. Purchase Items'

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.price <= 0:
            raise ValidationError("Purchase price must be greater than zero.")
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if PurchaseItem.objects.filter(purchase=self.purchase, product=self.product).exclude(pk=self.pk).exists():
            raise ValidationError(f"The product {self.product.name} is already added to this Purchase.")

        self.total_amt = Decimal(self.qty) * self.price

        warehouse = self.purchase.warehouse
        
        is_new = self.pk is None
        
        if not is_new:
            # Update existing item
            existing_item = PurchaseItem.objects.get(pk=self.pk)
            qty_diff = self.qty - existing_item.qty
            batch = StockBatch.objects.filter(purchase_item=self).first()
            if batch:
                batch.remaining_qty += qty_diff
                batch.qty += qty_diff
                batch.price = self.price
                batch.batch_no = self.batch_no  # [agri-edition:pi-sync]
                batch.expiry_date = self.expiry_date
                batch.save()
            Inventory.update_stock(self.product, qty_diff, warehouse)
            super().save(*args, **kwargs)
        else:
            # New item - ONLY ONE SAVE
            super().save(*args, **kwargs)
            StockBatch.add_batch(self.product, self.qty, self.price, purchase_item=self, warehouse=warehouse,
                                 batch_no=self.batch_no, expiry_date=self.expiry_date)  # [agri-edition:pi-add]
            Inventory.update_stock(self.product, self.qty, warehouse)

    def __str__(self):
        return f"{self.qty} x {self.product.name}"


# ============================================
# PURCHASE QUOTATION MODEL
# ============================================
class PurchaseQuotation(models.Model):
    QUOTATION_STATUS = [
        ('draft', 'Draft'),
        ('requested', 'Requested from Vendor'),
        ('received', 'Received'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('converted', 'Converted to PO'),
    ]
    
    quotation_no = models.CharField(max_length=20, unique=True, verbose_name="Quotation Number")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='purchase_quotations')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='purchase_quotations')
    quotation_date = models.DateTimeField(default=now, verbose_name="Quotation Date")
    valid_until = models.DateField(verbose_name="Valid Until")
    status = models.CharField(max_length=20, choices=QUOTATION_STATUS, default='draft')
    vendor_reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="Vendor's Reference No")
    notes = models.TextField(blank=True, null=True, verbose_name="Quotation Notes")
    terms_conditions = models.TextField(blank=True, null=True, verbose_name="Terms & Conditions")
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    converted_to_order = models.ForeignKey('PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_from_quotation')
    vendor_so_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Vendor SO Number")
    
    class Meta:
        verbose_name_plural = '4.0.2 Purchase Quotations'
        ordering = ['-quotation_date']
        indexes = [
            models.Index(fields=['quotation_no']),
            models.Index(fields=['vendor']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"RFQ #{self.quotation_no} - {self.vendor.name}"
    
    def total_amount(self):
        return sum(item.total_amt for item in self.items.all())
    
    def total_after_discount(self):
        return self.total_amount() - self.discount_value
    
    def is_expired(self):
        return self.valid_until < localdate()
    
    def save(self, *args, **kwargs):
        if not self.quotation_no:
            today = datetime.now().strftime('%Y%m%d')
            last_quote = PurchaseQuotation.objects.filter(
                quotation_no__startswith=f'RFQ-{today}'
            ).order_by('-quotation_no').first()
            if last_quote:
                last_num = int(last_quote.quotation_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.quotation_no = f'RFQ-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        if self.valid_until < localdate() and self.status in ['draft', 'requested', 'received']:
            self.status = 'expired'
        
        super().save(*args, **kwargs)


class PurchaseQuotationItem(models.Model):
    quotation = models.ForeignKey(PurchaseQuotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quoted Price")
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    
    class Meta:
        verbose_name_plural = '4.0.2.1 Purchase Quotation Items'
        unique_together = ('quotation', 'product')
    
    def __str__(self):
        return f"{self.qty} x {self.product.name} @ {self.price}"
    
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        self.total_amt = Decimal(self.qty) * self.price
        super().save(*args, **kwargs)
