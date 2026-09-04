from django.db import models, transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime, timedelta,date
from django.utils.timezone import now, localdate
from django.db.models import Sum,F
from django.db.models import Min
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
import hashlib

logger = logging.getLogger(__name__)

class CompanyInfo(models.Model):
    name = models.CharField("Company Name", max_length=255)
    tagline = models.CharField("Tagline", max_length=255, blank=True, null=True)
    address = models.TextField("Address")
    contact_number = models.CharField("Phone", max_length=50)
    email = models.EmailField("Email")
    website = models.URLField("Website", blank=True, null=True)
    logo = models.ImageField("Company Logo", upload_to="company_logo/", blank=True, null=True)
    footer_note = models.CharField("Footer Note (for reports)", max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Company Information"
        verbose_name_plural = "Company Information"


class TrainingTopic(models.Model):
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100, choices=[
        ('product', 'Product Management'),
        ('purchase', 'Purchases'),
        ('sale', 'Sales'),
        ('warehouse', 'Warehouse Management'),
        ('report', 'Reporting'),
        ('backup', 'Backup & Restore'),
        ('other', 'Other')
    ])
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']
        verbose_name_plural = "📘 Training Topics"

    def __str__(self):
        return self.title


class TrainingStep(models.Model):
    topic = models.ForeignKey(TrainingTopic, on_delete=models.CASCADE, related_name="steps")
    step_number = models.PositiveIntegerField()
    description = models.TextField(help_text="Explain what the user should do in this step.")
    screenshot = models.ImageField(upload_to="training_screenshots/", null=True, blank=True)

    class Meta:
        ordering = ['step_number']
        verbose_name_plural = "📗 Training Steps"

    def __str__(self):
        return f"{self.topic.title} - Step {self.step_number}"


class Saving(models.Model):
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateTimeField(default=now)
    category = models.CharField(max_length=100, choices=[
        ('utilities', 'Utilities'),
        ('other', 'Other'),
    ], default='other')

    def __str__(self):
        return f"{self.description} - {self.amount}"

    class Meta:
        verbose_name_plural = "10.2 Savings"

# New model for debts
class Debt(models.Model):
    lender = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    start_date = models.DateField(default=now)
    due_date = models.DateField()

    def __str__(self):
        return f"{self.lender} - {self.amount}"

    class Meta:
        verbose_name_plural = "10.1. Debts"

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

# Updated Product 
class Product(models.Model):
    serial_no = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name=_("Serial Number"))
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name=_("Barcode"))
    use_custom_barcode = models.BooleanField(default=False, verbose_name=_("Use Custom/Supplier Barcode"), help_text="Check this to manually enter supplier barcode instead of auto-generating")
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    used = models.TextField(null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    types = models.ForeignKey(Types, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.0'), editable=False)
    low_stock_threshold = models.FloatField(default=10.0, help_text="Set minimum stock level for alerts.")
    
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
    
    def save(self, *args, **kwargs):
        # ✅ Agar use_custom_barcode True hai ya barcode already set hai to auto-generate NA karein
        if not self.use_custom_barcode and not self.barcode:
            self.barcode = self.generate_barcode()
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

# models.py - Complete Purchase Model

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

                               # ( Sale Part )
# CustomerGroup model to group customers together
class CustomerGroup(models.Model):
    name = models.CharField(max_length=20, unique=True)
    description = models.TextField(null=True, blank=True)

    def total_outstanding_balance(self):
        return sum(customer.adjusted_outstanding_balance() for customer in self.customers.all())

    class Meta:
        verbose_name_plural = '2.1 Customer Groups'

    def __str__(self):
        return self.name

# Customer model to store customer 
class Customer(models.Model):
    customer_code = models.CharField(
        max_length=50, 
        unique=True, 
        null=True,          # ✅ Migration ke liye temporarily null allow
        blank=True,         # ✅ Form mein temporarily blank allow
        verbose_name=_("Customer Code"),
        help_text="Enter unique customer code manually (e.g., CUS-001, WALKIN)"
    )
    name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    ref_name_1 = models.CharField(max_length=100, null=True, blank=True)
    ref_contact_number_1 = models.CharField(max_length=15, null=True, blank=True)
    ref_name_2 = models.CharField(max_length=100, null=True, blank=True)
    ref_contact_number_2 = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    profit_margin = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        help_text="Set profit margin percentage (e.g., 20.00 for 20%)"
    )
    group = models.ForeignKey(
        'CustomerGroup', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customers'
    )

    class Meta:
        verbose_name_plural = '2. Customers'
        indexes = [
            models.Index(fields=['customer_code']),
            models.Index(fields=['name']),
            models.Index(fields=['group']),
        ]

    def __str__(self):
        if self.customer_code:
            return f"{self.customer_code} - {self.name}"
        return self.name

    def adjusted_outstanding_balance(self):
        # Calculate the total outstanding balance from sales
        total_outstanding = self.sale_set.aggregate(
            total=(Sum('saleitem__total_amt') - Sum('discount_value')) - Sum('paid')
        )['total'] or Decimal('0.0')

        # Calculate the total amount returned in sale returns
        total_returned = SaleRetrn.objects.filter(sale__customer=self).aggregate(
            total_returned=Sum('return_items__total_amt')
        )['total_returned'] or Decimal('0.0')

        # Subtract the returned amount from the outstanding balance
        adjusted_balance = total_outstanding - total_returned

        return adjusted_balance

    def save(self, *args, **kwargs):
        # ✅ Agar customer_code empty hai to auto-generate karo
        if not self.customer_code:
            last_customer = Customer.objects.exclude(
                customer_code__isnull=True
            ).exclude(
                customer_code=''
            ).order_by('-id').first()
            
            if last_customer and last_customer.customer_code and last_customer.customer_code.startswith('CUS-'):
                try:
                    last_num = int(last_customer.customer_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            
            self.customer_code = f'CUS-{new_num}'
        
        super().save(*args, **kwargs)

# Sale model for sales transactions
# Sale model for sales transactions
class Sale(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, null=False, blank=False, related_name='sales')
    bill_no = models.CharField(max_length=17) 
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    sale_date = models.DateTimeField(default=now)
    paid = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    previous_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.0'), editable=False)
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    monthly_sale=models.ForeignKey('MonthlyClosing', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales', editable=False)
    is_installment = models.BooleanField(default=False)
    installment_plan = models.ForeignKey('InstallmentPlan', on_delete=models.SET_NULL, null=True, blank=True)
    down_payment_received = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_converted_to_expense = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = '5. Sales'

    def total_amount_without_profit(self):
        total_cost = Decimal('0.0')
        for item in self.saleitem_set.all():
            batches = StockBatch.get_batches_for_sale(item.product, item.qty)
            item_cost = sum(Decimal(qty_in_batch) * batch.price for batch, qty_in_batch in batches)
            total_cost += item_cost
        return total_cost

    def __str__(self):
        return f"Sale Bill No. {self.bill_no} - {self.customer.name} on {self.sale_date}"

    def total_without_discount(self):
        """Calculates the total amount for all items in this sale without discount."""
        return sum(item.total_amt for item in self.saleitem_set.all())

    def total_amount(self):
        """Calculates the total amount for all items in this sale, considering only a fixed discount."""
        total = self.total_without_discount()
        discount = self.discount_value  # Always treat discount as a fixed amount
        return total - discount

    def total_profit(self):
        total_profit = self.saleitem_set.aggregate(total=Sum('profit'))['total']
        total_profit = total_profit if total_profit is not None else Decimal('0.0')
        return total_profit - self.discount_value
    
    def outstanding_balance(self):
        """Calculates the outstanding balance for the sale, considering the discount."""
        return self.total_amount() - self.paid

    @property
    def total_outstanding_with_previous(self):
        """Calculates the total outstanding balance including the previous balance."""
        return self.previous_balance + self.outstanding_balance()

    @transaction.atomic
    def save(self, *args, **kwargs):
        # ✅ AUTO-GENERATE BILL NUMBER
        if not self.bill_no:
            today = now().strftime('%Y%m%d')
            last_sale = Sale.objects.filter(
                bill_no__startswith=f'INV-{today}'
            ).order_by('-bill_no').first()
            
            if last_sale:
                try:
                    last_num = int(last_sale.bill_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.bill_no = f'INV-{today}-{new_num}'

        if not self.pk and not self.created_by:
            self.created_by = kwargs.pop('user', None)

        # ✅ DEFAULT WAREHOUSE
        if not self.warehouse_id:
            default_warehouse = Warehouse.objects.first()
            if not default_warehouse:
                raise ValidationError("کوئی ویئرہاؤس موجود نہیں ہے۔ براہ کرم پہلے ایک ویئرہاؤس بنائیں۔")
            self.warehouse = default_warehouse

        # Check if the month is locked
        sale_month = self.sale_date.replace(day=1)
        monthly_closing, created = MonthlyClosing.objects.get_or_create(month=sale_month)

        if monthly_closing and monthly_closing.locked:
            raise ValidationError(f"Cannot add or modify sales for {sale_month.strftime('%B %Y')} as the month is locked.")

        self.monthly_sale = monthly_closing
        
        # Track if this is a new sale (for WhatsApp and Cash)
        is_new_sale = self.pk is None
        
        # Calculate previous balance for new sales
        if not self.pk:
            previous_sales_balance = self.customer.sale_set.annotate(
                total_amount=Sum('saleitem__total_amt')
            ).aggregate(
                total_balance=Sum(F('saleitem__total_amt')) - Sum(F('discount_value')) - Sum(F('paid'))
            )['total_balance']

            self.previous_balance = previous_sales_balance if previous_sales_balance else Decimal('0.0')
            if self.created_by is None:
                self.created_by = kwargs.get('user')

        super().save(*args, **kwargs)

        # ============================================
        # ✅ CASH BALANCE INCREASE - SALE SE CASH ADD
        # ============================================
        if is_new_sale:
            try:
                from .models import CashBalance
                total_amount = self.total_amount()
                if total_amount > 0:
                    CashBalance.update_balance(
                        amount=total_amount,
                        transaction_type='sale',
                        user=self.created_by,
                        description=f"Sale #{self.bill_no} - {self.customer.name}"
                    )
            except Exception as e:
                # Agar cash update fail ho to sirf log karo, sale rukni nahi chahiye
                import logging
                logging.getLogger(__name__).warning(f"Cash update failed for sale {self.bill_no}: {e}")

        # ============================================
        # 📱 WHATSAPP INVOICE AUTO-SEND
        # ============================================
        if is_new_sale:
            try:
                from .whatsapp_utils import WhatsAppSender
                if self.customer.contact_number:
                    WhatsAppSender.send_invoice(
                        self.customer.contact_number,
                        self.bill_no,
                        self.total_amount()
                    )
            except Exception:
                pass  # Agar WhatsApp fail ho to sale rukni nahi chahiye


class SaleItem(models.Model):
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE)
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional")
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    profit = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.0'), editable=False)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    batches_used = models.ManyToManyField('StockBatch', blank=True, related_name='sale_items')

    class Meta:
        verbose_name_plural = '5.1. Sale Items'

    # ============================================
    # FIFO PRICE
    # ============================================
    def get_fifo_price(self):
        """Fetch FIFO price from stock batches"""
        warehouse = self.sale.warehouse
        if not warehouse:
            raise ValidationError(f"Warehouse must be specified for sale {self.sale.bill_no}.")
        batches = StockBatch.get_batches_for_sale(self.product, self.qty, warehouse)
        total_cost = sum(Decimal(qty_in_batch) * batch.price for batch, qty_in_batch in batches)
        total_qty = sum(qty_in_batch for _, qty_in_batch in batches)
        if total_qty < self.qty:
            raise ValidationError(f"Insufficient stock batches for {self.product.name} in {warehouse.name}.")
        return total_cost / Decimal(total_qty) if total_qty > 0 else Decimal('0.0')

    # ============================================
    # SALE PRICE CALCULATION
    # ============================================
    def calculate_sale_price(self, fifo_price):
        """Calculate sale price - batch SP or FIFO + margin"""
        customer_profit_margin = self.sale.customer.profit_margin or Decimal('0.0')
        
        # Check if batches have custom selling price
        if self.pk and self.batches_used.exists():
            for batch in self.batches_used.all():
                if batch.selling_price and batch.selling_price > 0:
                    return batch.selling_price
        
        # Default: FIFO + customer margin
        return fifo_price * (1 + customer_profit_margin / 100)

    # ============================================
    # STOCK UPDATE
    # ============================================
    def validate_and_update_stock(self):
        """Validate stock and update inventory"""
        warehouse = self.sale.warehouse
        if not warehouse:
            raise ValidationError(f"Warehouse must be specified for sale {self.sale.bill_no}.")
        
        # ✅ Pehle check karo available stock
        current_stock = Inventory.get_stock(self.product, warehouse)
        if self.qty > current_stock:
            raise ValidationError(
                f"Insufficient stock for {self.product.name} in {warehouse.name}. "
                f"Available: {current_stock}, Requested: {self.qty}"
            )
        
        batches = StockBatch.get_batches_for_sale(self.product, self.qty, warehouse)
        remaining_qty = self.qty
        total_cost = Decimal('0.0')
        used_batches = []

        for batch, qty_in_batch in batches:
            if remaining_qty <= 0:
                break
            batch.remaining_qty -= qty_in_batch
            batch.save()
            total_cost += Decimal(qty_in_batch) * batch.price
            remaining_qty -= qty_in_batch
            used_batches.append(batch)

        Inventory.update_stock(self.product, -self.qty, warehouse)
        return total_cost, used_batches

    # ============================================
    # PROFIT CALCULATION
    # ============================================
    def calculate_profit(self, total_cost):
        """Calculate profit with batch selling price support"""
        if self.pk and self.batches_used.exists():
            total_batch_profit = Decimal('0.0')
            for batch in self.batches_used.all():
                if batch.selling_price and batch.selling_price > 0:
                    batch_profit = (batch.selling_price - batch.price) * Decimal(str(self.qty))
                    total_batch_profit += batch_profit
            if total_batch_profit > 0:
                return total_batch_profit
        
        return self.total_amt - total_cost

    # ============================================
    # ✅ SAVE METHOD (FIXED - FIFO pehle, stock baad mein)
    # ============================================
    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        
        # Ensure Sale is saved first
        if not self.sale.pk:
            self.sale.save()

        warehouse = self.sale.warehouse
        if not warehouse:
            raise ValidationError(f"Warehouse is not set for sale {self.sale.bill_no}.")

        # ✅ STEP 1: Pehle FIFO price calculate karo (stock consume karne se pehle)
        fifo_price = self.get_fifo_price()
        recommended_price = self.calculate_sale_price(fifo_price)
        
        # ✅ STEP 2: Ab price set karo
        if self.price and Decimal(self.price) > 0:
            self.price = Decimal(self.price)
        else:
            self.price = recommended_price

        # ✅ STEP 3: Ab stock validate aur update karo
        total_cost, used_batches = self.validate_and_update_stock()
        
        # ✅ STEP 4: Batch selling price validation
        if used_batches:
            for batch in used_batches:
                if batch.selling_price and batch.selling_price > 0:
                    if self.price < batch.selling_price:
                        raise ValidationError(
                            f"Sale price (Rs. {self.price:,.2f}) for {self.product.name} "
                            f"batch selling price (Rs. {batch.selling_price:,.2f}) se kam nahi ho sakti!"
                        )

        # ✅ STEP 5: Calculate totals
        self.total_amt = Decimal(self.qty) * self.price
        
        # Discount share
        total_sale_amount = self.sale.total_without_discount()
        if total_sale_amount > 0:
            discount_ratio = self.total_amt / total_sale_amount
            self.discount = discount_ratio * self.sale.discount_value
        else:
            self.discount = Decimal('0.00')
        
        # ✅ STEP 6: Profit calculate
        self.profit = self.calculate_profit(total_cost)

        # Save the item
        super().save(*args, **kwargs)
        
        # Set batches_used
        if used_batches:
            self.batches_used.set(used_batches)

    def __str__(self):
        return f"{self.qty} x {self.product.name} at Rs. {self.price:,.2f}"
        
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
    help_text="Customer ke system ka Purchase Order number"
)
    converted_to_sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_from_order')
    
    class Meta:
        verbose_name_plural = '5.0 Sale Orders'
        indexes = [
            models.Index(fields=['order_no']),
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
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

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator  # ✅ YEH ADD KARO
from decimal import Decimal
from datetime import datetime, timedelta, date
from django.utils.timezone import now, localdate
from django.db.models import Sum, F, Q, Min
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
import hashlib

logger = logging.getLogger(__name__)

# models.py - Complete PurchaseRetrn Model

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

class SaleRetrn(models.Model):
    bill_no = models.CharField(max_length=10)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="returns", null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    sale_return_date = models.DateTimeField(default=now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, editable=False)
    return_reason = models.CharField(
        max_length=255, choices=[
            ('damaged', 'Damaged Goods'),
            ('incorrect', 'Incorrect Shipment'),
            ('expired', 'Expired Stock'),
            ('other', 'Other'),
        ], default='other',
    )
    monthly_sale = models.ForeignKey(
        MonthlyClosing, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='sale_returns', editable=False
    )
    
    # ✅ NEW: Warehouse Field
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sale_returns'
    )
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    
    def total_return_amount(self):
        """Calculate total return amount"""
        return self.return_items.aggregate(
            total=Sum('total_amt')
        )['total'] or Decimal('0.00')
    
    def total_return_qty(self):
        """Calculate total return quantity"""
        return self.return_items.aggregate(
            total=Sum('qty')
        )['total'] or Decimal('0.00')
    
    def total_items_returned(self):
        """Count total items returned"""
        return self.return_items.count()
    
    @property
    def reason_color(self):
        colors = {
            'damaged': 'danger',
            'incorrect': 'warning',
            'expired': 'danger',
            'other': 'secondary',
        }
        return colors.get(self.return_reason, 'secondary')
    
    @property
    def reason_icon(self):
        icons = {
            'damaged': 'bi bi-exclamation-triangle',
            'incorrect': 'bi bi-x-circle',
            'expired': 'bi bi-clock',
            'other': 'bi bi-three-dots'
        }
        return icons.get(self.return_reason, 'bi bi-question-circle')
    
    @property
    def can_edit(self):
        days_diff = (now().date() - self.sale_return_date.date()).days
        return days_diff <= 7
    
    @property
    def can_delete(self):
        days_diff = (now().date() - self.sale_return_date.date()).days
        return days_diff <= 7

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.pk and not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        # ✅ Auto-set warehouse from sale
        if not self.warehouse and self.sale:
            self.warehouse = self.sale.warehouse
        
        # ✅ Fallback: Get first warehouse
        if not self.warehouse:
            self.warehouse = Warehouse.objects.first()
        
        sale_month = self.sale_return_date.replace(day=1)
        monthly_closing, _ = MonthlyClosing.objects.get_or_create(month=sale_month)
        self.monthly_sale = monthly_closing

        if monthly_closing.locked:
            raise ValidationError(
                f"Cannot process sale return for {sale_month.strftime('%B %Y')}, as the month is locked."
            )
        self.monthly_sale = monthly_closing

        if not self.created_by:
            self.created_by = User.objects.first()
        super().save(*args, **kwargs)


class SaleRetrnItem(models.Model):
    sale_return = models.ForeignKey(
        'SaleRetrn',
        on_delete=models.CASCADE,
        related_name="return_items",
        null=True,
        blank=True
    )
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    qty = models.DecimalField(max_digits=15, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be positive.")
        
        self.total_amt = self.qty * self.price
        
        # Get warehouse
        warehouse = None
        if self.sale_return and self.sale_return.sale:
            warehouse = self.sale_return.sale.warehouse
        elif self.sale_return and hasattr(self.sale_return, 'warehouse'):
            warehouse = self.sale_return.warehouse
        
        if not warehouse:
            warehouse = Warehouse.objects.first()
            if not warehouse:
                raise ValidationError("No warehouse found! Please create a warehouse first.")
        
        if self.pk:
            # Update existing item
            existing = SaleRetrnItem.objects.get(pk=self.pk)
            qty_diff = self.qty - existing.qty
            
            if qty_diff != 0:
                self._adjust_stock(float(qty_diff), warehouse)
                Inventory.update_stock(self.product, float(qty_diff), warehouse)
        else:
            # ✅ SALE RETURN: New item - INCREASE stock (Customer returning)
            self._adjust_stock(float(self.qty), warehouse)
            Inventory.update_stock(self.product, float(self.qty), warehouse)
        
        self._validate_sale_item()
        super().save(*args, **kwargs)
    
    def _adjust_stock(self, qty, warehouse):
        """
        Adjust stock for sale return
        ✅ FIXED: No purchase_item reference
        """
        if qty > 0:
            # ✅ Customer returning - INCREASE stock
            self._increase_stock(qty, warehouse)
        else:
            # ✅ Removing return - DECREASE stock
            self._decrease_stock(abs(qty), warehouse)
    
    def _increase_stock(self, qty, warehouse):
        """Increase stock in batches"""
        remaining = qty
        
        # Try to find existing batch with same price
        existing_batch = StockBatch.objects.filter(
            product=self.product,
            warehouse=warehouse,
            price=self.price,
            remaining_qty__gt=0
        ).order_by('id').first()
        
        if existing_batch:
            existing_batch.remaining_qty += remaining
            existing_batch.qty += remaining
            existing_batch.save()
        else:
            # Create new batch
            StockBatch.objects.create(
                product=self.product,
                warehouse=warehouse,
                qty=remaining,
                remaining_qty=remaining,
                price=self.price
            )
    
    def _decrease_stock(self, qty, warehouse):
        """Decrease stock from batches (FIFO)"""
        remaining = qty
        batches = StockBatch.objects.filter(
            product=self.product,
            warehouse=warehouse,
            remaining_qty__gt=0
        ).order_by('id')
        
        for batch in batches:
            if remaining <= 0:
                break
            dec = min(batch.remaining_qty, remaining)
            batch.remaining_qty -= dec
            batch.qty -= dec
            batch.save()
            remaining -= dec
        
        if remaining > 0:
            logger.warning(
                f"Insufficient stock to decrease {remaining} units of {self.product.name}"
            )
    
    def _validate_sale_item(self):
        """Validate against sale"""
        sale = self.sale_return.sale
        sale_item = sale.saleitem_set.filter(product=self.product).first()
        
        if not sale_item:
            raise ValidationError(f"Product '{self.product}' not found in sale.")
        
        if self.price != sale_item.price:
            raise ValidationError(
                f"Price mismatch: Sale price {sale_item.price}, Return price {self.price}"
            )
        
        already_returned = SaleRetrnItem.objects.filter(
            sale_return__sale=sale,
            product=self.product
        ).exclude(pk=self.pk).aggregate(total=Sum('qty'))['total'] or 0
        
        if self.qty + already_returned > sale_item.qty:
            raise ValidationError(
                f"Quantity exceeds sale: Available {sale_item.qty - already_returned}, "
                f"Requested {self.qty}"
            )
    
    def delete(self, *args, **kwargs):
        """Restore stock when deleted"""
        warehouse = None
        if self.sale_return and self.sale_return.sale:
            warehouse = self.sale_return.sale.warehouse
        elif self.sale_return and hasattr(self.sale_return, 'warehouse'):
            warehouse = self.sale_return.warehouse
        
        if warehouse:
            # ✅ SALE RETURN DELETE: Decrease stock (remove the return effect)
            self._adjust_stock(-float(self.qty), warehouse)
            Inventory.update_stock(self.product, -float(self.qty), warehouse)
        
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"{self.qty} x {self.product.name}"
    
    class Meta:
        verbose_name_plural = '5.4. Sale Return Items'


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

class License(models.Model):
    key = models.CharField(max_length=255, unique=True)  # License Key
    expiry_date = models.DateField()  # Expiration Date
    created_at = models.DateTimeField(auto_now_add=True)  # When the key was created
    is_active = models.BooleanField(default=True)

    def is_valid(self):
        """Check if the license is still valid."""
        return self.expiry_date >= localdate()

    @staticmethod
    def generate_license_key(secret):
        """Generate a hash-based license key using a secret string."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def save(self, *args, **kwargs):
        """Ensure only programmers can set the license key."""
        if not self.key:
            raise ValidationError("License key cannot be empty.")
        if not self.expiry_date:
            raise ValidationError("Expiry date must be set.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"License (Valid till {self.expiry_date})"
        
        
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
# RANGE REPORTING FUNCTIONS
# ============================================

class ReportManager:
    
    @staticmethod
    def get_sales_by_date_range(from_date, to_date, warehouse=None):
        """Get sales between two dates"""
        sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        )
        if warehouse:
            sales = sales.filter(warehouse_id=warehouse)
        
        total_sales = sum(sale.total_amount() for sale in sales)
        total_profit = sum(sale.total_profit() for sale in sales)
        total_items = SaleItem.objects.filter(sale__in=sales).count()
        
        return {
            'count': sales.count(),
            'total_amount': total_sales,
            'total_profit': total_profit,
            'total_items': total_items,
            'sales': sales
        }
    
    @staticmethod
    def get_purchases_by_date_range(from_date, to_date, warehouse=None):
        """Get purchases between two dates"""
        purchases = Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        )
        if warehouse:
            purchases = purchases.filter(warehouse_id=warehouse)
        
        total_amount = sum(p.total_amount() for p in purchases)
        total_paid = sum(p.paid for p in purchases)
        
        return {
            'count': purchases.count(),
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_outstanding': total_amount - total_paid,
            'purchases': purchases
        }
    
    @staticmethod
    def get_top_products_by_date_range(from_date, to_date, limit=10):
        """Get best selling products between two dates"""
        from django.db.models import Sum
        top_products = SaleItem.objects.filter(
            sale__sale_date__date__gte=from_date,
            sale__sale_date__date__lte=to_date
        ).values('product__name').annotate(
            total_qty=Sum('qty'),
            total_sales=Sum('total_amt'),
            total_profit=Sum('profit')
        ).order_by('-total_sales')[:limit]
        
        return top_products
    
    @staticmethod
    def get_daily_summary(from_date, to_date):
        """Get day-wise summary"""
        from django.db.models import Sum
        from datetime import timedelta
        
        daily_data = []
        current = from_date
        while current <= to_date:
            sales = Sale.objects.filter(sale_date__date=current)
            purchases = Purchase.objects.filter(pur_date__date=current)
            
            daily_data.append({
                'date': current,
                'sales_count': sales.count(),
                'sales_amount': sum(s.total_amount() for s in sales),
                'purchase_count': purchases.count(),
                'purchase_amount': sum(p.total_amount() for p in purchases),
                'profit': sum(s.total_profit() for s in sales),
            })
            current += timedelta(days=1)
        
        return daily_data
    
    @staticmethod
    def get_customer_wise_sales(from_date, to_date):
        """Get customer-wise sales report"""
        from django.db.models import Sum
        customer_sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).values('customer__name').annotate(
            total_sales=Sum('saleitem__total_amt'),
            total_profit=Sum('saleitem__profit'),
            sale_count=Count('id')
        ).order_by('-total_sales')
        
        return customer_sales
    
    @staticmethod
    def get_vendor_wise_purchases(from_date, to_date):
        """Get vendor-wise purchase report"""
        from django.db.models import Sum
        vendor_purchases = Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        ).values('vendor__name').annotate(
            total_purchases=Sum('purchaseitem__total_amt'),
            purchase_count=Count('id')
        ).order_by('-total_purchases')
        
        return vendor_purchases


class SaleRangeReport(models.Model):
    """Saved range reports for reference"""
    name = models.CharField(max_length=255)
    from_date = models.DateField()
    to_date = models.DateField()
    report_type = models.CharField(max_length=50, choices=[
        ('sales', 'Sales Report'),
        ('purchases', 'Purchase Report'),
        ('profit_loss', 'Profit & Loss'),
        ('customer_wise', 'Customer Wise'),
        ('vendor_wise', 'Vendor Wise'),
        ('product_wise', 'Product Wise'),
    ])
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "📊 Range Reports"
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.name} ({self.from_date} to {self.to_date})"


# ============================================
# SALE QUOTATION MODEL
# ============================================
class SaleQuotation(models.Model):
    QUOTATION_STATUS = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('converted', 'Converted to Order'),
    ]
    
    quotation_no = models.CharField(max_length=20, unique=True, verbose_name="Quotation Number")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='sale_quotations')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='sale_quotations')
    quotation_date = models.DateTimeField(default=now, verbose_name="Quotation Date")
    valid_until = models.DateField(verbose_name="Valid Until")
    status = models.CharField(max_length=20, choices=QUOTATION_STATUS, default='draft')
    notes = models.TextField(blank=True, null=True, verbose_name="Quotation Notes")
    terms_conditions = models.TextField(blank=True, null=True, verbose_name="Terms & Conditions")
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    converted_to_order = models.ForeignKey('SaleOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_from_quotation')
    customer_po_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Customer PO Number")
    
    class Meta:
        verbose_name_plural = '5.5 Sale Quotations'
        ordering = ['-quotation_date']
        indexes = [
            models.Index(fields=['quotation_no']),
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Quote #{self.quotation_no} - {self.customer.name}"
    
    def total_amount(self):
        return sum(item.total_amt for item in self.items.all())
    
    def total_after_discount(self):
        return self.total_amount() - self.discount_value
    
    def is_expired(self):
        return self.valid_until < localdate()
    
    def save(self, *args, **kwargs):
        if not self.quotation_no:
            today = datetime.now().strftime('%Y%m%d')
            last_quote = SaleQuotation.objects.filter(
                quotation_no__startswith=f'QT-{today}'
            ).order_by('-quotation_no').first()
            if last_quote:
                last_num = int(last_quote.quotation_no.split('-')[-1])
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = '0001'
            self.quotation_no = f'QT-{today}-{new_num}'
        
        if not self.created_by:
            self.created_by = kwargs.pop('user', None)
        
        # Auto-expire if past valid date
        if self.valid_until < localdate() and self.status in ['draft', 'sent']:
            self.status = 'expired'
        
        super().save(*args, **kwargs)


class SaleQuotationItem(models.Model):
    quotation = models.ForeignKey(SaleQuotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quoted Price")
    total_amt = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.0'))
    
    class Meta:
        verbose_name_plural = '5.5.1 Sale Quotation Items'
        unique_together = ('quotation', 'product')
    
    def __str__(self):
        return f"{self.qty} x {self.product.name} @ {self.price}"
    
    def save(self, *args, **kwargs):
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        self.total_amt = Decimal(self.qty) * self.price
        super().save(*args, **kwargs)


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
        
# ============================================
# PAYMENT METHODS MODEL
# ============================================
class PaymentMethod(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('jazzcash', 'JazzCash'),
        ('easypaisa', 'EasyPaisa'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    
    name = models.CharField(max_length=50, choices=METHOD_CHOICES, unique=True)
    is_active = models.BooleanField(default=True)
    icon = models.CharField(max_length=50, blank=True, null=True)
    
    def __str__(self):
        return self.get_name_display()
    
    class Meta:
        verbose_name_plural = 'Payment Methods'


class SalePayment(models.Model):
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='payments')
    method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reference_no = models.CharField(max_length=100, blank=True, null=True, help_text="Card/Transaction reference")
    payment_date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.sale.bill_no} - {self.method} - Rs.{self.amount}"
    
    class Meta:
        verbose_name_plural = 'Sale Payments'
        
# ============================================
# DAILY CLOSING MODEL
# ============================================
class DailyClosing(models.Model):
    closing_date = models.DateField(unique=True)
    opening_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Sales by payment method
    cash_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    jazzcash_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    easypaisa_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bank_transfer_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_difference = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Daily Closing Reports'
        ordering = ['-closing_date']
    
    def __str__(self):
        return f"Closing - {self.closing_date}"
    
    def total_sales_today(self):
        return self.cash_sales + self.card_sales + self.jazzcash_sales + self.easypaisa_sales + self.bank_transfer_sales
    
    def expected_cash(self):
        return self.opening_cash + self.cash_sales - self.total_expenses
    
    def calculate_difference(self):
        return self.closing_cash - self.expected_cash()
    
    def save(self, *args, **kwargs):
        self.cash_difference = self.calculate_difference()
        super().save(*args, **kwargs)


class DailyClosingExpense(models.Model):
    closing = models.ForeignKey(DailyClosing, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    category = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.description} - Rs.{self.amount}"
        
        
# ============================================
# INSTALLMENT PLAN MODELS
# ============================================

class InstallmentPlan(models.Model):
    """Installment plan template (e.g., 3 months, 6 months)"""
    name = models.CharField(max_length=100, help_text="e.g., 3-Month Plan, 6-Month Plan")
    duration_months = models.PositiveIntegerField(help_text="Number of months")
    down_payment_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, 
                                                 help_text="Down payment % (e.g., 20 for 20%)")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         help_text="Interest rate % per annum")
    late_fee_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                            help_text="Late fee per day (Rs.)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Installment Plans"
        ordering = ['duration_months']
    
    def __str__(self):
        return f"{self.name} ({self.duration_months} months)"
    
    def calculate_emi(self, total_amount):
        """Calculate EMI amount"""
        down_payment = (self.down_payment_percent / 100) * total_amount
        loan_amount = total_amount - down_payment
        
        if self.interest_rate > 0 and self.duration_months > 0:
            monthly_rate = (self.interest_rate / 100) / 12
            emi = loan_amount * monthly_rate * (1 + monthly_rate) ** self.duration_months
            emi = emi / ((1 + monthly_rate) ** self.duration_months - 1) if emi else loan_amount / self.duration_months
        else:
            emi = loan_amount / self.duration_months if self.duration_months > 0 else 0
        
        return {
            'down_payment': round(down_payment, 2),
            'loan_amount': round(loan_amount, 2),
            'emi': round(emi, 2),
            'total_payable': round(down_payment + (emi * self.duration_months), 2),
            'total_interest': round((down_payment + (emi * self.duration_months)) - total_amount, 2)
        }


class SaleInstallment(models.Model):
    """Link sale with installment plan"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]
    
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='installments')
    plan = models.ForeignKey(InstallmentPlan, on_delete=models.SET_NULL, null=True)
    
    # Amounts
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    down_payment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    down_payment_paid = models.BooleanField(default=False)
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    emi_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_interest = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Tracking
    start_date = models.DateField(default=now)
    end_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Late fees
    late_fee_accrued = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Sale Installments"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Installment - {self.sale.bill_no} ({self.plan.name if self.plan else 'Custom'})"
    
    # ============================================
    # PAYMENT CALCULATION METHODS
    # ============================================
    
    def total_paid(self):
        """Total paid amount including down payment and EMI payments"""
        paid_emis = self.emi_payments.aggregate(total=Sum('amount_paid'))['total'] or 0
        down_payment_paid = self.down_payment_amount if self.down_payment_paid else 0
        return down_payment_paid + paid_emis
    
    def remaining_amount(self):
        """Remaining amount to pay"""
        return self.total_payable - self.total_paid()
    
    def next_emi_due(self):
        """Get next pending EMI"""
        return self.emi_payments.filter(status='pending').order_by('due_date').first()
    
    def calculate_late_fee(self):
        """Calculate accrued late fee"""
        today = now().date()
        pending_emis = self.emi_payments.filter(status='pending', due_date__lt=today)
        
        total_late_fee = 0
        for emi in pending_emis:
            days_late = (today - emi.due_date).days
            if days_late > 0 and self.plan:
                total_late_fee += days_late * self.plan.late_fee_per_day
        
        return total_late_fee
    
    # ============================================
    # STATUS UPDATE METHODS
    # ============================================
    
    def update_status(self):
        """Auto-update status based on payments"""
        remaining = self.remaining_amount()
        if remaining <= 0:
            self.status = 'paid'
            self.end_date = now().date()
        elif self.total_paid() > 0:
            self.status = 'partial'
        else:
            self.status = 'pending'
        
        # Check if defaulted
        if self.next_due_date and now().date() > self.next_due_date and remaining > 0:
            days_overdue = (now().date() - self.next_due_date).days
            if days_overdue > 30:  # 30 days overdue = defaulted
                self.status = 'defaulted'
        
        self.save(update_fields=['status', 'end_date'])
    
    # ✅ FIX: ADD THIS MISSING METHOD
    def update_next_due_date(self):
        """Update next due date based on first unpaid EMI"""
        next_emi = self.emi_payments.filter(status='pending').order_by('due_date').first()
        if next_emi:
            self.next_due_date = next_emi.due_date
        else:
            self.next_due_date = None
        self.save(update_fields=['next_due_date'])
    
    # ============================================
    # WHATSAPP METHODS
    # ============================================
    
    def send_overdue_alert(self):
        """Send overdue alert to customer"""
        try:
            from ..utils.whatsapp_utils import WhatsAppSender
            
            customer = self.sale.customer
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            overdue_emis = self.emi_payments.filter(status='pending', due_date__lt=now().date())
            total_overdue = sum(emi.remaining_due() for emi in overdue_emis)
            days_overdue = (now().date() - self.next_due_date).days if self.next_due_date else 0
            
            result = WhatsAppSender.send_overdue_alert(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=self.sale.bill_no,
                overdue_amount=float(total_overdue),
                days_overdue=days_overdue,
                late_fee=float(self.calculate_late_fee()),
                next_due_date=self.next_due_date
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_monthly_statement(self):
        """Send monthly statement to customer"""
        try:
            from ..utils.whatsapp_utils import WhatsAppSender
            
            customer = self.sale.customer
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            paid_emis = self.emi_payments.filter(status='paid').count()
            total_emis = self.emi_payments.count()
            
            result = WhatsAppSender.send_monthly_statement(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=self.sale.bill_no,
                total_paid=float(self.total_paid()),
                remaining=float(self.remaining_amount()),
                paid_emis=paid_emis,
                total_emis=total_emis,
                next_due_date=self.next_due_date,
                plan_name=self.plan.name if self.plan else 'Installment'
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def progress_percentage(self):
        """Calculate payment progress percentage"""
        if self.total_payable > 0:
            return (self.total_paid() / self.total_payable) * 100
        return 0
    
    @property
    def is_completed(self):
        """Check if installment is fully paid"""
        return self.status == 'paid'
    
    @property
    def is_defaulted(self):
        """Check if installment is defaulted"""
        return self.status == 'defaulted'
    
    @property
    def is_active(self):
        """Check if installment is active (not completed or defaulted)"""
        return self.status in ['pending', 'partial']
    
    @property
    def formatted_total_amount(self):
        """Formatted total amount"""
        return f"Rs. {self.total_amount:,.2f}"
    
    @property
    def formatted_total_paid(self):
        """Formatted total paid"""
        return f"Rs. {self.total_paid():,.2f}"
    
    @property
    def formatted_remaining(self):
        """Formatted remaining amount"""
        return f"Rs. {self.remaining_amount():,.2f}"
    
    @property
    def formatted_emi(self):
        """Formatted EMI amount"""
        return f"Rs. {self.emi_amount:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'defaulted':
            return '<span class="badge bg-danger">⚠️ Defaulted</span>'
        elif self.status == 'partial':
            return '<span class="badge bg-warning">🟡 Partial</span>'
        else:
            return '<span class="badge bg-secondary">⏳ Pending</span>'
    
    # ============================================
    # EMI GENERATION
    # ============================================
    
    def generate_emi_schedule(self):
        """Generate EMI schedule for this installment"""
        if not self.plan:
            raise ValidationError("Cannot generate EMI schedule without a plan")
        
        # Clear existing EMIs
        self.emi_payments.all().delete()
        
        # Generate new EMIs
        for i in range(1, self.plan.duration_months + 1):
            due_date = self.start_date + timedelta(days=30 * i)
            EmiPayment.objects.create(
                installment=self,
                installment_number=i,
                due_date=due_date,
                amount_due=self.emi_amount
            )
        
        # Update next due date
        self.update_next_due_date()
        
        return True
    
    # ============================================
    # SAVE METHOD
    # ============================================
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.next_due_date = self.start_date + timedelta(days=30)  # First EMI after 1 month
            if self.plan:
                self.end_date = self.start_date + timedelta(days=self.plan.duration_months * 30)
        super().save(*args, **kwargs)


class EmiPayment(models.Model):
    """Individual EMI payment record"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('overdue', 'Overdue'),
    ]
    
    installment = models.ForeignKey('SaleInstallment', on_delete=models.CASCADE, related_name='emi_payments')
    installment_number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=15, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee_charged = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "EMI Payments"
        ordering = ['due_date']
        unique_together = ['installment', 'installment_number']
    
    def __str__(self):
        return f"EMI #{self.installment_number} - {self.installment.sale.bill_no} - Rs.{self.amount_due}"
    
    def remaining_due(self):
        """Calculate remaining amount to pay"""
        return self.amount_due - self.amount_paid
    
    def is_overdue(self):
        """Check if EMI is overdue"""
        from django.utils.timezone import now
        return self.due_date < now().date() and self.status != 'paid'
    
    def get_overdue_days(self):
        """Get number of days overdue"""
        from django.utils.timezone import now
        if self.is_overdue():
            return (now().date() - self.due_date).days
        return 0
    
    def calculate_late_fee(self):
        """Calculate late fee for this EMI"""
        if self.is_overdue() and self.installment.plan:
            days = self.get_overdue_days()
            return days * self.installment.plan.late_fee_per_day
        return Decimal('0.00')
    
    # ============================================
    # WHATSAPP METHODS
    # ============================================
    
    def send_payment_confirmation_whatsapp(self, amount_paid):
        """Send WhatsApp confirmation after payment"""
        try:
            from ..utils.whatsapp_utils import WhatsAppSender
            
            installment = self.installment
            sale = installment.sale
            customer = sale.customer
            
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            remaining_balance = installment.remaining_amount()
            next_due = installment.next_emi_due()
            
            result = WhatsAppSender.send_emi_payment_confirmation(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=sale.bill_no,
                emi_number=self.installment_number,
                amount_paid=float(amount_paid),
                due_date=self.due_date,
                remaining_balance=float(remaining_balance),
                next_due_date=next_due.due_date if next_due else None
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_reminder_whatsapp(self):
        """Send reminder for this EMI"""
        try:
            from ..utils.whatsapp_utils import WhatsAppSender
            
            installment = self.installment
            sale = installment.sale
            customer = sale.customer
            
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            result = WhatsAppSender.send_emi_reminder(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=sale.bill_no,
                emi_number=self.installment_number,
                due_date=self.due_date,
                amount_due=float(self.remaining_due()),
                remaining_balance=float(installment.remaining_amount()),
                plan_name=installment.plan.name if installment.plan else 'Installment',
                late_fee_per_day=float(installment.plan.late_fee_per_day) if installment.plan else 0
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # MARK AS PAID METHOD
    # ============================================
    
    def mark_paid(self, amount, payment_method=None, reference_no='', notes='', user=None):
        """Mark EMI as paid partially or fully"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero")
        
        if amount > self.remaining_due():
            raise ValidationError(f"Amount cannot exceed remaining due: Rs. {self.remaining_due():,.2f}")
        
        # Update payment
        self.amount_paid += amount
        self.payment_date = now()
        self.reference_no = reference_no
        self.notes = notes
        
        if payment_method:
            self.payment_method = payment_method
        
        # Update status
        if self.amount_paid >= self.amount_due:
            self.status = 'paid'
            self.amount_paid = self.amount_due
        else:
            self.status = 'partial'
        
        self.save()
        
        # Update main installment status
        self.installment.update_status()
        
        # Create payment record in SalePayment
        from .models import SalePayment
        SalePayment.objects.create(
            sale=self.installment.sale,
            method=payment_method,
            amount=amount,
            reference_no=reference_no,
            created_by=user
        )
        
        # ✅ Send WhatsApp confirmation
        self.send_payment_confirmation_whatsapp(amount)
        
        return True
    
    def mark_full_paid(self, payment_method=None, reference_no='', notes='', user=None):
        """Mark full EMI as paid"""
        return self.mark_paid(self.remaining_due(), payment_method, reference_no, notes, user)
    
    # ============================================
    # UPDATE OVERDUE STATUS
    # ============================================
    
    def update_overdue_status(self):
        """Update status if overdue"""
        from django.utils.timezone import now
        
        if self.status != 'paid' and self.due_date < now().date():
            self.status = 'overdue'
            self.save(update_fields=['status'])
            return True
        return False
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def payment_percentage(self):
        """Calculate payment percentage for this EMI"""
        if self.amount_due > 0:
            return (self.amount_paid / self.amount_due) * 100
        return 0
    
    @property
    def is_fully_paid(self):
        """Check if fully paid"""
        return self.status == 'paid'
    
    @property
    def is_partially_paid(self):
        """Check if partially paid"""
        return self.status == 'partial'
    
    @property
    def formatted_amount_due(self):
        """Formatted amount due"""
        return f"Rs. {self.amount_due:,.2f}"
    
    @property
    def formatted_amount_paid(self):
        """Formatted amount paid"""
        return f"Rs. {self.amount_paid:,.2f}"
    
    @property
    def formatted_remaining(self):
        """Formatted remaining amount"""
        return f"Rs. {self.remaining_due():,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'overdue':
            return '<span class="badge bg-danger">⚠️ Overdue</span>'
        elif self.status == 'partial':
            return '<span class="badge bg-warning">🟡 Partial</span>'
        else:
            return '<span class="badge bg-secondary">⏳ Pending</span>'
    
    # ============================================
    # SAVE METHOD
    # ============================================
    
    def save(self, *args, **kwargs):
        """Override save to update overdue status"""
        # Check if this is a new record
        is_new = self.pk is None
        
        # For existing records, check overdue status
        if not is_new:
            self.update_overdue_status()
        
        super().save(*args, **kwargs)
        
        # Update installment's next due date if needed
        if not is_new and self.status == 'paid':
            self.installment.update_next_due_date()

# ============================================
# IN-APP NOTIFICATION MODEL
# ============================================

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('info', 'ℹ️ Info'),
        ('success', '✅ Success'),
        ('warning', '⚠️ Warning'),
        ('danger', '❌ Danger'),
        ('sale', '🛒 New Sale'),
        ('installment', '📅 Installment Due'),
        ('stock', '📦 Low Stock'),
        ('payment', '💰 Payment Received'),
    ]
    
    # Categories for filtering
    NOTIFICATION_CATEGORIES = [
        ('all', 'All Notifications'),
        ('sales', 'Sales'),
        ('payments', 'Payments'),
        ('installments', 'Installments'),
        ('stock', 'Stock Alerts'),
        ('system', 'System'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    category = models.CharField(max_length=20, choices=NOTIFICATION_CATEGORIES, default='all')
    is_read = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    link = models.CharField(max_length=200, blank=True, null=True, help_text="URL to redirect when clicked")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_read']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%d-%m-%Y %H:%M')}"
    
    @classmethod
    def send(cls, user, title, message, notification_type='info', category='all', link=None):
        """Create notification for a user"""
        notification = cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            category=category,
            link=link
        )
        return notification
    
    @classmethod
    def send_to_all(cls, title, message, notification_type='info', category='all', link=None):
        """Send notification to all staff users"""
        users = User.objects.filter(is_staff=True)
        for user in users:
            cls.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                link=link
            )
    
    @classmethod
    def send_sale_notification(cls, user, sale):
        """Send sale notification"""
        return cls.send(
            user=user,
            title="🛒 New Sale Created",
            message=f"Sale #{sale.bill_no} of Rs. {sale.total_amount():,.2f} created successfully!",
            notification_type='sale',
            category='sales',
            link=f"/sales/{sale.id}/"
        )
    
    @classmethod
    def send_payment_notification(cls, user, sale, amount):
        """Send payment notification"""
        return cls.send(
            user=user,
            title="💰 Payment Received",
            message=f"Payment of Rs. {amount:,.2f} received for {sale.bill_no}",
            notification_type='payment',
            category='payments',
            link=f"/sales/{sale.id}/"
        )
    
    @classmethod
    def send_installment_notification(cls, user, installment):
        """Send installment notification"""
        return cls.send(
            user=user,
            title="📅 Installment Due",
            message=f"Installment for Bill #{installment.sale.bill_no} is due on {installment.next_due_date}. Amount: Rs. {installment.remaining_amount():,.2f}",
            notification_type='installment',
            category='installments',
            link=f"/installments/{installment.id}/"
        )
    
    @classmethod
    def send_low_stock_notification(cls, user, product, current_stock):
        """Send low stock notification"""
        return cls.send(
            user=user,
            title="⚠️ Low Stock Alert",
            message=f"Product '{product.name}' has only {current_stock} units left. Threshold is {product.low_stock_threshold}.",
            notification_type='stock',
            category='stock',
            link=f"/admin/app/product/{product.id}/change/"
        )
    
    @classmethod
    def send_system_notification(cls, user, title, message):
        """Send system notification"""
        return cls.send(
            user=user,
            title=title,
            message=message,
            notification_type='info',
            category='system'
        )
    
    @classmethod
    def send_installment_paid_notification(cls, user, installment, amount):
        """Send installment paid notification"""
        remaining = installment.remaining_amount()
        if remaining <= 0:
            message = f"✅ Installment for Bill #{installment.sale.bill_no} has been fully paid! Total paid: Rs. {installment.total_paid():,.2f}"
        else:
            message = f"💰 Payment of Rs. {amount:,.2f} received for Bill #{installment.sale.bill_no}. Remaining: Rs. {remaining:,.2f}"
        
        return cls.send(
            user=user,
            title="✅ Installment Payment",
            message=message,
            notification_type='payment',
            category='payments',
            link=f"/installments/{installment.id}/"
        )    
        
# models.py mein yeh add karo (apne existing models ke saath)

class SalesTarget(models.Model):
    TARGET_TYPES = [
        ('daily', '📅 Daily Target'),
        ('weekly', '📆 Weekly Target'),
        ('monthly', '📊 Monthly Target'),
        ('salesman', '👤 Salesman-wise'),
        ('product', '📦 Product-wise'),
    ]
    
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_amount = models.DecimalField(max_digits=15, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    salesman = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='targets')
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Bonus settings
    bonus_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    bonus_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_targets')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_target_type_display()}: Rs. {self.target_amount} ({self.start_date} to {self.end_date})"
    
    def current_progress(self):
        """Calculate current progress percentage"""
        from django.db.models import Sum
        from django.utils.timezone import now
        
        if self.target_type == 'daily':
            sales_today = Sale.objects.filter(
                sale_date__date=now().date()
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_today / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        elif self.target_type == 'monthly':
            sales_this_month = Sale.objects.filter(
                sale_date__month=now().month,
                sale_date__year=now().year
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_this_month / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        elif self.target_type == 'salesman' and self.salesman:
            sales_by_salesman = Sale.objects.filter(
                created_by=self.salesman,
                sale_date__date__gte=self.start_date,
                sale_date__date__lte=self.end_date
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            return (sales_by_salesman / self.target_amount) * 100 if self.target_amount > 0 else 0
            
        return 0
    
    def achieved_amount(self):
        from django.db.models import Sum
        from django.utils.timezone import now
        
        if self.target_type == 'daily':
            return Sale.objects.filter(
                sale_date__date=now().date()
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        elif self.target_type == 'monthly':
            return Sale.objects.filter(
                sale_date__month=now().month,
                sale_date__year=now().year
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        elif self.target_type == 'salesman' and self.salesman:
            return Sale.objects.filter(
                created_by=self.salesman,
                sale_date__date__gte=self.start_date,
                sale_date__date__lte=self.end_date
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
        return 0
    
    def remaining_amount(self):
        return max(0, self.target_amount - self.achieved_amount())
    
    def days_remaining(self):
        from django.utils.timezone import now
        remaining = (self.end_date - now().date()).days
        return max(0, remaining)
    
    def daily_needed(self):
        days = self.days_remaining()
        if days > 0:
            return self.remaining_amount() / days
        return 0


class TargetProgress(models.Model):
    target = models.ForeignKey(SalesTarget, on_delete=models.CASCADE, related_name='progress_records')
    date = models.DateField(auto_now_add=True)
    achieved_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.target} - {self.date}: {self.percentage}%"
    
    def save(self, *args, **kwargs):
        if self.target.target_amount > 0:
            self.percentage = (self.achieved_amount / self.target.target_amount) * 100
        super().save(*args, **kwargs)
        
# ============================================
# HR & STAFF MANAGEMENT MODELS
# ============================================

class Employee(models.Model):
    DEPARTMENT_CHOICES = [
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('accounts', 'Accounts'),
        ('warehouse', 'Warehouse'),
        ('admin', 'Admin'),
        ('hr', 'Human Resources'),
        ('it', 'IT'),
        ('marketing', 'Marketing'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('inactive', 'Inactive'),
        ('terminated', 'Terminated'),
    ]
    
    # Personal Information
    employee_id = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)
    dob = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    profile_pic = models.ImageField(upload_to='employee_profiles/', null=True, blank=True)
    
    # Employment Information
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Salary Information
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    house_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Bank Information
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Documents
    cv = models.FileField(upload_to='employee_cv/', null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_employees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "HR - Employees"
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['department', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee_id} - {self.name}"
    
    def total_salary(self):
        """Calculate total monthly salary"""
        return self.basic_salary + self.house_allowance + self.other_allowance
    
    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_emp = Employee.objects.order_by('-id').first()
            if last_emp and last_emp.employee_id:
                try:
                    last_num = int(last_emp.employee_id.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.employee_id = f'EMP-{new_num}'
        super().save(*args, **kwargs)


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('halfday', 'Half Day'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "HR - Attendance"
        unique_together = ['employee', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['employee', 'date']),
        ]
    
    def __str__(self):
        return f"{self.employee.name} - {self.date} - {self.get_status_display()}"


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('casual', 'Casual Leave'),
        ('sick', 'Sick Leave'),
        ('annual', 'Annual Leave'),
        ('unpaid', 'Unpaid Leave'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=10, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_leaves')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "HR - Leave Requests"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.name} - {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"
    
    def total_days(self):
        delta = self.end_date - self.start_date
        return delta.days + 1


class Payroll(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    month = models.DateField(help_text="First day of the month")
    
    # Earnings
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    house_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Deductions
    tax_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    loan_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Attendance Summary
    total_present = models.IntegerField(default=0)
    total_absent = models.IntegerField(default=0)
    total_late = models.IntegerField(default=0)
    total_halfday = models.IntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "HR - Payroll"
        unique_together = ['employee', 'month']
        ordering = ['-month']
    
    def __str__(self):
        return f"{self.employee.name} - {self.month.strftime('%B %Y')}"
    
    def total_earnings(self):
        return self.basic_salary + self.house_allowance + self.other_allowance + self.bonus + self.overtime
    
    def total_deductions(self):
        return self.tax_deduction + self.loan_deduction + self.absence_deduction + self.other_deduction
    
    def net_salary(self):
        return self.total_earnings() - self.total_deductions()


class EmployeeSalaryHistory(models.Model):
    """Track salary changes history"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_history')
    old_basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    new_basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    change_date = models.DateField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "HR - Salary History"
        ordering = ['-change_date']
    
    def __str__(self):
        return f"{self.employee.name} - {self.change_date}: {self.old_basic_salary} → {self.new_basic_salary}"
        
# ============================================
# PRODUCTION MODELS
# ============================================

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
        
# ============================================
# SYSTEM SETTINGS MODEL (For Module Visibility)
# ============================================

class SystemSetting(models.Model):
    """System settings for modules visibility and other configurations"""
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.CharField(max_length=255, default='true')
    description = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "System Settings"
        ordering = ['setting_key']
    
    def __str__(self):
        return f"{self.setting_key}: {self.setting_value}"

    @classmethod
    def get_value(cls, key, default='true'):
        """Get setting value by key"""
        setting = cls.objects.filter(setting_key=key).first()
        if setting:
            return setting.setting_value
        return default
    
    @classmethod
    def get_bool(cls, key, default=True):
        """Get setting as boolean"""
        value = cls.get_value(key, str(default).lower())
        return value.lower() in ['true', '1', 'yes', 'on']
    
    @classmethod
    def set_value(cls, key, value, user=None):
        """Set setting value"""
        setting, created = cls.objects.get_or_create(setting_key=key)
        setting.setting_value = str(value).lower()
        if user:
            setting.updated_by = user
        setting.save()
        return setting
    
    @classmethod
    def toggle(cls, key, user=None):
        """Toggle boolean setting"""
        current = cls.get_bool(key)
        cls.set_value(key, not current, user)
        return not current
        
class CashTransaction(models.Model):
    """Cash generate aur use track karne ke liye"""
    
    TRANSACTION_TYPES = [
        ('deposit', '💰 Cash Deposit (Add)'),
        ('withdraw', '💸 Cash Withdrawal (Remove)'),
        ('sale', '🛒 Sale Income'),
        ('purchase', '📥 Purchase Expense'),
        ('expense', '📝 Other Expense'),
        ('transfer', '🔄 Transfer'),
        ('opening', '🏁 Opening Balance'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', '💵 Cash'),
        ('bank', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('card', '💳 Card'),
    ]
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    description = models.TextField()
    date = models.DateTimeField(default=now)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    # ✅ NEW: Debit/Credit fields
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Related models
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_transactions')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_transactions')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cash_transactions')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name_plural = "💰 Cash Transactions"
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - Rs. {self.amount:,.2f} on {self.date.strftime('%d-%m-%Y')}"
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def is_inflow(self):
        """Cash inflow hai ya outflow?"""
        return self.transaction_type in ['deposit', 'sale', 'opening']
    
    @property
    def is_outflow(self):
        """Cash outflow hai ya?"""
        return self.transaction_type in ['withdraw', 'purchase', 'expense']
    
    @property
    def formatted_debit(self):
        return f"Rs. {self.debit:,.2f}" if self.debit > 0 else "-"
    
    @property
    def formatted_credit(self):
        return f"Rs. {self.credit:,.2f}" if self.credit > 0 else "-"
    
    @property
    def formatted_balance(self):
        return f"Rs. {self.balance:,.2f}"
    
    @classmethod
    def create_with_balance(cls, amount, transaction_type, user=None, description="", 
                           reference_no="", payment_method='cash', related_obj=None):
        """Create transaction with debit/credit/balance - ✅ FIXED"""
        from django.db import transaction
        
        with transaction.atomic():
            # Get current balance
            balance_obj = CashBalance.objects.first()
            if not balance_obj:
                balance_obj = CashBalance.objects.create(balance=0)
            
            current_balance = balance_obj.balance
            
            # Determine debit or credit
            if transaction_type in ['deposit', 'sale', 'opening']:
                debit = amount
                credit = 0
                new_balance = current_balance + amount
                balance_obj.balance = new_balance
            else:  # withdraw, purchase, expense
                debit = 0
                credit = amount
                if current_balance < amount:
                    raise ValidationError(f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}")
                new_balance = current_balance - amount
                balance_obj.balance = new_balance
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # Create transaction with debit/credit/balance
            cash_trans = cls.objects.create(
                amount=amount,
                transaction_type=transaction_type,
                payment_method=payment_method,
                description=description,
                reference_no=reference_no,
                debit=debit,
                credit=credit,
                balance=new_balance,
                created_by=user
            )
            
            # Link related objects
            if related_obj:
                if transaction_type == 'sale' and isinstance(related_obj, Sale):
                    cash_trans.sale = related_obj
                elif transaction_type == 'purchase' and isinstance(related_obj, Purchase):
                    cash_trans.purchase = related_obj
                cash_trans.save()
            
            return cash_trans


class CashBalance(models.Model):
    """Current cash balance track karne ke liye"""
    
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "💰 Cash Balance"
    
    def __str__(self):
        return f"Current Cash Balance: Rs. {self.balance:,.2f}"
    
    @classmethod
    def get_balance(cls):
        """Get current cash balance"""
        balance_obj = cls.objects.first()
        if not balance_obj:
            balance_obj = cls.objects.create(balance=0)
        return balance_obj.balance
    
    @classmethod
    def update_balance(cls, amount, transaction_type, user=None, description="", 
                      reference_no="", payment_method='cash', related_obj=None):
        """Update cash balance with debit/credit transaction record"""
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            balance_obj, _ = cls.objects.get_or_create(id=1)
            
            old_balance = balance_obj.balance
            
            if transaction_type in ['deposit', 'sale', 'opening']:
                balance_obj.balance += amount
                debit = amount
                credit = 0
            elif transaction_type in ['withdraw', 'purchase', 'expense']:
                if balance_obj.balance < amount:
                    raise ValidationError(f"Insufficient cash balance! Available: Rs. {balance_obj.balance:,.2f}")
                balance_obj.balance -= amount
                debit = 0
                credit = amount
            else:
                raise ValidationError(f"Invalid transaction type: {transaction_type}")
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # ✅ Create transaction with debit/credit/balance
            cash_trans = CashTransaction.objects.create(
                amount=amount,
                transaction_type=transaction_type,
                payment_method=payment_method,
                description=description,
                reference_no=reference_no,
                debit=debit,
                credit=credit,
                balance=balance_obj.balance,
                created_by=user
            )
            
            # Link related objects
            if related_obj:
                if transaction_type == 'sale' and isinstance(related_obj, Sale):
                    cash_trans.sale = related_obj
                elif transaction_type == 'purchase' and isinstance(related_obj, Purchase):
                    cash_trans.purchase = related_obj
                cash_trans.save(update_fields=['sale', 'purchase'])
            
            return balance_obj.balance

class Shareholder(models.Model):
    """
    Shareholder Model - Complete with Balance Management & Deduction Methods
    """
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    SHAREHOLDER_TYPES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
        ('trust', 'Trust'),
        ('partnership', 'Partnership'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    shareholder_code = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False
    )
    name = models.CharField(max_length=200)
    shareholder_type = models.CharField(
        max_length=20, 
        choices=SHAREHOLDER_TYPES, 
        default='individual'
    )
    
    # ========================================== #
    # CONTACT DETAILS                           #
    # ========================================== #
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # ========================================== #
    # IDENTIFICATION                            #
    # ========================================== #
    cnic = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        verbose_name="CNIC/NTN"
    )
    passport_no = models.CharField(max_length=20, blank=True, null=True)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    registration_no = models.CharField(max_length=50, blank=True, null=True)
    
    # ========================================== #
    # BANKING DETAILS                           #
    # ========================================== #
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    account_title = models.CharField(max_length=200, blank=True, null=True)
    iban = models.CharField(max_length=50, blank=True, null=True)
    
    # ========================================== #
    # STATUS & FLAGS                            #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='active'
    )
    is_founder = models.BooleanField(
        default=False, 
        help_text="Founder shareholder"
    )
    is_board_member = models.BooleanField(
        default=False, 
        help_text="Board member"
    )
    
    # ========================================== #
    # LOGIN FIELDS                              #
    # ========================================== #
    user = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='shareholder_profile'
    )
    allow_login = models.BooleanField(
        default=False, 
        help_text="Allow shareholder to login to portal"
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_shareholders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "👥 Shareholders"
        indexes = [
            models.Index(fields=['shareholder_code']),
            models.Index(fields=['name']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.shareholder_code} - {self.name}"

    # ========================================== #
    # SHARE CALCULATIONS                        #
    # ========================================== #
    
    def total_shares(self):
        """Total shares held by this shareholder"""
        return self.shares.aggregate(total=Sum('quantity'))['total'] or 0

    def total_investment(self):
        """Total investment amount"""
        return self.shares.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')

    def total_dividends(self):
        """Total dividends received"""
        return self.dividend_payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    def current_value(self, current_price=None):
        """Current value of holdings"""
        total_shares = self.total_shares()
        if current_price:
            return total_shares * current_price
        latest_price = SharePrice.objects.filter(is_active=True).first()
        if latest_price:
            return total_shares * latest_price.price
        return Decimal('0.00')

    def ownership_percentage(self, total_shares=None):
        """Ownership percentage"""
        if total_shares is None:
            total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
        if total_shares > 0:
            return (self.total_shares() / total_shares) * 100
        return Decimal('0.00')

    # ========================================== #
    # BALANCE MANAGEMENT METHODS                #
    # ========================================== #
    
    def get_balance(self):
        """Get current cash balance"""
        return ShareholderCashBalance.get_balance(self)

    def deposit(self, amount, user=None, description=""):
        """Deposit money into shareholder's balance"""
        return ShareholderCashBalance.deposit(
            shareholder=self,
            amount=amount,
            user=user,
            description=description
        )

    def withdraw(self, amount, user=None, description=""):
        """Withdraw money from shareholder's balance"""
        return ShareholderCashBalance.withdraw(
            shareholder=self,
            amount=amount,
            user=user,
            description=description
        )

    # ========================================== #
    # LOGIN METHODS                             #
    # ========================================== #
    
    def get_username(self):
        """Generate username from shareholder name"""
        base = self.name.lower().replace(' ', '').replace('-', '').replace('_', '')
        username = base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1
        return username

    
        
    def create_user(self,password='password123'):
        """Create user with name as username"""
        if self.user:
            return self.user
        
        username = self.get_username()
        user = User.objects.create_user(
            username=username,
            email=self.email or '',
            password=password
        )
        self.user = user
        self.save()
        return user

    def get_user(self):
        """Get existing user or create new"""
        if self.user:
            return self.user
        return self.create_user()

    def set_password(self, raw_password):
        """Set password for shareholder"""
        if self.user:
            self.user.set_password(raw_password)
            self.user.save()
        return True

    def check_password(self, raw_password):
        """Check password"""
        if self.user:
            return self.user.check_password(raw_password)
        return False

    # ========================================== #
    # ✅ SHAREHOLDER DEDUCTION METHODS (FIXED)  #
    # ========================================== #
    
    @classmethod
    def get_all_active_shareholders_with_balance(cls):
        """
        Get all active shareholders with their balances
        ✅ FIXED: Decimal to float conversion
        Returns: List of (shareholder, balance) tuples
        """
        shareholders = cls.objects.filter(status='active')
        result = []
        for shareholder in shareholders:
            balance = shareholder.get_balance()
            if balance > 0:  # Only positive balance shareholders
                result.append({
                    'shareholder': shareholder,
                    'balance': float(balance)  # ✅ Convert to float
                })
        return result

    @classmethod
    def deduct_purchase_equally(cls, purchase_amount, purchase_obj=None, user=None):
        """
        ✅ Deduct purchase amount equally from all shareholders
        Jis ka balance zyada ho ya kam, sab se barabar deduction
        ✅ FIXED: NO main cash deduction - only shareholder balances
        """
        from decimal import Decimal
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get all active shareholders
        shareholders = cls.objects.filter(status='active')
        
        if not shareholders.exists():
            return False, "No active shareholders found"
        
        total_shareholders = shareholders.count()
        
        # ✅ Convert to float for calculation
        purchase_amount_float = float(purchase_amount)
        per_shareholder_float = purchase_amount_float / total_shareholders
        
        # ✅ Convert to Decimal for withdrawal
        per_shareholder_decimal = Decimal(str(per_shareholder_float))
        
        # ✅ Results (all floats for JSON)
        results = {
            'total_shareholders': total_shareholders,
            'per_shareholder': per_shareholder_float,
            'total_amount': purchase_amount_float,
            'deduction_type': 'equal',
            'deducted_from': [],
            'failed': [],
            'skipped': [],
        }
        
        try:
            with transaction.atomic():
                # ❌ REMOVED: CashBalance.update_balance() - NO main cash deduction
                
                # Deduct from each shareholder
                for shareholder in shareholders:
                    try:
                        current_balance = shareholder.get_balance()
                        new_balance = shareholder.withdraw(
                            amount=per_shareholder_decimal,  # ✅ Decimal
                            user=user,
                            description=f"Purchase deduction (Equal) - Rs. {per_shareholder_decimal:,.2f}"
                        )
                        
                        # ✅ Convert to float
                        results['deducted_from'].append({
                            'name': shareholder.name,
                            'code': shareholder.shareholder_code,
                            'balance_before': float(current_balance),
                            'balance_after': float(new_balance),
                            'deducted': per_shareholder_float,
                            'percentage': (per_shareholder_float / purchase_amount_float) * 100,
                            'shares': shareholder.total_shares()
                        })
                        
                        logger.info(f"Deducted Rs. {per_shareholder_float:,.2f} from {shareholder.name}")
                        
                    except Exception as e:
                        logger.error(f"Failed to deduct from {shareholder.name}: {e}")
                        results['failed'].append({
                            'name': shareholder.name,
                            'error': str(e)
                        })
                
                # Save in purchase
                if purchase_obj:
                    purchase_obj.shareholder_deduction_done = True
                    purchase_obj.shareholder_deduction_data = results
                    purchase_obj.shareholder_deduction_date = now()
                    purchase_obj.shareholder_deduction_type = 'equal'
                    purchase_obj.save()
                
                return True, results
                
        except Exception as e:
            logger.error(f"Equal deduction failed: {e}")
            return False, str(e)

    @classmethod
    def deduct_purchase_proportionally_by_balance(cls, purchase_amount, purchase_obj=None, user=None):
        """
        ✅ Deduct purchase amount proportionally by shareholder balance
        Jis ka balance zyada, us ki deduction zyada
        Jis ka balance kam, us ki deduction kam
        Zero balance walo se kuch nahi kata
        ✅ FIXED: NO main cash deduction - only shareholder balances
        ✅ FIXED: Proper Decimal handling for withdrawal
        """
        from decimal import Decimal
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        # ✅ Get active shareholders with positive balance
        shareholders_with_balance = cls.get_all_active_shareholders_with_balance()
        
        if not shareholders_with_balance:
            return False, "No shareholders with positive balance found"
        
        # ✅ Calculate total balance
        total_balance = sum(item['balance'] for item in shareholders_with_balance)
        
        if total_balance == 0:
            return False, "Total shareholder balance is zero"
        
        # ✅ Convert purchase_amount to float for calculations
        purchase_amount_float = float(purchase_amount)
        
        # ✅ Results (all floats for JSON)
        results = {
            'total_shareholders': len(shareholders_with_balance),
            'total_balance': total_balance,
            'total_amount': purchase_amount_float,
            'deduction_type': 'proportional',
            'deducted_from': [],
            'failed': [],
            'skipped': [],
        }
        
        # ✅ Track zero balance shareholders to skip
        all_shareholders = cls.objects.filter(status='active')
        for shareholder in all_shareholders:
            balance = shareholder.get_balance()
            if balance == 0:
                results['skipped'].append({
                    'name': shareholder.name,
                    'code': shareholder.shareholder_code,
                    'reason': 'Zero balance'
                })
        
        try:
            with transaction.atomic():
                # ❌ REMOVED: CashBalance.update_balance() - NO main cash deduction
                
                # ✅ Deduct from each shareholder proportionally
                for item in shareholders_with_balance:
                    shareholder = item['shareholder']
                    balance = item['balance']  # float
                    
                    # ✅ Calculate proportion (float / float = float)
                    proportion = balance / total_balance
                    
                    # ✅ Calculate deduction amount (float * float = float)
                    deduction_amount_float = purchase_amount_float * proportion
                    
                    # ✅ Convert back to Decimal for withdrawal (with rounding)
                    deduction_decimal = Decimal(str(round(deduction_amount_float, 2)))
                    
                    try:
                        current_balance = shareholder.get_balance()
                        new_balance = shareholder.withdraw(
                            amount=deduction_decimal,  # ✅ Decimal with rounding
                            user=user,
                            description=f"Purchase deduction (Proportional) - {proportion*100:.1f}% of total"
                        )
                        
                        # ✅ Store as float in results
                        results['deducted_from'].append({
                            'name': shareholder.name,
                            'code': shareholder.shareholder_code,
                            'balance_before': float(current_balance),
                            'balance_after': float(new_balance),
                            'deducted': deduction_amount_float,
                            'percentage': proportion * 100,
                            'shares': shareholder.total_shares()
                        })
                        
                        logger.info(f"Deducted Rs. {deduction_amount_float:,.2f} ({proportion*100:.1f}%) from {shareholder.name}")
                        
                    except Exception as e:
                        logger.error(f"Failed to deduct from {shareholder.name}: {e}")
                        results['failed'].append({
                            'name': shareholder.name,
                            'error': str(e)
                        })
                
                # ✅ Save in purchase
                if purchase_obj:
                    purchase_obj.shareholder_deduction_done = True
                    purchase_obj.shareholder_deduction_data = results
                    purchase_obj.shareholder_deduction_date = now()
                    purchase_obj.shareholder_deduction_type = 'proportional'
                    purchase_obj.save()
                
                return True, results
                
        except Exception as e:
            logger.error(f"Proportional deduction failed: {e}")
            return False, str(e)

    @classmethod
    def process_purchase_deduction(cls, purchase, user=None):
        """
        ✅ Main method to process purchase deduction
        Automatically selects the best deduction type
        """
        from django.utils.timezone import now
        
        if not purchase:
            return False, "Purchase object required"
        
        if purchase.shareholder_deduction_done:
            return False, "Deduction already processed"
        
        # ✅ Get deduction type from system setting
        deduction_type = SystemSetting.get_value('shareholder_deduction_type', 'proportional')
        
        # ✅ Also check purchase override
        if hasattr(purchase, 'shareholder_deduction_type') and purchase.shareholder_deduction_type != 'skip':
            deduction_type = purchase.shareholder_deduction_type
        
        # ✅ Process based on type
        if deduction_type == 'equal':
            return cls.deduct_purchase_equally(
                purchase_amount=purchase.total_amount(),
                purchase_obj=purchase,
                user=user or purchase.created_by
            )
        else:  # proportional (default)
            return cls.deduct_purchase_proportionally_by_balance(
                purchase_amount=purchase.total_amount(),
                purchase_obj=purchase,
                user=user or purchase.created_by
            )

    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate code"""
        if not self.shareholder_code:
            last_shareholder = Shareholder.objects.order_by('-id').first()
            if last_shareholder and last_shareholder.shareholder_code:
                try:
                    last_num = int(last_shareholder.shareholder_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.shareholder_code = f'SH-{new_num}'
        
        super().save(*args, **kwargs)

    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def formatted_total_shares(self):
        return f"{self.total_shares():,}"

    @property
    def formatted_total_investment(self):
        return f"Rs. {self.total_investment():,.2f}"

    @property
    def formatted_ownership(self):
        return f"{self.ownership_percentage():.2f}%"

    @property
    def status_badge(self):
        if self.status == 'active':
            return '<span class="badge bg-success">✅ Active</span>'
        elif self.status == 'inactive':
            return '<span class="badge bg-secondary">⏸️ Inactive</span>'
        else:
            return '<span class="badge bg-danger">⛔ Suspended</span>'

    @property
    def has_login(self):
        """Check if shareholder has login access"""
        return self.allow_login and self.user is not None

    @property
    def username(self):
        """Get username"""
        if self.user:
            return self.user.username
        return None


class Share(models.Model):
    """Share/Stock holding record with shareholder cash balance support"""
    SHARE_TYPES = [
        ('ordinary', 'Ordinary Share'),
        ('preference', 'Preference Share'),
        ('bonus', 'Bonus Share'),
        ('founder', 'Founder Share'),
    ]
    
    # ============================================
    # BASIC INFORMATION
    # ============================================
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='shares'
    )
    share_type = models.CharField(
        max_length=20, 
        choices=SHARE_TYPES, 
        default='ordinary'
    )
    quantity = models.PositiveIntegerField(
        help_text="Number of shares held"
    )
    purchase_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Price per share at time of purchase"
    )
    
    # ============================================
    # CERTIFICATE INFORMATION
    # ============================================
    certificate_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True,
        help_text="Unique certificate number"
    )
    certificate_issue_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when certificate was issued"
    )
    certificate_printed = models.BooleanField(
        default=False,
        help_text="Has certificate been printed?"
    )
    certificate_printed_at = models.DateTimeField(
        null=True, 
        blank=True
    )
    certificate_printed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='share_certificates_printed'
    )
    certificate_template = models.CharField(
        max_length=50, 
        default='standard', 
        choices=[
            ('standard', 'Standard'),
            ('premium', 'Premium'),
            ('simple', 'Simple'),
        ],
        help_text="Certificate template style"
    )
    certificate_notes = models.TextField(
        blank=True, 
        null=True,
        help_text="Any notes about the certificate"
    )
    
    # ============================================
    # ISSUE DETAILS
    # ============================================
    issue_date = models.DateField(
        default=now,
        help_text="Date when shares were issued"
    )
    is_locked = models.BooleanField(
        default=False, 
        help_text="Locked shares cannot be transferred"
    )
    notes = models.TextField(
        blank=True, 
        null=True,
        help_text="General notes about this share holding"
    )
    
    # ============================================
    # TRANSFER TRACKING
    # ============================================
    transferred_from = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='transferred_to',
        help_text="Original share this was transferred from"
    )
    transfer_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date of transfer"
    )
    transfer_notes = models.TextField(
        blank=True, 
        null=True,
        help_text="Notes about the transfer"
    )
    
    # ============================================
    # SHAREHOLDER CASH BALANCE SETTINGS
    # ============================================
    paid_from_shareholder_balance = models.BooleanField(
        default=True,
        help_text="If True, shares are purchased from shareholder's cash balance. If False, from main cash balance."
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_shares'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ============================================
    # META
    # ============================================
    class Meta:
        verbose_name_plural = "📈 Share Holdings"
        indexes = [
            models.Index(fields=['shareholder']),
            models.Index(fields=['share_type']),
            models.Index(fields=['certificate_number']),
        ]
    
    # ============================================
    # STRING REPRESENTATION
    # ============================================
    def __str__(self):
        return f"{self.shareholder.name} - {self.quantity} x {self.share_type}"
    
    # ============================================
    # VALUE CALCULATIONS
    # ============================================
    def total_value(self, price=None):
        """Total value of this share holding"""
        if price:
            return self.quantity * price
        latest_price = SharePrice.objects.filter(is_active=True).first()
        if latest_price:
            return self.quantity * latest_price.price
        return self.quantity * self.purchase_price
    
    def total_investment(self):
        """Total investment amount for this holding"""
        return self.quantity * self.purchase_price
    
    def profit_loss(self, current_price=None):
        """Profit/Loss on this holding"""
        if current_price is None:
            latest_price = SharePrice.objects.filter(is_active=True).first()
            current_price = latest_price.price if latest_price else self.purchase_price
        return self.quantity * (current_price - self.purchase_price)
    
    def profit_loss_percent(self, current_price=None):
        """Profit/Loss percentage"""
        if current_price is None:
            latest_price = SharePrice.objects.filter(is_active=True).first()
            current_price = latest_price.price if latest_price else self.purchase_price
        if self.purchase_price > 0:
            return ((current_price - self.purchase_price) / self.purchase_price) * 100
        return Decimal('0.00')
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_quantity(self):
        return f"{self.quantity:,}"
    
    @property
    def formatted_purchase_price(self):
        return f"Rs. {self.purchase_price:,.2f}"
    
    @property
    def formatted_total_value(self):
        return f"Rs. {self.total_value():,.2f}"
    
    @property
    def formatted_total_investment(self):
        return f"Rs. {self.total_investment():,.2f}"
    
    @property
    def formatted_profit_loss(self):
        pl = self.profit_loss()
        if pl >= 0:
            return f"+Rs. {pl:,.2f} (↑{self.profit_loss_percent():.1f}%)"
        return f"-Rs. {abs(pl):,.2f} (↓{abs(self.profit_loss_percent()):.1f}%)"
    
    @property
    def is_transferred(self):
        """Check if this share has been transferred"""
        return self.transferred_from is not None
    
    @property
    def is_active(self):
        """Check if share is active (not locked and quantity > 0)"""
        return not self.is_locked and self.quantity > 0
    
    @property
    def share_status(self):
        """Return status as string"""
        if self.is_locked:
            return "Locked"
        if self.quantity == 0:
            return "Transferred"
        if self.transferred_from:
            return "Transferred In"
        return "Active"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.is_locked:
            return '<span class="badge bg-secondary">🔒 Locked</span>'
        if self.quantity == 0:
            return '<span class="badge bg-info">🔄 Transferred</span>'
        if self.transferred_from:
            return '<span class="badge bg-primary">📥 Transferred In</span>'
        return '<span class="badge bg-success">✅ Active</span>'
    
    # ============================================
    # BUSINESS METHODS
    # ============================================
    def mark_as_transferred(self, new_share, user):
        """Mark this share as transferred"""
        self.quantity = 0
        self.is_locked = True
        self.transfer_date = now().date()
        self.transfer_notes = f"Transferred to {new_share.shareholder.name}"
        self.save()
    
    def lock(self, user, reason=""):
        """Lock shares"""
        self.is_locked = True
        self.notes = f"{self.notes}\nLocked by {user.username}: {reason}".strip()
        self.save()
    
    def unlock(self, user, reason=""):
        """Unlock shares"""
        self.is_locked = False
        self.notes = f"{self.notes}\nUnlocked by {user.username}: {reason}".strip()
        self.save()
    
    def generate_certificate(self, user):
        """Generate certificate for this share"""
        if not self.certificate_number:
            self.certificate_number = f"CERT-{self.id:06d}"
        self.certificate_issue_date = now().date()
        self.certificate_printed = True
        self.certificate_printed_at = now()
        self.certificate_printed_by = user
        self.save()
        return self.certificate_number
    
    # ============================================
    # SAVE METHOD - WITH SHAREHOLDER CASH BALANCE
    # ============================================
    def save(self, *args, **kwargs):
        """Save share with automatic shareholder cash balance update"""
        
        # Auto-set issue date
        if not self.issue_date:
            self.issue_date = now().date()
        
        # Auto-generate certificate number
        if not self.certificate_number and self.id:
            self.certificate_number = f"CERT-{self.id:06d}"
        
        # Check if this is a NEW share or UPDATE
        is_new = self.pk is None
        old_investment = Decimal('0.00')
        old_share = None
        
        # If updating, get old investment amount
        if not is_new:
            old_share = Share.objects.get(pk=self.pk)
            old_investment = old_share.quantity * old_share.purchase_price
        
        # Save the share first
        super().save(*args, **kwargs)
        
        # ============================================
        # SHAREHOLDER CASH BALANCE UPDATE
        # ============================================
        if is_new:
            # ✅ NEW SHARE - Deduct from shareholder's cash balance
            total_investment = self.quantity * self.purchase_price
            
            if total_investment > 0 and self.paid_from_shareholder_balance:
                try:
                    # Check if shareholder has enough balance
                    current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                    if current_balance < total_investment:
                        raise ValidationError(
                            f"❌ {self.shareholder.name} has insufficient balance! "
                            f"Available: Rs. {current_balance:,.2f}, Required: Rs. {total_investment:,.2f}"
                        )
                    
                    # Deduct from shareholder's cash balance
                    ShareholderCashBalance.withdraw(
                        shareholder=self.shareholder,
                        amount=total_investment,
                        user=self.created_by,
                        description=f"Share purchase: {self.quantity} shares @ Rs. {self.purchase_price:,.2f} (Certificate #{self.certificate_number or 'N/A'})"
                    )
                    
                    # Also add to main cash balance (company receives money)
                    CashBalance.update_balance(
                        amount=total_investment,
                        transaction_type='deposit',
                        user=self.created_by,
                        description=f"Share investment from {self.shareholder.name} - {self.quantity} shares @ Rs. {self.purchase_price:,.2f}"
                    )
                    
                except ValidationError as e:
                    # If shareholder doesn't have enough balance, allow fallback to main cash
                    if not self.paid_from_shareholder_balance:
                        raise
                    # Re-raise with clear message
                    raise ValidationError(f"❌ {str(e)}. You can uncheck 'Paid from Shareholder Balance' to use main cash.")
            
            elif total_investment > 0 and not self.paid_from_shareholder_balance:
                # ✅ Using main cash balance
                CashBalance.update_balance(
                    amount=total_investment,
                    transaction_type='deposit',
                    user=self.created_by,
                    description=f"Share investment from {self.shareholder.name} - {self.quantity} shares @ Rs. {self.purchase_price:,.2f} (Main Cash)"
                )
        
        else:
            # ✅ UPDATE SHARE - Adjust difference in balances
            new_investment = self.quantity * self.purchase_price
            difference = new_investment - old_investment
            
            if difference != 0:
                if self.paid_from_shareholder_balance:
                    if difference > 0:
                        # More investment - deduct more from shareholder
                        # Check if shareholder has enough balance for the increase
                        current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                        if current_balance < difference:
                            raise ValidationError(
                                f"❌ {self.shareholder.name} has insufficient balance for increase! "
                                f"Available: Rs. {current_balance:,.2f}, Required: Rs. {difference:,.2f}"
                            )
                        
                        ShareholderCashBalance.withdraw(
                            shareholder=self.shareholder,
                            amount=difference,
                            user=self.created_by,
                            description=f"Share investment increase: +{self.quantity - old_share.quantity} shares (New total: {self.quantity} @ Rs. {self.purchase_price:,.2f})"
                        )
                        CashBalance.update_balance(
                            amount=difference,
                            transaction_type='deposit',
                            user=self.created_by,
                            description=f"Additional investment from {self.shareholder.name} - +{self.quantity - old_share.quantity} shares"
                        )
                    else:
                        # Less investment - refund to shareholder
                        refund_amount = abs(difference)
                        ShareholderCashBalance.deposit(
                            shareholder=self.shareholder,
                            amount=refund_amount,
                            user=self.created_by,
                            description=f"Share investment decrease: -{old_share.quantity - self.quantity} shares (New total: {self.quantity} @ Rs. {self.purchase_price:,.2f})"
                        )
                        CashBalance.update_balance(
                            amount=refund_amount,
                            transaction_type='withdraw',
                            user=self.created_by,
                            description=f"Refund to {self.shareholder.name} - share decrease"
                        )
                else:
                    # Using main cash balance
                    if difference > 0:
                        CashBalance.update_balance(
                            amount=difference,
                            transaction_type='deposit',
                            user=self.created_by,
                            description=f"Additional investment from {self.shareholder.name} - +{self.quantity - old_share.quantity} shares (Main Cash)"
                        )
                    else:
                        CashBalance.update_balance(
                            amount=abs(difference),
                            transaction_type='withdraw',
                            user=self.created_by,
                            description=f"Refund to {self.shareholder.name} - share decrease (Main Cash)"
                        )
    
    # ============================================
    # CLASS METHODS
    # ============================================
    @classmethod
    def create_from_investment(cls, shareholder, quantity, price, user, paid_from_balance=True):
        """Create shares from investment"""
        share = cls.objects.create(
            shareholder=shareholder,
            quantity=quantity,
            purchase_price=price,
            issue_date=now().date(),
            created_by=user,
            paid_from_shareholder_balance=paid_from_balance
        )
        return share
    
    @classmethod
    def get_total_shares(cls):
        """Get total number of shares in the system"""
        return cls.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    @classmethod
    def get_total_investment(cls):
        """Get total investment in the system"""
        return cls.objects.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')
    
    @classmethod
    def get_shareholder_summary(cls, shareholder):
        """Get summary for a specific shareholder"""
        shares = cls.objects.filter(shareholder=shareholder)
        total_shares = shares.aggregate(total=Sum('quantity'))['total'] or 0
        total_investment = shares.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')
        
        latest_price = SharePrice.objects.filter(is_active=True).first()
        current_value = total_shares * (latest_price.price if latest_price else 0)
        
        return {
            'total_shares': total_shares,
            'total_investment': total_investment,
            'current_value': current_value,
            'profit_loss': current_value - total_investment,
            'profit_loss_percent': ((current_value - total_investment) / total_investment * 100) if total_investment > 0 else 0,
        }



class SharePrice(models.Model):
    """Share price history"""
    price = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField(default=now)
    is_active = models.BooleanField(default=True, help_text="Current active price")
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='share_prices')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "💰 Share Prices"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Rs. {self.price:,.2f} - {self.date.strftime('%d-%m-%Y')}"
    
    def save(self, *args, **kwargs):
        # Only one active price at a time
        if self.is_active:
            SharePrice.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Dividend(models.Model):
    """Dividend declaration and distribution with custom percentage allocations"""
    
    STATUS_CHOICES = [
        ('declared', 'Declared'),
        ('approved', 'Approved'),
        ('distributed', 'Distributed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # ============================================
    # BASIC INFORMATION
    # ============================================
    dividend_no = models.CharField(max_length=20, unique=True, editable=False)
    amount_per_share = models.DecimalField(max_digits=15, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ============================================
    # DATES
    # ============================================
    declaration_date = models.DateField()
    record_date = models.DateField(help_text="Date to determine eligible shareholders")
    payment_date = models.DateField(null=True, blank=True)
    
    # ============================================
    # STATUS
    # ============================================
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='declared')
    is_interim = models.BooleanField(default=False, help_text="Interim dividend")
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # ALLOCATION PERCENTAGES
    # ============================================
    admin_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Admin's percentage of dividend (default: 5%)"
    )
    manager_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=28.00,
        help_text="Store Manager's percentage of dividend (default: 28%)"
    )
    shareholders_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=67.00,
        help_text="Shareholders' percentage of dividend (default: 67%)"
    )
    
    # ============================================
    # ALLOCATED AMOUNTS
    # ============================================
    admin_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Admin"
    )
    manager_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Store Manager"
    )
    shareholders_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Shareholders"
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_dividends'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Dividends"
        ordering = ['-declaration_date']
        indexes = [
            models.Index(fields=['dividend_no']),
            models.Index(fields=['status']),
            models.Index(fields=['declaration_date']),
        ]
    
    def __str__(self):
        return f"Dividend #{self.dividend_no} - Rs. {self.amount_per_share:,.2f}/share"
    
    # ============================================
    # TOTAL ELIGIBLE SHARES
    # ============================================
    def total_eligible_shares(self):
        """Total shares eligible for this dividend"""
        return Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    # ============================================
    # CALCULATE TOTAL AMOUNT
    # ============================================
    def calculate_total_amount(self):
        """Calculate total dividend amount"""
        total_shares = self.total_eligible_shares()
        return total_shares * self.amount_per_share
    
    # ============================================
    # ✅ FIXED: CALCULATE ALLOCATIONS (NO SAVE CALL)
    # ============================================
    def calculate_allocation(self):
        """
        Calculate dividend allocation based on percentages
        ✅ FIXED: Removed self.save() call to prevent recursion
        """
        total = self.total_amount
        
        self.admin_amount = (self.admin_percentage / 100) * total
        self.manager_amount = (self.manager_percentage / 100) * total
        self.shareholders_amount = (self.shareholders_percentage / 100) * total
        
        return {
            'admin': self.admin_amount,
            'manager': self.manager_amount,
            'shareholders': self.shareholders_amount
        }
    
    # ============================================
    # ✅ CHECK: Can create new dividend?
    # ============================================
    @classmethod
    def can_create_new_dividend(cls):
        """
        Check if a new dividend can be created
        Returns: (bool, message)
        """
        # Check if any active dividend exists
        active_dividends = cls.objects.filter(
            status__in=['declared', 'approved']
        ).exists()
        
        if active_dividends:
            return False, "❌ An active dividend already exists! Please complete or cancel it first."
        
        # Check if any dividend is pending payment
        pending_payments = DividendPayment.objects.filter(status='pending').exists()
        if pending_payments:
            return False, "❌ There are pending dividend payments! Please complete them first."
        
        return True, "✅ You can create a new dividend."
    
    # ============================================
    # ✅ CHECK: Can modify this dividend?
    # ============================================
    def can_modify(self):
        """
        Check if this dividend can be modified
        Returns: (bool, message)
        """
        if self.status == 'distributed':
            return False, "❌ This dividend is already distributed and cannot be modified!"
        
        if self.status == 'cancelled':
            return False, "❌ This dividend is cancelled and cannot be modified!"
        
        # Check if payments exist
        if self.payments.exists():
            paid_count = self.payments.filter(status='paid').count()
            if paid_count > 0:
                return False, f"❌ {paid_count} payment(s) already made! Cannot modify this dividend."
        
        return True, "✅ You can modify this dividend."
    
    # ============================================
    # ✅ CHECK: Can delete this dividend?
    # ============================================
    def can_delete(self):
        """
        Check if this dividend can be deleted
        Returns: (bool, message)
        """
        if self.status == 'distributed':
            return False, "❌ Cannot delete a distributed dividend!"
        
        if self.status == 'approved':
            return False, "❌ Cannot delete an approved dividend! Cancel it first."
        
        if self.payments.filter(status='paid').exists():
            return False, "❌ Cannot delete dividend with paid payments!"
        
        return True, "✅ You can delete this dividend."
    
    # ============================================
    # ✅ CANCEL DIVIDEND
    # ============================================
    def cancel_dividend(self, user, reason=""):
        """
        Cancel a dividend
        ✅ Only if not distributed
        """
        if self.status == 'distributed':
            raise ValidationError("❌ Cannot cancel a distributed dividend!")
        
        if self.status == 'cancelled':
            raise ValidationError("❌ This dividend is already cancelled!")
        
        # Check if any paid payments exist
        if self.payments.filter(status='paid').exists():
            raise ValidationError(
                "❌ Cannot cancel dividend! Some payments have already been made. "
                "Please refund them first."
            )
        
        # Cancel all pending payments
        pending_payments = self.payments.filter(status='pending')
        for payment in pending_payments:
            payment.status = 'failed'
            payment.notes = f"Cancelled due to dividend cancellation: {reason}"
            payment.save()
        
        self.status = 'cancelled'
        self.notes = f"{self.notes}\nCancelled by {user.username}: {reason}".strip()
        self.save()
        
        # Create notification
        try:
            from .models import Notification
            Notification.send(
                user=user,
                title="❌ Dividend Cancelled",
                message=f"Dividend #{self.dividend_no} has been cancelled. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments'
            )
        except Exception:
            pass
        
        return True
    
    # ============================================
    # ✅ SAVE METHOD (NO RECURSION)
    # ============================================
    def save(self, *args, **kwargs):
        """
        Save dividend with allocations
        ✅ FIXED: No recursive calls
        ✅ ADDED: Prevent duplicate/approved dividend modification
        """
        
        # ============================================
        # 🔒 CHECK: If updating existing dividend
        # ============================================
        if self.pk:
            old_dividend = Dividend.objects.filter(pk=self.pk).first()
            
            if old_dividend:
                # 🔒 Cannot modify distributed dividend
                if old_dividend.status == 'distributed':
                    raise ValidationError(
                        "❌ This dividend is already distributed and cannot be modified!"
                    )
                
                # 🔒 Cannot modify cancelled dividend
                if old_dividend.status == 'cancelled':
                    raise ValidationError(
                        "❌ This dividend is cancelled and cannot be modified!"
                    )
                
                # 🔒 Cannot modify if payments exist
                if old_dividend.payments.filter(status='paid').exists():
                    raise ValidationError(
                        "❌ Cannot modify dividend! Payments have already been made."
                    )
                
                # 🔒 Cannot change status from approved back to declared
                if old_dividend.status == 'approved' and self.status == 'declared':
                    raise ValidationError(
                        "❌ Cannot change status from 'Approved' back to 'Declared'!"
                    )
        
        # ============================================
        # 🔒 CHECK: If creating new dividend
        # ============================================
        else:
            # Check if a dividend already exists
            active_dividends = Dividend.objects.filter(
                status__in=['declared', 'approved', 'distributed']
            ).exists()
            
            if active_dividends:
                raise ValidationError(
                    "❌ A dividend already exists! Only one dividend can be active at a time. "
                    "Please complete or cancel the existing dividend first."
                )
            
            # Check if any pending payments from previous dividend
            pending_payments = DividendPayment.objects.filter(status='pending').exists()
            if pending_payments:
                raise ValidationError(
                    "❌ There are pending dividend payments! Please complete them before creating a new dividend."
                )
        
        # ============================================
        # Auto-generate dividend number
        # ============================================
        if not self.dividend_no:
            last_dividend = Dividend.objects.order_by('-id').first()
            if last_dividend and last_dividend.dividend_no:
                try:
                    last_num = int(last_dividend.dividend_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.dividend_no = f'DIV-{new_num}'
        
        # Calculate total amount
        self.total_amount = self.calculate_total_amount()
        
        # ✅ Calculate allocations (NO SAVE CALL INSIDE)
        self.calculate_allocation()
        
        # ✅ Single save call
        super().save(*args, **kwargs)
    
    # ============================================
    # GENERATE ALLOCATIONS
    # ============================================
    def generate_allocations(self, user):
        """Generate allocation records for all parties"""
        
        # Admin Allocation
        admin_allocation, admin_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='admin',
            defaults={
                'recipient_name': 'Admin',
                'percentage': self.admin_percentage,
                'amount': self.admin_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not admin_created and admin_allocation.amount != self.admin_amount:
            admin_allocation.amount = self.admin_amount
            admin_allocation.percentage = self.admin_percentage
            admin_allocation.save(update_fields=['amount', 'percentage'])
        
        # Manager Allocation
        manager_users = User.objects.filter(groups__name='Store Manager').first()
        manager_name = manager_users.get_full_name() if manager_users else 'Store Manager'
        
        manager_allocation, manager_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='manager',
            defaults={
                'recipient_name': manager_name,
                'recipient_id': manager_users.id if manager_users else None,
                'percentage': self.manager_percentage,
                'amount': self.manager_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not manager_created and manager_allocation.amount != self.manager_amount:
            manager_allocation.amount = self.manager_amount
            manager_allocation.percentage = self.manager_percentage
            manager_allocation.save(update_fields=['amount', 'percentage'])
        
        # Shareholders Allocation
        shareholders_allocation, shareholders_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='shareholders',
            defaults={
                'recipient_name': 'All Shareholders',
                'percentage': self.shareholders_percentage,
                'amount': self.shareholders_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not shareholders_created and shareholders_allocation.amount != self.shareholders_amount:
            shareholders_allocation.amount = self.shareholders_amount
            shareholders_allocation.percentage = self.shareholders_percentage
            shareholders_allocation.save(update_fields=['amount', 'percentage'])
        
        return {
            'admin': admin_allocation,
            'manager': manager_allocation,
            'shareholders': shareholders_allocation
        }
    
    # ============================================
    # GENERATE SHAREHOLDER PAYMENTS
    # ============================================
    def generate_shareholder_payments(self, user):
        """Generate dividend payments for all shareholders"""
        
        if self.status not in ['declared', 'approved']:
            raise ValidationError("Dividend must be declared or approved to generate payments!")
        
        # 🔒 Check if payments already exist
        if self.payments.exists():
            raise ValidationError(
                f"❌ Payments already exist for this dividend! "
                f"Total: {self.payments.count()} payments."
            )
        
        shareholders = Shareholder.objects.filter(status='active')
        count = 0
        
        for shareholder in shareholders:
            shares = shareholder.total_shares()
            if shares > 0:
                amount = shares * self.amount_per_share
                DividendPayment.objects.get_or_create(
                    dividend=self,
                    shareholder=shareholder,
                    defaults={
                        'shares_held': shares,
                        'amount': amount,
                        'status': 'pending'
                    }
                )
                count += 1
        
        self.status = 'approved'
        # ✅ Single save, no recursion
        self.save(update_fields=['status'])
        
        return count
    
    # ============================================
    # MARK AS DISTRIBUTED
    # ============================================
    def mark_distributed(self, user):
        """
        Mark entire dividend as distributed
        ✅ Only if all payments are paid
        """
        if self.status == 'distributed':
            raise ValidationError("❌ This dividend is already distributed!")
        
        # Check if all payments are paid
        pending_payments = self.payments.filter(status='pending')
        if pending_payments.exists():
            raise ValidationError(
                f"❌ Cannot mark as distributed! {pending_payments.count()} payments are still pending."
            )
        
        self.status = 'distributed'
        self.payment_date = now()
        self.save(update_fields=['status', 'payment_date'])
        
        # Create notification
        try:
            from .models import Notification
            Notification.send(
                user=user,
                title="✅ Dividend Distributed",
                message=f"Dividend #{self.dividend_no} of Rs. {self.total_amount:,.2f} has been fully distributed.",
                notification_type='success',
                category='payments'
            )
        except Exception:
            pass
        
        return True
    
    # ============================================
    # GET ALLOCATION SUMMARY
    # ============================================
    def get_allocation_summary(self):
        """Get allocation summary with percentages and amounts"""
        return {
            'admin': {
                'percentage': self.admin_percentage,
                'amount': self.admin_amount,
                'is_paid': self.allocations.filter(allocation_type='admin', is_paid=True).exists()
            },
            'manager': {
                'percentage': self.manager_percentage,
                'amount': self.manager_amount,
                'is_paid': self.allocations.filter(allocation_type='manager', is_paid=True).exists()
            },
            'shareholders': {
                'percentage': self.shareholders_percentage,
                'amount': self.shareholders_amount,
                'is_paid': self.allocations.filter(allocation_type='shareholders', is_paid=True).exists()
            }
        }
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def admin_allocation_paid(self):
        return self.allocations.filter(allocation_type='admin', is_paid=True).exists()
    
    @property
    def manager_allocation_paid(self):
        return self.allocations.filter(allocation_type='manager', is_paid=True).exists()
    
    @property
    def shareholders_allocation_paid(self):
        return self.allocations.filter(allocation_type='shareholders', is_paid=True).exists()
    
    @property
    def all_allocations_paid(self):
        return (self.admin_allocation_paid and 
                self.manager_allocation_paid and 
                self.shareholders_allocation_paid)
    
    @property
    def total_paid_allocations(self):
        total = 0
        for alloc in self.allocations.filter(is_paid=True):
            total += alloc.amount
        return total
    
    @property
    def total_pending_allocations(self):
        total = 0
        for alloc in self.allocations.filter(is_paid=False):
            total += alloc.amount
        return total
    
    @property
    def status_badge(self):
        colors = {
            'declared': 'primary',
            'approved': 'warning',
            'distributed': 'success',
            'cancelled': 'danger'
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def is_active(self):
        return self.status not in ['cancelled', 'distributed']
    
    @property
    def can_generate_payments(self):
        return self.status in ['declared', 'approved'] and not self.payments.exists()
    
    @property
    def total_payments(self):
        return self.payments.count()
    
    @property
    def total_paid_payments(self):
        return self.payments.filter(status='paid').count()
    
    @property
    def total_pending_payments(self):
        return self.payments.filter(status='pending').count()
        
class DividendAllocation(models.Model):
    """Track dividend allocations to different parties"""
    
    ALLOCATION_TYPES = [
        ('admin', '👑 Admin'),
        ('manager', '👔 Store Manager'),
        ('shareholders', '👥 Shareholders'),
        ('individual', '👤 Individual Shareholder'),
    ]
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    dividend = models.ForeignKey(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='allocations'
    )
    allocation_type = models.CharField(max_length=20, choices=ALLOCATION_TYPES)
    recipient_name = models.CharField(max_length=200, blank=True, null=True)
    recipient_id = models.PositiveIntegerField(null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Dividend Allocations"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dividend']),
            models.Index(fields=['allocation_type']),
            models.Index(fields=['is_paid']),
        ]
    
    def __str__(self):
        return f"{self.dividend.dividend_no} - {self.get_allocation_type_display()} - Rs. {self.amount:,.2f}"
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def status_badge(self):
        if self.is_paid:
            return '<span class="badge bg-success">✅ Paid</span>'
        return '<span class="badge bg-warning">⏳ Pending</span>'
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def formatted_percentage(self):
        return f"{self.percentage}%"
    
    # ============================================
    # ✅ MARK AS PAID (NO RECURSION)
    # ============================================
    def mark_paid(self, user, payment_method=None, reference_no=None):
        """
        Mark allocation as paid
        ✅ FIXED: No recursion, proper transaction handling
        """
        from django.db import transaction
        
        # 🔒 Check if already paid
        if self.is_paid:
            raise ValidationError("This allocation is already marked as paid!")
        
        try:
            with transaction.atomic():
                # 🔒 Lock the record
                allocation = DividendAllocation.objects.select_for_update().get(pk=self.pk)
                
                if allocation.is_paid:
                    raise ValidationError(
                        "❌ This allocation was just marked as paid by another process!"
                    )
                
                # Update allocation status
                self.is_paid = True
                self.payment_date = now()
                self.payment_method = payment_method
                self.reference_no = reference_no
                
                # ✅ Use update() to avoid recursive save signals
                DividendAllocation.objects.filter(pk=self.pk).update(
                    is_paid=True,
                    payment_date=self.payment_date,
                    payment_method=payment_method,
                    reference_no=reference_no
                )
                
                # For admin/manager, deduct from cash balance
                if self.allocation_type in ['admin', 'manager']:
                    from .models import CashBalance
                    
                    current_balance = CashBalance.get_balance()
                    if current_balance < self.amount:
                        raise ValidationError(
                            f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                            f"Required: Rs. {self.amount:,.2f}"
                        )
                    
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='withdraw',
                        user=user,
                        description=f"Dividend allocation - {self.get_allocation_type_display()} - {self.dividend.dividend_no}"
                    )
                
                # Create notification
                try:
                    from .models import Notification
                    Notification.send(
                        user=user,
                        title="💰 Dividend Allocation Paid",
                        message=f"Dividend allocation of Rs. {self.amount:,.2f} for {self.get_allocation_type_display()} has been paid.",
                        notification_type='success',
                        category='payments',
                        link=f"/admin/app/dividend/{self.dividend.id}/change/"
                    )
                except Exception:
                    pass
                
                return True
                
        except ValidationError as e:
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error marking dividend allocation as paid: {str(e)}")
            raise ValidationError(f"Failed to mark allocation as paid: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Save allocation with proper validation"""
        # 🔒 Prevent changing paid allocation
        if self.pk:
            old = DividendAllocation.objects.filter(pk=self.pk).first()
            if old and old.is_paid and not self.is_paid:
                raise ValidationError(
                    "❌ Cannot change status of a paid allocation!"
                )
        
        super().save(*args, **kwargs)      
            
class DividendPayment(models.Model):
    """Individual dividend payment to shareholder with cash balance support"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    dividend = models.ForeignKey(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='dividend_payments'
    )
    shares_held = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # PAYMENT SETTINGS
    # ============================================
    paid_to_shareholder_balance = models.BooleanField(
        default=True,
        help_text="If True, dividend is paid to shareholder's cash balance. If False, paid as separate payment."
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='processed_dividend_payments'
    )
    
    class Meta:
        verbose_name_plural = "📤 Dividend Payments"
        ordering = ['-created_at']
        unique_together = ['dividend', 'shareholder']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(status='paid', payment_date__isnull=True),
                name='paid_payment_must_have_date'
            )
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['dividend', 'shareholder']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.amount:,.2f}"
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'pending':
            return '<span class="badge bg-warning">⏳ Pending</span>'
        else:
            return '<span class="badge bg-danger">❌ Failed</span>'
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    # ============================================
    # ✅ MARK AS PAID - COMPLETE PROTECTION
    # ============================================
    def mark_paid(self, payment_method=None, reference_no=None, processed_by=None):
        """
        Mark dividend as paid - Shareholder ko paisa MILTA hai
        ✅ FIXED: Complete double-payment protection
        """
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        # ============================================
        # 🔒 CHECK 1: Already paid?
        # ============================================
        if self.status == 'paid':
            raise ValidationError(
                "❌ This dividend payment is already marked as paid! "
                "Double payment is not allowed."
            )
        
        # ============================================
        # 🔒 CHECK 2: Amount validation
        # ============================================
        if self.amount <= 0:
            raise ValidationError("Dividend amount must be greater than zero!")
        
        # ============================================
        # 🔒 CHECK 3: Shareholder exists?
        # ============================================
        if self.paid_to_shareholder_balance and not self.shareholder:
            raise ValidationError("Shareholder not found!")
        
        try:
            with transaction.atomic():
                # ============================================
                # 🔒 CHECK 4: Lock the record for update
                # ============================================
                payment = DividendPayment.objects.select_for_update().get(pk=self.pk)
                
                # Double-check (prevent race condition)
                if payment.status == 'paid':
                    raise ValidationError(
                        "❌ This payment was just marked as paid by another process! "
                        "Please refresh and try again."
                    )
                
                # ============================================
                # ✅ PAY TO SHAREHOLDER (DEPOSIT)
                # ============================================
                if self.paid_to_shareholder_balance:
                    # 🔒 Check if shareholder already received this dividend
                    existing_transaction = ShareholderCashTransaction.objects.filter(
                        shareholder=self.shareholder,
                        dividend_payment=self,
                        transaction_type='dividend'
                    ).exists()
                    
                    if existing_transaction:
                        raise ValidationError(
                            f"❌ {self.shareholder.name} has already received this dividend payment!"
                        )
                    
                    # ✅ DEPOSIT to shareholder
                    new_balance = ShareholderCashBalance.deposit(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        user=processed_by or self.processed_by,
                        description=f"Dividend #{self.dividend.dividend_no} - {self.amount:,.2f} for {self.shares_held} shares"
                    )
                    
                    # ✅ Create transaction record
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        transaction_type='dividend',
                        balance_after=new_balance,
                        description=f"Dividend #{self.dividend.dividend_no} payment",
                        reference_no=reference_no,
                        dividend_payment=self,
                        created_by=processed_by or self.processed_by
                    )
                
                # ============================================
                # ✅ COMPANY CASH DEDUCT
                # ============================================
                from .models import CashBalance
                current_balance = CashBalance.get_balance()
                if current_balance < self.amount:
                    raise ValidationError(
                        f"Insufficient company cash balance! "
                        f"Available: Rs. {current_balance:,.2f}, Required: Rs. {self.amount:,.2f}"
                    )
                
                CashBalance.update_balance(
                    amount=self.amount,
                    transaction_type='withdraw',
                    user=processed_by or self.processed_by,
                    description=f"Dividend Payment #{self.dividend.dividend_no} to {self.shareholder.name}"
                )
                
                # ============================================
                # ✅ UPDATE PAYMENT STATUS
                # ============================================
                self.status = 'paid'
                self.payment_date = now()
                if payment_method:
                    self.payment_method = payment_method
                if reference_no:
                    self.reference_no = reference_no
                if processed_by:
                    self.processed_by = processed_by
                
                # ✅ Use update() to avoid recursion
                DividendPayment.objects.filter(pk=self.pk).update(
                    status='paid',
                    payment_date=self.payment_date,
                    payment_method=self.payment_method,
                    reference_no=self.reference_no,
                    processed_by=self.processed_by
                )
                
                # ============================================
                # ✅ UPDATE DIVIDEND STATUS IF ALL PAID
                # ============================================
                self._update_dividend_status()
                
                # ============================================
                # ✅ CREATE NOTIFICATION
                # ============================================
                try:
                    from .models import Notification
                    if self.processed_by:
                        Notification.send(
                            user=self.processed_by,
                            title="💰 Dividend Paid",
                            message=f"Dividend of Rs. {self.amount:,.2f} paid to {self.shareholder.name}",
                            notification_type='success',
                            category='payments'
                        )
                except Exception:
                    pass
                
                return True
                
        except ValidationError as e:
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error marking dividend payment as paid: {str(e)}")
            raise ValidationError(f"Failed to mark dividend as paid: {str(e)}")
    
    # ============================================
    # HELPER: Update Dividend Status
    # ============================================
    def _update_dividend_status(self):
        """
        Update dividend status based on payments
        Called after each payment is marked paid
        """
        total_payments = self.dividend.payments.count()
        paid_payments = self.dividend.payments.filter(status='paid').count()
        
        if total_payments > 0 and paid_payments == total_payments:
            self.dividend.status = 'distributed'
            self.dividend.payment_date = now()
            self.dividend.save(update_fields=['status', 'payment_date'])
    
    # ============================================
    # BULK PAYMENT
    # ============================================
    def mark_paid_bulk(self, processed_by=None):
        """Mark as paid without custom fields (for bulk operations)"""
        return self.mark_paid(
            payment_method='Bank Transfer',
            processed_by=processed_by
        )
    
    # ============================================
    # CANCEL PAYMENT
    # ============================================
    def cancel_payment(self, processed_by=None, reason=""):
        """
        Cancel a paid dividend payment - reverse the transaction
        """
        if self.status != 'paid':
            raise ValidationError("Only paid payments can be cancelled!")
        
        try:
            with transaction.atomic():
                if self.paid_to_shareholder_balance:
                    # 🔒 Check if shareholder has enough balance to refund
                    current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                    if current_balance < self.amount:
                        raise ValidationError(
                            f"Insufficient balance in {self.shareholder.name}'s account for refund! "
                            f"Available: Rs. {current_balance:,.2f}"
                        )
                    
                    # ✅ Deduct from shareholder
                    new_balance = ShareholderCashBalance.withdraw(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund #{self.dividend.dividend_no} - Cancelled: {reason}"
                    )
                    
                    # ✅ Create transaction record
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        transaction_type='adjustment',
                        balance_after=new_balance,
                        description=f"Dividend refund - Cancelled: {reason}",
                        reference_no=self.reference_no,
                        dividend_payment=self,
                        created_by=processed_by or self.processed_by
                    )
                    
                    # ✅ Add back to company cash
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='deposit',
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund from {self.shareholder.name} - #{self.dividend.dividend_no}"
                    )
                    
                else:
                    # Direct refund to company cash
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='deposit',
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund - {self.shareholder.name} - #{self.dividend.dividend_no}"
                    )
                
                # ✅ Update payment status
                self.status = 'failed'
                self.notes = f"{self.notes}\nCancelled by {processed_by.username if processed_by else 'System'}: {reason}".strip()
                self.save()
                
                # ✅ Update dividend status
                self._update_dividend_status()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to cancel payment: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Save payment without recursion"""
        # 🔒 Prevent changing status of paid payments
        if self.pk:
            old = DividendPayment.objects.filter(pk=self.pk).first()
            if old and old.status == 'paid' and self.status != 'paid':
                raise ValidationError(
                    "❌ Cannot change status of a paid payment!"
                )
        
        super().save(*args, **kwargs)
    
    # ============================================
    # DELETE PROTECTION
    # ============================================
    def delete(self, *args, **kwargs):
        """🔒 Prevent deleting paid payments"""
        if self.status == 'paid':
            raise ValidationError(
                "❌ Cannot delete a paid dividend payment! "
                "Use cancel_payment() to reverse the transaction first."
            )
        super().delete(*args, **kwargs)


class ShareTransfer(models.Model):
    """Share transfer between shareholders with cash balance support"""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    transfer_no = models.CharField(max_length=20, unique=True, editable=False)
    
    # ============================================
    # FROM/TO SHAREHOLDERS
    # ============================================
    from_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='share_transfers_out'
    )
    to_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='share_transfers_in'
    )
    
    # ============================================
    # SHARES BEING TRANSFERRED
    # ============================================
    shares = models.ManyToManyField('Share', related_name='share_transfers')
    quantity = models.PositiveIntegerField()
    transfer_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transfer_date = models.DateField(default=now)
    
    # ============================================
    # STATUS
    # ============================================
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # ============================================
    # APPROVAL
    # ============================================
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='share_transfers_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # ============================================
    # NOTES
    # ============================================
    reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='share_transfers_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ============================================
    # META
    # ============================================
    class Meta:
        verbose_name_plural = "🔄 Share Transfers"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transfer_no']),
            models.Index(fields=['from_shareholder', 'to_shareholder']),
            models.Index(fields=['status']),
        ]
    
    # ============================================
    # STRING REPRESENTATION
    # ============================================
    def __str__(self):
        return f"Transfer #{self.transfer_no} - {self.quantity} shares from {self.from_shareholder.name} to {self.to_shareholder.name}"
    
    # ============================================
    # VALUE CALCULATIONS
    # ============================================
    def total_value(self):
        """Calculate total transfer value"""
        return self.quantity * self.transfer_price
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_quantity(self):
        """Formatted quantity with commas"""
        return f"{self.quantity:,}"
    
    @property
    def formatted_value(self):
        """Formatted total value"""
        return f"Rs. {self.total_value():,.2f}"
    
    @property
    def formatted_transfer_price(self):
        """Formatted transfer price per share"""
        return f"Rs. {self.transfer_price:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status display"""
        colors = {
            'completed': 'success',
            'approved': 'primary',
            'pending': 'warning',
            'rejected': 'danger'
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def status_text(self):
        """Plain text status"""
        return self.get_status_display()
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_rejected(self):
        return self.status == 'rejected'
    
    @property
    def is_actionable(self):
        """Check if transfer can be acted upon"""
        return self.status in ['pending', 'approved']
    
    # ============================================
    # BUSINESS METHODS
    # ============================================
    def approve(self, user):
        """Approve transfer"""
        if self.status != 'pending':
            raise ValidationError(f"Transfer is already {self.status}")
        
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Create notification
        try:
            from .models import Notification
            Notification.send(
                user=user,
                title="✅ Transfer Approved",
                message=f"Share transfer #{self.transfer_no} has been approved. {self.quantity} shares from {self.from_shareholder.name} to {self.to_shareholder.name}.",
                notification_type='success',
                category='system',
                link=f"/transfers/{self.id}/"
            )
        except Exception:
            pass
    
    def reject(self, user):
        """Reject transfer"""
        if self.status != 'pending':
            raise ValidationError(f"Transfer is already {self.status}")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Create notification
        try:
            from .models import Notification
            Notification.send(
                user=user,
                title="❌ Transfer Rejected",
                message=f"Share transfer #{self.transfer_no} has been rejected.",
                notification_type='danger',
                category='system',
                link=f"/transfers/{self.id}/"
            )
        except Exception:
            pass
    
    @transaction.atomic
    def complete(self, user):
        """
        Complete transfer - move shares with exact quantity and update cash balances
        """
        from decimal import Decimal
        
        if self.status != 'approved':
            raise ValidationError(f"Transfer must be approved first. Current status: {self.status}")
        
        try:
            with transaction.atomic():
                # ============================================
                # VALIDATE SHAREHOLDER BALANCES
                # ============================================
                total_transfer_value = self.quantity * self.transfer_price
                
                if total_transfer_value > 0:
                    # Check if from_shareholder has enough balance
                    from_balance = ShareholderCashBalance.get_balance(self.from_shareholder)
                    if from_balance < total_transfer_value:
                        raise ValidationError(
                            f"❌ {self.from_shareholder.name} has insufficient balance! "
                            f"Available: Rs. {from_balance:,.2f}, Required: Rs. {total_transfer_value:,.2f}"
                        )
                    
                    # ============================================
                    # DEDUCT FROM SELLER'S BALANCE
                    # ============================================
                    new_from_balance = ShareholderCashBalance.withdraw(
                        shareholder=self.from_shareholder,
                        amount=total_transfer_value,
                        user=user,
                        description=f"Share transfer OUT: {self.quantity} shares @ Rs. {self.transfer_price:,.2f} to {self.to_shareholder.name} - #{self.transfer_no}"
                    )
                    
                    # Create transaction record for from_shareholder
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.from_shareholder,
                        amount=total_transfer_value,
                        transaction_type='transfer_out',
                        balance_after=new_from_balance,
                        description=f"Share transfer to {self.to_shareholder.name} - {self.quantity} shares @ Rs. {self.transfer_price:,.2f}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                    
                    # ============================================
                    # ADD TO BUYER'S BALANCE
                    # ============================================
                    new_to_balance = ShareholderCashBalance.deposit(
                        shareholder=self.to_shareholder,
                        amount=total_transfer_value,
                        user=user,
                        description=f"Share transfer IN: {self.quantity} shares @ Rs. {self.transfer_price:,.2f} from {self.from_shareholder.name} - #{self.transfer_no}"
                    )
                    
                    # Create transaction record for to_shareholder
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.to_shareholder,
                        amount=total_transfer_value,
                        transaction_type='transfer_in',
                        balance_after=new_to_balance,
                        description=f"Share transfer from {self.from_shareholder.name} - {self.quantity} shares @ Rs. {self.transfer_price:,.2f}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                
                # ============================================
                # TRANSFER SHARES
                # ============================================
                remaining_to_transfer = self.quantity
                transferred_shares = []
                
                # Get all shares in the transfer (ordered by issue date - FIFO)
                for share in self.shares.all().order_by('issue_date'):
                    if remaining_to_transfer <= 0:
                        break
                    
                    take = min(share.quantity, remaining_to_transfer)
                    
                    if take <= 0:
                        continue
                    
                    # ============================================
                    # CREATE NEW SHARE FOR RECIPIENT
                    # ============================================
                    new_share = Share(
                        shareholder=self.to_shareholder,
                        share_type=share.share_type,
                        quantity=take,
                        purchase_price=self.transfer_price,  # Transfer price becomes purchase price
                        certificate_number=f"TRF-{self.transfer_no}-{share.id}",
                        issue_date=now().date(),
                        transferred_from=share,
                        transfer_date=now().date(),
                        transfer_notes=f"Transferred from {self.from_shareholder.name} via {self.transfer_no}",
                        created_by=self.created_by or user,
                        paid_from_shareholder_balance=False  # Already handled by transfer
                    )
                    # Bypass cash balance update by using save_base()
                    new_share.save_base()
                    transferred_shares.append(new_share)
                    
                    # ============================================
                    # REDUCE THE OLD SHARE QUANTITY
                    # ============================================
                    share.quantity -= take
                    if share.quantity == 0:
                        share.is_locked = True
                        share.transfer_notes = f"Fully transferred to {self.to_shareholder.name} via {self.transfer_no}"
                    
                    # Bypass cash balance update by using save_base()
                    share.save_base()
                    
                    remaining_to_transfer -= take
                
                # Verify all shares were transferred
                if remaining_to_transfer > 0:
                    raise ValidationError(f"Could not transfer all shares! Remaining: {remaining_to_transfer}")
                
                # ============================================
                # UPDATE TRANSFER STATUS
                # ============================================
                self.status = 'completed'
                self.completed_at = now()
                self.save()
                
                # ============================================
                # CREATE NOTIFICATIONS
                # ============================================
                try:
                    from .models import Notification
                    
                    # Notification for from_shareholder (if user exists)
                    if self.from_shareholder.created_by:
                        Notification.send(
                            user=self.from_shareholder.created_by,
                            title="📤 Shares Transferred Out",
                            message=f"{self.quantity} shares transferred to {self.to_shareholder.name}. Amount: Rs. {total_transfer_value:,.2f}",
                            notification_type='success',
                            category='system',
                            link=f"/transfers/{self.id}/"
                        )
                    
                    # Notification for to_shareholder (if user exists)
                    if self.to_shareholder.created_by:
                        Notification.send(
                            user=self.to_shareholder.created_by,
                            title="📥 Shares Received",
                            message=f"{self.quantity} shares received from {self.from_shareholder.name}. Amount: Rs. {total_transfer_value:,.2f}",
                            notification_type='success',
                            category='system',
                            link=f"/transfers/{self.id}/"
                        )
                except Exception:
                    pass
                
                return transferred_shares
                
        except ValidationError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error completing share transfer: {str(e)}")
            raise ValidationError(f"Failed to complete transfer: {str(e)}")
    
    # ============================================
    # CANCEL TRANSFER (Rollback)
    # ============================================
    @transaction.atomic
    def cancel(self, user):
        """
        Cancel a completed transfer - reverse all transactions
        """
        if self.status != 'completed':
            raise ValidationError(f"Cannot cancel a transfer that is not completed. Current status: {self.status}")
        
        try:
            with transaction.atomic():
                total_value = self.quantity * self.transfer_price
                
                if total_value > 0:
                    # ============================================
                    # REVERSE SHAREHOLDER BALANCES
                    # ============================================
                    # Refund to from_shareholder
                    new_from_balance = ShareholderCashBalance.deposit(
                        shareholder=self.from_shareholder,
                        amount=total_value,
                        user=user,
                        description=f"Transfer cancellation refund: #{self.transfer_no}"
                    )
                    
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.from_shareholder,
                        amount=total_value,
                        transaction_type='deposit',
                        balance_after=new_from_balance,
                        description=f"Refund for cancelled transfer #{self.transfer_no}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                    
                    # Deduct from to_shareholder
                    try:
                        new_to_balance = ShareholderCashBalance.withdraw(
                            shareholder=self.to_shareholder,
                            amount=total_value,
                            user=user,
                            description=f"Transfer cancellation deduction: #{self.transfer_no}"
                        )
                    except ValidationError:
                        # If buyer doesn't have enough balance, we need to handle differently
                        # This is a complex case - maybe use main cash as backup
                        main_balance = CashBalance.get_balance()
                        if main_balance < total_value:
                            raise ValidationError(
                                f"Cannot cancel transfer! {self.to_shareholder.name} doesn't have enough balance "
                                f"and main cash is also insufficient."
                            )
                        
                        CashBalance.update_balance(
                            amount=total_value,
                            transaction_type='withdraw',
                            user=user,
                            description=f"Transfer cancellation from {self.to_shareholder.name} - #{self.transfer_no}"
                        )
                    
                    # ============================================
                    # REVERSE SHARE MOVEMENTS
                    # ============================================
                    # Restore original shares (simplified - in real system, need proper tracking)
                    # This is a simplified version - in production, you'd track this more carefully
                    
                # Update status
                self.status = 'rejected'
                self.notes = f"{self.notes}\nCancelled by {user.username}".strip()
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to cancel transfer: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Generate transfer number on save"""
        if not self.transfer_no:
            last_transfer = ShareTransfer.objects.order_by('-id').first()
            if last_transfer and last_transfer.transfer_no:
                try:
                    last_num = int(last_transfer.transfer_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.transfer_no = f'ST-{new_num}'
        super().save(*args, **kwargs)


class ShareholderMeeting(models.Model):
    """Shareholder meetings and minutes"""
    MEETING_TYPES = [
        ('agm', 'Annual General Meeting'),
        ('egm', 'Extraordinary General Meeting'),
        ('board', 'Board Meeting'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('held', 'Held'),
        ('cancelled', 'Cancelled'),
        ('adjourned', 'Adjourned'),
    ]
    
    meeting_no = models.CharField(max_length=20, unique=True, editable=False)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES)
    title = models.CharField(max_length=255)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    venue = models.TextField()
    agenda = models.TextField()
    minutes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Attendance
    attendees = models.ManyToManyField(Shareholder, through='MeetingAttendance', related_name='meetings')
    total_attendees = models.PositiveIntegerField(default=0)
    
    # Resolutions
    resolutions = models.TextField(blank=True, null=True)
    resolutions_passed = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_meetings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "📋 Shareholder Meetings"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['meeting_no']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"#{self.meeting_no} - {self.title} ({self.date.strftime('%d-%m-%Y')})"
    
    def save(self, *args, **kwargs):
        if not self.meeting_no:
            last_meeting = ShareholderMeeting.objects.order_by('-id').first()
            if last_meeting and last_meeting.meeting_no:
                try:
                    last_num = int(last_meeting.meeting_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.meeting_no = f'MTG-{new_num}'
        super().save(*args, **kwargs)


class MeetingAttendance(models.Model):
    """Meeting attendance record"""
    ATTENDANCE_STATUS = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('proxy', 'Proxy'),
        ('online', 'Online'),
    ]
    
    meeting = models.ForeignKey(ShareholderMeeting, on_delete=models.CASCADE, related_name='attendance_records')
    shareholder = models.ForeignKey(Shareholder, on_delete=models.CASCADE, related_name='meeting_attendance')
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS)
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Meeting Attendance"
        unique_together = ['meeting', 'shareholder']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.get_status_display()}"
        
# models.py - Complete ShareholderCashBalance

class ShareholderCashBalance(models.Model):
    """Har shareholder ka apna cash balance"""
    
    shareholder = models.OneToOneField(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='cash_balance',
        unique=True
    )
    balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        verbose_name_plural = "💰 Shareholder Cash Balances"
        ordering = ['shareholder__name']
        indexes = [
            models.Index(fields=['shareholder']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.balance:,.2f}"
    
    @classmethod
    def get_balance(cls, shareholder):
        """Get balance for a specific shareholder"""
        balance_obj, created = cls.objects.get_or_create(
            shareholder=shareholder,
            defaults={'balance': Decimal('0.00')}
        )
        return balance_obj.balance
    
    @classmethod
    def update_balance(cls, shareholder, amount, transaction_type, user=None, description=""):
        """Update shareholder's cash balance with transaction record"""
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            balance_obj, created = cls.objects.select_for_update().get_or_create(
                shareholder=shareholder,
                defaults={'balance': Decimal('0.00')}
            )
            
            old_balance = balance_obj.balance
            
            if transaction_type == 'deposit':
                balance_obj.balance += amount
            elif transaction_type == 'withdraw':
                if balance_obj.balance < amount:
                    raise ValidationError(
                        f"Insufficient balance for {shareholder.name}! "
                        f"Available: Rs. {balance_obj.balance:,.2f}, Required: Rs. {amount:,.2f}"
                    )
                balance_obj.balance -= amount
            else:
                raise ValidationError(f"Invalid transaction type: {transaction_type}")
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # Create transaction record
            ShareholderCashTransaction.objects.get_or_create(
                shareholder=shareholder,
                transaction_type=transaction_type,
                amount=amount,
                balance_after=balance_obj.balance,
                defaults={
                    'description': description,
                    'created_by': user
                }
            )
            
            return balance_obj.balance
    
    @classmethod
    def deposit(cls, shareholder, amount, user=None, description=""):
        """Deposit money into shareholder's cash balance"""
        return cls.update_balance(shareholder, amount, 'deposit', user, description)
    
    @classmethod
    def withdraw(cls, shareholder, amount, user=None, description=""):
        """Withdraw money from shareholder's cash balance"""
        return cls.update_balance(shareholder, amount, 'withdraw', user, description)
    
    # ========================================== #
    # ✅ NEW: Withdraw from both balances        #
    # ========================================== #
    @classmethod
    def withdraw_from_main_cash(cls, shareholder, amount, user=None, description=""):
        """
        Withdraw from shareholder balance AND main cash
        ✅ Called when shareholder actually withdraws money
        """
        from django.db import transaction as db_transaction
        from .models import CashBalance
        
        with db_transaction.atomic():
            # Step 1: Deduct from shareholder balance
            new_balance = cls.withdraw(
                shareholder=shareholder,
                amount=amount,
                user=user,
                description=description
            )
            
            # Step 2: Deduct from main cash
            CashBalance.update_balance(
                amount=amount,
                transaction_type='withdraw',
                user=user,
                description=f"Shareholder withdrawal: {shareholder.name} - {description}"
            )
            
            return new_balance
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

# models.py - Complete ShareholderCashTransaction

class ShareholderCashTransaction(models.Model):
    """Shareholder cash transaction history"""
    
    TRANSACTION_TYPES = [
        ('deposit', '💰 Deposit (Added)'),
        ('withdraw', '💸 Withdrawal (Removed)'),
        ('share_purchase', '📈 Share Purchase'),
        ('dividend', '💵 Dividend Received'),
        ('balance_dividend', '💵 Balance Dividend (Refund + Profit)'),
        ('transfer_in', '🔄 Transfer In'),
        ('transfer_out', '🔄 Transfer Out'),
        ('adjustment', '📝 Adjustment'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='cash_transactions'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    # Keep existing fields
    share = models.ForeignKey(
        'Share', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    dividend_payment = models.ForeignKey(
        'DividendPayment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cash_transactions'
    )
    
    # Balance dividend payment
    balance_dividend_payment = models.ForeignKey(
        'BalanceDividendPayment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cash_transactions'
    )
    
    share_transfer = models.ForeignKey(
        'ShareTransfer', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 Shareholder Cash Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shareholder']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]
        unique_together = [
            ['shareholder', 'transaction_type', 'amount', 'balance_after', 'created_at']
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.get_transaction_type_display()} - Rs. {self.amount:,.2f}"
    
    @property
    def formatted_amount(self):
        if self.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']:
            return f"+Rs. {self.amount:,.2f}"
        return f"-Rs. {self.amount:,.2f}"
    
    @property
    def is_deposit(self):
        return self.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    
    @property
    def is_withdraw(self):
        return self.transaction_type in ['withdraw', 'share_purchase', 'transfer_out']

class DividendReinvestmentPlan(models.Model):
    """DRIP settings per dividend"""
    
    DRIP_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('market', 'Market Price'),
    ]
    
    dividend = models.OneToOneField(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='drip',
        help_text="Dividend for which DRIP is available"
    )
    plan_name = models.CharField(
        max_length=200,
        default='Dividend Reinvestment Plan',
        help_text="Name of the DRIP plan"
    )
    
    discount_type = models.CharField(
        max_length=20, 
        choices=DISCOUNT_TYPES, 
        default='percentage'
    )
    discount_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Discount on share price (e.g., 5 for 5%)"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee per reinvestment"
    )
    
    min_shares = models.PositiveIntegerField(
        default=1,
        help_text="Minimum shares to reinvest"
    )
    max_shares = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maximum shares to reinvest (optional)"
    )
    
    start_date = models.DateField(
        help_text="Date when DRIP becomes available"
    )
    end_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when DRIP expires (optional)"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=DRIP_STATUS, 
        default='active'
    )
    is_auto_enroll = models.BooleanField(
        default=False,
        help_text="Auto-enroll all eligible shareholders"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Default DRIP for all dividends"
    )
    
    round_down_to_nearest = models.PositiveIntegerField(
        default=1,
        help_text="Round down shares to nearest integer"
    )
    fractional_shares_allowed = models.BooleanField(
        default=False,
        help_text="Allow fractional shares"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_drips'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Dividend Reinvestment Plans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP - {self.dividend.dividend_no} ({self.get_discount_type_display()})"
    
    def calculate_shares(self, dividend_amount, share_price):
        """Calculate number of shares to reinvest"""
        if self.discount_type == 'percentage':
            effective_price = share_price * (1 - self.discount_value / 100)
        elif self.discount_type == 'fixed':
            effective_price = share_price - self.discount_value
        else:
            effective_price = share_price
        
        amount_after_fee = dividend_amount - self.admin_fee
        
        if amount_after_fee <= 0:
            return 0
        
        shares = amount_after_fee / effective_price
        
        if not self.fractional_shares_allowed:
            shares = int(shares // self.round_down_to_nearest) * self.round_down_to_nearest
        
        if self.max_shares:
            shares = min(shares, self.max_shares)
        if self.min_shares and shares < self.min_shares:
            shares = 0
        
        return shares


class ShareholderDRIPEnrollment(models.Model):
    """Shareholder enrollment in DRIP"""
    
    ENROLLMENT_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='drip_enrollments'
    )
    drip = models.ForeignKey(
        DividendReinvestmentPlan, 
        on_delete=models.CASCADE, 
        related_name='enrollments'
    )
    
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=ENROLLMENT_STATUS, 
        default='active'
    )
    auto_reinvest = models.BooleanField(
        default=True,
        help_text="Auto-reinvest future dividends"
    )
    min_dividend_to_reinvest = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=500,
        help_text="Minimum dividend amount to trigger reinvestment"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_enrollments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Shareholder Enrollments"
        unique_together = ['shareholder', 'drip']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.drip.plan_name}"
    
    def is_eligible(self, dividend_amount):
        """Check if shareholder is eligible for reinvestment"""
        if self.status != 'active':
            return False
        if not self.auto_reinvest:
            return False
        if dividend_amount < self.min_dividend_to_reinvest:
            return False
        return True


class DRIPTransaction(models.Model):
    """DRIP transaction record"""
    
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    dividend_payment = models.ForeignKey(
        'DividendPayment', 
        on_delete=models.CASCADE, 
        related_name='drip_transactions'
    )
    enrollment = models.ForeignKey(
        ShareholderDRIPEnrollment, 
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    new_shares = models.ManyToManyField(
        'Share', 
        blank=True, 
        related_name='drip_transactions'
    )
    
    dividend_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Original dividend amount"
    )
    shares_purchased = models.PositiveIntegerField(
        default=0,
        help_text="Number of shares purchased"
    )
    purchase_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Price per share"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee deducted"
    )
    total_cost = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Total cost of reinvestment"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=TRANSACTION_STATUS, 
        default='pending'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    reference_no = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Transactions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP {self.reference_no} - {self.dividend_payment.shareholder.name}"
    
    def save(self, *args, **kwargs):
        if not self.reference_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.reference_no = f'DRIP-{timestamp}-{self.dividend_payment.id}'
        super().save(*args, **kwargs)
    
    def process(self):
        """Process the DRIP transaction"""
        from decimal import Decimal
        from django.db import transaction
        
        try:
            with transaction.atomic():
                drip = self.enrollment.drip
                share_price = SharePrice.objects.filter(is_active=True).first()
                
                if not share_price:
                    self.status = 'failed'
                    self.notes = "No active share price found"
                    self.save()
                    return False
                
                shares = drip.calculate_shares(
                    self.dividend_amount,
                    share_price.price
                )
                
                if shares <= 0:
                    self.status = 'failed'
                    self.notes = "Insufficient amount to purchase shares"
                    self.save()
                    return False
                
                shareholder = self.dividend_payment.shareholder
                
                new_share = Share.objects.create(
                    shareholder=shareholder,
                    quantity=shares,
                    purchase_price=share_price.price,
                    share_type='ordinary',
                    issue_date=now().date(),
                    created_by=self.created_by,
                    paid_from_shareholder_balance=False,
                    notes=f"DRIP purchase from dividend #{self.dividend_payment.dividend.dividend_no}"
                )
                
                new_share.certificate_number = f"DRIP-{new_share.id:06d}"
                new_share.certificate_issue_date = now().date()
                new_share.save()
                
                self.new_shares.add(new_share)
                self.shares_purchased = shares
                self.purchase_price = share_price.price
                self.total_cost = shares * share_price.price
                self.status = 'completed'
                self.completed_at = now()
                
                self.dividend_payment.status = 'paid'
                self.dividend_payment.payment_date = now()
                self.dividend_payment.payment_method = 'DRIP (Dividend Reinvestment)'
                self.dividend_payment.notes = f"Reinvested as {shares} shares via DRIP"
                self.dividend_payment.save()
                
                self.save()
                return True
                
        except Exception as e:
            self.status = 'failed'
            self.notes = str(e)
            self.save()
            return False
            
# ============================================
# SHARE BUYBACK MODELS
# ============================================

class ShareBuyback(models.Model):
    """Company share buyback program"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    BUYBACK_TYPES = [
        ('open_market', 'Open Market'),
        ('tender', 'Tender Offer'),
        ('negotiated', 'Negotiated'),
    ]
    
    # Basic Information
    buyback_no = models.CharField(max_length=20, unique=True, editable=False)
    buyback_type = models.CharField(max_length=20, choices=BUYBACK_TYPES, default='open_market')
    description = models.CharField(max_length=255, help_text="Purpose of buyback")
    
    # Financial Details
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Total budget for buyback")
    price_per_share = models.DecimalField(max_digits=15, decimal_places=2, help_text="Price per share")
    min_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_shares = models.PositiveIntegerField(help_text="Maximum shares to buyback")
    shares_bought = models.PositiveIntegerField(default=0, help_text="Shares already bought")
    amount_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    record_date = models.DateField(help_text="Shareholders eligible for buyback")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_buybacks')
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_buybacks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Share Buybacks"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.buyback_no} - {self.get_buyback_type_display()} (Rs. {self.total_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.buyback_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = ShareBuyback.objects.filter(buyback_no__startswith=f'BB-{year}').order_by('-buyback_no').first()
            if last:
                try:
                    last_num = int(last.buyback_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.buyback_no = f'BB-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def remaining_shares(self):
        return self.max_shares - self.shares_bought
    
    def remaining_amount(self):
        return self.total_amount - self.amount_spent
    
    def progress_percent(self):
        if self.max_shares > 0:
            return (self.shares_bought / self.max_shares) * 100
        return 0
    
    def is_active(self):
        from django.utils.timezone import now
        return self.status in ['approved', 'in_progress'] and self.end_date >= now().date()


class BuybackOffer(models.Model):
    """Shareholder offer to sell shares in buyback"""
    
    OFFER_STATUS = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    buyback = models.ForeignKey(ShareBuyback, on_delete=models.CASCADE, related_name='offers')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='buyback_offers')
    shares_offered = models.PositiveIntegerField()
    shares_accepted = models.PositiveIntegerField(default=0)
    price_offered = models.DecimalField(max_digits=15, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=OFFER_STATUS, default='pending')
    offer_date = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='buyback_offers')
    
    class Meta:
        verbose_name_plural = "Buyback Offers"
        unique_together = ['buyback', 'shareholder']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.shares_offered} shares"
    
    def accept(self, shares_accepted=None):
        from django.utils.timezone import now
        if shares_accepted is None:
            shares_accepted = self.shares_offered
        self.shares_accepted = shares_accepted
        self.total_amount = shares_accepted * self.price_offered
        self.status = 'accepted'
        self.processed_at = now()
        self.save()
        
        # Update buyback
        self.buyback.shares_bought += shares_accepted
        self.buyback.amount_spent += self.total_amount
        self.buyback.save()
        
        # Transfer shares to company
        self.transfer_shares_to_company(shares_accepted)
    
    def transfer_shares_to_company(self, shares):
        """Transfer shares from shareholder to company"""
        # Get shareholder shares (FIFO)
        shares_to_transfer = self.shareholder.shares.filter(
            is_locked=False,
            quantity__gt=0
        ).order_by('issue_date')
        
        remaining = shares
        for share in shares_to_transfer:
            if remaining <= 0:
                break
            take = min(share.quantity, remaining)
            
            # Reduce shareholder's shares
            share.quantity -= take
            if share.quantity == 0:
                share.is_locked = True
            share.save()
            
            # Create company share (treasury)
            company_share = Share.objects.create(
                shareholder=None,  # Company own shares
                quantity=take,
                purchase_price=self.price_offered,
                share_type='treasury',
                issue_date=now().date(),
                notes=f"Buyback {self.buyback.buyback_no}",
                is_locked=True,
                paid_from_shareholder_balance=False,
                certificate_number=f"TR-{self.buyback.buyback_no}"
            )
            remaining -= take
        
        # Update shareholder's cash balance (they get money)
        ShareholderCashBalance.deposit(
            shareholder=self.shareholder,
            amount=self.total_amount,
            user=self.created_by,
            description=f"Share buyback {self.buyback.buyback_no} - {shares} shares @ Rs. {self.price_offered:,.2f}"
        )


# ============================================
# SHAREHOLDER DISCOUNT PROGRAM
# ============================================

class ShareholderDiscountProgram(models.Model):
    """Discount program for shareholders"""
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('tiered', 'Tiered Discount'),
    ]
    
    name = models.CharField(max_length=100)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=5, decimal_places=2, help_text="Discount % or fixed amount")
    
    min_shares_required = models.PositiveIntegerField(default=1)
    max_shares_required = models.PositiveIntegerField(null=True, blank=True)
    
    min_holding_period = models.IntegerField(default=0, help_text="Minimum months held")
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Product restrictions
    apply_to_all_products = models.BooleanField(default=True)
    products = models.ManyToManyField('Product', blank=True, related_name='discount_programs')
    categories = models.ManyToManyField('Category', blank=True, related_name='discount_programs')
    
    # Usage limits
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_per_shareholder = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    min_order_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher number = higher priority")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_discounts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Discount Programs"
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.discount_value}% off)"
    
    def get_discount_amount(self, shareholder, product=None, amount=0):
        """Calculate discount for shareholder"""
        if not self.is_active:
            return 0
        
        # Check share requirement
        shares = shareholder.total_shares()
        if shares < self.min_shares_required:
            return 0
        if self.max_shares_required and shares > self.max_shares_required:
            return 0
        
        # Check holding period
        if self.min_holding_period > 0:
            first_share = shareholder.shares.order_by('issue_date').first()
            if not first_share:
                return 0
            from datetime import date
            months_held = (date.today() - first_share.issue_date).days // 30
            if months_held < self.min_holding_period:
                return 0
        
        # Check product eligibility
        if not self.apply_to_all_products and product:
            if not self.products.filter(id=product.id).exists():
                if not self.categories.filter(id=product.category.id).exists():
                    return 0
        
        # Check min order
        if amount < self.min_order_amount:
            return 0
        
        # Check uses
        if self.max_uses > 0:
            uses = ShareholderDiscountUsage.objects.filter(program=self).count()
            if uses >= self.max_uses:
                return 0
        
        # Calculate discount
        if self.discount_type == 'percentage':
            return amount * (self.discount_value / 100)
        elif self.discount_type == 'fixed':
            return self.discount_value
        elif self.discount_type == 'tiered':
            # Tiered logic - can be customized
            if shares >= 1000:
                return amount * 0.15  # 15% for 1000+ shares
            elif shares >= 500:
                return amount * 0.10  # 10% for 500+ shares
            elif shares >= 100:
                return amount * 0.05   # 5% for 100+ shares
            else:
                return 0
        
        return 0


class ShareholderDiscountUsage(models.Model):
    """Track discount usage"""
    
    program = models.ForeignKey(ShareholderDiscountProgram, on_delete=models.CASCADE, related_name='usages')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='discount_usages')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, related_name='discount_usages')
    
    original_amount = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2)
    final_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    used_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Discount Usages"
        ordering = ['-used_at']
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.discount_amount:,.2f} off"


# ============================================
# SHAREHOLDER LOAN MANAGEMENT
# ============================================

class ShareholderLoan(models.Model):
    """Loans against shares"""
    
    LOAN_STATUS = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('partial_paid', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]
    
    LOAN_TYPES = [
        ('margin', 'Margin Loan'),
        ('pledge', 'Share Pledge'),
        ('personal', 'Personal Loan'),
        ('business', 'Business Loan'),
    ]
    
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='margin')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='loans')
    
    # Loan Details
    principal = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Annual interest rate %")
    disbursed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    outstanding = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Collateral
    collateral_shares = models.ManyToManyField('Share', related_name='loans', blank=True)
    collateral_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ltv_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=60, help_text="Loan to Value %")
    
    # Dates
    start_date = models.DateField()
    maturity_date = models.DateField()
    approval_date = models.DateField(null=True, blank=True)
    disbursement_date = models.DateField(null=True, blank=True)
    
    # Interest
    interest_accrued = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_interest_date = models.DateField(null=True, blank=True)
    
    # Fees
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_loans')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_loans')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Loans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.loan_no} - {self.shareholder.name} (Rs. {self.principal:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = ShareholderLoan.objects.filter(loan_no__startswith=f'LN-{year}').order_by('-loan_no').first()
            if last:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LN-{year}-{new_num}'
        self.outstanding = self.principal - self.disbursed_amount
        super().save(*args, **kwargs)
    
    def calculate_interest(self, days=None):
        """Calculate interest for given days"""
        from datetime import date
        if days is None:
            today = date.today()
            if self.last_interest_date:
                days = (today - self.last_interest_date).days
            else:
                days = (today - self.start_date).days
        
        if days <= 0:
            return 0
        
        daily_rate = self.interest_rate / 100 / 365
        return self.outstanding * daily_rate * days
    
    def accrue_interest(self):
        """Accrue interest automatically"""
        from django.utils.timezone import now
        interest = self.calculate_interest()
        if interest > 0:
            self.interest_accrued += interest
            self.last_interest_date = now().date()
            self.save()
        return interest
    
    def make_payment(self, amount, payment_method=None):
        """Make loan payment"""
        from decimal import Decimal
        from django.db import transaction
        
        with transaction.atomic():
            # First pay interest
            if self.interest_accrued > 0:
                interest_payment = min(amount, self.interest_accrued)
                self.interest_accrued -= interest_payment
                self.interest_paid += interest_payment
                amount -= interest_payment
                InterestPayment.objects.create(
                    loan=self,
                    amount=interest_payment,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    notes="Interest payment"
                )
            
            # Then pay principal
            if amount > 0:
                principal_payment = min(amount, self.outstanding)
                self.outstanding -= principal_payment
                self.disbursed_amount += principal_payment
                
                PrincipalPayment.objects.create(
                    loan=self,
                    amount=principal_payment,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    notes="Principal payment"
                )
            
            # Update status
            if self.outstanding <= 0 and self.interest_accrued <= 0:
                self.status = 'paid'
            
            self.save()
    
    def get_ltv_percent(self):
        """Calculate Loan to Value percentage"""
        if self.collateral_value > 0:
            return (self.outstanding / self.collateral_value) * 100
        return 0
    
    def is_margin_call(self):
        """Check if margin call needed"""
        ltv = self.get_ltv_percent()
        return ltv > self.ltv_ratio


class LoanPayment(models.Model):
    """Base loan payment (abstract)"""
    
    class Meta:
        abstract = True
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InterestPayment(LoanPayment):
    """Interest payment record"""
    
    class Meta:
        verbose_name_plural = "Interest Payments"
    
    def __str__(self):
        return f"Interest - {self.loan.loan_no} - Rs. {self.amount:,.2f}"


class PrincipalPayment(LoanPayment):
    """Principal payment record"""
    
    class Meta:
        verbose_name_plural = "Principal Payments"
    
    def __str__(self):
        return f"Principal - {self.loan.loan_no} - Rs. {self.amount:,.2f}"
        
# ============================================
# SERVICE MANAGEMENT MODELS
# ============================================

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
        
# ============================================
# SERVICE INVENTORY MODELS - Complete
# ============================================

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
        
# ============================================
# DEPARTMENT & PROJECT MODELS
# ============================================

class Department(models.Model):
    """Department model for cost centers"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Departments"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.name[:3].upper()
        super().save(*args, **kwargs)


class Project(models.Model):
    """Project model for project-wise expenses"""
    
    STATUS_CHOICES = [
        ('active', '✅ Active'),
        ('completed', '🎯 Completed'),
        ('on_hold', '⏸️ On Hold'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Projects"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            last_project = Project.objects.order_by('-id').first()
            if last_project and last_project.code:
                try:
                    last_num = int(last_project.code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'PRJ-{new_num}'
        super().save(*args, **kwargs)
    
    def total_expenses(self):
        return self.expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    def remaining_budget(self):
        return self.budget - self.total_expenses()

class ExpenseCategory(models.Model):
    """Hierarchical expense categories"""
    
    CATEGORY_TYPES = [
        ('operating', 'Operating Expenses'),
        ('capital', 'Capital Expenses'),
        ('administrative', 'Administrative Expenses'),
        ('selling', 'Selling Expenses'),
        ('research', 'Research & Development'),
        ('other', 'Other Expenses'),
    ]
    
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, default='operating')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    code = models.CharField(max_length=20, unique=True, editable=False)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['category_type']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            last_cat = ExpenseCategory.objects.order_by('-id').first()
            if last_cat and last_cat.code:
                try:
                    last_num = int(last_cat.code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'EC-{new_num}'
        super().save(*args, **kwargs)
    
    def get_full_path(self):
        """Get full category path"""
        if self.parent:
            return f"{self.parent.get_full_path()} > {self.name}"
        return self.name
    
    def get_all_children(self):
        """Get all children categories recursively"""
        children = []
        for child in self.children.filter(is_active=True):
            children.append(child)
            children.extend(child.get_all_children())
        return children

class Budget(models.Model):
    """Main Budget Model"""
    
    BUDGET_TYPES = [
        ('department', '🏢 Department Budget'),
        ('project', '📋 Project Budget'),
        ('category', '📂 Category Budget'),
        ('annual', '📅 Annual Budget'),
        ('quarterly', '📊 Quarterly Budget'),
        ('monthly', '📆 Monthly Budget'),
        ('flexible', '🔄 Flexible Budget'),
    ]
    
    BUDGET_STATUS = [
        ('draft', '📝 Draft'),
        ('pending', '⏳ Pending Approval'),
        ('approved', '✅ Approved'),
        ('active', '✅ Active'),
        ('review', '📋 Under Review'),
        ('expired', '⏰ Expired'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    BUDGET_FREQUENCY = [
        ('one_time', 'One Time'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('half_yearly', 'Half Yearly'),
        ('yearly', 'Yearly'),
    ]
    
    # Basic Information
    budget_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    budget_type = models.CharField(max_length=20, choices=BUDGET_TYPES)
    description = models.TextField(blank=True, null=True)
    
    # Budget Details
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reserved_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Time Period
    period_start = models.DateField()
    period_end = models.DateField()
    frequency = models.CharField(max_length=20, choices=BUDGET_FREQUENCY, default='monthly')
    
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_items')
    
    # Status
    status = models.CharField(max_length=20, choices=BUDGET_STATUS, default='draft')
    
    # Alert Thresholds
    alert_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    critical_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=95)
    
    # Approval
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='approved_budget_items')
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='submitted_budget_items')
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # Rollover
    allow_rollover = models.BooleanField(default=False)
    rollover_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='created_budget_items')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Budgets"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['budget_no']),
            models.Index(fields=['budget_type']),
            models.Index(fields=['status']),
            models.Index(fields=['period_start', 'period_end']),
        ]
    
    def __str__(self):
        return f"{self.budget_no} - {self.name} (Rs. {self.allocated_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        from datetime import datetime
        if not self.budget_no:
            year = datetime.now().strftime('%Y')
            last_budget = Budget.objects.filter(budget_no__startswith=f'BDG-{year}').order_by('-budget_no').first()
            if last_budget and last_budget.budget_no:
                try:
                    last_num = int(last_budget.budget_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.budget_no = f'BDG-{year}-{new_num}'
        
        self.remaining_amount = self.allocated_amount - self.used_amount - self.reserved_amount
        super().save(*args, **kwargs)
    
    def calculate_used(self):
        """Calculate used amount from linked expenses"""
        from django.db.models import Sum
        from .models import Expense
        
        # ✅ INCLUDING PAID STATUS
        used = Expense.objects.filter(
            budget=self,
            status__in=['approved', 'paid'],
            expense_date__gte=self.period_start,
            expense_date__lte=self.period_end
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        self.used_amount = used
        self.remaining_amount = self.allocated_amount - used - self.reserved_amount
        self.save(update_fields=['used_amount', 'remaining_amount'])
        return used
    
    def utilization_percent(self):
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return 0
    
    def is_over_budget(self):
        return self.used_amount > self.allocated_amount
    
    def remaining_days(self):
        from datetime import date
        if self.period_end:
            return (self.period_end - date.today()).days
        return 0
    
    def daily_allowance(self):
        days = self.remaining_days()
        if days > 0 and self.remaining_amount > 0:
            return self.remaining_amount / days
        return 0
    
    def submit(self, user):
        from django.utils.timezone import now
        self.status = 'pending'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        from django.utils.timezone import now
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    def activate(self, user):
        self.status = 'active'
        self.save()
    
    def get_status_badge(self):
        colors = {
            'draft': 'secondary',
            'pending': 'warning',
            'approved': 'primary',
            'active': 'success',
            'review': 'info',
            'expired': 'danger',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'

class BudgetAllocation(models.Model):
    """Detailed budget allocation by sub-category"""
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='allocations')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.CASCADE, related_name='budget_allocations')
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Budget Allocations"
        unique_together = ['budget', 'category']
    
    def __str__(self):
        return f"{self.budget.name} - {self.category.name} (Rs. {self.allocated_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        self.remaining_amount = self.allocated_amount - self.used_amount
        super().save(*args, **kwargs)
    
    def utilization_percent(self):
        """Calculate utilization percentage for this allocation"""
        from decimal import Decimal
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return Decimal('0.00')


class BudgetTransaction(models.Model):
    """Track budget transactions"""
    
    TRANSACTION_TYPES = [
        ('allocation', '💰 Budget Allocated'),
        ('adjustment', '📝 Budget Adjusted'),
        ('transfer', '🔄 Budget Transferred'),
        ('expense', '📤 Expense Deducted'),
        ('reserve', '🔒 Budget Reserved'),
        ('release', '🔓 Budget Released'),
        ('rollover', '🔄 Budget Rollover'),
    ]
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField()
    expense = models.ForeignKey('Expense', on_delete=models.SET_NULL, null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Budget Transactions"
        ordering = ['-performed_at']
    
    def __str__(self):
        return f"{self.budget.budget_no} - {self.get_transaction_type_display()} (Rs. {self.amount:,.2f})"


class BudgetAlert(models.Model):
    """Budget alerts and notifications"""
    
    ALERT_TYPES = [
        ('warning', '⚠️ Warning'),
        ('critical', '🔴 Critical'),
        ('over_budget', '❌ Over Budget'),
        ('expiring', '⏰ Expiring'),
    ]
    
    ALERT_STATUS = [
        ('new', '🆕 New'),
        ('read', '📖 Read'),
        ('acknowledged', '✅ Acknowledged'),
        ('resolved', '✅ Resolved'),
    ]
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=ALERT_STATUS, default='new')
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='resolved_budget_alerts')
    
    class Meta:
        verbose_name_plural = "Budget Alerts"
        ordering = ['-triggered_at']
    
    def __str__(self):
        return f"{self.budget.budget_no} - {self.get_alert_type_display()}"
    
    def resolve(self, user):
        self.status = 'resolved'
        self.resolved_at = now()
        self.resolved_by = user
        self.save()


class BudgetForecast(models.Model):
    """Budget forecasting"""
    
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField()
    forecasted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Budget Forecasts"
        ordering = ['forecast_date']
    
    def __str__(self):
        return f"{self.budget.name} - {self.forecast_date.strftime('%B %Y')}"
    
    def calculate_variance(self):
        if self.forecasted_amount > 0:
            self.variance = self.actual_amount - self.forecasted_amount
            self.variance_percent = (self.variance / self.forecasted_amount) * 100
        return self.variance

# ============================================
# PROFESSIONAL EXPENSES MODULE - MODELS
# ============================================




class ExpenseBudget(models.Model):
    """Department/project wise budgets"""
    
    BUDGET_PERIODS = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('project', 'Project Based'),
    ]
    
    BUDGET_STATUS = [
        ('draft', '📝 Draft'),
        ('active', '✅ Active'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('expired', '⏰ Expired'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='budgets')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_budgets')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_budgets')
    
    budget_period = models.CharField(max_length=20, choices=BUDGET_PERIODS, default='monthly')
    period_start = models.DateField()
    period_end = models.DateField()
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    used_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=BUDGET_STATUS, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_budgets')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_budgets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expense Budgets"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'department']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.category.name}) - Rs. {self.allocated_amount:,.2f}"
    
    def calculate_used(self):
        """Calculate used amount from expenses"""
        used = Expense.objects.filter(
            category=self.category,
            expense_date__gte=self.period_start,
            expense_date__lte=self.period_end,
            status='approved'
        ).aggregate(total=Sum('amount'))['total'] or 0
        self.used_amount = used
        self.remaining_amount = self.allocated_amount - used
        self.save(update_fields=['used_amount', 'remaining_amount'])
        return used
    
    def is_over_budget(self):
        """Check if budget is exceeded"""
        return self.remaining_amount < 0
    
    def budget_utilization_percent(self):
        """Calculate budget utilization percentage"""
        if self.allocated_amount > 0:
            return (self.used_amount / self.allocated_amount) * 100
        return 0


class Expense(models.Model):
    """Main Expense Model with Professional Features"""
    
    EXPENSE_STATUS = [
        ('draft', '📝 Draft'),
        ('submitted', '📤 Submitted'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('paid', '💰 Paid'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', '💵 Cash'),
        ('bank_transfer', '🏦 Bank Transfer'),
        ('credit_card', '💳 Credit Card'),
        ('debit_card', '💳 Debit Card'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Payment'),
        ('other', '📋 Other'),
    ]
    
    # Basic Information
    expense_no = models.CharField(max_length=20, unique=True, editable=False)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='expenses')
    description = models.TextField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    expense_date = models.DateField()
    
    # Additional Details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    vendor_invoice_no = models.CharField(max_length=100, blank=True, null=True)
    
    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    
    # Budget & Cost Center
    budget = models.ForeignKey(Budget, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    cost_center = models.CharField(max_length=100, blank=True, null=True)
    
    # Approval
    status = models.CharField(max_length=20, choices=EXPENSE_STATUS, default='draft')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_expenses')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_expenses')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Payment
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='paid_expenses')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    
    # Documents
    receipt = models.FileField(upload_to='expenses/receipts/%Y/%m/', null=True, blank=True)
    attachment = models.FileField(upload_to='expenses/attachments/%Y/%m/', null=True, blank=True)
    
    # Recurring
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(max_length=20, choices=ExpenseBudget.BUDGET_PERIODS, null=True, blank=True)
    recurring_end_date = models.DateField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expenses"
        indexes = [
            models.Index(fields=['expense_no']),
            models.Index(fields=['category', 'expense_date']),
            models.Index(fields=['status']),
            models.Index(fields=['vendor']),
        ]
    
    def __str__(self):
        return f"{self.expense_no} - {self.description[:30]} (Rs. {self.amount:,.2f})"
    
    def save(self, *args, **kwargs):
        # Generate expense number
        if not self.expense_no:
            year = datetime.now().strftime('%Y%m')
            last_exp = Expense.objects.filter(expense_no__startswith=f'EXP-{year}').order_by('-expense_no').first()
            if last_exp and last_exp.expense_no:
                try:
                    last_num = int(last_exp.expense_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.expense_no = f'EXP-{year}-{new_num}'
        
        # Calculate total with tax
        self.total_amount = self.amount + self.tax_amount
        
        # Update budget if expense is approved
        if self.pk and self.status == 'approved':
            try:
                old_status = Expense.objects.get(pk=self.pk).status
                if old_status != 'approved' and self.budget:
                    self.budget.calculate_used()
            except Expense.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def submit(self, user):
        """Submit expense for approval"""
        self.status = 'submitted'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        """Approve expense"""
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Update budget
        if self.budget:
            self.budget.calculate_used()
    
    def reject(self, user, reason=""):
        """Reject expense"""
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejection_reason = reason
        self.save()
    
    def mark_paid(self, user, payment_date=None):
        """Mark expense as paid"""
        self.status = 'paid'
        self.paid_by = user
        self.paid_at = now()
        self.payment_date = payment_date or date.today()
        self.save()
        
        # Update cash balance
        if self.payment_method == 'cash':
            try:
                from .models import CashBalance
                CashBalance.update_balance(
                    amount=self.total_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Expense #{self.expense_no} - {self.description[:50]}"
                )
            except ImportError:
                pass
    
    def get_status_badge(self):
        """HTML badge for status"""
        colors = {
            'draft': 'secondary',
            'submitted': 'primary',
            'review': 'info',
            'approved': 'success',
            'rejected': 'danger',
            'paid': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def is_approved(self):
        return self.status in ['approved', 'paid']
    
    @property
    def is_pending(self):
        return self.status in ['draft', 'submitted', 'review']


class ExpenseApprovalHistory(models.Model):
    """Track approval history"""
    
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='approval_history')
    action = models.CharField(max_length=20, choices=[
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ])
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    remarks = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Approval History"
        ordering = ['-performed_at']
    
    def __str__(self):
        return f"{self.expense.expense_no} - {self.action} by {self.performed_by}"


class ExpenseClaim(models.Model):
    """Employee expense claims / reimbursement"""
    
    CLAIM_STATUS = [
        ('draft', '📝 Draft'),
        ('submitted', '📤 Submitted'),
        ('review', '📋 Under Review'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('reimbursed', '💰 Reimbursed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    claim_no = models.CharField(max_length=20, unique=True, editable=False)
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='expense_claims')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    claim_date = models.DateField(default=now)
    
    # Expenses linked to this claim
    expenses = models.ManyToManyField(Expense, related_name='claims', blank=True)
    
    # Approval
    status = models.CharField(max_length=20, choices=CLAIM_STATUS, default='draft')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_claims')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_claims')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Reimbursement
    reimbursed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reimbursed_claims')
    reimbursed_at = models.DateTimeField(null=True, blank=True)
    reimbursement_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_claims')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Expense Claims"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.claim_no} - {self.employee.name} (Rs. {self.total_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.claim_no:
            year = datetime.now().strftime('%Y%m')
            last_claim = ExpenseClaim.objects.filter(claim_no__startswith=f'CLM-{year}').order_by('-claim_no').first()
            if last_claim and last_claim.claim_no:
                try:
                    last_num = int(last_claim.claim_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.claim_no = f'CLM-{year}-{new_num}'
        
        # Calculate total from expenses
        if self.pk:
            total = self.expenses.aggregate(total=Sum('total_amount'))['total'] or 0
            self.total_amount = total
        
        super().save(*args, **kwargs)
    
    def submit(self, user):
        """Submit claim for approval"""
        self.status = 'submitted'
        self.submitted_by = user
        self.submitted_at = now()
        self.save()
    
    def approve(self, user):
        """Approve claim"""
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
    
    def reject(self, user, reason=""):
        """Reject claim"""
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejection_reason = reason
        self.save()
    
    def mark_reimbursed(self, user, payment_method=None, reference_no=None):
        """Mark claim as reimbursed"""
        self.status = 'reimbursed'
        self.reimbursed_by = user
        self.reimbursed_at = now()
        self.reimbursement_date = date.today()
        if payment_method:
            self.payment_method = payment_method
        if reference_no:
            self.reference_no = reference_no
        self.save()


class ExpenseForecast(models.Model):
    """Expense forecasting"""
    
    month = models.DateField(unique=True)
    forecasted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Expense Forecasts"
        ordering = ['month']
    
    def __str__(self):
        return f"{self.month.strftime('%B %Y')} - Rs. {self.forecasted_amount:,.2f}"
    
    def calculate_variance(self):
        """Calculate variance between forecast and actual"""
        if self.forecasted_amount > 0:
            self.variance = self.actual_amount - self.forecasted_amount
            self.variance_percent = (self.variance / self.forecasted_amount) * 100
        else:
            self.variance = 0
            self.variance_percent = 0
        return self.variance
        
# ============================================
# PROFESSIONAL BUDGET MODULE - MODELS
# ============================================

# ============================================
# PROFESSIONAL BUDGET MODULE - FIXED MODELS
# ============================================


        
# ============================================
# SHAREHOLDER DEPOSIT REQUEST MODEL
# ============================================

class ShareholderDepositRequest(models.Model):
    """Deposit request from shareholder that needs admin approval"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('bank_transfer', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('cash', '💵 Cash Deposit'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Payment'),
    ]
    
    request_no = models.CharField(max_length=200, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bank_transfer')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='deposit_requests/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_deposits')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    
    # Payment confirmation after approval
    payment_confirmed = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_deposits')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Notifications
    notification_sent = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Shareholder Deposit Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_no']),
            models.Index(fields=['shareholder', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.request_no} - {self.shareholder.name} - Rs. {self.amount:,.2f} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.request_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            import random
            random_suffix = str(random.randint(100, 999))
            self.request_no = f'DEP-{timestamp}{random_suffix}'
        super().save(*args, **kwargs)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    def approve(self, user):
        """Approve deposit and add to shareholder balance"""
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be approved!")
        
        with transaction.atomic():
            # Update request status
            self.status = 'approved'
            self.approved_by = user
            self.approved_at = now()
            self.save()
            
            # Add to shareholder's cash balance
            new_balance = ShareholderCashBalance.deposit(
                shareholder=self.shareholder,
                amount=self.amount,
                user=user,
                description=f"Deposit request #{self.request_no}: {self.description or 'Deposit'}"
            )
            
            # Add to main cash balance (company received money)
            CashBalance.update_balance(
                amount=self.amount,
                transaction_type='deposit',
                user=user,
                description=f"Deposit from {self.shareholder.name} - Request #{self.request_no}"
            )
            
            # Create notification for shareholder
            try:
                from .models import Notification
                Notification.send(
                    user=self.shareholder.created_by if self.shareholder.created_by else user,
                    title="💰 Deposit Approved",
                    message=f"Your deposit of Rs. {self.amount:,.2f} has been approved! New balance: Rs. {new_balance:,.2f}",
                    notification_type='success',
                    category='payments',
                    link=f"/shareholder/transactions/"
                )
            except Exception:
                pass
            
            return new_balance
    
    def reject(self, user, reason=""):
        """Reject deposit request"""
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be rejected!")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejected_reason = reason
        self.save()
        
        # Create notification for shareholder
        try:
            from .models import Notification
            Notification.send(
                user=self.shareholder.created_by if self.shareholder.created_by else user,
                title="❌ Deposit Rejected",
                message=f"Your deposit of Rs. {self.amount:,.2f} was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments',
                link=f"/shareholder/transactions/"
            )
        except Exception:
            pass
            
# ============================================
# SHAREHOLDER WITHDRAWAL REQUEST MODEL
# ============================================

class ShareholderWithdrawalRequest(models.Model):
    """Withdrawal request from shareholder that needs admin approval"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('bank_transfer', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('cash', '💵 Cash Withdrawal'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Transfer'),
    ]
    
    request_no = models.CharField(max_length=20, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bank_transfer')
    account_details = models.TextField(blank=True, null=True, help_text="Bank account, JazzCash number, etc.")
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='withdrawal_requests/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_withdrawals')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    
    # Payment confirmation after approval
    payment_confirmed = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_withdrawals')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Notifications
    notification_sent = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💸 Shareholder Withdrawal Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_no']),
            models.Index(fields=['shareholder', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.request_no} - {self.shareholder.name} - Rs. {self.amount:,.2f} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.request_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            import random
            random_suffix = str(random.randint(100, 999))
            self.request_no = f'WDR-{timestamp}{random_suffix}'
        super().save(*args, **kwargs)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    def approve(self, user):
        """Approve withdrawal and deduct from shareholder balance"""
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be approved!")
        
        with transaction.atomic():
            # Check if shareholder has enough balance
            current_balance = ShareholderCashBalance.get_balance(self.shareholder)
            if current_balance < self.amount:
                raise ValidationError(
                    f"Insufficient balance! {self.shareholder.name} has Rs. {current_balance:,.2f}, "
                    f"Requested withdrawal: Rs. {self.amount:,.2f}"
                )
            
            # Update request status
            self.status = 'approved'
            self.approved_by = user
            self.approved_at = now()
            self.save()
            
            # Deduct from shareholder's cash balance
            new_balance = ShareholderCashBalance.withdraw(
                shareholder=self.shareholder,
                amount=self.amount,
                user=user,
                description=f"Withdrawal request #{self.request_no}: {self.description or 'Withdrawal'}"
            )
            
            # Deduct from main cash balance (company pays out)
            main_balance = CashBalance.get_balance()
            if main_balance < self.amount:
                raise ValidationError(
                    f"Insufficient main cash balance! Available: Rs. {main_balance:,.2f}, "
                    f"Required: Rs. {self.amount:,.2f}"
                )
            
            CashBalance.update_balance(
                amount=self.amount,
                transaction_type='withdraw',
                user=user,
                description=f"Withdrawal to {self.shareholder.name} - Request #{self.request_no}"
            )
            
            # Create notification for shareholder
            try:
                from .models import Notification
                Notification.send(
                    user=self.shareholder.created_by if self.shareholder.created_by else user,
                    title="💸 Withdrawal Approved",
                    message=f"Your withdrawal of Rs. {self.amount:,.2f} has been approved! New balance: Rs. {new_balance:,.2f}",
                    notification_type='success',
                    category='payments',
                    link=f"/shareholder/transactions/"
                )
            except Exception:
                pass
            
            return new_balance
    
    def reject(self, user, reason=""):
        """Reject withdrawal request"""
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be rejected!")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejected_reason = reason
        self.save()
        
        # Create notification for shareholder
        try:
            from .models import Notification
            Notification.send(
                user=self.shareholder.created_by if self.shareholder.created_by else user,
                title="❌ Withdrawal Rejected",
                message=f"Your withdrawal of Rs. {self.amount:,.2f} was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments',
                link=f"/shareholder/transactions/"
            )
        except Exception:
            pass
            
class BudgetGoal(models.Model):
    """Budget goals and targets"""
    
    GOAL_TYPES = [
        ('saving', '💰 Saving Goal'),
        ('spending', '💳 Spending Goal'),
        ('emergency', '🆘 Emergency Fund'),
        ('investment', '📈 Investment Goal'),
        ('debt', '💸 Debt Reduction'),
        ('purchase', '🛒 Big Purchase'),
    ]
    
    STATUS_CHOICES = [
        ('active', '✅ Active'),
        ('completed', '🎉 Completed'),
        ('cancelled', '❌ Cancelled'),
        ('expired', '⏰ Expired'),
    ]
    
    # Relationships
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, related_name='goals')
    category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True, blank=True, 
                                  help_text="Leave empty for overall budget goal")
    
    # Goal Details
    name = models.CharField(max_length=200)
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPES, default='saving')
    description = models.TextField(blank=True, null=True)
    
    # Amounts
    target_amount = models.DecimalField(max_digits=15, decimal_places=2)
    current_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Budget Goals"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.progress:.1f}% ({self.get_status_display()})"
    
    def update_progress(self):
        """Update goal progress based on current amount"""
        from decimal import Decimal
        if self.target_amount > 0:
            self.progress = (self.current_amount / self.target_amount) * 100
            if self.progress >= 100:
                self.is_completed = True
                self.completed_at = now()
                self.status = 'completed'
        self.save()
    
    def get_status_badge(self):
        """Get HTML badge for status"""
        if self.status == 'completed':
            return '<span class="badge bg-success">✅ Completed</span>'
        elif self.progress >= 80:
            return '<span class="badge bg-warning text-dark">🟡 Almost Done</span>'
        elif self.progress >= 50:
            return '<span class="badge bg-info">🟢 In Progress</span>'
        else:
            return '<span class="badge bg-danger">🔴 Behind</span>'
    
    def days_remaining(self):
        """Days until goal deadline"""
        from datetime import date
        if self.end_date:
            days = (self.end_date - date.today()).days
            return max(0, days)
        return 0
    
    def daily_required(self):
        """Amount needed per day to achieve goal"""
        from decimal import Decimal
        days = self.days_remaining()
        remaining = self.target_amount - self.current_amount
        if days > 0 and remaining > 0:
            return remaining / days
        return Decimal('0.00')
    
    def progress_color(self):
        """Get color based on progress"""
        if self.progress >= 80:
            return 'success'
        elif self.progress >= 50:
            return 'warning'
        else:
            return 'danger'
    
    @classmethod
    def check_all_goals(cls):
        """Check all active goals and update progress"""
        goals = cls.objects.filter(status='active')
        for goal in goals:
            goal.update_progress()
        return goals.count()
        


class AuditPlan(models.Model):
    """Audit plan template"""
    
    AUDIT_TYPES = [
        ('internal', '🔍 Internal Audit'),
        ('external', '📋 External Audit'),
        ('financial', '💰 Financial Audit'),
        ('compliance', '⚖️ Compliance Audit'),
        ('operational', '⚙️ Operational Audit'),
        ('it', '💻 IT Audit'),
        ('quality', '✅ Quality Audit'),
    ]
    
    AUDIT_STATUS = [
        ('draft', '📝 Draft'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    plan_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=AUDIT_STATUS, default='draft')
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Scope
    scope = models.TextField(help_text="Audit scope and objectives")
    criteria = models.TextField(help_text="Audit criteria")
    
    # Team
    lead_auditor = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, related_name='lead_audits')
    audit_team = models.ManyToManyField('Employee', blank=True, related_name='audit_team_member')
    
    # Department
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Finding
    findings_count = models.IntegerField(default=0)
    critical_findings = models.IntegerField(default=0)
    high_findings = models.IntegerField(default=0)
    medium_findings = models.IntegerField(default=0)
    low_findings = models.IntegerField(default=0)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_audits')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Audit Plans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.plan_no} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.plan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = AuditPlan.objects.filter(plan_no__startswith=f'AP-{year}').order_by('-plan_no').first()
            if last and last.plan_no:
                try:
                    last_num = int(last.plan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.plan_no = f'AP-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def get_progress(self):
        """Calculate audit progress"""
        if self.status in ['completed', 'cancelled']:
            return 100 if self.status == 'completed' else 0
        checklists = self.checklists.all()
        if checklists:
            completed = checklists.filter(is_completed=True).count()
            return int((completed / checklists.count()) * 100)
        return 0


class AuditChecklist(models.Model):
    """Audit checklist template"""
    
    CHECKLIST_TYPES = [
        ('compliance', '⚖️ Compliance'),
        ('financial', '💰 Financial'),
        ('operational', '⚙️ Operational'),
        ('it', '💻 IT'),
        ('quality', '✅ Quality'),
        ('hse', '🛡️ HSE'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='checklists')
    name = models.CharField(max_length=200)
    checklist_type = models.CharField(max_length=20, choices=CHECKLIST_TYPES)
    description = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.name}"
    
    def get_progress(self):
        items = self.items.all()
        if items:
            checked = items.filter(is_checked=True).count()
            return int((checked / items.count()) * 100)
        return 0


class AuditChecklistItem(models.Model):
    """Individual checklist items"""
    
    PRIORITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    checklist = models.ForeignKey(AuditChecklist, on_delete=models.CASCADE, related_name='items')
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['priority', 'id']
    
    def __str__(self):
        return f"{self.checklist.name} - {self.description[:50]}"


class AuditFinding(models.Model):
    """Audit findings"""
    
    SEVERITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    STATUS_CHOICES = [
        ('open', '📂 Open'),
        ('in_progress', '⚙️ In Progress'),
        ('resolved', '✅ Resolved'),
        ('accepted', '📋 Accepted'),
        ('rejected', '❌ Rejected'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='findings')
    checklist_item = models.ForeignKey(AuditChecklistItem, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Evidence
    evidence = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='audit_findings/', null=True, blank=True)
    
    # Recommendation
    recommendation = models.TextField()
    management_response = models.TextField(blank=True, null=True)
    
    # Dates
    found_date = models.DateField(auto_now_add=True)
    target_completion_date = models.DateField(null=True, blank=True)
    resolved_date = models.DateField(null=True, blank=True)
    
    # Assigned to
    assigned_to = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_findings')
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_findings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Audit Findings"
        ordering = ['-severity', '-created_at']
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.title} ({self.get_severity_display()})"
    
    def mark_resolved(self, user):
        self.status = 'resolved'
        self.resolved_date = date.today()
        self.save()


class AuditSchedule(models.Model):
    """Audit schedule"""
    
    SCHEDULE_STATUS = [
        ('scheduled', '📅 Scheduled'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
        ('postponed', '⏰ Postponed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    audit_plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='schedules')
    scheduled_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=SCHEDULE_STATUS, default='scheduled')
    attendees = models.ManyToManyField('Employee', blank=True, related_name='audit_attendees')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.audit_plan.plan_no} - {self.scheduled_date}"


class AuditReport(models.Model):
    """Audit report"""
    
    audit_plan = models.OneToOneField(AuditPlan, on_delete=models.CASCADE, related_name='report')
    report_no = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    executive_summary = models.TextField()
    findings_summary = models.TextField()
    recommendations = models.TextField()
    conclusion = models.TextField()
    
    # Files
    pdf_file = models.FileField(upload_to='audit_reports/', null=True, blank=True)
    word_file = models.FileField(upload_to='audit_reports/', null=True, blank=True)
    
    # Approval
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_audit_reports')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_audit_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Audit Reports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.report_no} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.report_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = AuditReport.objects.filter(report_no__startswith=f'AR-{year}').order_by('-report_no').first()
            if last and last.report_no:
                try:
                    last_num = int(last.report_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.report_no = f'AR-{year}-{new_num}'
        super().save(*args, **kwargs)


class AuditTrail(models.Model):
    """Track all changes in the system"""
    
    ACTION_TYPES = [
        ('created', '📝 Created'),
        ('updated', '✏️ Updated'),
        ('deleted', '🗑️ Deleted'),
        ('viewed', '👁️ Viewed'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('submitted', '📤 Submitted'),
        ('completed', '🎯 Completed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    model_name = models.CharField(max_length=100)
    record_id = models.IntegerField()
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Audit Trails"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.action} - {self.model_name}"


class InternalControl(models.Model):
    """Internal controls register"""
    
    CONTROL_TYPES = [
        ('preventive', '🛡️ Preventive'),
        ('detective', '🔍 Detective'),
        ('corrective', '🔧 Corrective'),
    ]
    
    CONTROL_CATEGORIES = [
        ('financial', '💰 Financial'),
        ('operational', '⚙️ Operational'),
        ('compliance', '⚖️ Compliance'),
        ('it', '💻 IT'),
        ('fraud', '🚨 Fraud Prevention'),
    ]
    
    CONTROL_STATUS = [
        ('active', '✅ Active'),
        ('inactive', '❌ Inactive'),
        ('review', '📋 Under Review'),
        ('improved', '📈 Improved'),
    ]
    
    control_no = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField()
    control_type = models.CharField(max_length=20, choices=CONTROL_TYPES)
    category = models.CharField(max_length=20, choices=CONTROL_CATEGORIES)
    status = models.CharField(max_length=20, choices=CONTROL_STATUS, default='active')
    
    # Risk assessment
    risk_level = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    likelihood = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    impact = models.CharField(max_length=20, choices=[('low', '🟢 Low'), ('medium', '🟡 Medium'), ('high', '🔴 High')])
    
    # Implementation
    implementation_date = models.DateField()
    review_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    
    # Responsible
    responsible_person = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, related_name='controls')
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Documents
    document = models.FileField(upload_to='internal_controls/', null=True, blank=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_controls')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Internal Controls"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.control_no} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.control_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = InternalControl.objects.filter(control_no__startswith=f'IC-{year}').order_by('-control_no').first()
            if last and last.control_no:
                try:
                    last_num = int(last.control_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.control_no = f'IC-{year}-{new_num}'
        super().save(*args, **kwargs)
        
# ========================================== #
# SUPPLY CHAIN MODULE - MODELS              #
# ========================================== #

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
        
# ========================================== #
# HIGH SECURITY MODULE - MODELS             #
# ========================================== #

class SecuritySettings(models.Model):
    """Global security settings"""
    
    # Authentication
    enable_2fa = models.BooleanField(default=False)
    max_login_attempts = models.IntegerField(default=5)
    lockout_time = models.IntegerField(default=30, help_text="Minutes")
    session_timeout = models.IntegerField(default=60, help_text="Minutes")
    enable_auto_logout = models.BooleanField(default=True)
    
    # Password Policy
    min_password_length = models.IntegerField(default=8)
    require_uppercase = models.BooleanField(default=True)
    require_lowercase = models.BooleanField(default=True)
    require_numbers = models.BooleanField(default=True)
    require_special_chars = models.BooleanField(default=True)
    password_expiry_days = models.IntegerField(default=90)
    prevent_password_reuse = models.BooleanField(default=True)
    password_history_count = models.IntegerField(default=5)
    
    # IP Security
    enable_ip_whitelist = models.BooleanField(default=False)
    enable_ip_blacklist = models.BooleanField(default=True)
    
    # API Security
    enable_api_auth = models.BooleanField(default=True)
    api_rate_limit = models.IntegerField(default=100)
    
    # Alerts
    enable_security_alerts = models.BooleanField(default=True)
    alert_email = models.EmailField(blank=True, null=True)
    alert_whatsapp = models.CharField(max_length=20, blank=True, null=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Security Settings"
    
    def __str__(self):
        return f"Security Settings (Updated: {self.updated_at})"
    
    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings


class User2FASettings(models.Model):
    """User-specific 2FA settings"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security_settings')
    is_2fa_enabled = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    secret_key = models.CharField(max_length=255, blank=True, null=True)
    backup_codes = models.JSONField(default=list, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - 2FA: {self.is_2fa_enabled}"


class OTPVerification(models.Model):
    """OTP verification records"""
    
    OTP_TYPES = [
        ('login', 'Login OTP'),
        ('password_reset', 'Password Reset'),
        ('email_verification', 'Email Verification'),
        ('transaction', 'Transaction OTP'),
        ('api', 'API Authentication'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_verifications')
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPES)
    is_used = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.otp_type} - {self.otp_code}"
    
    def is_valid(self):
        from django.utils.timezone import now
        return not self.is_used and not self.is_expired and self.expires_at > now()


class IPWhitelist(models.Model):
    """IP whitelist for secure access"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    description = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.ip_address} ({self.description})"


class IPBlacklist(models.Model):
    """IP blacklist for blocked access"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    reason = models.TextField()
    blocked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    blocked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.ip_address} - {self.reason[:50]}"


class LoginAttempt(models.Model):
    """Track login attempts for security"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='login_attempts')
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True, null=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-attempted_at']
    
    def __str__(self):
        return f"{self.username} - {self.ip_address} - {'Success' if self.is_success else 'Failed'}"


class AccessLog(models.Model):
    """Detailed access log for all actions"""
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='access_logs')
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    is_sensitive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['module', 'created_at']),
            models.Index(fields=['ip_address']),
        ]
    
    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'} - {self.action} - {self.module}"


class SecurityAlert(models.Model):
    """Security alerts and notifications"""
    
    SEVERITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🔴 High'),
        ('critical', '🔥 Critical'),
    ]
    
    ALERT_TYPES = [
        ('brute_force', 'Brute Force Attack'),
        ('suspicious_login', 'Suspicious Login'),
        ('ip_blocked', 'IP Blocked'),
        ('password_change', 'Password Changed'),
        ('2fa_failed', '2FA Failed'),
        ('unauthorized_access', 'Unauthorized Access'),
        ('api_key_compromised', 'API Key Compromised'),
        ('data_breach', 'Data Breach'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='resolved_alerts')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='security_alerts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_severity_display()} - {self.title}"


class APIKey(models.Model):
    """API key management for secure API access"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    permissions = models.JSONField(default=list, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.key:
            import secrets
            self.key = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)


class PasswordHistory(models.Model):
    """Track password history for reuse prevention"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.created_at}"


class SessionLog(models.Model):
    """Active session management"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.ip_address} - {'Active' if self.is_active else 'Logged Out'}"
        
# ========================================== #
# BUSINESS INTELLIGENCE MODULE - MODELS     #
# ========================================== #

class BIDashboard(models.Model):
    """BI Dashboard configuration"""
    
    DASHBOARD_TYPES = [
        ('sales', '📊 Sales Dashboard'),
        ('financial', '💰 Financial Dashboard'),
        ('inventory', '📦 Inventory Dashboard'),
        ('customer', '👥 Customer Dashboard'),
        ('employee', '👔 Employee Dashboard'),
        ('custom', '🎯 Custom Dashboard'),
    ]
    
    name = models.CharField(max_length=200)
    dashboard_type = models.CharField(max_length=20, choices=DASHBOARD_TYPES)
    description = models.TextField(blank=True, null=True)
    layout = models.JSONField(default=dict, help_text="Dashboard layout configuration")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_dashboards')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI Dashboards"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_dashboard_type_display()})"


class BIWidget(models.Model):
    """BI Dashboard widgets"""
    
    WIDGET_TYPES = [
        ('chart', '📈 Chart'),
        ('kpi', '🎯 KPI'),
        ('table', '📋 Table'),
        ('pie', '🥧 Pie Chart'),
        ('bar', '📊 Bar Chart'),
        ('line', '📉 Line Chart'),
        ('metric', '📊 Metric'),
        ('heatmap', '🔥 Heat Map'),
    ]
    
    dashboard = models.ForeignKey(BIDashboard, on_delete=models.CASCADE, related_name='widgets')
    title = models.CharField(max_length=200)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    data_source = models.CharField(max_length=100, help_text="Model or query name")
    data_query = models.JSONField(default=dict, help_text="Query parameters")
    chart_config = models.JSONField(default=dict, help_text="Chart configuration")
    position = models.JSONField(default=dict, help_text="Widget position")
    size = models.JSONField(default=dict, help_text="Widget size")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI Widgets"
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.title} ({self.get_widget_type_display()})"


class BIReport(models.Model):
    """BI Reports configuration"""
    
    REPORT_TYPES = [
        ('sales', '📊 Sales Report'),
        ('financial', '💰 Financial Report'),
        ('inventory', '📦 Inventory Report'),
        ('customer', '👥 Customer Report'),
        ('employee', '👔 Employee Report'),
        ('custom', '🎯 Custom Report'),
    ]
    
    REPORT_FORMATS = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('html', 'HTML'),
    ]
    
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField(blank=True, null=True)
    format = models.CharField(max_length=10, choices=REPORT_FORMATS, default='pdf')
    data_source = models.CharField(max_length=100)
    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)
    schedule = models.CharField(max_length=50, blank=True, null=True, help_text="Daily, Weekly, Monthly")
    recipients = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "BI Reports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class BIKPI(models.Model):
    """Key Performance Indicators"""
    
    KPI_CATEGORIES = [
        ('sales', '📊 Sales'),
        ('financial', '💰 Financial'),
        ('customer', '👥 Customer'),
        ('operational', '⚙️ Operational'),
        ('employee', '👔 Employee'),
        ('quality', '✅ Quality'),
    ]
    
    KPI_STATUS = [
        ('on_track', '✅ On Track'),
        ('warning', '⚠️ Warning'),
        ('critical', '🔴 Critical'),
        ('achieved', '🎉 Achieved'),
    ]
    
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=KPI_CATEGORIES)
    description = models.TextField(blank=True, null=True)
    formula = models.TextField(help_text="KPI calculation formula")
    target = models.DecimalField(max_digits=15, decimal_places=2)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unit = models.CharField(max_length=50, default='%')
    status = models.CharField(max_length=20, choices=KPI_STATUS, default='on_track')
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    dashboard = models.ForeignKey(BIDashboard, on_delete=models.SET_NULL, null=True, blank=True, related_name='kpis')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI KPIs"
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"
    
    def update_progress(self):
        if self.target > 0:
            self.progress = (self.current_value / self.target) * 100
            if self.progress >= 100:
                self.status = 'achieved'
            elif self.progress >= 80:
                self.status = 'on_track'
            elif self.progress >= 50:
                self.status = 'warning'
            else:
                self.status = 'critical'
        self.save()


class BIAlert(models.Model):
    """BI Alerts and notifications"""
    
    ALERT_TYPES = [
        ('kpi', '📊 KPI Alert'),
        ('trend', '📈 Trend Alert'),
        ('anomaly', '🔍 Anomaly Detection'),
        ('forecast', '🔮 Forecast Alert'),
        ('threshold', '📊 Threshold Alert'),
    ]
    
    name = models.CharField(max_length=200)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    description = models.TextField()
    condition = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    is_triggered = models.BooleanField(default=False)
    triggered_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_alerts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Alerts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_alert_type_display()})"


class BIInsight(models.Model):
    """AI-generated business insights"""
    
    INSIGHT_TYPES = [
        ('opportunity', '💡 Opportunity'),
        ('risk', '⚠️ Risk'),
        ('trend', '📈 Trend'),
        ('anomaly', '🔍 Anomaly'),
        ('recommendation', '🎯 Recommendation'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    data = models.JSONField(default=dict)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_actioned = models.BooleanField(default=False)
    actioned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Insights"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.get_insight_type_display()})"


class BIForecast(models.Model):
    """Business forecasting"""
    
    FORECAST_TYPES = [
        ('sales', '📊 Sales Forecast'),
        ('revenue', '💰 Revenue Forecast'),
        ('demand', '📦 Demand Forecast'),
        ('profit', '💵 Profit Forecast'),
    ]
    
    name = models.CharField(max_length=200)
    forecast_type = models.CharField(max_length=20, choices=FORECAST_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    forecasted_value = models.DecimalField(max_digits=15, decimal_places=2)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    methodology = models.CharField(max_length=100)
    data = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_forecasts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Forecasts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_forecast_type_display()})"
        
# ========================================== #
# TESTING MODULE - MODELS                   #
# ========================================== #

class TestProject(models.Model):
    """Testing projects"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='test_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    class Meta:
        verbose_name_plural = "Test Projects"


class TestSuite(models.Model):
    """Test suites - group of test cases"""
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='suites')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"
    
    class Meta:
        verbose_name_plural = "Test Suites"


class TestCase(models.Model):
    """Individual test cases"""
    
    PRIORITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('high', '🟠 High'),
        ('medium', '🟡 Medium'),
        ('low', '🟢 Low'),
    ]
    
    TYPE_CHOICES = [
        ('functional', '✅ Functional'),
        ('integration', '🔗 Integration'),
        ('unit', '📦 Unit'),
        ('performance', '⚡ Performance'),
        ('security', '🔒 Security'),
        ('ui', '🎨 UI/UX'),
        ('api', '🔌 API'),
    ]
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('ready', '✅ Ready'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('failed', '❌ Failed'),
        ('passed', '✅ Passed'),
        ('blocked', '🚫 Blocked'),
    ]
    
    suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, related_name='cases')
    title = models.CharField(max_length=200)
    description = models.TextField()
    test_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='functional')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Test steps
    pre_conditions = models.TextField(blank=True, null=True)
    test_steps = models.JSONField(default=list, help_text="Steps to execute")
    expected_result = models.TextField()
    actual_result = models.TextField(blank=True, null=True)
    
    # Execution
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='executed_tests')
    executed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.DurationField(null=True, blank=True)
    
    # Automation
    is_automated = models.BooleanField(default=False)
    automation_script = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Test Cases"


class TestExecution(models.Model):
    """Test execution records"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('running', '⚙️ Running'),
        ('passed', '✅ Passed'),
        ('failed', '❌ Failed'),
        ('blocked', '🚫 Blocked'),
        ('skipped', '⏭️ Skipped'),
    ]
    
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='executions')
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    results = models.JSONField(default=dict)
    notes = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.test_case.title} - {self.get_status_display()}"
    
    class Meta:
        verbose_name_plural = "Test Executions"
        ordering = ['-started_at']


class Bug(models.Model):
    """Bug tracking"""
    
    SEVERITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('major', '🟠 Major'),
        ('minor', '🟡 Minor'),
        ('trivial', '🟢 Trivial'),
    ]
    
    STATUS_CHOICES = [
        ('new', '🆕 New'),
        ('assigned', '📋 Assigned'),
        ('in_progress', '⚙️ In Progress'),
        ('fixed', '🔧 Fixed'),
        ('verified', '✅ Verified'),
        ('closed', '✅ Closed'),
        ('reopened', '🔄 Reopened'),
        ('duplicate', '📋 Duplicate'),
        ('won_fix', '❌ Won\'t Fix'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='major')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    
    # Related
    test_case = models.ForeignKey(TestCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='bugs')
    module = models.CharField(max_length=100, blank=True, null=True)
    
    # Environment
    browser = models.CharField(max_length=50, blank=True, null=True)
    os = models.CharField(max_length=50, blank=True, null=True)
    device = models.CharField(max_length=50, blank=True, null=True)
    
    # Steps to reproduce
    steps_to_reproduce = models.TextField()
    actual_result = models.TextField()
    expected_result = models.TextField()
    
    # Attachments
    screenshot = models.ImageField(upload_to='bug_screenshots/', null=True, blank=True)
    attachment = models.FileField(upload_to='bug_attachments/', null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_bugs')
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_bugs')
    
    # Dates
    reported_at = models.DateTimeField(auto_now_add=True)
    fixed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"BUG-{self.id}: {self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Bugs"
        ordering = ['-reported_at']


class TestPlan(models.Model):
    """Test plans"""
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('review', '📋 Review'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '✅ Completed'),
    ]
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=200)
    description = models.TextField()
    test_scope = models.TextField()
    test_strategy = models.TextField()
    resources = models.TextField(blank=True, null=True)
    schedule = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    class Meta:
        verbose_name_plural = "Test Plans"


class TestReport(models.Model):
    """Test reports"""
    
    project = models.ForeignKey(TestProject, on_delete=models.CASCADE, related_name='reports')
    name = models.CharField(max_length=200)
    description = models.TextField()
    
    # Metrics
    total_tests = models.IntegerField(default=0)
    passed_tests = models.IntegerField(default=0)
    failed_tests = models.IntegerField(default=0)
    blocked_tests = models.IntegerField(default=0)
    skipped_tests = models.IntegerField(default=0)
    
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Bugs
    total_bugs = models.IntegerField(default=0)
    critical_bugs = models.IntegerField(default=0)
    major_bugs = models.IntegerField(default=0)
    minor_bugs = models.IntegerField(default=0)
    
    # Files
    pdf_file = models.FileField(upload_to='test_reports/', null=True, blank=True)
    
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.generated_at.strftime('%d-%m-%Y')}"
    
    def calculate_metrics(self):
        total = self.total_tests
        if total > 0:
            self.pass_rate = (self.passed_tests / total) * 100
        return self.pass_rate
    
    class Meta:
        verbose_name_plural = "Test Reports"
        ordering = ['-generated_at']
        
      
# ========================================== #
# DOCUMENT MANAGEMENT MODULE - MODELS       #
# ========================================== #

class DocumentCategory(models.Model):
    """Document categories"""
    
    CATEGORY_TYPES = [
        ('financial', '💰 Financial'),
        ('customer', '👤 Customer'),
        ('employee', '👥 Employee'),
        ('company', '🏢 Company'),
        ('legal', '⚖️ Legal'),
        ('reports', '📊 Reports'),
        ('property', '🏠 Property'),
        ('vehicle', '🚗 Vehicle'),
        ('loan', '💳 Loan'),
        ('other', '📋 Other'),
    ]
    
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='📄')
    color = models.CharField(max_length=20, default='#667eea')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.icon} {self.name}"
    
    class Meta:
        verbose_name_plural = "Document Categories"
        ordering = ['name']


class Document(models.Model):
    """Main Document model"""
    
    DOCUMENT_STATUS = [
        ('draft', '📝 Draft'),
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('archived', '📦 Archived'),
        ('expired', '⏰ Expired'),
    ]
    
    DOCUMENT_VISIBILITY = [
        ('public', '🌍 Public'),
        ('internal', '🏢 Internal'),
        ('private', '🔒 Private'),
        ('confidential', '🤫 Confidential'),
    ]
    
    # Basic Info
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    document_no = models.CharField(max_length=50, unique=True, blank=True)
    category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True, related_name='documents')
    document_type = models.CharField(max_length=100, blank=True, null=True)
    
    # File
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    file_size = models.BigIntegerField(default=0)
    file_type = models.CharField(max_length=50, blank=True, null=True)
    thumbnail = models.ImageField(upload_to='document_thumbnails/', null=True, blank=True)
    
    # Metadata
    version = models.IntegerField(default=1)
    page_count = models.IntegerField(default=0)
    keywords = models.CharField(max_length=500, blank=True, null=True)
    
    # Dates
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_date = models.DateField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=DOCUMENT_STATUS, default='draft')
    visibility = models.CharField(max_length=20, choices=DOCUMENT_VISIBILITY, default='private')
    is_template = models.BooleanField(default=False)
    
    # Relationships
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reviewed_documents')
    
    # Related Modules
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    employee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.document_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = Document.objects.filter(document_no__startswith=f'DOC-{year}').order_by('-document_no').first()
            if last and last.document_no:
                try:
                    last_num = int(last.document_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.document_no = f'DOC-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.document_no} - {self.title}"
    
    def get_file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
    
    class Meta:
        verbose_name_plural = "Documents"
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['document_no']),
            models.Index(fields=['title']),
            models.Index(fields=['status']),
            models.Index(fields=['uploaded_at']),
        ]


class DocumentVersion(models.Model):
    """Document version history"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    file = models.FileField(upload_to='document_versions/%Y/%m/%d/')
    file_size = models.BigIntegerField(default=0)
    changes = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.document.document_no} - v{self.version_number}"
    
    class Meta:
        ordering = ['-version_number']


class DocumentShare(models.Model):
    """Document sharing"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='shares')
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_documents')
    shared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='documents_shared')
    permission = models.CharField(max_length=20, choices=[
        ('view', '👁️ View'),
        ('edit', '✏️ Edit'),
        ('delete', '🗑️ Delete'),
        ('share', '🔗 Share'),
    ], default='view')
    is_active = models.BooleanField(default=True)
    shared_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.document.title} → {self.shared_with.username}"
    
    class Meta:
        unique_together = ['document', 'shared_with']


class DocumentApproval(models.Model):
    """Document approval workflow"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_approvals')
    status = models.CharField(max_length=20, choices=[
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
    ], default='pending')
    comments = models.TextField(blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.document.document_no} - {self.approver.username}"
    
    class Meta:
        unique_together = ['document', 'approver']


class DocumentTemplate(models.Model):
    """Document templates"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='document_templates/')
    category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True)
    variables = models.JSONField(default=list, help_text="Variables to replace")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class DocumentFolder(models.Model):
    """Document folders for organization"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    color = models.CharField(max_length=20, default='#667eea')
    icon = models.CharField(max_length=50, default='📁')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    def get_full_path(self):
        if self.parent:
            return f"{self.parent.get_full_path()} / {self.name}"
        return self.name
    
    class Meta:
        verbose_name_plural = "Document Folders"
        ordering = ['name']
        
# models.py

# models.py - Complete BalanceDividend

# models.py - Complete BalanceDividend

# models.py - Complete BalanceDividend

# models.py - Complete BalanceDividend

class BalanceDividend(models.Model):
    """
    Balance-Based Dividend Model
    Profit distribution based on balance usage (not shares)
    ✅ NEW: Refund + Profit system with Balance-Only option
    """
    
    # ========================================== #
    # STATUS CHOICES                            #
    # ========================================== #
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('declared', '📢 Declared'),
        ('approved', '✅ Approved'),
        ('distributed', '💰 Distributed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    DISTRIBUTION_TYPES = [
        ('balance_used', 'Based on Balance Used'),
        ('equal', 'Equal Distribution'),
        ('proportional', 'Proportional by Balance'),
    ]
    
    # ========================================== #
    # REFUND TYPES                              #
    # ========================================== #
    REFUND_TYPES = [
        ('full', 'Full Refund + Profit'),
        ('partial', 'Partial Refund + Profit'),
        ('profit_only', 'Profit Only'),
    ]
    
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    dividend_no = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False,
        verbose_name="Dividend Number"
    )
    total_profit = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Total Profit",
        help_text="Total profit from sales"
    )
    dividend_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=Decimal('50.00'),
        verbose_name="Dividend Percentage",
        help_text="% of profit to distribute"
    )
    
    # ========================================== #
    # DATES                                     #
    # ========================================== #
    declaration_date = models.DateField(
        verbose_name="Declaration Date",
        help_text="Date when dividend is declared"
    )
    record_date = models.DateField(
        verbose_name="Record Date",
        help_text="Date to check active shareholders"
    )
    distribution_date = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Distribution Date",
        help_text="Date when dividend was distributed"
    )
    
    # ========================================== #
    # DATE RANGE FOR PROFIT CALCULATION         #
    # ========================================== #
    profit_from_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Profit From Date",
        help_text="Start date for profit calculation"
    )
    profit_to_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Profit To Date",
        help_text="End date for profit calculation"
    )
    
    # ========================================== #
    # REFUND SETTINGS                           #
    # ========================================== #
    refund_type = models.CharField(
        max_length=20,
        choices=REFUND_TYPES,
        default='full',
        verbose_name="Refund Type",
        help_text="How to return deducted balance"
    )
    refund_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        verbose_name="Refund Percentage",
        help_text="% of deducted balance to refund (100 = full refund)"
    )
    total_refund_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Refund Amount"
    )
    total_payment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Payment Amount",
        help_text="Refund + Profit total"
    )
    
    # ========================================== #
    # STATUS & TYPE                             #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft'
    )
    distribution_type = models.CharField(
        max_length=20, 
        choices=DISTRIBUTION_TYPES, 
        default='balance_used'
    )
    notes = models.TextField(
        blank=True, 
        null=True,
        verbose_name="Notes"
    )
    
    # ========================================== #
    # TRACK USED SALES                          #
    # ========================================== #
    used_sales = models.ManyToManyField(
        'Sale',
        blank=True,
        related_name='balance_dividends',
        help_text="Sales used in this dividend"
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_balance_dividends'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Balance-Based Dividends"
        ordering = ['-declaration_date']
        indexes = [
            models.Index(fields=['dividend_no']),
            models.Index(fields=['status']),
            models.Index(fields=['declaration_date']),
        ]
    
    def __str__(self):
        return f"BD-{self.dividend_no} - {self.declaration_date.strftime('%B %Y')}"
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def amount_to_distribute(self):
        """Calculate total profit amount to distribute"""
        return self.total_profit * (self.dividend_percentage / 100)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount_to_distribute:,.2f}"
    
    @property
    def formatted_refund(self):
        return f"Rs. {self.total_refund_amount:,.2f}"
    
    @property
    def formatted_total_payment(self):
        return f"Rs. {self.total_payment_amount:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        colors = {
            'draft': 'secondary',
            'declared': 'primary',
            'approved': 'info',
            'distributed': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def refund_badge(self):
        """HTML badge for refund type"""
        colors = {
            'full': 'success',
            'partial': 'warning',
            'profit_only': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.refund_type, "secondary")}">{self.get_refund_type_display()}</span>'
    
    @property
    def is_active(self):
        """Check if dividend is active"""
        return self.status not in ['cancelled', 'distributed']
    
    @property
    def can_generate_payments(self):
        """Can generate payments?"""
        return self.status in ['draft', 'declared'] and not self.payments.exists()
    
    @property
    def can_edit(self):
        """Can edit?"""
        return self.status in ['draft', 'declared'] and not self.payments.exists()
    
    @property
    def can_delete(self):
        """Can delete?"""
        return self.status == 'draft'
    
    @property
    def can_distribute(self):
        """Can distribute?"""
        return self.status in ['declared', 'approved'] and self.payments.exists()
    
    @property
    def used_sales_count(self):
        """Get count of used sales"""
        return self.used_sales.count()
    
    @property
    def total_sales_profit(self):
        """Get total profit from used sales"""
        from decimal import Decimal
        from django.db.models import Sum
        
        total = self.used_sales.aggregate(
            total=Sum('saleitem__profit')
        )['total'] or Decimal('0.00')
        
        discounts = self.used_sales.aggregate(
            total=Sum('discount_value')
        )['total'] or Decimal('0.00')
        
        return total - discounts
    
    # ========================================== #
    # CORE BUSINESS METHODS                      #
    # ========================================== #
    
    def get_shareholder_balance_used(self, shareholder):
        """
        Calculate total balance used by a specific shareholder
        Returns: Decimal
        """
        from decimal import Decimal
        
        total = Decimal('0.00')
        
        # Get all purchases with shareholder deductions
        purchases = Purchase.objects.filter(
            shareholder_deduction_done=True
        )
        
        for purchase in purchases:
            data = purchase.shareholder_deduction_data
            if data and data.get('deducted_from'):
                for item in data['deducted_from']:
                    # Match by name or ID
                    if item.get('name') == shareholder.name:
                        total += Decimal(str(item.get('deducted', 0)))
                        break
        
        return total
    
    def get_eligible_shareholders(self):
        """
        Get shareholders eligible for dividend
        Returns: List of dicts with shareholder and balance_used
        """
        # Get system settings
        min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
        min_months = int(SystemSetting.get_value('min_holding_months', '0'))
        
        eligible = []
        
        for shareholder in Shareholder.objects.filter(status='active'):
            # Get balance used
            balance_used = self.get_shareholder_balance_used(shareholder)
            
            # Check min balance requirement
            if balance_used < min_balance:
                continue
            
            # Check min holding period (in months)
            if min_months > 0:
                first_share = shareholder.shares.order_by('issue_date').first()
                if not first_share:
                    continue
                months_held = (date.today() - first_share.issue_date).days // 30
                if months_held < min_months:
                    continue
            
            # Add to eligible list
            eligible.append({
                'shareholder': shareholder,
                'balance_used': balance_used,
                'shares': shareholder.total_shares(),
                'investment': shareholder.total_investment(),
                'percentage': 0,
                'dividend_amount': Decimal('0.00'),
                'refund_amount': Decimal('0.00'),
                'total_payment': Decimal('0.00'),
            })
        
        # Calculate percentages
        total_used = sum(item['balance_used'] for item in eligible)
        
        if total_used > 0:
            for item in eligible:
                item['percentage'] = (item['balance_used'] / total_used) * 100
        
        return eligible
    
    def calculate_distribution(self):
        """
        Calculate dividend distribution for all eligible shareholders
        ✅ NEW: Includes refund of deducted balance
        """
        eligible = self.get_eligible_shareholders()
        total_to_distribute = self.amount_to_distribute
        
        # Calculate refund for each shareholder
        total_refund = Decimal('0.00')
        
        for item in eligible:
            # Calculate refund amount based on balance used
            if self.refund_type == 'full':
                refund_amount = item['balance_used']
            elif self.refund_type == 'partial':
                refund_amount = item['balance_used'] * (self.refund_percentage / 100)
            else:  # profit_only
                refund_amount = Decimal('0.00')
            
            item['refund_amount'] = refund_amount
            total_refund += refund_amount
        
        self.total_refund_amount = total_refund
        
        # Calculate profit distribution
        if self.distribution_type == 'equal':
            per_shareholder = total_to_distribute / len(eligible) if eligible else 0
            for item in eligible:
                item['dividend_amount'] = per_shareholder
        elif self.distribution_type == 'proportional':
            total_balance_used = sum(item['balance_used'] for item in eligible) or Decimal('1')
            for item in eligible:
                proportion = item['balance_used'] / total_balance_used
                item['dividend_amount'] = total_to_distribute * proportion
        else:  # balance_used (default)
            total_balance_used = sum(item['balance_used'] for item in eligible) or Decimal('1')
            for item in eligible:
                proportion = item['balance_used'] / total_balance_used
                item['dividend_amount'] = total_to_distribute * proportion
        
        # Calculate total payment (refund + profit)
        total_payment = Decimal('0.00')
        for item in eligible:
            item['total_payment'] = item['dividend_amount'] + item['refund_amount']
            total_payment += item['total_payment']
        
        self.total_payment_amount = total_payment
        
        return eligible
    
    def generate_payments(self):
        """
        Generate dividend payments for all eligible shareholders
        ✅ Returns: (count, total_profit, total_refund)
        """
        from django.db import transaction
        from django.utils.timezone import now
        from decimal import Decimal
        
        if self.payments.exists():
            raise ValidationError("Payments already exist for this dividend!")
        
        # Get unused sales for this period
        used_sale_ids = list(
            BalanceDividend.objects.exclude(pk=self.pk).values_list('used_sales', flat=True).distinct()
        )
        
        from_date = self.profit_from_date or self.declaration_date
        to_date = self.profit_to_date or self.declaration_date
        
        unused_sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).exclude(
            id__in=used_sale_ids
        )
        
        distribution = self.calculate_distribution()
        count = 0
        total_profit = Decimal('0.00')
        total_refund = Decimal('0.00')
        
        with transaction.atomic():
            for item in distribution:
                if item['total_payment'] > 0:
                    # Create payment with refund details
                    payment = BalanceDividendPayment.objects.create(
                        dividend=self,
                        shareholder=item['shareholder'],
                        balance_used=item['balance_used'],
                        percentage=item['percentage'],
                        amount=item['dividend_amount'],  # Profit
                        refund_amount=item['refund_amount'],
                        total_payment=item['total_payment'],
                        status='pending',
                        main_cash_deducted=False  # ✅ Default: No cash deduction
                    )
                    count += 1
                    total_profit += item['dividend_amount']
                    total_refund += item['refund_amount']
            
            # Track which sales were used
            if unused_sales.exists():
                self.used_sales.set(unused_sales)
            
            # Update dividend status and totals
            if count > 0:
                self.total_refund_amount = total_refund
                self.total_payment_amount = total_profit + total_refund
                self.status = 'declared'
                self.save(update_fields=['status', 'total_refund_amount', 'total_payment_amount'])
        
        return count, total_profit, total_refund
    
    def distribute(self, user):
        """
        Distribute dividend (mark all as distributed)
        Requires all payments to be paid
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status not in ['declared', 'approved']:
            raise ValidationError("Dividend must be declared or approved!")
        
        pending_payments = self.payments.filter(status='pending')
        if pending_payments.exists():
            raise ValidationError(
                f"Cannot distribute! {pending_payments.count()} payments are still pending."
            )
        
        with transaction.atomic():
            self.status = 'distributed'
            self.distribution_date = now().date()
            self.save(update_fields=['status', 'distribution_date'])
        
        return True
    
    def cancel(self, user, reason=""):
        """
        Cancel dividend
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status == 'distributed':
            raise ValidationError("Cannot cancel a distributed dividend!")
        
        if self.status == 'cancelled':
            raise ValidationError("Dividend is already cancelled!")
        
        # Check if any paid payments exist
        if self.payments.filter(status='paid').exists():
            raise ValidationError(
                "Cannot cancel! Some payments have already been paid."
            )
        
        with transaction.atomic():
            # Delete all pending payments
            self.payments.filter(status='pending').delete()
            
            # Remove used sales tracking
            self.used_sales.clear()
            
            # Update status
            self.status = 'cancelled'
            self.notes = f"{self.notes}\nCancelled by {user.username}: {reason}".strip()
            self.save(update_fields=['status', 'notes'])
        
        return True
    
    # ========================================== #
    # STATIC METHODS                             #
    # ========================================== #
    
    @classmethod
    def get_auto_profit(cls, from_date=None, to_date=None, exclude_used=True):
        """
        Auto-calculate profit from sales
        ✅ NEW: Exclude sales already used in dividends
        """
        from decimal import Decimal
        from django.db.models import Sum, F, Q
        
        if not from_date:
            from_date = date.today().replace(day=1)
        if not to_date:
            to_date = date.today()
        
        # Get all sale IDs already used in balance dividends
        used_sale_ids = []
        if exclude_used:
            used_sale_ids = list(
                BalanceDividend.objects.values_list('used_sales', flat=True).distinct()
            )
        
        # Build query - exclude used sales
        sales_query = Q(
            sale__sale_date__date__gte=from_date,
            sale__sale_date__date__lte=to_date
        )
        
        if used_sale_ids:
            sales_query &= ~Q(sale_id__in=used_sale_ids)
        
        # Total Sales Profit (only from unused sales)
        total_sales_profit = SaleItem.objects.filter(
            sales_query
        ).aggregate(
            total=Sum('profit')
        )['total'] or Decimal('0.00')
        
        # Total Discounts (only from unused sales)
        total_discounts = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date,
            id__in=SaleItem.objects.filter(sales_query).values_list('sale_id', flat=True).distinct()
        ).aggregate(
            total=Sum('discount_value')
        )['total'] or Decimal('0.00')
        
        # Total Expenses (all expenses, not just sales)
        total_expenses = Expense.objects.filter(
            expense_date__gte=from_date,
            expense_date__lte=to_date,
            status__in=['approved', 'paid']
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Net Profit = Sales Profit - Discounts - Expenses
        net_profit = total_sales_profit - total_discounts
        final_profit = net_profit - total_expenses
        
        # Get list of unused sales for display
        unused_sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).exclude(
            id__in=used_sale_ids
        ).values('id', 'bill_no', 'sale_date')
        
        return {
            'total_sales_profit': total_sales_profit,
            'total_discounts': total_discounts,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'final_profit': final_profit,
            'from_date': from_date,
            'to_date': to_date,
            'used_sale_count': len(used_sale_ids),
            'unused_sale_count': unused_sales.count(),
            'unused_sales': list(unused_sales),
            'total_sales_count': Sale.objects.filter(
                sale_date__date__gte=from_date,
                sale_date__date__lte=to_date
            ).count(),
        }
    
    @classmethod
    def get_total_balance_used(cls):
        """
        Get total balance used by all shareholders
        Returns: Decimal
        """
        total = Decimal('0.00')
        
        for shareholder in Shareholder.objects.filter(status='active'):
            dummy_dividend = cls.objects.first()
            if dummy_dividend:
                total += dummy_dividend.get_shareholder_balance_used(shareholder)
        
        return total
    
    @classmethod
    def get_eligible_shareholders_count(cls):
        """
        Get count of shareholders eligible for dividend
        Returns: int
        """
        min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
        min_months = int(SystemSetting.get_value('min_holding_months', '0'))
        
        count = 0
        dummy_dividend = cls.objects.first()
        
        if not dummy_dividend:
            dummy_dividend = cls(
                total_profit=Decimal('1000'),
                dividend_percentage=50,
                declaration_date=date.today(),
                record_date=date.today()
            )
        
        for shareholder in Shareholder.objects.filter(status='active'):
            balance_used = dummy_dividend.get_shareholder_balance_used(shareholder)
            
            if balance_used < min_balance:
                continue
            
            if min_months > 0:
                first_share = shareholder.shares.order_by('issue_date').first()
                if not first_share:
                    continue
                months_held = (date.today() - first_share.issue_date).days // 30
                if months_held < min_months:
                    continue
            
            count += 1
        
        return count
    
    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate number and validate"""
        
        # Auto-generate dividend number
        if not self.dividend_no:
            last_dividend = BalanceDividend.objects.order_by('-id').first()
            if last_dividend and last_dividend.dividend_no:
                try:
                    last_num = int(last_dividend.dividend_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.dividend_no = f'BD-{new_num}'
        
        # Set default date range if not set
        if not self.profit_from_date:
            self.profit_from_date = self.declaration_date.replace(day=1)
        if not self.profit_to_date:
            self.profit_to_date = self.declaration_date
        
        # Validate refund type and percentage
        if self.refund_type == 'profit_only':
            self.refund_percentage = Decimal('0.00')
        elif self.refund_type == 'full':
            self.refund_percentage = Decimal('100.00')
        elif self.refund_type == 'partial':
            if self.refund_percentage < 0 or self.refund_percentage > 100:
                raise ValidationError("Refund percentage must be between 0 and 100!")
        
        # Validate status transitions
        if self.pk:
            old = BalanceDividend.objects.filter(pk=self.pk).first()
            if old:
                if old.status == 'distributed' and self.status != 'distributed':
                    raise ValidationError("Cannot change status of distributed dividend!")
                if old.status == 'cancelled' and self.status != 'cancelled':
                    raise ValidationError("Cannot change status of cancelled dividend!")
        
        super().save(*args, **kwargs)
    
    # ========================================== #
    # DELETE METHOD                              #
    # ========================================== #
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of distributed dividends"""
        if self.status == 'distributed':
            raise ValidationError("Cannot delete a distributed dividend!")
        if self.payments.filter(status='paid').exists():
            raise ValidationError("Cannot delete dividend with paid payments!")
        super().delete(*args, **kwargs)


# models.py - Complete BalanceDividendPayment

class BalanceDividendPayment(models.Model):
    """
    Individual dividend payment based on balance usage
    ✅ NEW: Refund + Profit system with Balance-Only option
    """
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('paid', '✅ Paid'),
        ('failed', '❌ Failed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    dividend = models.ForeignKey(
        BalanceDividend, 
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    shareholder = models.ForeignKey(
        Shareholder, 
        on_delete=models.CASCADE,
        related_name='balance_dividend_payments'
    )
    
    # ========================================== #
    # BALANCE USAGE DETAILS                     #
    # ========================================== #
    balance_used = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Balance Used"
    )
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        verbose_name="Percentage"
    )
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Dividend Amount (Profit)"
    )
    
    # ========================================== #
    # REFUND FIELDS                             #
    # ========================================== #
    refund_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Refund Amount",
        help_text="Deducted balance being returned"
    )
    total_payment = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Payment",
        help_text="Refund + Profit"
    )
    
    # ========================================== #
    # MAIN CASH DEDUCTION TRACKING              #
    # ========================================== #
    main_cash_deducted = models.BooleanField(
        default=False,
        verbose_name="Main Cash Deducted",
        help_text="Has main cash been deducted for this payment?"
    )
    main_cash_deducted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Main Cash Deducted At"
    )
    
    # ========================================== #
    # PAYMENT STATUS                            #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    payment_date = models.DateTimeField(
        null=True, 
        blank=True
    )
    payment_method = models.CharField(
        max_length=50, 
        blank=True, 
        null=True
    )
    reference_no = models.CharField(
        max_length=100, 
        blank=True, 
        null=True
    )
    notes = models.TextField(
        blank=True, 
        null=True
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='processed_balance_dividend_payments'
    )
    
    class Meta:
        verbose_name_plural = "💰 Balance Dividend Payments"
        ordering = ['-created_at']
        unique_together = ['dividend', 'shareholder']
        indexes = [
            models.Index(fields=['dividend', 'shareholder']),
            models.Index(fields=['status']),
            models.Index(fields=['main_cash_deducted']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Profit: Rs. {self.amount:,.2f}, Refund: Rs. {self.refund_amount:,.2f}, Total: Rs. {self.total_payment:,.2f}"
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def formatted_refund(self):
        return f"Rs. {self.refund_amount:,.2f}"
    
    @property
    def formatted_total(self):
        return f"Rs. {self.total_payment:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        colors = {
            'pending': 'warning',
            'paid': 'success',
            'failed': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def cash_badge(self):
        """HTML badge for cash deduction status"""
        if self.main_cash_deducted:
            return '<span class="badge bg-success">✅ Cash Deducted</span>'
        return '<span class="badge bg-secondary">⏳ Balance Only</span>'
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    @property
    def is_cancelled(self):
        return self.status == 'cancelled'
    
    @property
    def is_cash_deducted(self):
        return self.main_cash_deducted
    
    # ========================================== #
    # PAYMENT METHODS                            #
    # ========================================== #
    
    def mark_paid(self, user, payment_method=None, reference_no=None, deduct_main_cash=False):
        """
        Mark payment as paid
        ✅ NEW: Main cash deduction is optional
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status == 'paid':
            raise ValidationError("Already paid!")
        
        if self.total_payment <= 0:
            raise ValidationError("Total payment must be greater than zero!")
        
        with transaction.atomic():
            # ========================================== #
            # STEP 1: DEPOSIT TO SHAREHOLDER BALANCE    #
            # ========================================== #
            new_balance = ShareholderCashBalance.deposit(
                shareholder=self.shareholder,
                amount=self.total_payment,
                user=user,
                description=f"Balance Dividend #{self.dividend.dividend_no} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f})"
            )
            
            # ========================================== #
            # STEP 2: CREATE TRANSACTION RECORD         #
            # ========================================== #
            ShareholderCashTransaction.objects.create(
                shareholder=self.shareholder,
                amount=self.total_payment,
                transaction_type='balance_dividend',
                balance_after=new_balance,
                description=f"Balance Dividend #{self.dividend.dividend_no} - Refund: Rs. {self.refund_amount:,.2f}, Profit: Rs. {self.amount:,.2f}",
                reference_no=reference_no,
                balance_dividend_payment=self,
                created_by=user
            )
            
            # ========================================== #
            # STEP 3: MAIN CASH DEDUCTION (OPTIONAL)    #
            # ========================================== #
            if deduct_main_cash:
                current_balance = CashBalance.get_balance()
                if current_balance < self.total_payment:
                    raise ValidationError(
                        f"Insufficient main cash balance! Available: Rs. {current_balance:,.2f}, Required: Rs. {self.total_payment:,.2f}"
                    )
                
                CashBalance.update_balance(
                    amount=self.total_payment,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Balance Dividend withdrawal by {self.shareholder.name} - #{self.dividend.dividend_no}"
                )
                
                self.main_cash_deducted = True
                self.main_cash_deducted_at = now()
            
            # ========================================== #
            # STEP 4: UPDATE PAYMENT STATUS            #
            # ========================================== #
            self.status = 'paid'
            self.payment_date = now()
            self.payment_method = payment_method or 'Bank Transfer'
            self.reference_no = reference_no
            self.processed_by = user
            self.save(update_fields=[
                'status', 'payment_date', 'payment_method', 
                'reference_no', 'processed_by',
                'main_cash_deducted', 'main_cash_deducted_at'
            ])
            
            # ========================================== #
            # STEP 5: UPDATE DIVIDEND STATUS           #
            # ========================================== #
            self._update_dividend_status()
            
            # ========================================== #
            # STEP 6: CREATE NOTIFICATION              #
            # ========================================== #
            try:
                from .models import Notification
                if deduct_main_cash:
                    message = f"Rs. {self.total_payment:,.2f} paid to {self.shareholder.name} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f}) - Cash Withdrawn"
                else:
                    message = f"Rs. {self.total_payment:,.2f} credited to {self.shareholder.name} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f}) - Balance Only"
                
                Notification.send(
                    user=user,
                    title="💰 Balance Dividend Paid" if deduct_main_cash else "💰 Balance Dividend Credited",
                    message=message,
                    notification_type='success',
                    category='payments',
                    link=f"/balance-dividend/{self.dividend.id}/"
                )
            except:
                pass
            
            return True
    
    def mark_paid_no_cash(self, user, payment_method=None, reference_no=None):
        """
        Mark payment as paid WITHOUT main cash deduction
        Only shareholder balance increases
        """
        return self.mark_paid(user, payment_method, reference_no, deduct_main_cash=False)
    
    def mark_paid_with_cash(self, user, payment_method=None, reference_no=None):
        """
        Mark payment as paid WITH main cash deduction
        Shareholder balance increases AND main cash decreases
        """
        return self.mark_paid(user, payment_method, reference_no, deduct_main_cash=True)
    
    # ========================================== #
    # HELPER METHODS                            #
    # ========================================== #
    
    def _update_dividend_status(self):
        """
        Update dividend status based on payments
        """
        total_payments = self.dividend.payments.count()
        paid_payments = self.dividend.payments.filter(status='paid').count()
        
        if total_payments > 0 and paid_payments == total_payments:
            self.dividend.status = 'distributed'
            self.dividend.distribution_date = date.today()
            self.dividend.save(update_fields=['status', 'distribution_date'])
    
    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Prevent changing status of paid payments"""
        if self.pk:
            old = BalanceDividendPayment.objects.filter(pk=self.pk).first()
            if old and old.status == 'paid' and self.status != 'paid':
                raise ValidationError("Cannot change status of a paid payment!")
        super().save(*args, **kwargs)
    
    # ========================================== #
    # DELETE METHOD                              #
    # ========================================== #
    
    def delete(self, *args, **kwargs):
        """Prevent deleting paid payments"""
        if self.status == 'paid':
            raise ValidationError("Cannot delete a paid payment!")
        super().delete(*args, **kwargs)
# ========================================== #
# HELPER FUNCTION FOR BALANCE DIVIDEND      #
# ========================================== #

def get_shareholder_balance_used(shareholder):
    """
    Calculate total balance used by a specific shareholder
    Used by BalanceDividend model
    """
    from decimal import Decimal
    
    total = Decimal('0.00')
    
    purchases = Purchase.objects.filter(shareholder_deduction_done=True)
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    total += Decimal(str(item.get('deducted', 0)))
    
    return total
    
# models.py - Add these models at the end of your file

# ========================================== #
# ACCOUNTS MODULE - COMPLETE                #
# ========================================== #

# ========================================== #
# 1. CHART OF ACCOUNTS                       #
# ========================================== #

class AccountType(models.Model):
    """Account Types like Assets, Liabilities, Equity, Income, Expenses"""
    
    ACCOUNT_CLASSES = [
        ('asset', 'Assets'),
        ('liability', 'Liabilities'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expenses'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    account_class = models.CharField(max_length=20, choices=ACCOUNT_CLASSES)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Account Types"
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Account(models.Model):
    """Chart of Accounts - Each account entry"""
    
    # Basic Information
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.ForeignKey(AccountType, on_delete=models.CASCADE, related_name='accounts')
    
    # Parent-Child (Hierarchy)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    
    # Opening Balance
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    opening_balance_date = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_contra = models.BooleanField(default=False, help_text="Contra account (e.g., Accumulated Depreciation)")
    is_bank = models.BooleanField(default=False, help_text="Bank account")
    is_cash = models.BooleanField(default=False, help_text="Cash account")
    is_payable = models.BooleanField(default=False, help_text="Accounts Payable")
    is_receivable = models.BooleanField(default=False, help_text="Accounts Receivable")
    
    # Bank Details
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_account_no = models.CharField(max_length=50, blank=True, null=True)
    
    # Description
    description = models.TextField(blank=True, null=True)
    
    # System
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Chart of Accounts"
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['account_type']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_full_code(self):
        """Get full hierarchical code"""
        if self.parent:
            return f"{self.parent.get_full_code()}-{self.code}"
        return self.code
    
    def get_level(self):
        """Get hierarchy level"""
        if self.parent:
            return self.parent.get_level() + 1
        return 1
    
    def current_balance(self):
        """Calculate current balance of this account"""
        from django.db.models import Sum
        
        # Debits increase Assets & Expenses, decrease Liabilities & Equity & Income
        # Credits decrease Assets & Expenses, increase Liabilities & Equity & Income
        is_debit_balance = self.account_type.account_class in ['asset', 'expense']
        
        debit_total = JournalEntryItem.objects.filter(
            account=self,
            is_debit=True
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        credit_total = JournalEntryItem.objects.filter(
            account=self,
            is_debit=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        if is_debit_balance:
            balance = debit_total - credit_total + self.opening_balance
        else:
            balance = credit_total - debit_total + self.opening_balance
        
        return balance
    
    def debit_balance(self):
        """Get debit balance"""
        if self.account_type.account_class in ['asset', 'expense']:
            return self.current_balance()
        return 0
    
    def credit_balance(self):
        """Get credit balance"""
        if self.account_type.account_class in ['liability', 'equity', 'income']:
            return self.current_balance()
        return 0
    
    def save(self, *args, **kwargs):
        # Auto-generate code if not provided
        if not self.code:
            last_account = Account.objects.order_by('-id').first()
            if last_account and last_account.code:
                try:
                    last_num = int(last_account.code.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'ACC-{new_num}'
        super().save(*args, **kwargs)


# ========================================== #
# 2. JOURNAL ENTRIES                         #
# ========================================== #

class JournalEntry(models.Model):
    """Journal Entry - Main transaction record"""
    
    ENTRY_TYPES = [
        ('manual', 'Manual Entry'),
        ('sale', 'Sale Entry'),
        ('purchase', 'Purchase Entry'),
        ('expense', 'Expense Entry'),
        ('payment', 'Payment Entry'),
        ('receipt', 'Receipt Entry'),
        ('adjustment', 'Adjustment'),
        ('closing', 'Closing Entry'),
    ]
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('posted', '✅ Posted'),
        ('reversed', '🔄 Reversed'),
        ('void', '❌ Void'),
    ]
    
    # Basic Information
    entry_no = models.CharField(max_length=20, unique=True)
    entry_date = models.DateField()
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='manual')
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    
    # Related Documents
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    expense = models.ForeignKey('Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    payment = models.ForeignKey('SalePayment', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_entries')
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='posted_entries')
    posted_at = models.DateTimeField(null=True, blank=True)
    
    # Reversal
    reversed_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reversal_entries')
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    
    # System
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_journal_entries')
    
    class Meta:
        verbose_name_plural = "Journal Entries"
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['entry_no']),
            models.Index(fields=['entry_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.entry_no} - {self.entry_date.strftime('%d-%m-%Y')} - {self.description[:30]}"
    
    def total_debit(self):
        """Total debit amount"""
        return self.items.filter(is_debit=True).aggregate(total=Sum('amount'))['total'] or 0
    
    def total_credit(self):
        """Total credit amount"""
        return self.items.filter(is_debit=False).aggregate(total=Sum('amount'))['total'] or 0
    
    def is_balanced(self):
        """Check if entry is balanced (Debit = Credit)"""
        return self.total_debit() == self.total_credit()
    
    def post(self, user):
        """Post the journal entry"""
        if self.status != 'draft':
            raise ValidationError("Only draft entries can be posted!")
        
        if not self.is_balanced():
            raise ValidationError("Journal entry is not balanced! Debit must equal Credit.")
        
        self.status = 'posted'
        self.posted_by = user
        self.posted_at = now()
        self.save()
        
        # Update account balances
        for item in self.items.all():
            account = item.account
            if item.is_debit:
                account.debit_total = (account.debit_total or 0) + item.amount
            else:
                account.credit_total = (account.credit_total or 0) + item.amount
            account.save()
        
        return True
    
    def reverse(self, user, reason=""):
        """Reverse a posted journal entry"""
        if self.status != 'posted':
            raise ValidationError("Only posted entries can be reversed!")
        
        # Create reversal entry
        reversal = JournalEntry.objects.create(
            entry_no=f"REV-{self.entry_no}",
            entry_date=now().date(),
            entry_type='adjustment',
            reference=f"Reversal of {self.entry_no}",
            description=f"Reversal: {self.description} - Reason: {reason}",
            status='draft',
            created_by=user,
            reversed_from=self
        )
        
        # Create reversal items (opposite)
        for item in self.items.all():
            JournalEntryItem.objects.create(
                journal_entry=reversal,
                account=item.account,
                is_debit=not item.is_debit,  # Reverse the direction
                amount=item.amount,
                description=f"Reversal: {item.description}"
            )
        
        # Post the reversal
        reversal.post(user)
        
        # Mark original as reversed
        self.status = 'reversed'
        self.save()
        
        return reversal
    
    def save(self, *args, **kwargs):
        if not self.entry_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last_entry = JournalEntry.objects.filter(entry_no__startswith=f'JRNL-{year}').order_by('-entry_no').first()
            if last_entry and last_entry.entry_no:
                try:
                    last_num = int(last_entry.entry_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.entry_no = f'JRNL-{year}-{new_num}'
        super().save(*args, **kwargs)


class JournalEntryItem(models.Model):
    """Journal Entry Items - Debit/Credit lines"""
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='items')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='journal_items')
    is_debit = models.BooleanField(help_text="True for Debit, False for Credit")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Journal Entry Items"
        ordering = ['id']
    
    def __str__(self):
        direction = "Dr" if self.is_debit else "Cr"
        return f"{self.account.name} - {direction} - Rs. {self.amount:,.2f}"


# ========================================== #
# 3. GENERAL LEDGER                          #
# ========================================== #

class LedgerEntry(models.Model):
    """General Ledger - All transactions with running balance"""
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='ledger_entries')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='ledger_entries')
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Ledger Entries"
        ordering = ['date', 'id']
        indexes = [
            models.Index(fields=['account', 'date']),
            models.Index(fields=['journal_entry']),
        ]
    
    def __str__(self):
        return f"{self.account.name} - {self.date.strftime('%d-%m-%Y')} - Dr: {self.debit} Cr: {self.credit}"


# ========================================== #
# 4. TRIAL BALANCE                          #
# ========================================== #

class TrialBalance(models.Model):
    """Trial Balance Report - Summary of all accounts"""
    
    as_at_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    opening_debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    opening_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Trial Balance"
        unique_together = ['as_at_date', 'account']
    
    def __str__(self):
        return f"{self.account.name} - {self.as_at_date}"


# ========================================== #
# 5. FINANCIAL STATEMENTS                   #
# ========================================== #

class FinancialStatement(models.Model):
    """Store generated financial statements"""
    
    STATEMENT_TYPES = [
        ('balance_sheet', 'Balance Sheet'),
        ('profit_loss', 'Profit & Loss Statement'),
        ('cash_flow', 'Cash Flow Statement'),
        ('trial_balance', 'Trial Balance'),
    ]
    
    statement_type = models.CharField(max_length=20, choices=STATEMENT_TYPES)
    as_at_date = models.DateField()
    data = models.JSONField()  # Store full statement data
    pdf_file = models.FileField(upload_to='financial_statements/%Y/%m/', null=True, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Financial Statements"
        ordering = ['-as_at_date', '-generated_at']
    
    def __str__(self):
        return f"{self.get_statement_type_display()} - {self.as_at_date}"


# ========================================== #
# 6. FINANCIAL PERIODS                      #
# ========================================== #

class FinancialPeriod(models.Model):
    """Accounting periods (Monthly, Quarterly, Yearly)"""
    
    PERIOD_TYPES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='closed_periods')
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Financial Periods"
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_closed']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date.strftime('%d-%m-%Y')} to {self.end_date.strftime('%d-%m-%Y')})"
    
    def is_active(self):
        from django.utils.timezone import now
        return self.start_date <= now().date() <= self.end_date and not self.is_closed
        
class LoanReturn(models.Model):
    """Loan repayment/return record"""
    
    RETURN_TYPES = [
        ('installment', '📅 Installment Payment'),
        ('full', '💰 Full Settlement'),
        ('partial', '📊 Partial Payment'),
        ('early', '⚡ Early Repayment'),
    ]
    
    # Basic Info
    return_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_agreement_no = models.CharField(max_length=50, verbose_name="Loan Agreement No")
    lender_name = models.CharField(max_length=200, verbose_name="Lender/Bank Name")
    return_type = models.CharField(max_length=20, choices=RETURN_TYPES, default='installment')
    
    # Amounts
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Return Amount")
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    
    # Dates
    return_date = models.DateField(default=now)
    due_date = models.DateField(null=True, blank=True)
    
    # Payment
    payment_method = models.CharField(max_length=50, choices=Expense.PAYMENT_METHODS, default='bank_transfer')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    receipt = models.FileField(upload_to='loan_returns/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', '⏳ Pending'),
        ('paid', '✅ Paid'),
        ('cancelled', '❌ Cancelled'),
    ], default='pending')
    
    # Notes
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loan Returns"
        ordering = ['-return_date']
    
    def __str__(self):
        return f"{self.return_no} - {self.lender_name} - Rs. {self.amount:,.2f}"
    
    def save(self, *args, **kwargs):
        if not self.return_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = LoanReturn.objects.filter(return_no__startswith=f'LR-{year}').order_by('-return_no').first()
            if last and last.return_no:
                try:
                    last_num = int(last.return_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.return_no = f'LR-{year}-{new_num}'
        
        self.total_amount = self.amount + self.interest_amount + self.late_fee
        super().save(*args, **kwargs)
    
    def process_payment(self, user):
        """Process loan return payment - Deduct from main cash"""
        from decimal import Decimal
        
        if self.status == 'paid':
            raise ValidationError("This loan return is already paid!")
        
        try:
            with transaction.atomic():
                # Check main cash balance
                current_balance = CashBalance.get_balance()
                if current_balance < self.total_amount:
                    raise ValidationError(
                        f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                        f"Required: Rs. {self.total_amount:,.2f}"
                    )
                
                # Deduct from main cash
                CashBalance.update_balance(
                    amount=self.total_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Loan Return #{self.return_no} - {self.lender_name} - {self.description or 'Loan repayment'}"
                )
                
                # Update status
                self.status = 'paid'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process payment: {str(e)}")
            
class Loan(models.Model):
    """Loan received from bank/lender"""
    
    LOAN_TYPES = [
        ('business', '🏢 Business Loan'),
        ('personal', '👤 Personal Loan'),
        ('vehicle', '🚗 Vehicle Loan'),
        ('property', '🏠 Property Loan'),
        ('education', '📚 Education Loan'),
        ('other', '📋 Other'),
    ]
    
    LOAN_STATUS = [
        ('active', '✅ Active'),
        ('paid', '💰 Paid'),
        ('defaulted', '❌ Defaulted'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Basic Info
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='business')
    lender_name = models.CharField(max_length=200, verbose_name="Lender/Bank Name")
    lender_contact = models.CharField(max_length=20, blank=True, null=True)
    agreement_no = models.CharField(max_length=50, blank=True, null=True)
    
    # Amounts
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Principal Amount")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Annual interest rate %")
    total_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    loan_date = models.DateField(default=now, verbose_name="Loan Received Date")
    due_date = models.DateField(verbose_name="Due Date")
    paid_date = models.DateField(null=True, blank=True)
    
    # Installments
    total_installments = models.IntegerField(default=0)
    paid_installments = models.IntegerField(default=0)
    installment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='active')
    
    # Purpose
    purpose = models.TextField(blank=True, null=True, verbose_name="Purpose of Loan")
    notes = models.TextField(blank=True, null=True)
    
    # Documents
    agreement_file = models.FileField(upload_to='loan_agreements/', null=True, blank=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loans"
        ordering = ['-loan_date']
        indexes = [
            models.Index(fields=['loan_no']),
            models.Index(fields=['lender_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.loan_no} - {self.lender_name} (Rs. {self.principal_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = Loan.objects.filter(loan_no__startswith=f'LN-{year}').order_by('-loan_no').first()
            if last and last.loan_no:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LN-{year}-{new_num}'
        
        # Calculate totals
        self.total_payable = self.principal_amount + (self.principal_amount * self.interest_rate / 100)
        self.remaining_amount = self.total_payable - self.paid_amount
        
        if self.total_installments > 0:
            self.installment_amount = self.total_payable / self.total_installments
        
        super().save(*args, **kwargs)
    
    def process_loan_received(self, user):
        """Add loan amount to main cash"""
        from decimal import Decimal
        
        try:
            with transaction.atomic():
                # Add to main cash
                CashBalance.update_balance(
                    amount=self.principal_amount,
                    transaction_type='deposit',
                    user=user,
                    description=f"Loan Received: {self.loan_no} - {self.lender_name} - {self.purpose or 'Loan'}"
                )
                
                # Update status
                self.status = 'active'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process loan: {str(e)}")
            
# ========================================== #
# LOAN GIVEN MODEL (Aap ne kisi ko diya)    #
# ========================================== #

class LoanGiven(models.Model):
    """Loan Given to someone (Aap ne kisi ko paisa diya)"""
    
    LOAN_TYPES = [
        ('personal', '👤 Personal Loan'),
        ('business', '🏢 Business Loan'),
        ('employee', '👔 Employee Loan'),
        ('customer', '🛒 Customer Loan'),
        ('friend', '🤝 Friend/Family Loan'),
        ('other', '📋 Other'),
    ]
    
    LOAN_STATUS = [
        ('active', '✅ Active'),
        ('paid', '💰 Paid'),
        ('defaulted', '❌ Defaulted'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Basic Info
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='personal')
    borrower_name = models.CharField(max_length=200, verbose_name="Borrower Name")
    borrower_contact = models.CharField(max_length=20, blank=True, null=True)
    borrower_cnic = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNIC")
    borrower_address = models.TextField(blank=True, null=True)
    
    # Amounts
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Principal Amount")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Annual interest rate %")
    total_receivable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    received_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    loan_date = models.DateField(default=now, verbose_name="Loan Given Date")
    due_date = models.DateField(verbose_name="Expected Return Date")
    paid_date = models.DateField(null=True, blank=True)
    
    # Installments
    total_installments = models.IntegerField(default=0)
    received_installments = models.IntegerField(default=0)
    installment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='active')
    
    # Documents
    agreement_file = models.FileField(upload_to='loan_given_agreements/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    # Guarantor
    guarantor_name = models.CharField(max_length=200, blank=True, null=True)
    guarantor_contact = models.CharField(max_length=20, blank=True, null=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loans Given"
        ordering = ['-loan_date']
        indexes = [
            models.Index(fields=['loan_no']),
            models.Index(fields=['borrower_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.loan_no} - {self.borrower_name} (Rs. {self.principal_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = LoanGiven.objects.filter(loan_no__startswith=f'LG-{year}').order_by('-loan_no').first()
            if last and last.loan_no:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LG-{year}-{new_num}'
        
        # Calculate totals
        self.total_receivable = self.principal_amount + (self.principal_amount * self.interest_rate / 100)
        self.remaining_amount = self.total_receivable - self.received_amount
        
        if self.total_installments > 0:
            self.installment_amount = self.total_receivable / self.total_installments
        
        super().save(*args, **kwargs)
    
    def process_loan_given(self, user):
        """✅ Cash OUTFLOW - Aap ne paisa diya"""
        from decimal import Decimal
        
        try:
            with transaction.atomic():
                # Check if sufficient cash balance
                current_balance = CashBalance.get_balance()
                if current_balance < self.principal_amount:
                    raise ValidationError(
                        f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                        f"Required: Rs. {self.principal_amount:,.2f}"
                    )
                
                # Cash OUTFLOW
                CashBalance.update_balance(
                    amount=self.principal_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Loan Given to {self.borrower_name} - {self.loan_no}"
                )
                
                self.status = 'active'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process loan: {str(e)}")
    
    def receive_payment(self, amount, user, payment_method='cash', reference_no=''):
        """✅ Receive payment from borrower (Cash INFLOW)"""
        from decimal import Decimal
        
        if self.status == 'paid':
            raise ValidationError("This loan is already fully paid!")
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero!")
        
        if amount > self.remaining_amount:
            raise ValidationError(f"Amount exceeds remaining balance: Rs. {self.remaining_amount:,.2f}")
        
        try:
            with transaction.atomic():
                # Cash INFLOW - Payment received
                CashBalance.update_balance(
                    amount=amount,
                    transaction_type='deposit',
                    user=user,
                    description=f"Loan repayment from {self.borrower_name} - {self.loan_no}"
                )
                
                # Update loan
                self.received_amount += amount
                self.remaining_amount = self.total_receivable - self.received_amount
                
                # Update installments
                if self.total_installments > 0:
                    self.received_installments += 1
                
                if self.remaining_amount <= 0:
                    self.status = 'paid'
                    self.paid_date = now().date()
                
                self.save()
                
                # Create payment record
                LoanGivenPayment.objects.create(
                    loan_given=self,
                    amount=amount,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    reference_no=reference_no,
                    created_by=user
                )
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to record payment: {str(e)}")


class LoanGivenPayment(models.Model):
    """Payments received from borrower"""
    
    loan_given = models.ForeignKey(LoanGiven, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, default='cash')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.loan_given.loan_no} - Rs. {self.amount:,.2f} on {self.payment_date}"
        
 # ========================================== #
# VENDOR PAYMENT MODEL                       #
# ========================================== #

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
        
# ========================================== #
# CUSTOMER PAYMENT MODEL                     #
# ========================================== #

class CustomerPayment(models.Model):
    """Customer payment record - Separate from SalePayment"""
    
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='payments')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_payments')  # ✅ Changed
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateTimeField(default=now)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Customer Payments"
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['customer', 'payment_date']),
            models.Index(fields=['sale']),
        ]
    
    def __str__(self):
        return f"{self.customer.name} - Rs. {self.amount:,.2f} - {self.payment_date.strftime('%d-%m-%Y')}"
        
# ========================================== #
# TERMS & CONDITIONS MODELS                   #
# ========================================== #

class TermsAndConditions(models.Model):
    """Terms & Conditions for Shareholders"""
    
    version = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200, default="Shareholder Terms & Conditions")
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    effective_date = models.DateField(default=now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Terms & Conditions"
        ordering = ['-version']
    
    def __str__(self):
        return f"Terms v{self.version} - {self.effective_date}"


class ShareholderTermsAcceptance(models.Model):
    """Track shareholder acceptance of terms"""
    
    shareholder = models.OneToOneField('Shareholder', on_delete=models.CASCADE, related_name='terms_acceptance')
    terms_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(default=now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Terms Acceptances"
    
    def __str__(self):
        return f"{self.shareholder.name} - Accepted v{self.terms_version}"


# ========================================== #
# SHAREHOLDER SUPPORT TICKET MODEL           #
# ========================================== #

class ShareholderSupportTicket(models.Model):
    """Support tickets for shareholders"""
    
    STATUS_CHOICES = [
        ('new', '🆕 New'),
        ('in_progress', '⚙️ In Progress'),
        ('resolved', '✅ Resolved'),
        ('closed', '🔒 Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🔴 High'),
        ('urgent', '🔥 Urgent'),
    ]
    
    ticket_no = models.CharField(max_length=20, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    attachment = models.FileField(upload_to='support_tickets/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Support Tickets"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.ticket_no} - {self.subject[:30]}"
    
    def save(self, *args, **kwargs):
        if not self.ticket_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.ticket_no = f'ST-{timestamp}'
        super().save(*args, **kwargs)


class SupportTicketReply(models.Model):
    """Replies to support tickets"""
    
    ticket = models.ForeignKey(ShareholderSupportTicket, on_delete=models.CASCADE, related_name='replies')
    message = models.TextField()
    is_internal = models.BooleanField(default=False, help_text="Internal note (not visible to shareholder)")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to='support_replies/', null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Support Ticket Replies"
        ordering = ['created_at']
    
    def __str__(self):
        return f"Reply to {self.ticket.ticket_no}"
        
class ShareholderLoginRequest(models.Model):
    """
    Shareholder login request - pending approval
    Admin approve karega to user + shareholder create ho ga
    """
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
    ]
    
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    full_name = models.CharField(max_length=200, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    phone = models.CharField(max_length=20, verbose_name="Phone Number")
    cnic = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNIC")
    address = models.TextField(blank=True, null=True, verbose_name="Address")
    notes = models.TextField(blank=True, null=True, verbose_name="Additional Notes")
    
    # ========================================== #
    # REQUEST DETAILS                           #
    # ========================================== #
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Requested At")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Status")
    
    # ========================================== #
    # ADMIN RESPONSE                            #
    # ========================================== #
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reviewed_requests',
        verbose_name="Reviewed By"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Reviewed At")
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="Rejection Reason")
    
    # ========================================== #
    # ✅ GENERATED CREDENTIALS - YEH IMPORTANT   #
    # ========================================== #
    generated_username = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        verbose_name="Generated Username"
    )
    generated_password = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        verbose_name="Generated Password"
    )
    
    # ========================================== #
    # CREATED SHAREHOLDER                       #
    # ========================================== #
    created_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='login_requests',
        verbose_name="Created Shareholder"
    )
    
    # ========================================== #
    # IP AND DEVICE INFO                        #
    # ========================================== #
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="User Agent")
    
    # ========================================== #
    # META                                      #
    # ========================================== #
    class Meta:
        verbose_name_plural = "Shareholder Login Requests"
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['email']),
            models.Index(fields=['requested_at']),
        ]
    
    def __str__(self):
        return f"{self.full_name} - {self.email} ({self.get_status_display()})"
    
    # ========================================== #
    # ✅ APPROVE METHOD - COMPLETE              #
    # ========================================== #
    
    def approve(self, admin_user):
        """
        ✅ Approve request and create:
        1. User account
        2. Shareholder profile
        3. Cash balance
        4. Store credentials
        """
        from django.contrib.auth.models import User
        from django.utils.timezone import now
        from django.db import transaction
        from decimal import Decimal
        import secrets
        import string
        
        # Check if already approved
        if self.status == 'approved':
            raise ValidationError("This request is already approved!")
        
        # Check if already rejected
        if self.status == 'rejected':
            raise ValidationError("This request was rejected and cannot be approved!")
        
        try:
            with transaction.atomic():
                # ========================================== #
                # STEP 1: CREATE USERNAME                   #
                # ========================================== #
                username = self.email.split('@')[0]
                base_username = username
                counter = 1
                
                # Ensure username is unique
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # ========================================== #
                # STEP 2: GENERATE RANDOM PASSWORD          #
                # ========================================== #
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for i in range(10))
                
                # ========================================== #
                # STEP 3: CREATE USER                       #
                # ========================================== #
                user = User.objects.create_user(
                    username=username,
                    email=self.email,
                    password=password
                )
                user.is_active = True
                user.first_name = self.full_name.split()[0] if self.full_name else ''
                user.last_name = ' '.join(self.full_name.split()[1:]) if self.full_name else ''
                user.save()
                
                # ========================================== #
                # STEP 4: CREATE SHAREHOLDER                #
                # ========================================== #
                shareholder = Shareholder.objects.create(
                    user=user,
                    name=self.full_name,
                    email=self.email,
                    phone=self.phone,
                    cnic=self.cnic,
                    address=self.address,
                    allow_login=True,
                    status='active',
                    created_by=user,
                    shareholder_type='individual',
                    notes=f"Created from registration request #{self.id}"
                )
                
                # ========================================== #
                # STEP 5: CREATE CASH BALANCE               #
                # ========================================== #
                ShareholderCashBalance.objects.create(
                    shareholder=shareholder,
                    balance=Decimal('0.00')
                )
                
                # ========================================== #
                # STEP 6: ✅ STORE CREDENTIALS - YEH IMPORTANT #
                # ========================================== #
                self.generated_username = username
                self.generated_password = password  # Plain password store for display
                
                # ========================================== #
                # STEP 7: UPDATE REQUEST STATUS            #
                # ========================================== #
                self.status = 'approved'
                self.reviewed_by = admin_user
                self.reviewed_at = now()
                self.created_shareholder = shareholder
                
                # ✅ FORCE SAVE WITH UPDATE_FIELDS
                self.save(update_fields=[
                    'generated_username',
                    'generated_password',
                    'status',
                    'reviewed_by',
                    'reviewed_at',
                    'created_shareholder'
                ])
                
                # ========================================== #
                # STEP 8: CREATE NOTIFICATION               #
                # ========================================== #
                try:
                    from .models import Notification
                    # Notify admin
                    Notification.send(
                        user=admin_user,
                        title="✅ Shareholder Request Approved",
                        message=f"{self.full_name} has been approved as shareholder! Username: {username}",
                        notification_type='success',
                        category='system',
                        link=f"/shareholder-requests/{self.id}/"
                    )
                except:
                    pass
                
                # ========================================== #
                # STEP 9: RETURN RESULT                     #
                # ========================================== #
                return {
                    'success': True,
                    'user': user,
                    'shareholder': shareholder,
                    'username': username,
                    'password': password,
                    'email': self.email,
                    'message': f"✅ Request approved! Username: {username}, Password: {password}"
                }
                
        except Exception as e:
            # Rollback will happen automatically due to atomic
            raise ValidationError(f"Approval failed: {str(e)}")
    
    # ========================================== #
    # REJECT METHOD                             #
    # ========================================== #
    
    def reject(self, admin_user, reason=""):
        """
        ❌ Reject request with reason
        """
        from django.utils.timezone import now
        
        if self.status == 'approved':
            raise ValidationError("Cannot reject an already approved request!")
        
        if self.status == 'rejected':
            raise ValidationError("This request is already rejected!")
        
        self.status = 'rejected'
        self.reviewed_by = admin_user
        self.reviewed_at = now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])
        
        # Create notification
        try:
            from .models import Notification
            Notification.send(
                user=admin_user,
                title="❌ Shareholder Request Rejected",
                message=f"{self.full_name}'s request was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='system',
                link=f"/shareholder-requests/{self.id}/"
            )
        except:
            pass
        
        return {
            'success': True,
            'message': f"Request rejected! Reason: {reason or 'Not specified'}"
        }
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_rejected(self):
        return self.status == 'rejected'
    
    @property
    def can_act(self):
        """Can admin act on this request?"""
        return self.status == 'pending'
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'pending':
            return '<span class="badge bg-warning text-dark">⏳ Pending</span>'
        elif self.status == 'approved':
            return '<span class="badge bg-success">✅ Approved</span>'
        else:
            return '<span class="badge bg-danger">❌ Rejected</span>'
    
    @property
    def has_credentials(self):
        """Check if credentials are stored"""
        return bool(self.generated_username and self.generated_password)
    
    @property
    def formatted_date(self):
        return self.requested_at.strftime('%d-%m-%Y %H:%M')
    
    @property
    def formatted_reviewed_date(self):
        if self.reviewed_at:
            return self.reviewed_at.strftime('%d-%m-%Y %H:%M')
        return '-'