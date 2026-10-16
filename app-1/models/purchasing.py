"""Purchasing models."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from datetime import timedelta
from datetime import date
from django.utils.timezone import now
from django.utils.timezone import localdate
from django.db.models import Sum
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)
from .catalog import Product, Warehouse

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
        null=True,          # ✅ Migration ke liye temporarily null allow
        blank=True,         # ✅ Form mein temporarily blank allow
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
        # ✅ Agar vendor_code empty hai to auto-generate karo
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


# ============================================
# PURCHASE ORDER MODEL
# ============================================
class PurchaseOrder(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    order_no = models.CharField(max_length=20, unique=True, verbose_name="PO Number")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='purchase_orders')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='purchase_orders')
    order_date = models.DateTimeField(default=now, verbose_name="Order Date")
    expected_date = models.DateField(null=True, blank=True, verbose_name="Expected Delivery Date")
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    notes = models.TextField(blank=True, null=True, verbose_name="Order Notes")
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    advance_payment = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name="Advance Payment")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    vendor_so_number = models.CharField(
    max_length=50,
    blank=True,
    null=True,
    verbose_name="Vendor SO Number",
    help_text="Vendor ke system ka Sale Order number"
)
    converted_to_purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_from_order')
    
    class Meta:
        verbose_name_plural = '4.0 Purchase Orders'
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['order_no']),
            models.Index(fields=['vendor']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"PO #{self.order_no} - {self.vendor.name}"
    
    def total_amount(self):
        return sum(item.total_amt for item in self.items.all())
    
    def total_after_discount(self):
        return self.total_amount() - self.discount_value
    
    def outstanding_advance(self):
        return self.total_after_discount() - self.advance_payment
    
    def received_qty(self, product):
        """Calculate total received qty for a product across all GRNs"""
        from django.db.models import Sum
        total = GoodsReceivedItem.objects.filter(
            grn__purchase_order=self,
            product=product
        ).aggregate(total=Sum('qty'))['total']
        return total or 0
    
    def pending_qty(self, product, order_qty):
        return order_qty - self.received_qty(product)
    
    def update_receive_status(self):
        """Auto-update status based on GRNs"""
        if self.status in ['cancelled', 'completed']:
            return
        
        items = self.items.all()
        if not items:
            return
        
        all_received = True
        any_received = False
        
        for item in items:
            received = self.received_qty(item.product)
            if received > 0:
                any_received = True
            if received < item.qty:
                all_received = False
        
        if all_received and any_received:
            self.status = 'received'
        elif any_received and not all_received:
            self.status = 'partially_received'
        
        self.save(update_fields=['status'])
    
    def save(self, *args, **kwargs):
        if not self.order_no:
            today = datetime.now().strftime('%Y%m%d')
            last_order = PurchaseOrder.objects.filter(order_no__startswith=f'PO-{today}').order_by('-order_no').first()
            if last_order:
                last_num = int(last_order.order_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.order_no = f'PO-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        super().save(*args, **kwargs)


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    
    class Meta:
        verbose_name_plural = '4.0.1 Purchase Order Items'
        unique_together = ('order', 'product')
    
    def __str__(self):
        return f"{self.qty} x {self.product.name} @ {self.price}"
    
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        self.total_amt = Decimal(self.qty) * self.price
        super().save(*args, **kwargs)


# ============================================
# GOODS RECEIVED NOTE (GRN) MODEL
# ============================================
class GoodsReceivedNote(models.Model):
    GRN_REASONS = [
        ('purchase', 'Purchase Order'),
        ('direct', 'Direct Purchase'),
        ('return', 'Customer Return'),
        ('other', 'Other'),
    ]
    
    grn_no = models.CharField(max_length=20, unique=True, verbose_name="GRN Number")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='grns', null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, verbose_name="Vendor/Supplier")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    grn_date = models.DateTimeField(default=now, verbose_name="Received Date")
    reason = models.CharField(max_length=20, choices=GRN_REASONS, default='purchase', verbose_name="Reason")
    invoice_no = models.CharField(max_length=50, blank=True, null=True, verbose_name="Supplier Invoice No")
    vehicle_no = models.CharField(max_length=30, blank=True, null=True, verbose_name="Vehicle Number")
    driver_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Driver Name")
    notes = models.TextField(blank=True, null=True, verbose_name="Remarks")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    converted_to_purchase = models.BooleanField(default=False, verbose_name="Converted to Purchase")
    purchase = models.OneToOneField(
    'Purchase',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='converted_from_grn',
    verbose_name="Linked Purchase"
)
    converted_to_purchase = models.BooleanField(default=False, verbose_name="Converted to Purchase")
    
    class Meta:
        verbose_name_plural = '4.2 Goods Received Notes'
        indexes = [
            models.Index(fields=['grn_no']),
            models.Index(fields=['vendor']),
            models.Index(fields=['purchase_order']),
        ]
    
    def __str__(self):
        return f"GRN #{self.grn_no} - {self.vendor.name}"
    
    def total_qty(self):
        return sum(item.qty for item in self.items.all())
    
    def total_items(self):
        return self.items.count()
    
    def save(self, *args, **kwargs):
        if not self.grn_no:
            today = datetime.now().strftime('%Y%m%d')
            last_grn = GoodsReceivedNote.objects.filter(
                grn_no__startswith=f'GRN-{today}'
            ).order_by('-grn_no').first()
            if last_grn:
                last_num = int(last_grn.grn_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.grn_no = f'GRN-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        super().save(*args, **kwargs)
        
        # ✅ Update PO status after save
        if self.purchase_order and self.purchase_order.status not in ['cancelled', 'completed']:
            self.purchase_order.update_receive_status()


class GoodsReceivedItem(models.Model):
    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    order_qty = models.FloatField(default=0, verbose_name="Order Qty")
    qty = models.FloatField(verbose_name="Received Qty")
    pending_qty = models.FloatField(default=0, verbose_name="Pending Qty")
    unit = models.CharField(max_length=20, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    notes = models.CharField(max_length=255, blank=True, null=True, verbose_name="Remarks")
    
    class Meta:
        verbose_name_plural = '4.2.1 Goods Received Items'
    
    def __str__(self):
        return f"{self.qty}/{self.order_qty} x {self.product.name}"
    
    def save(self, *args, **kwargs):
        if not self.unit and self.product.unit:
            self.unit = self.product.unit.name
        
        self.total_amt = Decimal(self.qty) * self.price
        
        if self.order_qty > 0:
            self.pending_qty = max(0, self.order_qty - self.qty)
        
        super().save(*args, **kwargs)


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
                batch.save()
            Inventory.update_stock(self.product, qty_diff, warehouse)
            super().save(*args, **kwargs)
        else:
            # New item - ONLY ONE SAVE
            super().save(*args, **kwargs)
            StockBatch.add_batch(self.product, self.qty, self.price, purchase_item=self, warehouse=warehouse)
            Inventory.update_stock(self.product, self.qty, warehouse)

    def __str__(self):
        return f"{self.qty} x {self.product.name}"


class PurchaseRetrn(models.Model):
    """
    Purchase Return Model - Complete with all methods
    """
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    bill_no = models.CharField(max_length=10, blank=True, null=True)
    purchase = models.ForeignKey(
        'Purchase', 
        on_delete=models.CASCADE, 
        related_name="returns", 
        null=True, 
        blank=True
    )
    vendor = models.ForeignKey(
        'Vendor', 
        on_delete=models.CASCADE
    )
    purchase_return_date = models.DateTimeField(default=now)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        editable=False
    )
    return_reason = models.CharField(
        max_length=255, 
        choices=[
            ('damaged', 'Damaged Goods'),
            ('incorrect', 'Incorrect Shipment'),
            ('expired', 'Expired Stock'),
            ('quality', 'Quality Issue'),
            ('wrong_item', 'Wrong Item Received'),
            ('excess', 'Excess Quantity'),
            ('other', 'Other'),
        ], 
        default='other'
    )
    
    # ========================================== #
    # WAREHOUSE FIELD                           #
    # ========================================== #
    warehouse = models.ForeignKey(
        'Warehouse', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='purchase_returns'
    )
    
    # ========================================== #
    # MONTHLY CLOSING                           #
    # ========================================== #
    monthly_purchase = models.ForeignKey(
        'MonthlyClosing', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='purchase_returns', 
        editable=False
    )
    
    # ========================================== #
    # NOTES                                     #
    # ========================================== #
    notes = models.TextField(blank=True, null=True)
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = '4.4. Purchase Returns'
        ordering = ['-purchase_return_date']
        indexes = [
            models.Index(fields=['purchase', 'vendor']),
            models.Index(fields=['purchase_return_date']),
            models.Index(fields=['return_reason']),
        ]

    def __str__(self):
        return f"Return #{self.id} - {self.vendor.name} - {self.purchase_return_date.strftime('%d-%m-%Y')}"

    # ========================================== #
    # TOTAL CALCULATIONS                        #
    # ========================================== #
    
    def total_return_amount(self):
        """Calculate total return amount for this return"""
        return self.return_items.aggregate(
            total=Sum('total_amt')
        )['total'] or Decimal('0.00')
    
    def total_return_qty(self):
        """Calculate total return quantity for this return"""
        return self.return_items.aggregate(
            total=Sum('qty')
        )['total'] or Decimal('0.00')
    
    def total_items_returned(self):
        """Count total items in this return"""
        return self.return_items.count()
    
    def get_returned_qty(self, product):
        """
        ✅ NEW: Calculate total returned quantity for a specific product
        (across all returns of this purchase)
        Returns: Decimal
        """
        from django.db.models import Sum
        
        if not self.purchase:
            return Decimal('0.00')
        
        total = PurchaseRetrnItem.objects.filter(
            purchase_return__purchase=self.purchase,
            product=product
        ).aggregate(total=Sum('qty'))['total'] or Decimal('0.00')
        return total
    
    def get_remaining_qty(self, product, original_qty):
        """
        ✅ NEW: Calculate remaining quantity available for return
        Returns: Decimal
        """
        if not self.purchase:
            return Decimal('0.00')
        
        returned = self.get_returned_qty(product)
        remaining = Decimal(str(original_qty)) - returned
        return max(Decimal('0.00'), remaining)
    
    def get_product_return_summary(self, product):
        """
        ✅ NEW: Get detailed summary for a specific product return
        Returns: Dict
        """
        if not self.purchase:
            return {}
        
        purchase_item = self.purchase.purchaseitem_set.filter(product=product).first()
        if not purchase_item:
            return {}
        
        original_qty = Decimal(str(purchase_item.qty))
        returned_qty = self.get_returned_qty(product)
        remaining_qty = self.get_remaining_qty(product, original_qty)
        
        return {
            'product_name': product.name,
            'original_qty': float(original_qty),
            'returned_qty': float(returned_qty),
            'remaining_qty': float(remaining_qty),
            'is_fully_returned': remaining_qty <= 0,
            'is_partially_returned': returned_qty > 0 and remaining_qty > 0,
            'purchase_price': float(purchase_item.price),
        }
    
    def get_all_returned_items_summary(self):
        """
        ✅ NEW: Get summary of all returned items in this return
        Returns: Dict
        """
        items = []
        total_qty = Decimal('0.00')
        total_amount = Decimal('0.00')
        
        for item in self.return_items.all():
            items.append({
                'product_id': item.product.id,
                'product_name': item.product.name,
                'qty': float(item.qty),
                'amount': float(item.total_amt),
                'price': float(item.price),
                'unit': item.product.unit.name if item.product.unit else '',
            })
            total_qty += item.qty
            total_amount += item.total_amt
        
        return {
            'total_items': len(items),
            'total_qty': float(total_qty),
            'total_amount': float(total_amount),
            'items': items
        }
    
    def get_purchase_return_history(self):
        """
        ✅ NEW: Get all returns for this purchase
        Returns: List of dicts
        """
        if not self.purchase:
            return []
        
        returns = PurchaseRetrn.objects.filter(purchase=self.purchase).order_by('-purchase_return_date')
        history = []
        
        for ret in returns:
            items = []
            for item in ret.return_items.all():
                items.append({
                    'product_id': item.product.id,
                    'product_name': item.product.name,
                    'qty': float(item.qty),
                    'amount': float(item.total_amt),
                    'price': float(item.price)
                })
            
            history.append({
                'return_id': ret.id,
                'date': ret.purchase_return_date.strftime('%d-%m-%Y %H:%M'),
                'reason': ret.get_return_reason_display(),
                'bill_no': ret.bill_no or 'N/A',
                'items': items,
                'total_qty': float(sum(item['qty'] for item in items)),
                'total_amount': float(sum(item['amount'] for item in items)),
                'total_items': len(items)
            })
        
        return history
    
    def get_product_wise_return_summary(self):
        """
        ✅ NEW: Get product-wise return summary for this purchase
        Returns: Dict with product_id as key
        """
        if not self.purchase:
            return {}
        
        product_summary = {}
        purchase_items = self.purchase.purchaseitem_set.all()
        
        for p_item in purchase_items:
            product = p_item.product
            original_qty = Decimal(str(p_item.qty))
            returned_qty = self.get_returned_qty(product)
            remaining_qty = self.get_remaining_qty(product, original_qty)
            
            product_summary[str(product.id)] = {
                'product_id': product.id,
                'product_name': product.name,
                'original_qty': float(original_qty),
                'returned_qty': float(returned_qty),
                'remaining_qty': float(remaining_qty),
                'purchase_price': float(p_item.price),
                'unit': product.unit.name if product.unit else '',
                'is_fully_returned': remaining_qty <= 0,
                'return_percentage': float((returned_qty / original_qty * 100) if original_qty > 0 else 0)
            }
        
        return product_summary

    # ========================================== #
    # STATUS METHODS                            #
    # ========================================== #
    
    def get_status(self):
        """Get return status based on items"""
        total_items = self.return_items.count()
        if total_items == 0:
            return 'empty'
        return 'processed'
    
    def get_status_badge(self):
        """Get HTML badge for status"""
        status = self.get_status()
        if status == 'empty':
            return '<span class="badge bg-warning">⚠️ Empty</span>'
        return '<span class="badge bg-success">✅ Processed</span>'
    
    def is_fully_returned(self, product):
        """Check if a product is fully returned"""
        if not self.purchase:
            return False
        
        original_qty = self.purchase.purchaseitem_set.filter(
            product=product
        ).aggregate(total=Sum('qty'))['total'] or Decimal('0.00')
        
        returned_qty = self.get_returned_qty(product)
        
        return returned_qty >= original_qty and original_qty > 0
    
    def is_partially_returned(self, product):
        """Check if a product is partially returned"""
        if not self.purchase:
            return False
        
        original_qty = self.purchase.purchaseitem_set.filter(
            product=product
        ).aggregate(total=Sum('qty'))['total'] or Decimal('0.00')
        
        returned_qty = self.get_returned_qty(product)
        
        return returned_qty > 0 and returned_qty < original_qty

    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Override save to handle warehouse and monthly closing
        """
        # ✅ Set created_by if not set
        if not self.pk and not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        # ✅ Auto-set warehouse from purchase
        if not self.warehouse and self.purchase:
            self.warehouse = self.purchase.warehouse
        
        # ✅ Fallback: Get first warehouse
        if not self.warehouse:
            self.warehouse = Warehouse.objects.first()
        
        # ✅ Set monthly closing
        purchase_month = self.purchase_return_date.replace(day=1)
        monthly_closing, _ = MonthlyClosing.objects.get_or_create(month=purchase_month)
        self.monthly_purchase = monthly_closing
        
        # ✅ Check if month is locked
        if monthly_closing.locked:
            raise ValidationError(
                f"Cannot process purchase return for {purchase_month.strftime('%B %Y')}, "
                f"as the month is locked."
            )
        
        # ✅ Set created_by if still None
        if not self.created_by:
            self.created_by = User.objects.first()
        
        super().save(*args, **kwargs)

    # ========================================== #
    # DELETE METHOD                             #
    # ========================================== #
    
    def delete(self, *args, **kwargs):
        """
        Override delete to restore stock
        """
        # ✅ Restore stock before deleting
        for item in self.return_items.all():
            try:
                # Restore stock
                warehouse = self.warehouse or self.purchase.warehouse
                Inventory.update_stock(item.product, float(item.qty), warehouse)
                
                # Restore batch quantities
                batches = StockBatch.objects.filter(
                    product=item.product,
                    warehouse=warehouse,
                    price=item.price
                ).order_by('id')
                
                remaining_qty = float(item.qty)
                for batch in batches:
                    if remaining_qty <= 0:
                        break
                    # Restore quantity to batch
                    batch.remaining_qty += remaining_qty
                    batch.qty += remaining_qty
                    batch.save()
                    remaining_qty = 0
                    
            except Exception as e:
                # Log error but continue
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to restore stock for {item.product.name}: {e}")
        
        super().delete(*args, **kwargs)

    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def formatted_total_amount(self):
        """Formatted total amount"""
        return f"Rs. {self.total_return_amount():,.2f}"
    
    @property
    def formatted_total_qty(self):
        """Formatted total quantity"""
        return f"{self.total_return_qty():,.2f}"
    
    @property
    def formatted_date(self):
        """Formatted return date"""
        return self.purchase_return_date.strftime('%d-%m-%Y %H:%M')
    
    @property
    def vendor_name(self):
        """Get vendor name"""
        return self.vendor.name if self.vendor else 'Unknown'
    
    @property
    def vendor_code(self):
        """Get vendor code"""
        return self.vendor.vendor_code if self.vendor else 'N/A'
    
    @property
    def purchase_bill_no(self):
        """Get purchase bill number"""
        return self.purchase.bill_no if self.purchase else 'N/A'
    
    @property
    def warehouse_name(self):
        """Get warehouse name"""
        return self.warehouse.name if self.warehouse else 'N/A'
    
    @property
    def created_by_name(self):
        """Get created by username"""
        return self.created_by.username if self.created_by else 'System'
    
    @property
    def return_reason_display(self):
        """Get return reason display name"""
        return dict(self._meta.get_field('return_reason').choices).get(self.return_reason, self.return_reason)
    
    @property
    def is_damaged(self):
        """Check if return reason is damaged"""
        return self.return_reason == 'damaged'
    
    @property
    def is_incorrect(self):
        """Check if return reason is incorrect"""
        return self.return_reason == 'incorrect'
    
    @property
    def is_expired(self):
        """Check if return reason is expired"""
        return self.return_reason == 'expired'
    
    @property
    def is_quality_issue(self):
        """Check if return reason is quality issue"""
        return self.return_reason == 'quality'
    
    @property
    def is_wrong_item(self):
        """Check if return reason is wrong item"""
        return self.return_reason == 'wrong_item'
    
    @property
    def is_excess(self):
        """Check if return reason is excess quantity"""
        return self.return_reason == 'excess'
    
    @property
    def is_other(self):
        """Check if return reason is other"""
        return self.return_reason == 'other'
    
    @property
    def total_returned_value(self):
        """Alias for total_return_amount()"""
        return self.total_return_amount()
    
    @property
    def items_count(self):
        """Alias for total_items_returned()"""
        return self.total_items_returned()
    
    @property
    def reason_color(self):
        """Get color for return reason"""
        colors = {
            'damaged': 'danger',
            'incorrect': 'warning',
            'expired': 'danger',
            'quality': 'warning',
            'wrong_item': 'info',
            'excess': 'primary',
            'other': 'secondary'
        }
        return colors.get(self.return_reason, 'secondary')
    
    @property
    def reason_icon(self):
        """Get icon for return reason"""
        icons = {
            'damaged': 'bi bi-exclamation-triangle',
            'incorrect': 'bi bi-x-circle',
            'expired': 'bi bi-clock',
            'quality': 'bi bi-star',
            'wrong_item': 'bi bi-box',
            'excess': 'bi bi-plus-circle',
            'other': 'bi bi-three-dots'
        }
        return icons.get(self.return_reason, 'bi bi-question-circle')
    
    @property
    def can_edit(self):
        """Check if return can be edited"""
        # Return can be edited if it's recent (within 7 days)
        days_diff = (now().date() - self.purchase_return_date.date()).days
        return days_diff <= 7
    
    @property
    def can_delete(self):
        """Check if return can be deleted"""
        # Return can be deleted if it's recent (within 7 days)
        days_diff = (now().date() - self.purchase_return_date.date()).days
        return days_diff <= 7
    
    @property
    def month(self):
        """Get month of return"""
        return self.purchase_return_date.strftime('%B %Y')
    
    @property
    def year(self):
        """Get year of return"""
        return self.purchase_return_date.year
    
    @property
    def short_date(self):
        """Get short date format"""
        return self.purchase_return_date.strftime('%d %b, %Y')
    
    @property
    def time(self):
        """Get time of return"""
        return self.purchase_return_date.strftime('%I:%M %p')

    # ========================================== #
    # CLASS METHODS                             #
    # ========================================== #
    
    @classmethod
    def get_by_vendor(cls, vendor, start_date=None, end_date=None):
        """Get all returns for a vendor within date range"""
        queryset = cls.objects.filter(vendor=vendor)
        if start_date:
            queryset = queryset.filter(purchase_return_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(purchase_return_date__date__lte=end_date)
        return queryset
    
    @classmethod
    def get_by_purchase(cls, purchase):
        """Get all returns for a purchase"""
        return cls.objects.filter(purchase=purchase)
    
    @classmethod
    def get_by_reason(cls, reason, start_date=None, end_date=None):
        """Get all returns by reason"""
        queryset = cls.objects.filter(return_reason=reason)
        if start_date:
            queryset = queryset.filter(purchase_return_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(purchase_return_date__date__lte=end_date)
        return queryset
    
    @classmethod
    def get_monthly_summary(cls, year, month):
        """Get monthly return summary"""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        returns = cls.objects.filter(
            purchase_return_date__date__gte=start_date,
            purchase_return_date__date__lte=end_date
        )
        
        total_returns = returns.count()
        total_amount = sum(ret.total_return_amount() for ret in returns)
        total_items = sum(ret.total_items_returned() for ret in returns)
        
        return {
            'total_returns': total_returns,
            'total_amount': total_amount,
            'total_items': total_items,
            'by_reason': {
                reason: returns.filter(return_reason=reason).count()
                for reason, _ in cls._meta.get_field('return_reason').choices
            }
        }
    
    @classmethod
    def get_vendor_summary(cls, vendor):
        """Get summary for a specific vendor"""
        returns = cls.objects.filter(vendor=vendor)
        
        total_returns = returns.count()
        total_amount = sum(ret.total_return_amount() for ret in returns)
        total_items = sum(ret.total_items_returned() for ret in returns)
        
        return {
            'total_returns': total_returns,
            'total_amount': total_amount,
            'total_items': total_items,
            'reasons': {
                reason: returns.filter(return_reason=reason).count()
                for reason, _ in cls._meta.get_field('return_reason').choices
            },
            'latest_return': returns.order_by('-purchase_return_date').first(),
            'returns': returns.order_by('-purchase_return_date')[:10]
        }
    
    @classmethod
    def get_reason_stats(cls):
        """Get statistics by return reason"""
        reasons = {}
        for reason, label in cls._meta.get_field('return_reason').choices:
            count = cls.objects.filter(return_reason=reason).count()
            amount = cls.objects.filter(
                return_reason=reason
            ).aggregate(total=Sum('return_items__total_amt'))['total'] or Decimal('0.00')
            reasons[reason] = {
                'label': label,
                'count': count,
                'amount': amount
            }
        return reasons


class PurchaseRetrnItem(models.Model):
    purchase_return = models.ForeignKey(
        'PurchaseRetrn',
        on_delete=models.CASCADE,
        related_name="return_items",
        null=True,
        blank=True
    )
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    qty = models.DecimalField(max_digits=15, decimal_places=2)  # ✅ DecimalField
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be positive.")

        self.total_amt = self.qty * self.price

        # Get warehouse from purchase return
        warehouse = None
        if self.purchase_return and self.purchase_return.purchase:
            warehouse = self.purchase_return.purchase.warehouse
        elif self.purchase_return and hasattr(self.purchase_return, 'warehouse'):
            warehouse = self.purchase_return.warehouse

        if not warehouse:
            warehouse = Warehouse.objects.first()
            if not warehouse:
                raise ValidationError("No warehouse found! Please create a warehouse first.")

        if self.pk:
            existing = PurchaseRetrnItem.objects.get(pk=self.pk)
            # ✅ FIX: Decimal se Decimal subtract
            qty_diff = self.qty - existing.qty

            if qty_diff != 0:
                try:
                    self.adjust_batches(qty_diff, warehouse)  # ✅ Decimal pass ho raha hai
                    Inventory.update_stock(self.product, -float(qty_diff), warehouse)  # ✅ float mein convert
                except Exception as e:
                    raise ValidationError(f"Cannot update return: {str(e)}")
        else:
            try:
                self.adjust_batches(-self.qty, warehouse)  # ✅ Decimal pass
                Inventory.update_stock(self.product, -float(self.qty), warehouse)  # ✅ float convert
            except Exception as e:
                raise ValidationError(f"Cannot create return: {str(e)}")

        self.validate_purchase_item()
        super().save(*args, **kwargs)

    def adjust_batches(self, qty_diff, warehouse):
        """
        Adjust stock batches with warehouse
        qty_diff: Decimal
        """
        # ✅ qty_diff ko float mein convert karo for calculations
        qty_diff_float = float(qty_diff)
        remaining_qty_to_adjust = abs(qty_diff_float)
        
        batches = StockBatch.objects.filter(
            product=self.product, 
            price=self.price,
            warehouse=warehouse
        ).order_by('id')

        if qty_diff_float < 0:  # Returning stock (decrease batch)
            for batch in batches:
                if remaining_qty_to_adjust <= 0:
                    break
                # ✅ float use karo
                decrement = min(float(batch.remaining_qty), remaining_qty_to_adjust)
                if decrement > 0:
                    batch.remaining_qty -= decrement
                    batch.qty -= decrement
                    batch.save()
                    remaining_qty_to_adjust -= decrement

            if remaining_qty_to_adjust > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Could not return {remaining_qty_to_adjust} units of {self.product.name} "
                    f"in warehouse {warehouse.name}. Stock may already be adjusted."
                )
        else:  # Removing return (increase batch)
            for batch in batches:
                if remaining_qty_to_adjust <= 0:
                    break
                # ✅ float use karo
                increment = min(float(batch.qty - batch.remaining_qty), remaining_qty_to_adjust)
                if increment > 0:
                    batch.remaining_qty += increment
                    batch.qty += increment
                    batch.save()
                    remaining_qty_to_adjust -= increment

            if remaining_qty_to_adjust > 0:
                purchase_item = self.purchase_return.purchase.purchaseitem_set.filter(
                    product=self.product
                ).first()
                
                StockBatch.objects.create(
                    product=self.product,
                    warehouse=warehouse,
                    qty=remaining_qty_to_adjust,
                    remaining_qty=remaining_qty_to_adjust,
                    price=self.price,
                    purchase_item=purchase_item
                )

    def validate_purchase_item(self):
        """Validate the product against purchase"""
        purchase = self.purchase_return.purchase
        purchase_item = purchase.purchaseitem_set.filter(product=self.product).first()

        if not purchase_item:
            raise ValidationError(f"The product '{self.product}' does not exist in the selected purchase.")

        if self.price != purchase_item.price:
            raise ValidationError(
                f"Price mismatch: Purchase price is {purchase_item.price}, but return price is {self.price}."
            )

        if self.qty > purchase_item.qty:
            raise ValidationError(
                f"Quantity exceeds purchase limit: Purchased quantity is {purchase_item.qty}, but return quantity is {self.qty}."
            )

    def __str__(self):
        return f"{self.qty} x {self.product.name}"

    class Meta:
        verbose_name_plural = '4.4. Purchase Return Items'


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


class MonthlyPurchasePlan(models.Model):
    """
    Monthly Purchase Plan - Complete with Version Tracking, Inventory Integration & Safe Conversion
    Allows multiple plans per month with version history
    """
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    STOCK_STATUS_CHOICES = [
        ('sufficient', '✅ Sufficient'),
        ('low', '⚠️ Low Stock'),
        ('critical', '🔴 Critical'),
        ('out_of_stock', '❌ Out of Stock'),
    ]
    
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    month = models.DateField(help_text="First day of the month")
    plan_no = models.CharField(max_length=20, unique=True, editable=False, default='')
    
    # ========================================== #
    # VERSION TRACKING                          #
    # ========================================== #
    version = models.PositiveIntegerField(default=1, help_text="Plan version for the month")
    is_latest = models.BooleanField(default=True, help_text="Is this the latest version?")
    previous_plan = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='improved_plans',
        help_text="Previous plan that was improved"
    )
    
    # ========================================== #
    # PRODUCT & WAREHOUSE                       #
    # ========================================== #
    product = models.ForeignKey(
        'Product', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='purchase_plans'
    )
    product_name = models.CharField(max_length=200, blank=True, null=True)
    
    warehouse = models.ForeignKey(
        'Warehouse', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='purchase_plans',
        help_text="Warehouse for this plan"
    )
    
    # ========================================== #
    # PLANNING DETAILS                          #
    # ========================================== #
    expected_sales_quantity = models.IntegerField(default=0, help_text="Expected units to sell")
    expected_sales_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    purchase_quantity = models.IntegerField(default=0, help_text="Planned purchase quantity")
    purchase_price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_purchase_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ========================================== #
    # INVESTOR REQUIREMENTS                     #
    # ========================================== #
    required_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    existing_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    additional_investment_needed = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    current_investors = models.IntegerField(default=0)
    required_investors = models.IntegerField(default=0)
    additional_investors_needed = models.IntegerField(default=0)
    
    # ========================================== #
    # ✅ INVENTORY INTEGRATION FIELDS            #
    # ========================================== #
    current_stock = models.FloatField(default=0, help_text="Current stock of product")
    reserved_stock = models.FloatField(default=0, help_text="Reserved stock")
    available_stock = models.FloatField(default=0, help_text="Available stock")
    
    stock_required = models.FloatField(default=0, help_text="Total stock required")
    stock_to_purchase = models.FloatField(default=0, help_text="Stock to purchase")
    stock_after_purchase = models.FloatField(default=0, help_text="Stock after purchase")
    
    purchase_order = models.ForeignKey(
        'PurchaseOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='monthly_plans',
        help_text="Generated Purchase Order"
    )
    
    stock_status = models.CharField(
        max_length=20,
        choices=STOCK_STATUS_CHOICES,
        default='sufficient',
        help_text="Current stock status"
    )
    
    # ========================================== #
    # ACTUAL ACHIEVEMENT                        #
    # ========================================== #
    actual_purchase_quantity = models.IntegerField(default=0)
    actual_purchase_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_sales_quantity = models.IntegerField(default=0)
    actual_sales_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ========================================== #
    # VARIANCE ANALYSIS                         #
    # ========================================== #
    purchase_variance_qty = models.IntegerField(default=0, help_text="Actual - Planned")
    purchase_variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    sales_variance_qty = models.IntegerField(default=0)
    sales_variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    achievement_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # ========================================== #
    # STATUS & TRACKING                         #
    # ========================================== #
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_plans'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # ========================================== #
    # NOTES & DOCUMENTATION                     #
    # ========================================== #
    notes = models.TextField(blank=True, null=True)
    achievements = models.TextField(blank=True, null=True, help_text="What was achieved?")
    challenges = models.TextField(blank=True, null=True, help_text="What challenges were faced?")
    lessons_learned = models.TextField(blank=True, null=True, help_text="What was learned?")
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_plans'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "📊 Monthly Purchase Plans"
        ordering = ['-month', '-version']  # Latest version first
        indexes = [
            models.Index(fields=['month', 'version']),
            models.Index(fields=['status']),
            models.Index(fields=['is_latest']),
            models.Index(fields=['plan_no']),
            models.Index(fields=['stock_status']),
        ]
    
    def __str__(self):
        return f"Plan #{self.plan_no} (v{self.version}) - {self.month.strftime('%B %Y')}"
    
    # ========================================== #
    # SAVE METHOD WITH SAFE CONVERSION          #
    # ========================================== #
    def save(self, *args, **kwargs):
        """Override save with safe conversion and inventory integration"""
        
        # ========================================== #
        # AUTO-GENERATE PLAN NUMBER                 #
        # ========================================== #
        if not self.plan_no:
            last_plan = MonthlyPurchasePlan.objects.order_by('-id').first()
            if last_plan and last_plan.plan_no:
                try:
                    last_num = int(last_plan.plan_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.plan_no = f'MP-{new_num}'
        
        # ========================================== #
        # SET PRODUCT NAME                          #
        # ========================================== #
        if self.product and not self.product_name:
            self.product_name = self.product.name
        
        # ========================================== #
        # SAFE DECIMAL CONVERSION FUNCTION          #
        # ========================================== #
        def safe_decimal(value, default='0.00'):
            """Safely convert value to Decimal"""
            try:
                if value is None or value == '':
                    return Decimal(default)
                if isinstance(value, Decimal):
                    return value
                if isinstance(value, (int, float)):
                    return Decimal(str(value))
                cleaned = str(value).replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '').strip()
                if cleaned == '':
                    return Decimal(default)
                return Decimal(cleaned)
            except:
                return Decimal(default)
        
        def safe_int(value, default=0):
            """Safely convert value to Integer"""
            try:
                if value is None or value == '':
                    return default
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                cleaned = str(value).replace(',', '').replace(' ', '').strip()
                if cleaned == '':
                    return default
                return int(float(cleaned))
            except:
                return default
        
        def safe_float(value, default=0.0):
            """Safely convert value to Float"""
            try:
                if value is None or value == '':
                    return default
                return float(value)
            except:
                return default
        
        # ========================================== #
        # CALCULATE TOTAL PURCHASE                  #
        # ========================================== #
        qty = safe_decimal(self.purchase_quantity)
        price = safe_decimal(self.purchase_price_per_unit)
        self.total_purchase_amount = qty * price
        
        # ========================================== #
        # CALCULATE REQUIRED INVESTMENT             #
        # ========================================== #
        self.required_investment = self.total_purchase_amount
        
        # ========================================== #
        # CALCULATE ADDITIONAL INVESTMENT NEEDED    #
        # ========================================== #
        existing = safe_decimal(self.existing_investment)
        self.additional_investment_needed = max(
            Decimal('0.00'), 
            self.required_investment - existing
        )
        
        # ========================================== #
        # CALCULATE REQUIRED INVESTORS              #
        # ========================================== #
        avg_investment = Decimal('10000')
        if avg_investment > 0:
            self.required_investors = int(self.required_investment / avg_investment)
        else:
            self.required_investors = 0
        
        self.additional_investors_needed = max(
            0, 
            self.required_investors - safe_int(self.current_investors)
        )
        
        # ========================================== #
        # ✅ INVENTORY CALCULATIONS                  #
        # ========================================== #
        
        # Get current stock from inventory
        if self.product and self.warehouse:
            inventory = Inventory.objects.filter(
                product=self.product,
                warehouse=self.warehouse
            ).first()
            
            if inventory:
                self.current_stock = safe_float(inventory.stock)
                self.reserved_stock = safe_float(inventory.reserved_stock)
                self.available_stock = self.current_stock - self.reserved_stock
            else:
                self.current_stock = 0
                self.reserved_stock = 0
                self.available_stock = 0
        else:
            self.current_stock = 0
            self.reserved_stock = 0
            self.available_stock = 0
        
        # Calculate stock requirements
        self.stock_required = safe_float(self.expected_sales_quantity)
        
        # Calculate stock to purchase
        self.stock_to_purchase = max(0, self.stock_required - self.available_stock)
        
        # Calculate stock after purchase
        self.stock_after_purchase = self.available_stock + self.stock_to_purchase
        
        # ========================================== #
        # ✅ STOCK STATUS DETERMINATION              #
        # ========================================== #
        
        if self.available_stock <= 0:
            self.stock_status = 'out_of_stock'
        elif self.available_stock < (self.stock_required * 0.25):
            self.stock_status = 'critical'
        elif self.available_stock < self.stock_required:
            self.stock_status = 'low'
        else:
            self.stock_status = 'sufficient'
        
        # ========================================== #
        # CALCULATE VARIANCES                       #
        # ========================================== #
        self.purchase_variance_qty = safe_int(self.actual_purchase_quantity) - safe_int(self.purchase_quantity)
        self.purchase_variance_amount = safe_decimal(self.actual_purchase_amount) - safe_decimal(self.total_purchase_amount)
        self.sales_variance_qty = safe_int(self.actual_sales_quantity) - safe_int(self.expected_sales_quantity)
        self.sales_variance_amount = safe_decimal(self.actual_sales_amount) - safe_decimal(self.expected_sales_amount)
        
        # ========================================== #
        # CALCULATE PROFIT VARIANCE                 #
        # ========================================== #
        expected_profit = safe_decimal(self.expected_sales_amount) - safe_decimal(self.total_purchase_amount)
        self.profit_variance = safe_decimal(self.actual_profit) - expected_profit
        
        # ========================================== #
        # CALCULATE ACHIEVEMENT PERCENTAGE          #
        # ========================================== #
        expected = safe_decimal(self.expected_sales_amount)
        actual = safe_decimal(self.actual_sales_amount)
        
        if expected > 0:
            self.achievement_percentage = (actual / expected) * Decimal('100')
        else:
            self.achievement_percentage = Decimal('0.00')
        
        # ========================================== #
        # ROUND VALUES                              #
        # ========================================== #
        self.total_purchase_amount = round(self.total_purchase_amount, 2)
        self.required_investment = round(self.required_investment, 2)
        self.additional_investment_needed = round(self.additional_investment_needed, 2)
        self.purchase_variance_amount = round(self.purchase_variance_amount, 2)
        self.sales_variance_amount = round(self.sales_variance_amount, 2)
        self.profit_variance = round(self.profit_variance, 2)
        self.achievement_percentage = round(self.achievement_percentage, 2)
        
        super().save(*args, **kwargs)
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    @property
    def status_badge(self):
        colors = {
            'draft': 'secondary',
            'approved': 'primary',
            'in_progress': 'warning',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def stock_status_badge(self):
        colors = {
            'sufficient': 'success',
            'low': 'warning',
            'critical': 'danger',
            'out_of_stock': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.stock_status, "secondary")}">{self.get_stock_status_display()}</span>'
    
    @property
    def achievement_color(self):
        if self.achievement_percentage >= 100:
            return 'success'
        elif self.achievement_percentage >= 75:
            return 'warning'
        else:
            return 'danger'
    
    @property
    def is_achieved(self):
        return self.achievement_percentage >= 100
    
    @property
    def is_pending(self):
        return self.status in ['draft', 'approved', 'in_progress']
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_cancelled(self):
        return self.status == 'cancelled'
    
    @property
    def needs_purchase(self):
        return self.stock_to_purchase > 0
    
    @property
    def formatted_total(self):
        return f"Rs. {self.total_purchase_amount:,.2f}"
    
    @property
    def formatted_achievement(self):
        return f"{self.achievement_percentage:.1f}%"
    
    @property
    def version_badge(self):
        if self.is_latest:
            return f'<span class="badge bg-success">v{self.version} (Latest)</span>'
        return f'<span class="badge bg-secondary">v{self.version}</span>'
    
    # ========================================== #
    # METHODS                                   #
    # ========================================== #
    def approve(self, user):
        """Approve plan"""
        from django.utils.timezone import now
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        return True
    
    def start_progress(self):
        """Start progress"""
        self.status = 'in_progress'
        self.save()
        return True
    
    def complete(self, user):
        """Mark plan as completed"""
        from django.utils.timezone import now
        self.status = 'completed'
        self.completed_at = now()
        self.save()
        return True
    
    def cancel(self, user, reason=''):
        """Cancel plan"""
        self.status = 'cancelled'
        self.notes = f"{self.notes or ''}\nCancelled: {reason}".strip()
        self.save()
        return True
    
    def get_variance_summary(self):
        """Get variance summary"""
        return {
            'purchase_qty_variance': self.purchase_variance_qty,
            'purchase_amount_variance': float(self.purchase_variance_amount),
            'sales_qty_variance': self.sales_variance_qty,
            'sales_amount_variance': float(self.sales_variance_amount),
            'profit_variance': float(self.profit_variance),
            'achievement': float(self.achievement_percentage),
        }
    
    def get_investor_requirement(self):
        """Get investor requirement summary"""
        return {
            'total_investment': float(self.total_purchase_amount),
            'existing_investment': float(self.existing_investment),
            'additional_needed': float(self.additional_investment_needed),
            'current_investors': self.current_investors,
            'required_investors': self.required_investors,
            'additional_investors': self.additional_investors_needed,
        }
    
    def get_stock_summary(self):
        """Get stock summary"""
        return {
            'current_stock': self.current_stock,
            'reserved_stock': self.reserved_stock,
            'available_stock': self.available_stock,
            'stock_required': self.stock_required,
            'stock_to_purchase': self.stock_to_purchase,
            'stock_after_purchase': self.stock_after_purchase,
            'stock_status': self.stock_status,
            'stock_status_display': self.get_stock_status_display(),
        }
    
    def refresh_stock(self):
        """Refresh stock data from inventory"""
        if self.product and self.warehouse:
            inventory = Inventory.objects.filter(
                product=self.product,
                warehouse=self.warehouse
            ).first()
            
            if inventory:
                self.current_stock = float(inventory.stock)
                self.reserved_stock = float(inventory.reserved_stock)
                self.available_stock = self.current_stock - self.reserved_stock
                self.stock_to_purchase = max(0, self.stock_required - self.available_stock)
                self.stock_after_purchase = self.available_stock + self.stock_to_purchase
                self.save()
                return True
        return False
    
    # ========================================== #
    # CLASS METHODS                             #
    # ========================================== #
    @classmethod
    def get_latest_plan(cls, month):
        """Get latest plan for a month"""
        return cls.objects.filter(month=month, is_latest=True).first()
    
    @classmethod
    def get_all_plans_for_month(cls, month):
        """Get all plans for a month"""
        return cls.objects.filter(month=month).order_by('-version')
    
    @classmethod
    def create_new_version(cls, month, user, **kwargs):
        """Create a new version of plan for a month"""
        from django.db import transaction
        
        with transaction.atomic():
            # Mark all existing as not latest
            cls.objects.filter(month=month).update(is_latest=False)
            
            # Get last version
            last_plan = cls.objects.filter(month=month).order_by('-version').first()
            new_version = (last_plan.version + 1) if last_plan else 1
            
            # Create new plan
            plan = cls.objects.create(
                month=month,
                version=new_version,
                is_latest=True,
                previous_plan=last_plan,
                created_by=user,
                **kwargs
            )
            
            return plan


class MonthlyPlanHistory(models.Model):
    """
    Track all changes to monthly plans
    """
    ACTION_TYPES = [
        ('created', '📝 Created'),
        ('updated', '✏️ Updated'),
        ('approved', '✅ Approved'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    plan = models.ForeignKey(
        MonthlyPurchasePlan, 
        on_delete=models.CASCADE, 
        related_name='history'
    )
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changes = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 Monthly Plan History"
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['plan', '-performed_at']),
        ]
    
    def __str__(self):
        return f"{self.plan.plan_no} - {self.get_action_display()}"
