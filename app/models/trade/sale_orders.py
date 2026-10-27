"""Models: trade/sale_orders (split from the former sales.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from ..inventory.catalog import Product, Warehouse
from .customers import Customer
from .sales import SaleItem

# 
class SaleOrder(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('ready', 'Ready to Ship'),
        ('partially_delivered', 'Partially Delivered'),  # ✅ New
        ('delivered', 'Delivered'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled'),
    ]
    
    order_no = models.CharField(max_length=20, unique=True, verbose_name="Order Number")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(default=now, verbose_name="Order Date")
    delivery_date = models.DateField(null=True, blank=True, verbose_name="Expected Delivery Date")
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    notes = models.TextField(blank=True, null=True, verbose_name="Order Notes")
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    advance_payment = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name="Advance Payment")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    customer_po_number = models.CharField(
    max_length=50,
    blank=True,
    null=True,
    verbose_name="Customer PO Number",
    help_text="Purchase Order number in the customer system"
)
    converted_to_sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_from_order')
    
    # ✅ NEW field: Client IP (to detect duplicates)
    client_ip = models.GenericIPAddressField(
        null=True, 
        blank=True,
        verbose_name="Client IP"
    )
    
    class Meta:
        verbose_name_plural = '5.0 Sale Orders'
        indexes = [
            models.Index(fields=['order_no']),
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'created_at']),   # ✅ NAYA
            models.Index(fields=['client_ip']),                # ✅ NAYA
        ]
    
    def __str__(self):
        return f"Order #{self.order_no} - {self.customer.name}"
    
    def total_amount(self):
        return sum(item.total_amt for item in self.items.all())
    
    def total_after_discount(self):
        return self.total_amount() - self.discount_value
    
    def outstanding_advance(self):
        return self.total_after_discount() - self.advance_payment
    
    def delivered_qty(self, product):
        """Calculate total delivered qty for a product across all challans"""
        from django.db.models import Sum
        total = DeliveryChallanItem.objects.filter(
            challan__order=self,
            product=product
        ).aggregate(total=Sum('qty'))['total']
        return total or 0
    
    def pending_qty(self, product, order_qty):
        """Calculate pending qty"""
        return order_qty - self.delivered_qty(product)
    
    def update_delivery_status(self):
        """Auto-update status based on deliveries"""
        if self.status in ['cancelled', 'invoiced']:
            return
        
        items = self.items.all()
        if not items:
            return
        
        all_delivered = True
        any_delivered = False
        
        for item in items:
            delivered = self.delivered_qty(item.product)
            if delivered > 0:
                any_delivered = True
            if delivered < item.qty:
                all_delivered = False
        
        if all_delivered and any_delivered:
            self.status = 'delivered'
        elif any_delivered and not all_delivered:
            self.status = 'partially_delivered'
        
        self.save(update_fields=['status'])
    
    def save(self, *args, **kwargs):
        if not self.order_no:
            today = datetime.now().strftime('%Y%m%d')
            last_order = SaleOrder.objects.filter(order_no__startswith=f'ORD-{today}').order_by('-order_no').first()
            if last_order:
                last_num = int(last_order.order_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.order_no = f'ORD-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        super().save(*args, **kwargs)


class SaleOrderItem(models.Model):
    order = models.ForeignKey(SaleOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    reserved = models.BooleanField(default=False, help_text="Reserve this stock for the order")
    
    class Meta:
        verbose_name_plural = '5.0.1 Sale Order Items'
        unique_together = ('order', 'product')
    
    def __str__(self):
        return f"{self.qty} x {self.product.name} @ {self.price}"
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        
        self.total_amt = Decimal(self.qty) * self.price
        
        is_new = self.pk is None
        old_reserved = False
        old_qty = 0
        
        if not is_new:
            old_item = SaleOrderItem.objects.get(pk=self.pk)
            old_reserved = old_item.reserved
            old_qty = old_item.qty
        
        super().save(*args, **kwargs)
        
        if self.reserved and self.order.status not in ['cancelled', 'invoiced']:
            try:
                inventory = Inventory.objects.get(
                    product=self.product, 
                    warehouse=self.order.warehouse
                )
                
                if is_new:
                    qty_to_reserve = self.qty
                else:
                    if old_reserved:
                        qty_to_reserve = self.qty - old_qty
                    else:
                        qty_to_reserve = self.qty
                
                if qty_to_reserve > 0:
                    if inventory.available_stock < qty_to_reserve:
                        raise ValidationError(
                            f"Insufficient stock to reserve. Available: {inventory.available_stock}, Required: {qty_to_reserve}"
                        )
                    inventory.reserved_stock += qty_to_reserve
                    inventory.save()
                    
            except Inventory.DoesNotExist:
                raise ValidationError(f"No inventory for {self.product.name} in {self.order.warehouse.name}")
        
        elif not self.reserved and not is_new and old_reserved:
            try:
                inventory = Inventory.objects.get(
                    product=self.product, 
                    warehouse=self.order.warehouse
                )
                inventory.reserved_stock = max(0, inventory.reserved_stock - old_qty)
                inventory.save()
            except Inventory.DoesNotExist:
                pass


# ============================================
# DELIVERY CHALLAN MODEL
# ============================================
class DeliveryChallan(models.Model):
    CHALLAN_REASONS = [
        ('sale', 'Sale'),
        ('transfer', 'Stock Transfer'),
        ('job_work', 'Job Work'),
        ('approval', 'On Approval'),
        ('return', 'Return to Vendor'),
        ('other', 'Other'),
    ]
    
    challan_no = models.CharField(max_length=20, unique=True, verbose_name="Challan Number")
    order = models.ForeignKey(SaleOrder, on_delete=models.CASCADE, related_name='challans', null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name="Customer/Receiver")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    challan_date = models.DateTimeField(default=now, verbose_name="Challan Date")
    reason = models.CharField(max_length=20, choices=CHALLAN_REASONS, default='sale', verbose_name="Reason for Dispatch")
    vehicle_no = models.CharField(max_length=30, blank=True, null=True, verbose_name="Vehicle Number")
    transport_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Transport Company")
    driver_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Driver Name")
    driver_contact = models.CharField(max_length=15, blank=True, null=True, verbose_name="Driver Contact")
    notes = models.TextField(blank=True, null=True, verbose_name="Remarks")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    converted_to_sale = models.BooleanField(default=False, verbose_name="Converted to Invoice")
    
    class Meta:
        verbose_name_plural = '5.2 Delivery Challans'
        indexes = [
            models.Index(fields=['challan_no']),
            models.Index(fields=['customer']),
            models.Index(fields=['order']),
        ]
    
    def __str__(self):
        return f"Challan #{self.challan_no} - {self.customer.name}"
    
    def total_qty(self):
        return sum(item.qty for item in self.items.all())
    
    def total_items(self):
        return self.items.count()
    
    def save(self, *args, **kwargs):
        if not self.challan_no:
            today = datetime.now().strftime('%Y%m%d')
            last_challan = DeliveryChallan.objects.filter(
                challan_no__startswith=f'DC-{today}'
            ).order_by('-challan_no').first()
            if last_challan:
                last_num = int(last_challan.challan_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.challan_no = f'DC-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        super().save(*args, **kwargs)
        
        # ✅ Order status update after save
        if self.order and self.order.status not in ['cancelled', 'invoiced']:
            self.order.update_delivery_status()


class DeliveryChallanItem(models.Model):
    challan = models.ForeignKey(DeliveryChallan, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    order_qty = models.FloatField(default=0, verbose_name="Order Qty")
    qty = models.FloatField(verbose_name="Delivery Qty")
    pending_qty = models.FloatField(default=0, verbose_name="Pending Qty")
    unit = models.CharField(max_length=20, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Price (Optional)")
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    sale_item = models.ForeignKey(SaleItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='challan_items')
    notes = models.CharField(max_length=255, blank=True, null=True, verbose_name="Item Remarks")
    
    class Meta:
        verbose_name_plural = '5.2.1 Delivery Challan Items'
    
    def __str__(self):
        return f"{self.qty}/{self.order_qty} x {self.product.name}"
    
    def save(self, *args, **kwargs):
        if not self.unit and self.product.unit:
            self.unit = self.product.unit.name
        
        self.total_amt = Decimal(self.qty) * self.price
        
        # ✅ Pending qty auto-calculate
        if self.order_qty > 0:
            self.pending_qty = max(0, self.order_qty - self.qty)
        
        super().save(*args, **kwargs)
