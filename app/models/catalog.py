"""Catalog models."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Sum
from django.db.models import F
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
import os
import requests
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
from .constants import REMOVE_BG_API_KEY

# Brand model to store brand details
class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = '1.1 Product Brands'
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


# Category model to store category details
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = '1.2 Product Category'
        indexes = [
            models.Index(fields=['name']),
        ]
        

    def __str__(self):
        return self.name


class Types(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = '1.3 Product Type'

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = '1.4 Product Location'

    def __str__(self):
        return self.name


class Unit(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = description = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name_plural = '1.5 Product Unit'
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    serial_no = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name=_("Serial Number"))
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name=_("Barcode"))
    use_custom_barcode = models.BooleanField(default=False, verbose_name=_("Use Custom/Supplier Barcode"), help_text="Check this to manually enter supplier barcode instead of auto-generating")
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(
        upload_to='products/',
        null=True,
        blank=True,
        verbose_name="Product Image",
        help_text="Product ki tasveer"
    )
    used = models.TextField(null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    types = models.ForeignKey(Types, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.0'), editable=False)
    low_stock_threshold = models.FloatField(default=10.0, help_text="Set minimum stock level for alerts.")
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        verbose_name="Discount %",
        help_text="Discount percentage (0-100). 0 means no discount."
    )
    original_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        verbose_name="Original Price",
        help_text="Original price before discount"
    )
    
    # ✅ YEH FIELD ADD KARO - Product Active/Inactive Status
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"), help_text="Uncheck to deactivate product")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = '1. Product Name'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['barcode']),
            models.Index(fields=['is_active']),  # ✅ Index for faster filtering
        ]

    def __str__(self):
        serial = self.serial_no if self.serial_no else "N/A"
        status = "✓" if self.is_active else "✗"
        return f"{status} {self.name} (Barcode: {self.barcode or 'N/A'})"
    
    def remove_background_via_api(self, image_bytes):
        """Public API se background remove karne ka method"""
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': image_bytes},
            data={'size': 'auto'},
            headers={'X-Api-Key': REMOVE_BG_API_KEY},
        )
        if response.status_code == requests.codes.ok:
            return response.content
        return None

    def save(self, *args, **kwargs):
        # ========================================== #
        # ✅ DISCOUNT PRICE AUTO-CALCULATE            #
        # ========================================== #
        if self.discount_percentage and self.discount_percentage > 0:
            # Agar original_price set nahi hai to current price ko original maan lo
            if not self.original_price or self.original_price <= 0:
                self.original_price = self.price if self.price else Decimal('0.00')
            
            # ✅ Discount ke baad wali price calculate karo
            if self.original_price and self.original_price > 0:
                discount_amount = self.original_price * (self.discount_percentage / Decimal('100'))
                self.price = self.original_price - discount_amount
        else:
            # Agar discount nahi hai to original_price ko reset karo
            self.discount_percentage = Decimal('0.00')
            if self.original_price and self.original_price > 0:
                self.price = self.original_price
        
        # ✅ Agar use_custom_barcode True hai ya barcode already set hai to auto-generate NA karein
        if not self.use_custom_barcode and not self.barcode:
            self.barcode = self.generate_barcode()
            
        # ✅ API via Background Removal & Image Compression Logic
        if self.image and not getattr(self, '_image_processed', False):
            try:
                # Original image content Read karein
                self.image.open()
                image_bytes = self.image.read()

                # 1. API Call karke BG Remove karein
                api_result = self.remove_background_via_api(image_bytes)
                
                if api_result:
                    img = Image.open(BytesIO(api_result))
                else:
                    # Agar API fail/limit reach ho to original image processing par fall back karein
                    img = Image.open(BytesIO(image_bytes))

                # 2. Transparent RGBA format conversion
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                # 3. Resize (Max 800x800 resolution for fast loading)
                max_size = (800, 800)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # 4. Compress & Save into WebP format (Ultra lightweight)
                buffer = BytesIO()
                img.save(buffer, format='WEBP', optimize=True, quality=80)
                buffer.seek(0)

                # 5. File extension .webp par update karein
                base_name = os.path.splitext(os.path.basename(self.image.name))[0]
                new_filename = f"{base_name}.webp"

                # Infinite loop prevent karne ke liye flag set karein
                self._image_processed = True

                # 6. Processed file attach karein (Cloudinary Storage automatically handles this upload)
                self.image.save(new_filename, ContentFile(buffer.getvalue()), save=False)
            except Exception as e:
                pass

        super().save(*args, **kwargs)
    
    def generate_barcode(self):
        """Generate unique EAN-13 barcode"""
        import random
        prefix = "200"  # Company prefix (change as needed)
        while True:
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(9)])
            barcode = prefix + random_digits
            check_digit = self.calculate_ean13_check_digit(barcode)
            full_barcode = barcode + str(check_digit)
            if not Product.objects.filter(barcode=full_barcode).exists():
                return full_barcode
    
    def calculate_ean13_check_digit(self, barcode_12):
        """Calculate EAN-13 check digit"""
        if len(barcode_12) != 12:
            return 0
        odd_sum = sum(int(barcode_12[i]) for i in range(0, 12, 2))
        even_sum = sum(int(barcode_12[i]) for i in range(1, 12, 2))
        total = odd_sum + (even_sum * 3)
        check_digit = (10 - (total % 10)) % 10
        return check_digit
    
    def activate(self):
        """Activate product"""
        self.is_active = True
        self.save()
    
    def deactivate(self):
        """Deactivate product"""
        self.is_active = False
        self.save()


class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "6. Warehouses"
        indexes = [
            models.Index(fields=['name']),
        ]


class WarehouseTransfer(models.Model):
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transfers_out')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transfers_in')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.FloatField()
    transfer_date = models.DateTimeField(default=now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name_plural = "6.1. Warehouse Transfers"

    def __str__(self):
        return f"Transfer {self.qty} of {self.product.name} from {self.from_warehouse} to {self.to_warehouse}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Transfer quantity must be positive.")
        # Step 1: Fetch batches from the source warehouse using FIFO
        batches = StockBatch.get_batches_for_sale(self.product, self.qty, self.from_warehouse)
        remaining_qty_to_transfer = self.qty

        # Step 2: Process each batch for transfer
        for batch, qty_in_batch in batches:
            if remaining_qty_to_transfer <= 0:
                break
            # Reduce the quantity from the source batch
            batch.remaining_qty -= qty_in_batch
            batch.save()

            # Create or update the batch in the destination warehouse
            target_batch, created = StockBatch.objects.get_or_create(
                product=self.product,
                warehouse=self.to_warehouse,
                price=batch.price,
                purchase_item=batch.purchase_item,
                defaults={'qty': qty_in_batch, 'remaining_qty': qty_in_batch}
            )
            if not created:
                # If batch already exists in the target warehouse, increment its quantities
                target_batch.qty += qty_in_batch
                target_batch.remaining_qty += qty_in_batch
                target_batch.save()
            remaining_qty_to_transfer -= qty_in_batch
        if remaining_qty_to_transfer > 0:
            raise ValidationError(f"Not enough stock in batches for {self.product.name} in {self.from_warehouse.name}.")

        # Step 3: Update inventory (already handled by this method)
        Inventory.transfer_stock(self.product, self.from_warehouse, self.to_warehouse, self.qty)

        # Save the transfer record
        super().save(*args, **kwargs)


class MonthlyClosing(models.Model):
    month = models.DateField(default=datetime.now, unique=True)
    locked = models.BooleanField(default=False)
    previous_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.0'))  # New field

    def total_purchase_balance(self):
        total_purchases = self.purchases.aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0.0')
        total_returns = self.purchases.aggregate(total=Sum('returns__return_items__total_amt'))['total'] or Decimal('0.0')
        return total_purchases - total_returns


    def update_total_purchase_balance(self):
        """Update the total purchase balance field when a purchase is added/modified."""
        self.total_purchase_balance = self.total_purchase_balance()
        self.save(update_fields=['total_purchase_balance'])

    def total_purchase_return(self):
        return self.purchase_returns.aggregate(total=Sum('return_items__total_amt'))['total'] or Decimal('0.0')

    def total_sale_return(self):
        return self.sale_returns.aggregate(total=Sum('return_items__total_amt'))['total'] or Decimal('0.0')


    def total_sale_balance(self):
        total_sales = self.sales.aggregate(total=Sum('saleitem__total_amt') - Sum('saleitem__profit'))['total'] or Decimal('0.0')
        total_returns = self.sales.aggregate(total=Sum('returns__return_items__total_amt'))['total'] or Decimal('0.0')
        return total_sales - total_returns
    
    def update_total_sale_balance(self):
        """Update the total sale balance field when a sale is added/modified."""
        self.total_sale_balance = self.total_sale_balance()
        self.save(update_fields=['total_sale_balance'])

    def total_sale_profit(self):
        return self.sales.aggregate(
        total=Sum(F('saleitem__profit')  - F('discount_value'))
        )['total'] or Decimal('0.0')
    
    def update_total_sale_profit(self):
        """Update the total sale profit field when a sale is added/modified."""
        self.total_sale_profit = self.total_sale_profit()
        self.save(update_fields=['total_sale_profit'])

    def closing_balance(self):
        # Calculate closing balance as purchases minus sales profit
         return self.get_previous_month_closing() + self.total_purchase_balance() - self.total_sale_balance()

    def update_closing_balance(self):
        """Update the closing balance when purchase/sale is added/modified."""
        self.closing_balance = self.closing_balance()
        self.save(update_fields=['closing_balance'])

    def get_previous_month_closing(self):
        """Fetch the previous month's closing balance."""
        previous_month = (self.month.replace(day=1) - timedelta(days=1)).replace(day=1)
        previous_closing = MonthlyClosing.objects.filter(month=previous_month).first()
        return previous_closing.closing_balance() if previous_closing else Decimal('0.0')

    def net_profit_margin(self):
        """Calculate Net Profit Margin: ((Total Sale Profit - Expenses) / Total Sales) * 100"""
        total_sales = self.total_sale_balance()
        # یہاں اگر آپ کے سسٹم میں Operating Expenses ہوں تو انہیں بھی مائنس کریں
        if total_sales > 0:
            return ((self.total_sale_profit() - Decimal('0.0')) / total_sales) * 100
        return Decimal('0.0')

    def return_on_investment(self):
        """Calculate Return on Investment (ROI): Net Profit / Investment"""
        total_profit = self.total_sale_profit()
        total_investment = self.total_purchase_balance()
        if total_investment > 0:
            return (total_profit / total_investment) * 100
        return Decimal('0.0')

    

    def days_inventory_outstanding(self):
        """Calculate DIO: (Average Inventory / COGS) * 30"""
        average_inventory = Inventory.objects.aggregate(avg_stock=Sum('stock') / Inventory.objects.count())['avg_stock'] or Decimal('1.0')
        cogs = self.total_sale_balance()  # COGS = Total Sales Balance
        if cogs > 0:
            return Decimal(average_inventory) / Decimal(cogs) * 30
        return Decimal('0.0')

    

    

    def save(self, *args, **kwargs):
        """Override save to update the previous balance automatically."""
        if not self.pk:  # If creating a new record
            self.previous_balance = self.get_previous_month_closing()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.month.strftime('%B %Y')

    class Meta:
        verbose_name_plural = "9.0 Monthly Closings"
        ordering = ['-month']
        indexes = [
            models.Index(fields=['month']),
        ]
        

    def clean(self):
        """Ensure no duplicate entries for a month and validate locked status."""
        if MonthlyClosing.objects.filter(month__year=self.month.year, month__month=self.month.month).exclude(pk=self.pk).exists():
            raise ValueError(f"Monthly closing for {self.month.strftime('%B %Y')} already exists.")
        if self.locked:
            raise ValidationError(f"The month {self.month.strftime('%B %Y')} is locked and cannot be modified.")


                               # ( Purchase Part )
# GroupSummary Model to Summarize Balances
class GroupSummary(models.Model):
    summary_date = models.DateField(auto_now_add=True)
    total_vendor_outstanding = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_customer_outstanding = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    def calculate_totals(self):
        """Recalculate the total outstanding balances."""
        # Calculate vendor group outstanding balance
        vendor_groups = VendorGroup.objects.all()
        self.total_vendor_outstanding = sum(group.total_outstanding_balance() for group in vendor_groups)

        # Calculate customer group outstanding balance
        customer_groups = CustomerGroup.objects.all()
        self.total_customer_outstanding = sum(group.total_outstanding_balance() for group in customer_groups)

        self.save()

    class Meta:
        verbose_name_plural = "5. Group Summaries"

    def __str__(self):
        return f"Summary on {self.summary_date}"


# StockBatch model for managing FIFO stock batches
# StockBatch model for managing FIFO stock batches
class StockBatch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, db_index=True)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Purchase price
    remaining_qty = models.FloatField()
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    purchase_item = models.ForeignKey(
        'PurchaseItem', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='stock_batches'  # For reverse relation
    )
    
    # ============================================
    # ✅ NEW: Selling Price Field
    # ============================================
    selling_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        verbose_name="Selling Price",
        help_text="Purchase price se kam nahi ho sakti. 0 means auto-calculate"
    )

    class Meta:
        ordering = ['-id']
        verbose_name_plural = '7.1 Batches'
        indexes = [
            models.Index(fields=['product', 'warehouse']),
            models.Index(fields=['remaining_qty']),
            models.Index(fields=['selling_price']),
        ]

    # ============================================
    # ✅ VALIDATION
    # ============================================
    def clean(self):
        """Selling price purchase price se kam nahi ho sakti"""
        if self.selling_price > 0:
            if self.selling_price < self.price:
                raise ValidationError({
                    'selling_price': f'Selling price (Rs. {self.selling_price:,.2f}) purchase price (Rs. {self.price:,.2f}) se kam nahi ho sakti! Minimum Rs. {self.price:,.2f} hona chahiye.'
                })
    
    def save(self, *args, **kwargs):
        """Save se pehle validation run karo"""
        self.clean()
        super().save(*args, **kwargs)

    # ============================================
    # ✅ PROFIT CALCULATIONS
    # ============================================
    def profit_per_unit(self):
        """Profit per unit agar selling price set hai"""
        if self.selling_price > 0:
            return self.selling_price - self.price
        return Decimal('0.00')
    
    def profit_margin_percent(self):
        """Profit margin percentage"""
        if self.selling_price > 0 and self.price > 0:
            return ((self.selling_price - self.price) / self.price) * 100
        return Decimal('0.00')
    
    def total_profit_value(self):
        """Total profit for remaining stock"""
        return self.profit_per_unit() * Decimal(str(self.remaining_qty))
    
    def selling_value(self):
        """Total value at selling price"""
        if self.selling_price > 0:
            return Decimal(str(self.remaining_qty)) * self.selling_price
        return Decimal(str(self.remaining_qty)) * self.price

    # ============================================
    # CLASS METHODS
    # ============================================
    @classmethod
    def add_batch(cls, product, qty, price, purchase_item=None, warehouse=None):
        """Add a new batch to a specific warehouse."""
        if not warehouse:
            raise ValidationError("Warehouse must be specified for adding a batch.")
        batch = cls.objects.create(
            product=product, qty=qty, price=price, remaining_qty=qty,
            purchase_item=purchase_item, warehouse=warehouse
        )
        return batch

    @classmethod
    def get_batches_for_sale(cls, product, qty, warehouse=None):
        """Retrieve batches for sale from a specific warehouse."""
        if not warehouse:
            raise ValidationError("Warehouse must be specified for batch retrieval.")
        batches = []
        remaining_qty = qty
        for batch in cls.objects.filter(product=product, warehouse=warehouse, remaining_qty__gt=0).order_by('id'):
            if remaining_qty <= 0:
                break
            qty_in_batch = min(remaining_qty, batch.remaining_qty)
            batches.append((batch, qty_in_batch))
            remaining_qty -= qty_in_batch
        if remaining_qty > 0:
            raise ValidationError(f"Not enough stock for {product.name} in {warehouse.name}. Required: {qty}, Available: {qty - remaining_qty}")
        return batches

    def __str__(self):
        return f"Batch of {self.product.name} - {self.qty} units at Rs. {self.price} in {self.warehouse.name}"


# Inventory model to track stock levels for each product
class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    stock = models.FloatField(default=0, editable=False)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    reserved_stock = models.FloatField(default=0, editable=False)  # New field for reserved stock

    class Meta:
        verbose_name_plural = '7. Inventory'
        unique_together = ('product', 'warehouse')
        indexes = [
            models.Index(fields=['product', 'warehouse']),  # Composite index
        ]

    @classmethod
    def send_bulk_low_stock_alert(cls):
        """Send a single email with all low-stock products"""
        low_stock_items = cls.objects.filter(stock__lt=F('product__low_stock_threshold'))
        
        if low_stock_items.exists():
            subject = "Low Stock Alert for Multiple Products"
            message = "The following products are running low on stock:\n\n"

            for item in low_stock_items:
                message += f"- {item.product.name}: {item.stock} left (Minimum Qty: {item.product.low_stock_threshold})\n"

            message += "\nPlease take necessary action to restock these items."
            
            send_mail(
                subject, 
                message, 
                getattr(settings, 'ALERT_FROM_EMAIL', 'admin@example.com'),  # ✅ Settings se
            [getattr(settings, 'ALERT_TO_EMAIL', 'admin@example.com')]   # ✅ Settings se
            )

    @classmethod
    def check_low_stock(cls):
        """Fetch all products that are low in stock"""
        return cls.objects.filter(stock__lt=F('product__low_stock_threshold'))

    def is_low_stock(self):
        """Check if stock is below the low stock threshold"""
        return self.stock < self.product.low_stock_threshold

    @classmethod
    def get_stock(cls, product, warehouse=None):
        """Returns the current stock level for a product in a specific warehouse."""
        if warehouse:
            inventory = cls.objects.filter(product=product, warehouse=warehouse).first()
        else:
            inventory = cls.objects.filter(product=product).first()  # Fallback to any warehouse
        return inventory.stock if inventory else 0.0

    @property
    def available_stock(self):
        """Calculates stock available for new sales."""
        return self.stock - self.reserved_stock

    @classmethod
    def update_reserved_stock(cls, product, qty_delta):
        """Updates reserved stock for a product."""
        inventory, _ = cls.objects.get_or_create(product=product)
        inventory.reserved_stock += qty_delta
        if inventory.reserved_stock < 0:
            raise ValidationError(f"Reserved stock cannot be negative for {product.name}.")
        inventory.save()

    @classmethod
    def update_stock(cls, product, qty_delta, warehouse=None):
        """Updates stock for a product in a specific warehouse."""
        if not warehouse:
            raise ValidationError("Warehouse must be specified for stock updates.")
        inventory, _ = cls.objects.get_or_create(product=product, warehouse=warehouse)
        inventory.stock += qty_delta
        if inventory.stock < 0:
            raise ValidationError(f"Stock cannot be negative for {product.name} in {warehouse.name}.")
        inventory.save()

    @classmethod
    def transfer_stock(cls, product, from_warehouse, to_warehouse, qty):
        """Transfer stock between warehouses."""
        if qty <= 0:
            raise ValidationError("Transfer quantity must be positive.")
        from_inventory = cls.objects.get(product=product, warehouse=from_warehouse)
        if from_inventory.stock < qty:
            raise ValidationError(f"Insufficient stock in {from_warehouse.name} for transfer.")
        
        cls.update_stock(product, -qty, from_warehouse)
        cls.update_stock(product, qty, to_warehouse)
        logger.info(f"Transferred {qty} units of {product.name} from {from_warehouse.name} to {to_warehouse.name}")

    @classmethod
    def check_stock_availability(cls, product, required_qty):
        """Checks if sufficient stock is available."""
        inventory = cls.objects.get(product=product)
        if inventory.stock < required_qty:
            raise ValidationError(f"Insufficient stock for {product.name}. Available: {inventory.stock}, Required: {required_qty}")

    def stock_value(self):
        """Calculates the total stock value based on remaining batch quantities."""
        return sum(Decimal(batch.remaining_qty) * batch.price for batch in StockBatch.objects.filter(product=self.product,warehouse=self.warehouse))

    def check_low_stock(self):
        """Checks if stock is below the threshold."""
        if self.stock < self.product.low_stock_threshold:
            return True
        return False

    def __str__(self):
        return f"{self.product.name} - {self.stock} units in {self.warehouse.name}"


class StockAdjustment(models.Model):
    ADJUSTMENT_TYPES = [
        ('increase', 'Increase'),
        ('decrease', 'Decrease'),
    ]

    adjustment_type = models.CharField(max_length=10, choices=ADJUSTMENT_TYPES)
    reason = models.CharField(max_length=255)
    adjustment_date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "8.0 Stock Adjustments"

    def __str__(self):
        return f"{self.get_adjustment_type_display()} - {self.reason} on {self.adjustment_date}"


class StockAdjustmentItem(models.Model):
    adjustment = models.ForeignKey('StockAdjustment', on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), editable=False)

    class Meta:
        verbose_name_plural = "8.1. Stock Adjustment Items"

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Validate quantity
        if self.qty <= 0:
            raise ValidationError("Adjustment quantity must be positive.")

        # Fetch inventory for the product
        inventory, _ = Inventory.objects.get_or_create(product=self.product)
        
        # ✅ Warehouse determine karo
        warehouse = inventory.warehouse if inventory.warehouse else Warehouse.objects.first()

        if self.adjustment.adjustment_type == 'decrease':
            # Validate stock availability
            if inventory.available_stock < self.qty:
                raise ValidationError(
                    f"Insufficient stock for {self.product.name}. Available: {inventory.available_stock}, Required: {self.qty}."
                )
            
            # FIFO Logic for price and stock adjustment
            remaining_qty = self.qty
            total_price = Decimal('0.00')
            batches = StockBatch.objects.filter(product=self.product, remaining_qty__gt=0).order_by('id')
            for batch in batches:
                if remaining_qty <= 0:
                    break
                deduct_qty = min(batch.remaining_qty, remaining_qty)
                total_price += Decimal(deduct_qty) * batch.price
                batch.remaining_qty -= deduct_qty
                batch.save()
                remaining_qty -= deduct_qty

            self.price = total_price / Decimal(self.qty)  # Average price from batches
            Inventory.update_stock(self.product, -self.qty, warehouse=warehouse)

        else:  # Adjustment type: increase
            if self.price <= 0:
                raise ValidationError("Price must be greater than zero for stock increases.")
            Inventory.update_stock(self.product, self.qty, warehouse=warehouse)
            StockBatch.add_batch(self.product, self.qty, self.price, warehouse=warehouse)

        # Calculate total value
        self.total_value = Decimal(self.qty) * self.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Adjustment for {self.product.name} - {self.qty} units at {self.price} each"


# ============================================
# STOCK AUDIT MODEL
# ============================================
class StockAudit(models.Model):
    AUDIT_STATUS = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    audit_no = models.CharField(max_length=20, unique=True, verbose_name="Audit Number")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    audit_date = models.DateTimeField(default=now, verbose_name="Audit Date")
    status = models.CharField(max_length=20, choices=AUDIT_STATUS, default='draft')
    notes = models.TextField(blank=True, null=True, verbose_name="Audit Notes")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_variance_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.0'))
    
    class Meta:
        verbose_name_plural = '7.2 Stock Audits'
        ordering = ['-audit_date']
        indexes = [
            models.Index(fields=['audit_no']),
            models.Index(fields=['warehouse']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Audit #{self.audit_no} - {self.warehouse.name}"
    
    def total_items(self):
        return self.items.count()
    
    def items_with_variance(self):
        return self.items.filter(system_qty__gt=0, physical_qty__isnull=False)
    
    def save(self, *args, **kwargs):
        if not self.audit_no:
            today = datetime.now().strftime('%Y%m%d')
            last_audit = StockAudit.objects.filter(
                audit_no__startswith=f'AUD-{today}'
            ).order_by('-audit_no').first()
            if last_audit:
                last_num = int(last_audit.audit_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.audit_no = f'AUD-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = now()
        
        super().save(*args, **kwargs)


class StockAuditItem(models.Model):
    audit = models.ForeignKey(StockAudit, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    system_qty = models.FloatField(default=0, verbose_name="System Stock")
    physical_qty = models.FloatField(null=True, blank=True, verbose_name="Physical Count")
    variance = models.FloatField(default=0, verbose_name="Variance (+/-)")
    unit = models.CharField(max_length=20, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.0'))
    variance_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.0'))
    notes = models.CharField(max_length=255, blank=True, null=True, verbose_name="Remarks")
    adjusted = models.BooleanField(default=False, verbose_name="Stock Adjusted")
    
    class Meta:
        verbose_name_plural = '7.2.1 Stock Audit Items'
        unique_together = ('audit', 'product')
    
    def __str__(self):
        return f"{self.product.name}: System={self.system_qty}, Physical={self.physical_qty or '?'}, Variance={self.variance}"
    
    def variance_display(self):
        """Display variance quantity with brackets for negative"""
        if self.variance < 0:
            return f"({abs(self.variance):,.0f})"
        elif self.variance > 0:
            return f"{self.variance:+,.0f}"
        return "0"
    
    def variance_value_display(self):
        """Display variance value with brackets for negative"""
        if self.variance_value < 0:
            return f"Rs. ({abs(self.variance_value):,.2f})"
        elif self.variance_value > 0:
            return f"Rs. {self.variance_value:,.2f}"
        return "Rs. 0.00"
    
    def save(self, *args, **kwargs):
        if not self.unit and self.product.unit:
            self.unit = self.product.unit.name
        
        # Get latest price from inventory
        if not self.price or self.price == 0:
            batches = StockBatch.objects.filter(product=self.product, warehouse=self.audit.warehouse)
            if batches.exists():
                self.price = batches.first().price
        
        # Calculate variance
        if self.physical_qty is not None:
            self.variance = self.physical_qty - self.system_qty
            # ✅ FIX: abs() hataya - variance_value ab signed hai
            self.variance_value = Decimal(str(self.variance)) * self.price
        
        super().save(*args, **kwargs)


# ============================================
# PRODUCT ALIAS MODEL (User can create their own)
# ============================================
class ProductAlias(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=100, help_text="Short name or nickname for voice search")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Product Aliases (Voice Search)'
        unique_together = ('product', 'alias')  # Same product ke liye duplicate alias nahi ho sakta
        ordering = ['alias']
    
    def __str__(self):
        return f"{self.alias} → {self.product.name}"
