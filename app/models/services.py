"""Services models."""
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User

class ServiceCategory(models.Model):
    """Service categories (e.g., Repair, Maintenance, Consultancy)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, blank=True, null=True, help_text="FontAwesome icon class")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Service Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Service(models.Model):
    """Service product/service offering"""
    
    SERVICE_TYPES = [
        ('repair', '🔧 Repair Service'),
        ('maintenance', '🛠️ Maintenance'),
        ('consultancy', '💼 Consultancy'),
        ('labor', '👷 Labor Service'),
        ('installation', '📦 Installation'),
        ('delivery', '🚚 Delivery'),
        ('training', '📚 Training'),
        ('other', '📋 Other'),
    ]
    
    PRICING_TYPES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly Rate'),
        ('project', 'Project Based'),
        ('variable', 'Variable'),
    ]
    
    # Basic Info
    service_code = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES, default='other')
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='services')
    description = models.TextField(blank=True, null=True)
    
    # Pricing
    pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES, default='fixed')
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Fixed price or hourly rate")
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Estimated hours for service")
    min_charge = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Minimum charge")
    max_charge = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Maximum charge")
    
    # Product mapping (for inventory items used in service)
    required_products = models.ManyToManyField('Product', blank=True, related_name='services', through='ServiceProductRequirement')
    
    # Staff/Technician
    requires_technician = models.BooleanField(default=True)
    default_technician = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='default_services')
    
    # Settings
    is_active = models.BooleanField(default=True)
    needs_appointment = models.BooleanField(default=True)
    warranty_months = models.PositiveIntegerField(default=0, help_text="Warranty period in months")
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_services')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Services"
        ordering = ['name']
        indexes = [
            models.Index(fields=['service_code']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.service_code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.service_code:
            last_service = Service.objects.order_by('-id').first()
            if last_service and last_service.service_code:
                try:
                    last_num = int(last_service.service_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.service_code = f'SVC-{new_num}'
        super().save(*args, **kwargs)
    
    def get_price_for_customer(self, customer=None):
        """Get price with customer-specific adjustments"""
        base_price = self.price
        
        if customer:
            # Apply customer profit margin if configured
            if hasattr(customer, 'profit_margin') and customer.profit_margin > 0:
                base_price = base_price * (1 + customer.profit_margin / 100)
        
        return base_price


class ServiceProductRequirement(models.Model):
    """Products required for a service (with quantity)"""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='product_requirements')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.FloatField(default=1)
    is_optional = models.BooleanField(default=False, help_text="Optional product, not always required")
    
    class Meta:
        verbose_name_plural = "Service Product Requirements"
        unique_together = ['service', 'product']
    
    def __str__(self):
        return f"{self.service.name} -> {self.product.name} x {self.quantity}"


class ServiceRequest(models.Model):
    """Customer service request/order"""
    
    PRIORITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🔴 High'),
        ('urgent', '🔥 Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('confirmed', '✅ Confirmed'),
        ('assigned', '👤 Assigned'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Basic Info
    request_no = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='service_requests')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='requests')
    
    # Details
    description = models.TextField(help_text="Detailed description of service required")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Scheduling
    requested_date = models.DateField(help_text="Customer requested date")
    scheduled_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    appointment_time = models.TimeField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Location
    service_address = models.TextField(blank=True, null=True, help_text="If different from customer address")
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Pricing
    quoted_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Technician Assignment
    technician = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_services')
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    # Products Used
    products_used = models.ManyToManyField('Product', blank=True, through='ServiceProductUsed', related_name='services_used')
    
    # Follow-up
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)
    
    # Invoice
    invoice = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='service_requests')
    
    # Feedback
    feedback_rating = models.PositiveIntegerField(default=0, choices=[(i, f"{i}★") for i in range(1, 6)])
    feedback_comment = models.TextField(blank=True, null=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_service_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Service Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_no']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['status', 'scheduled_date']),
        ]
    
    def __str__(self):
        return f"{self.request_no} - {self.customer.name} - {self.service.name}"
    
    def save(self, *args, **kwargs):
        if not self.request_no:
            last_request = ServiceRequest.objects.order_by('-id').first()
            if last_request and last_request.request_no:
                try:
                    last_num = int(last_request.request_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.request_no = f'SR-{new_num}'
        
        # Auto-calculate quoted price if not set
        if self.quoted_price == 0 and self.service:
            self.quoted_price = self.service.get_price_for_customer(self.customer)
        
        # Auto-set estimated hours from service
        if self.estimated_hours == 0 and self.service:
            self.estimated_hours = self.service.estimated_hours
        
        super().save(*args, **kwargs)
    
    def total_amount(self):
        """Calculate total amount with discount"""
        return self.actual_price - self.discount if self.actual_price > 0 else self.quoted_price - self.discount
    
    def is_overdue(self):
        """Check if service request is overdue"""
        from django.utils.timezone import now
        if self.status not in ['completed', 'cancelled']:
            if self.scheduled_date and self.scheduled_date < now().date():
                return True
        return False
    
    def days_overdue(self):
        """Get days overdue"""
        from django.utils.timezone import now
        if self.is_overdue() and self.scheduled_date:
            return (now().date() - self.scheduled_date).days
        return 0
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        colors = {
            'pending': 'secondary',
            'confirmed': 'primary',
            'assigned': 'info',
            'in_progress': 'warning',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def priority_badge(self):
        """HTML badge for priority"""
        colors = {
            'low': 'secondary',
            'medium': 'primary',
            'high': 'warning',
            'urgent': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.priority, "secondary")}">{self.get_priority_display()}</span>'


class ServiceProductUsed(models.Model):
    """Products used during service execution"""
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='used_products')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.FloatField()
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    batch = models.ForeignKey('StockBatch', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Service Products Used"
    
    def __str__(self):
        return f"{self.service_request.request_no} - {self.product.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.total = Decimal(str(self.quantity)) * self.price
        super().save(*args, **kwargs)


class ServiceAppointment(models.Model):
    """Service appointment/schedule"""
    
    STATUS_CHOICES = [
        ('scheduled', '📅 Scheduled'),
        ('arrived', '📍 Arrived'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
        ('cancelled', '❌ Cancelled'),
        ('no_show', '🚫 No Show'),
    ]
    
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='appointments')
    technician = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='service_appointments')
    appointment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    duration_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Service Appointments"
        ordering = ['appointment_date', 'start_time']
    
    def __str__(self):
        return f"{self.service_request.request_no} - {self.technician.name} ({self.appointment_date})"
    
    def is_conflicting(self, other_appointment):
        """Check if this appointment conflicts with another"""
        if self.appointment_date != other_appointment.appointment_date:
            return False
        if self.status in ['cancelled', 'no_show'] or other_appointment.status in ['cancelled', 'no_show']:
            return False
        # Check time overlap
        start1 = f"{self.appointment_date} {self.start_time}"
        end1 = f"{self.appointment_date} {self.end_time or self.start_time}"
        start2 = f"{other_appointment.appointment_date} {other_appointment.start_time}"
        end2 = f"{other_appointment.appointment_date} {other_appointment.end_time or other_appointment.start_time}"
        return not (end1 <= start2 or end2 <= start1)


class ServiceTechnicianAssignment(models.Model):
    """Track technician assignments and availability"""
    technician = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='service_assignments')
    date = models.DateField()
    max_services = models.PositiveIntegerField(default=5)
    current_services = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Technician Assignments"
        unique_together = ['technician', 'date']
    
    def __str__(self):
        return f"{self.technician.name} - {self.date} ({self.current_services}/{self.max_services})"
    
    def is_full(self):
        return self.current_services >= self.max_services
    
    def can_assign(self):
        return self.is_available and not self.is_full()


class ServiceFeedback(models.Model):
    """Customer feedback for completed services"""
    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='feedback')
    rating = models.PositiveIntegerField(choices=[(i, f"{i}★") for i in range(1, 6)])
    comment = models.TextField()
    technician_rating = models.PositiveIntegerField(default=0, choices=[(i, f"{i}★") for i in range(1, 6)])
    timeliness_rating = models.PositiveIntegerField(default=0, choices=[(i, f"{i}★") for i in range(1, 6)])
    quality_rating = models.PositiveIntegerField(default=0, choices=[(i, f"{i}★") for i in range(1, 6)])
    would_recommend = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Service Feedback"
    
    def __str__(self):
        return f"{self.service_request.request_no} - {self.rating}★"
    
    def average_rating(self):
        """Calculate average rating"""
        total = self.rating + self.technician_rating + self.timeliness_rating + self.quality_rating
        return round(total / 4, 1)


class ServiceInventoryCategory(models.Model):
    """Categories for service inventory items"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Service Inventory Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class ServiceInventory(models.Model):
    """Service parts and materials inventory"""
    
    INVENTORY_TYPES = [
        ('part', '🔧 Spare Part'),
        ('consumable', '🛢️ Consumable'),
        ('tool', '🧰 Tool'),
        ('accessory', '📱 Accessory'),
        ('chemical', '🧪 Chemical'),
        ('packaging', '📦 Packaging'),
        ('other', '📦 Other'),
    ]
    
    # Basic Information
    item_code = models.CharField(max_length=50, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    item_type = models.CharField(max_length=20, choices=INVENTORY_TYPES, default='part')
    category = models.ForeignKey(ServiceInventoryCategory, on_delete=models.SET_NULL, 
                                 null=True, blank=True, related_name='items')
    
    # Product Reference (if same as a product)
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='service_inventory')
    
    # Stock Management
    current_stock = models.FloatField(default=0)
    min_stock = models.FloatField(default=5)
    max_stock = models.FloatField(default=100)
    reorder_level = models.FloatField(default=10)
    reorder_quantity = models.FloatField(default=20)
    
    # Costing
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    markup_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20, 
                                         help_text="Default markup % for selling")
    
    # Unit
    unit = models.ForeignKey('Unit', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Supplier
    preferred_supplier = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Warehouse
    warehouse = models.ForeignKey('Warehouse', on_delete=models.SET_NULL, null=True, blank=True)
    shelf_location = models.CharField(max_length=50, blank=True, null=True, help_text="Shelf/Rack location")
    
    # Barcode
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_consumable = models.BooleanField(default=False, help_text="Item is consumed during service")
    is_serialized = models.BooleanField(default=False, help_text="Items have serial numbers")
    
    # Tracking
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='updated_service_inventory')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, 
                                   related_name='created_service_inventory')
    
    class Meta:
        verbose_name_plural = "Service Inventory"
        ordering = ['name']
        indexes = [
            models.Index(fields=['item_code']),
            models.Index(fields=['name']),
            models.Index(fields=['item_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        unit_name = self.unit.name if self.unit else 'units'
        return f"{self.item_code} - {self.name} ({self.current_stock} {unit_name})"
    
    def save(self, *args, **kwargs):
        if not self.item_code:
            last_item = ServiceInventory.objects.order_by('-id').first()
            if last_item and last_item.item_code:
                try:
                    last_num = int(last_item.item_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.item_code = f'SINV-{new_num}'
        super().save(*args, **kwargs)
    
    def is_low_stock(self):
        """Check if stock is below reorder level"""
        return self.current_stock <= self.reorder_level
    
    def is_critical_stock(self):
        """Check if stock is critically low"""
        return self.current_stock <= self.min_stock
    
    def stock_value(self):
        """Total value of current stock"""
        return Decimal(str(self.current_stock)) * self.unit_cost
    
    def can_fulfill(self, quantity):
        """Check if enough stock is available"""
        return self.current_stock >= quantity
    
    def get_selling_price(self, quantity=1):
        """Get selling price with markup"""
        if self.selling_price > 0:
            return self.selling_price
        return self.unit_cost * (1 + self.markup_percent / 100)
    
    def reduce_stock(self, quantity, user=None, reason=""):
        """Reduce stock (consume)"""
        if not self.can_fulfill(quantity):
            raise ValidationError(
                f"Insufficient stock! Available: {self.current_stock}, Required: {quantity}"
            )
        
        self.current_stock -= quantity
        self.updated_by = user
        self.save()
        
        # Create transaction record
        ServiceInventoryTransaction.objects.create(
            inventory_item=self,
            transaction_type='consumed',
            quantity=quantity,
            balance_after=self.current_stock,
            notes=reason,
            created_by=user
        )
        
        return self.current_stock
    
    def increase_stock(self, quantity, user=None, reason=""):
        """Increase stock (receive/purchase)"""
        self.current_stock += quantity
        self.updated_by = user
        self.save()
        
        # Create transaction record
        ServiceInventoryTransaction.objects.create(
            inventory_item=self,
            transaction_type='received',
            quantity=quantity,
            balance_after=self.current_stock,
            notes=reason,
            created_by=user
        )
        
        return self.current_stock


class ServiceInventoryTransaction(models.Model):
    """Track inventory movements"""
    
    TRANSACTION_TYPES = [
        ('received', '📥 Received'),
        ('consumed', '📤 Consumed'),
        ('returned', '🔄 Returned'),
        ('adjusted', '📝 Adjusted'),
        ('transferred', '🚚 Transferred'),
        ('wasted', '🗑️ Wasted'),
        ('opening', '🏁 Opening Balance'),
        ('sold', '💰 Sold'),
    ]
    
    inventory_item = models.ForeignKey(ServiceInventory, on_delete=models.CASCADE, 
                                       related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.FloatField()
    balance_after = models.FloatField()
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    # Related models
    service_request = models.ForeignKey('ServiceRequest', on_delete=models.SET_NULL, 
                                        null=True, blank=True, related_name='inventory_transactions')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, 
                                 null=True, blank=True)
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, 
                            null=True, blank=True)
    part_usage = models.ForeignKey('ServicePartUsage', on_delete=models.SET_NULL,
                                   null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Inventory Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['inventory_item']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.inventory_item.name} - {self.get_transaction_type_display()} ({self.quantity})"


class ServicePartUsage(models.Model):
    """Track parts used in specific service requests"""
    
    service_request = models.ForeignKey('ServiceRequest', on_delete=models.CASCADE, 
                                        related_name='parts_used')
    inventory_item = models.ForeignKey(ServiceInventory, on_delete=models.CASCADE,
                                       related_name='usage_records')
    quantity = models.FloatField()
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    charged_to_customer = models.BooleanField(default=True)
    markup_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_charged = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    notes = models.TextField(blank=True, null=True)
    used_by = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Service Part Usage"
        ordering = ['-used_at']
    
    def __str__(self):
        return f"{self.service_request.request_no} - {self.inventory_item.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        """Calculate totals and update inventory"""
        self.total_cost = Decimal(str(self.quantity)) * self.unit_cost
        
        # Calculate selling price with markup
        if self.markup_percent > 0:
            self.selling_price = self.unit_cost * (1 + self.markup_percent / 100)
        else:
            self.selling_price = self.inventory_item.get_selling_price()
        
        self.total_charged = Decimal(str(self.quantity)) * self.selling_price
        
        # Reduce inventory (only if new record)
        if self.pk is None:
            try:
                from django.contrib.auth.models import User
                user = None
                if self.used_by:
                    user = User.objects.filter(username=self.used_by.name).first()
                self.inventory_item.reduce_stock(
                    quantity=self.quantity,
                    user=user,
                    reason=f"Used in service request {self.service_request.request_no}"
                )
            except ValidationError as e:
                raise ValidationError(f"Insufficient stock for {self.inventory_item.name}: {str(e)}")
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Restore stock when part usage is deleted"""
        self.inventory_item.increase_stock(
            quantity=self.quantity,
            reason=f"Removed from service request {self.service_request.request_no}"
        )
        super().delete(*args, **kwargs)


class ServiceInventoryPurchaseOrder(models.Model):
    """Purchase orders specifically for service inventory"""
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('ordered', '📦 Ordered'),
        ('received', '📥 Received'),
        ('partial', '📥 Partial Received'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    po_no = models.CharField(max_length=20, unique=True, editable=False)
    supplier = models.ForeignKey('Vendor', on_delete=models.CASCADE)
    order_date = models.DateField(auto_now_add=True)
    expected_delivery = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Service Inventory POs"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.po_no} - {self.supplier.name} (Rs. {self.net_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.po_no:
            last_po = ServiceInventoryPurchaseOrder.objects.order_by('-id').first()
            if last_po and last_po.po_no:
                try:
                    last_num = int(last_po.po_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.po_no = f'SIPO-{new_num}'
        
        # Calculate totals
        total = self.po_details.aggregate(total=Sum('total_price'))['total'] or 0
        self.total_amount = total
        self.net_amount = total - self.discount
        super().save(*args, **kwargs)
    
    def mark_received(self):
        """Mark PO as received and update stock"""
        for detail in self.po_details.all():
            if detail.received_quantity < detail.quantity:
                # Receive remaining quantity
                remaining = detail.quantity - detail.received_quantity
                detail.inventory_item.increase_stock(
                    quantity=remaining,
                    user=self.created_by,
                    reason=f"Received via PO {self.po_no}"
                )
                detail.received_quantity = detail.quantity
                detail.save()
        
        self.status = 'received'
        self.received_date = date.today()
        self.save()


class ServiceInventoryPODetail(models.Model):
    """Items in service inventory purchase order"""
    
    po = models.ForeignKey(ServiceInventoryPurchaseOrder, on_delete=models.CASCADE, 
                           related_name='po_details')
    inventory_item = models.ForeignKey(ServiceInventory, on_delete=models.CASCADE)
    quantity = models.FloatField()
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    received_quantity = models.FloatField(default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "PO Details"
        unique_together = ['po', 'inventory_item']
    
    def __str__(self):
        return f"{self.inventory_item.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.total_price = Decimal(str(self.quantity)) * self.unit_price
        super().save(*args, **kwargs)


class ServiceInventoryStockAdjustment(models.Model):
    """Manual stock adjustments for service inventory"""
    
    ADJUSTMENT_TYPES = [
        ('increase', '📈 Increase Stock'),
        ('decrease', '📉 Decrease Stock'),
    ]
    
    adjustment_no = models.CharField(max_length=20, unique=True, editable=False)
    inventory_item = models.ForeignKey(ServiceInventory, on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=10, choices=ADJUSTMENT_TYPES)
    quantity = models.FloatField()
    reason = models.TextField()
    previous_stock = models.FloatField()
    new_stock = models.FloatField()
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Stock Adjustments"
        ordering = ['-performed_at']
    
    def __str__(self):
        return f"{self.adjustment_no} - {self.inventory_item.name} ({self.get_adjustment_type_display()})"
    
    def save(self, *args, **kwargs):
        if not self.adjustment_no:
            last_adj = ServiceInventoryStockAdjustment.objects.order_by('-id').first()
            if last_adj and last_adj.adjustment_no:
                try:
                    last_num = int(last_adj.adjustment_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.adjustment_no = f'SADJ-{new_num}'
        
        self.previous_stock = self.inventory_item.current_stock
        
        if self.adjustment_type == 'increase':
            self.new_stock = self.previous_stock + self.quantity
        else:
            self.new_stock = self.previous_stock - self.quantity
        
        super().save(*args, **kwargs)
