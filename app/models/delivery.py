"""Delivery models."""
from django.db import models
from decimal import Decimal

class DeliverySettings(models.Model):
    """Delivery settings — admin configurable"""
    
    # Standard delivery
    standard_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('100.00'),
        verbose_name="Standard Delivery Charge (Rs.)"
    )
    standard_delivery_time = models.CharField(
        max_length=100, 
        default="2-4 working days",
        verbose_name="Standard Delivery Time"
    )
    
    # Express delivery
    express_delivery_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Express Delivery"
    )
    express_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('300.00'),
        verbose_name="Express Delivery Charge (Rs.)"
    )
    express_delivery_time = models.CharField(
        max_length=100, 
        default="Same day (within city)",
        verbose_name="Express Delivery Time"
    )
    
    # Store pickup
    store_pickup_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Store Pickup"
    )
    
    # Free delivery
    free_delivery_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Free Delivery Threshold"
    )
    free_delivery_threshold = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('1000.00'),
        verbose_name="Free Delivery Threshold (Rs.)"
    )
    
    # City-based charges
    city_charges = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="City-wise Delivery Charges",
        help_text='Format: {"karachi": 100, "lahore": 120, "other": 200}'
    )
    
    # Meta
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "🚚 Delivery Settings"
        verbose_name_plural = "🚚 Delivery Settings"
    
    def __str__(self):
        return f"Delivery Settings (Rs. {self.standard_charge})"
    
    def save(self, *args, **kwargs):
        # Only one active
        if self.is_active:
            DeliverySettings.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class DeliveryInfo(models.Model):
    """Delivery type aur rider/pickup info"""
    
    DELIVERY_TYPES = [
        ('local_rider', '🏍️ Local Rider'),
        ('customer_pickup', '🚶 Customer Pickup'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('assigned', '✅ Assigned'),
        ('picked_up', '📦 Picked Up'),
        ('in_transit', '🛵 In Transit'),
        ('delivered', '🎉 Delivered'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Link to order
    order = models.OneToOneField(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='delivery_info',
        null=True, blank=True
    )
    sale_order = models.OneToOneField(
        'SaleOrder',
        on_delete=models.CASCADE,
        related_name='delivery_info',
        null=True, blank=True
    )
    
    # Delivery type
    delivery_type = models.CharField(
        max_length=20,
        choices=DELIVERY_TYPES,
        default='local_rider'
    )
    
    # Rider Info (agar local_rider ho)
    rider_name = models.CharField(max_length=100, blank=True, null=True)
    rider_contact = models.CharField(max_length=20, blank=True, null=True)
    rider_vehicle = models.CharField(max_length=50, blank=True, null=True)
    rider_cnic = models.CharField(max_length=20, blank=True, null=True)
    
    # Pickup Info (agar customer_pickup ho)
    pickup_location = models.TextField(blank=True, null=True)
    pickup_ready_at = models.DateTimeField(null=True, blank=True)
    pickup_notes = models.CharField(max_length=255, blank=True, null=True)
    
    # Delivery proof
    delivery_photo = models.ImageField(
        upload_to='delivery_proof/%Y/%m/',
        null=True, blank=True,
        verbose_name="Delivery Proof Photo"
    )
    delivery_signature = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Receiver Name/Signature"
    )
    delivery_notes = models.TextField(blank=True, null=True)
    
    # Timing
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expected_delivery = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # System
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_deliveries'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "🚚 Delivery Info"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['delivery_type']),
        ]
    
    def __str__(self):
        order_no = ''
        if self.order:
            order_no = self.order.order_number
        elif self.sale_order:
            order_no = self.sale_order.order_no
        return f"Delivery for {order_no} - {self.get_delivery_type_display()}"
    
    @property
    def order_number(self):
        """Get order number regardless of type"""
        if self.order:
            return self.order.order_number
        elif self.sale_order:
            return self.sale_order.order_no
        return "N/A"
    
    @property
    def customer(self):
        """Get customer regardless of type"""
        if self.order:
            return self.order.customer
        elif self.sale_order:
            return self.sale_order.customer
        return None
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'secondary',
            'assigned': 'info',
            'picked_up': 'primary',
            'in_transit': 'warning',
            'delivered': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'


class OrderTracking(models.Model):
    """Order ki har movement ka record (Timeline)"""
    
    STATUS_CHOICES = [
        ('confirmed', '✅ Confirmed'),
        ('processing', '⚙️ Processing'),
        ('packed', '📦 Packed'),
        ('rider_assigned', '🏍️ Rider Assigned'),
        ('ready_for_pickup', '🚶 Ready for Pickup'),
        ('out_for_delivery', '🛵 Out for Delivery'),
        ('delivered', '🎉 Delivered'),
        ('picked_up', '✋ Picked Up by Customer'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Order link
    order = models.ForeignKey(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='tracking_history',
        null=True, blank=True
    )
    sale_order = models.ForeignKey(
        'SaleOrder',
        on_delete=models.CASCADE,
        related_name='tracking_history',
        null=True, blank=True
    )
    
    # Status
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    title = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    # Location & Notes
    location = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Proof
    proof_photo = models.ImageField(
        upload_to='tracking_proof/%Y/%m/',
        null=True, blank=True
    )
    
    # Rider info snapshot (at time of this update)
    rider_name = models.CharField(max_length=100, blank=True, null=True)
    rider_contact = models.CharField(max_length=20, blank=True, null=True)
    
    # GPS (optional)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # WhatsApp status
    whatsapp_sent = models.BooleanField(default=False)
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)
    
    # System
    updated_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='order_tracking_updates'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📍 Order Tracking"
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['order', '-timestamp']),
            models.Index(fields=['sale_order', '-timestamp']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        order_no = ''
        if self.order:
            order_no = self.order.order_number
        elif self.sale_order:
            order_no = self.sale_order.order_no
        return f"{order_no} - {self.get_status_display()}"
    
    @property
    def order_number(self):
        if self.order:
            return self.order.order_number
        elif self.sale_order:
            return self.sale_order.order_no
        return "N/A"
    
    @property
    def icon(self):
        icons = {
            'confirmed': '✅',
            'processing': '⚙️',
            'packed': '📦',
            'rider_assigned': '🏍️',
            'ready_for_pickup': '🚶',
            'out_for_delivery': '🛵',
            'delivered': '🎉',
            'picked_up': '✋',
            'cancelled': '❌',
        }
        return icons.get(self.status, '📌')
    
    @property
    def color(self):
        colors = {
            'confirmed': 'success',
            'processing': 'info',
            'packed': 'primary',
            'rider_assigned': 'info',
            'ready_for_pickup': 'warning',
            'out_for_delivery': 'warning',
            'delivered': 'success',
            'picked_up': 'success',
            'cancelled': 'danger',
        }
        return colors.get(self.status, 'secondary')


class DeliveryFeedback(models.Model):
    """Customer ka delivery feedback"""
    
    RATING_CHOICES = [(i, f'{i} ⭐') for i in range(1, 6)]
    
    order = models.OneToOneField(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='delivery_feedback',
        null=True, blank=True
    )
    
    rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField(blank=True, null=True)
    
    # Separate ratings
    rider_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    speed_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    packaging_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    
    would_recommend = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "⭐ Delivery Feedback"
    
    def __str__(self):
        return f"{self.order.order_number if self.order else 'N/A'} - {self.rating}⭐"
