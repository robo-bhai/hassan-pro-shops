"""Production models."""
from django.db import models
from django.db import transaction
from decimal import Decimal
from django.utils.timezone import now
from django.contrib.auth.models import User

class ProductionOrder(models.Model):
    """Production Order / Manufacturing Order"""
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('planned', '📅 Planned'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    order_no = models.CharField(max_length=20, unique=True, editable=False)
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='production_orders')
    quantity = models.FloatField(verbose_name="Production Quantity")
    produced_quantity = models.FloatField(default=0, verbose_name="Produced Quantity")
    
    # Dates
    planned_start_date = models.DateField()
    planned_end_date = models.DateField()
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Costing
    total_material_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_labor_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_overhead_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_production_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Warehouse
    source_warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='production_orders_source')
    target_warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='production_orders_target', null=True, blank=True)
    
    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='production_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Production Orders"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_no']),
            models.Index(fields=['status']),
            models.Index(fields=['planned_start_date']),
        ]
    
    def __str__(self):
        return f"PO-{self.order_no} - {self.product.name} ({self.quantity})"
    
    def remaining_quantity(self):
        return self.quantity - self.produced_quantity
    
    def progress_percent(self):
        if self.quantity > 0:
            return (self.produced_quantity / self.quantity) * 100
        return 0
    
    def calculate_total_cost(self):
        """Calculate total production cost"""
        bom_cost = sum(item.total_cost for item in self.bom_items.all())
        labor_cost = sum(op.labor_cost for op in self.operations.all())
        overhead_cost = sum(op.overhead_cost for op in self.operations.all())
        self.total_material_cost = bom_cost
        self.total_labor_cost = labor_cost
        self.total_overhead_cost = overhead_cost
        self.total_production_cost = bom_cost + labor_cost + overhead_cost
        self.save(update_fields=['total_material_cost', 'total_labor_cost', 'total_overhead_cost', 'total_production_cost'])
        return self.total_production_cost
    
    def save(self, *args, **kwargs):
        if not self.order_no:
            last_order = ProductionOrder.objects.order_by('-id').first()
            if last_order and last_order.order_no:
                try:
                    last_num = int(last_order.order_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.order_no = f'PO-{new_num}'
        super().save(*args, **kwargs)


class ProductionBOM(models.Model):
    """Bill of Materials - Raw materials required for production"""
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='bom_items')
    raw_material = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='bom_usage')
    quantity_required = models.FloatField(help_text="Quantity needed for one finished unit")
    quantity_consumed = models.FloatField(default=0, help_text="Actual quantity consumed")
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    waste_percentage = models.FloatField(default=0, help_text="Standard waste %")
    
    class Meta:
        verbose_name_plural = "Production BOM"
        unique_together = ['production_order', 'raw_material']
    
    def __str__(self):
        return f"{self.raw_material.name} - {self.quantity_required} units"
    
    def calculate_required_for_quantity(self, qty):
        return self.quantity_required * qty
    
    def save(self, *args, **kwargs):
        self.total_cost = Decimal(str(self.quantity_consumed)) * self.cost_per_unit
        super().save(*args, **kwargs)
        self.production_order.calculate_total_cost()


class ProductionOperation(models.Model):
    """Production operations/steps"""
    OPERATION_TYPES = [
        ('cutting', '✂️ Cutting'),
        ('stitching', '🪡 Stitching'),
        ('assembly', '🔧 Assembly'),
        ('packing', '📦 Packing'),
        ('quality', '✅ Quality Check'),
        ('painting', '🎨 Painting'),
        ('finishing', '✨ Finishing'),
        ('other', '📋 Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
    ]
    
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='operations')
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES)
    operation_name = models.CharField(max_length=100)
    sequence = models.PositiveIntegerField()
    assigned_to = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_operations')
    
    # Time tracking
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['sequence']
        verbose_name_plural = "Production Operations"
    
    def __str__(self):
        return f"{self.sequence}. {self.operation_name}"
    
    def mark_start(self):
        self.status = 'in_progress'
        self.started_at = now()
        self.save()
    
    def mark_complete(self):
        self.status = 'completed'
        self.completed_at = now()
        self.save()
        self.production_order.calculate_total_cost()


class ProductionStockUpdate(models.Model):
    """Track stock updates from production"""
    UPDATE_TYPES = [
        ('consume', 'Raw Material Consumed'),
        ('produce', 'Finished Goods Produced'),
        ('waste', 'Waste/Scrap'),
    ]
    
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='stock_updates')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    update_type = models.CharField(max_length=10, choices=UPDATE_TYPES)
    quantity = models.FloatField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    batch = models.ForeignKey('StockBatch', on_delete=models.SET_NULL, null=True, blank=True)
    warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Production Stock Updates"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_update_type_display()} - {self.product.name} ({self.quantity})"


class TransferOrder(models.Model):
    """Transfer finished goods to warehouse"""
    TRANSFER_TYPES = [
        ('production', '🏭 Production Transfer'),
        ('warehouse', '🏪 Warehouse to Warehouse'),
        ('customer', '🚚 Customer Dispatch'),
        ('return', '🔄 Return Transfer'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('in_transit', '🚚 In Transit'),
        ('delivered', '📦 Delivered'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    transfer_no = models.CharField(max_length=20, unique=True, editable=False)
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPES)
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, null=True, blank=True, related_name='transfers')
    
    # Source & Destination - ✅ FIXED: unique related_name added
    from_warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, 
                                        related_name='production_transfers_out')  # ✅ Changed
    to_warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='production_transfers_in')  # ✅ Changed
    
    # Product details
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.FloatField()
    batch_number = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Tracking
    transfer_date = models.DateTimeField(default=now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    delivered_date = models.DateTimeField(null=True, blank=True)
    vehicle_no = models.CharField(max_length=30, blank=True, null=True)
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    driver_contact = models.CharField(max_length=15, blank=True, null=True)
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_transfers')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_transfers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Transfer Orders"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transfer_no']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"TO-{self.transfer_no} - {self.product.name} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        if not self.transfer_no:
            last_transfer = TransferOrder.objects.order_by('-id').first()
            if last_transfer and last_transfer.transfer_no:
                try:
                    last_num = int(last_transfer.transfer_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.transfer_no = f'TO-{new_num}'
        super().save(*args, **kwargs)
    
    @transaction.atomic
    def approve(self, user):
        """Approve transfer order"""
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    @transaction.atomic
    def deliver(self):
        """Mark as delivered and update stock"""
        self.status = 'delivered'
        self.delivered_date = now()
        self.save()
        
        # Update stock in destination warehouse
        Inventory.update_stock(self.product, self.quantity, self.to_warehouse)
        
        # Create or update batch
        batch = StockBatch.objects.filter(
            product=self.product,
            warehouse=self.to_warehouse,
            price=self.price
        ).first()
        
        if batch:
            batch.qty += self.quantity
            batch.remaining_qty += self.quantity
            batch.save()
        else:
            StockBatch.objects.create(
                product=self.product,
                warehouse=self.to_warehouse,
                qty=self.quantity,
                remaining_qty=self.quantity,
                price=self.price
            )


class ProductionReport(models.Model):
    """Production reports and analytics"""
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='reports')
    report_date = models.DateField(auto_now_add=True)
    
    # Production metrics
    planned_quantity = models.FloatField()
    produced_quantity = models.FloatField()
    rejected_quantity = models.FloatField(default=0)
    waste_percentage = models.FloatField(default=0)
    
    # Efficiency
    planned_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    efficiency_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Cost
    planned_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cost_variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    class Meta:
        verbose_name_plural = "Production Reports"
        ordering = ['-report_date']
    
    def __str__(self):
        return f"Report - {self.production_order.order_no}"
    
    def calculate_efficiency(self):
        if self.planned_hours > 0:
            self.efficiency_percent = (self.planned_hours / self.actual_hours) * 100
        else:
            self.efficiency_percent = 0
        return self.efficiency_percent
    
    def calculate_cost_variance(self):
        self.cost_variance = self.actual_cost - self.planned_cost
        return self.cost_variance
