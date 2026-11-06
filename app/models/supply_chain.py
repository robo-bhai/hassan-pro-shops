"""Supply Chain models."""
from django.db import models
from datetime import datetime
from datetime import date
from django.contrib.auth.models import User

class SupplierCategory(models.Model):
    """Supplier categories"""
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Supplier Categories"


class Supplier(models.Model):
    """Supplier/ Vendor Management"""
    
    SUPPLIER_TYPES = [
        ('raw_material', '🔧 Raw Material'),
        ('packaging', '📦 Packaging'),
        ('logistics', '🚚 Logistics'),
        ('service', '🛠️ Service'),
        ('other', '📋 Other'),
    ]
    
    supplier_code = models.CharField(max_length=50, unique=True, editable=False)
    name = models.CharField(max_length=200)
    supplier_type = models.CharField(max_length=20, choices=SUPPLIER_TYPES, default='other')
    category = models.ForeignKey(SupplierCategory, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Contact
    contact_person = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    website = models.URLField(blank=True, null=True)
    
    # Performance
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    lead_time = models.IntegerField(help_text="Average lead time in days", default=7)
    payment_terms = models.CharField(max_length=100, default='30 days')
    
    # Metrics
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    price_competitiveness = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_orders = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Suppliers"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.supplier_code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.supplier_code:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = Supplier.objects.filter(supplier_code__startswith=f'SUP-{year}').order_by('-supplier_code').first()
            if last and last.supplier_code:
                try:
                    last_num = int(last.supplier_code.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.supplier_code = f'SUP-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def get_rating_display(self):
        if self.rating >= 4.5:
            return '⭐⭐⭐⭐⭐ Excellent'
        elif self.rating >= 4.0:
            return '⭐⭐⭐⭐ Good'
        elif self.rating >= 3.0:
            return '⭐⭐⭐ Average'
        elif self.rating >= 2.0:
            return '⭐⭐ Poor'
        else:
            return '⭐ Needs Improvement'


class SupplyChainForecast(models.Model):
    """Demand and supply forecasting"""
    
    FORECAST_TYPES = [
        ('demand', '📈 Demand Forecast'),
        ('supply', '📉 Supply Forecast'),
        ('inventory', '📦 Inventory Forecast'),
        ('sales', '🛒 Sales Forecast'),
    ]
    
    METHODOLOGY_CHOICES = [
        ('moving_average', 'Moving Average'),
        ('exponential', 'Exponential Smoothing'),
        ('trend', 'Trend Analysis'),
        ('seasonal', 'Seasonal Adjustment'),
        ('ml', 'Machine Learning'),
    ]
    
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='supply_forecasts')
    forecast_type = models.CharField(max_length=20, choices=FORECAST_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    forecasted_quantity = models.FloatField()
    actual_quantity = models.FloatField(default=0)
    variance = models.FloatField(default=0)
    variance_percent = models.FloatField(default=0)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    methodology = models.CharField(max_length=20, choices=METHODOLOGY_CHOICES, default='moving_average')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Supply Chain Forecasts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.product.name} - {self.get_forecast_type_display()} ({self.period_start} to {self.period_end})"
    
    def calculate_variance(self):
        if self.forecasted_quantity > 0:
            self.variance = self.actual_quantity - self.forecasted_quantity
            self.variance_percent = (self.variance / self.forecasted_quantity) * 100
        return self.variance
    
    def save(self, *args, **kwargs):
        self.calculate_variance()
        super().save(*args, **kwargs)


class DeliverySchedule(models.Model):
    """Delivery scheduling and tracking"""
    
    DELIVERY_TYPES = [
        ('inbound', '📥 Inbound'),
        ('outbound', '📤 Outbound'),
        ('transfer', '🔄 Transfer'),
    ]
    
    DELIVERY_STATUS = [
        ('scheduled', '📅 Scheduled'),
        ('in_transit', '🚚 In Transit'),
        ('delivered', '✅ Delivered'),
        ('delayed', '⏰ Delayed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    schedule_no = models.CharField(max_length=20, unique=True, editable=False)
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_TYPES)
    status = models.CharField(max_length=20, choices=DELIVERY_STATUS, default='scheduled')
    
    # Source/Destination
    from_location = models.CharField(max_length=200)
    to_location = models.CharField(max_length=200)
    from_warehouse = models.ForeignKey('Warehouse', on_delete=models.SET_NULL, null=True, related_name='deliveries_out')
    to_warehouse = models.ForeignKey('Warehouse', on_delete=models.SET_NULL, null=True, related_name='deliveries_in')
    
    # Products
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.FloatField()
    unit = models.CharField(max_length=50, blank=True, null=True)
    
    # Dates
    scheduled_date = models.DateField()
    actual_delivery_date = models.DateField(null=True, blank=True)
    
    # Transport
    vehicle_no = models.CharField(max_length=50, blank=True, null=True)
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    driver_phone = models.CharField(max_length=20, blank=True, null=True)
    transport_company = models.CharField(max_length=100, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Documents
    waybill = models.FileField(upload_to='waybills/', null=True, blank=True)
    receipt = models.FileField(upload_to='receipts/', null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Delivery Schedules"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.schedule_no} - {self.delivery_type} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        if not self.schedule_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = DeliverySchedule.objects.filter(schedule_no__startswith=f'DS-{year}').order_by('-schedule_no').first()
            if last and last.schedule_no:
                try:
                    last_num = int(last.schedule_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.schedule_no = f'DS-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def is_delayed(self):
        if self.status in ['scheduled', 'in_transit'] and self.scheduled_date < date.today():
            return True
        return False


class LogisticsTracking(models.Model):
    """Real-time logistics tracking"""
    
    delivery = models.ForeignKey(DeliverySchedule, on_delete=models.CASCADE, related_name='tracking')
    location = models.CharField(max_length=200)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    status = models.CharField(max_length=100)
    remarks = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Logistics Tracking"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.delivery.schedule_no} - {self.status} at {self.location}"


class SupplyChainAnalytics(models.Model):
    """Supply chain analytics and KPIs"""
    
    report_date = models.DateField(auto_now_add=True)
    
    # KPIs
    total_orders = models.IntegerField(default=0)
    on_time_delivery = models.IntegerField(default=0)
    delayed_orders = models.IntegerField(default=0)
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    avg_lead_time = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_lead_time = models.IntegerField(default=0)
    max_lead_time = models.IntegerField(default=0)
    
    inventory_turnover = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stockout_count = models.IntegerField(default=0)
    overstock_count = models.IntegerField(default=0)
    
    total_inventory_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_demand = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_supply = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Supply Chain Analytics"
        ordering = ['-report_date']
    
    def __str__(self):
        return f"Analytics - {self.report_date}"
    
    def calculate_on_time_rate(self):
        if self.total_orders > 0:
            self.on_time_delivery_rate = (self.on_time_delivery / self.total_orders) * 100
        return self.on_time_delivery_rate
    
    def save(self, *args, **kwargs):
        self.calculate_on_time_rate()
        super().save(*args, **kwargs)
