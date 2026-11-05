"""Models: trade/purchase_orders (split from the former purchasing.py)."""
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from ..inventory.catalog import Product, Warehouse
from .vendors import Vendor

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
    help_text="Sale Order number in the vendor system"
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
    # [agri-edition:grn-fields] batch / expiry noted at receiving, copied to the Purchase on convert
    batch_no = models.CharField(max_length=50, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
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
