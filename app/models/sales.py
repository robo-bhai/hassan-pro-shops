"""Sales models."""
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
from django.db.models import F
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
import logging

logger = logging.getLogger(__name__)
from .catalog import MonthlyClosing, Product, Warehouse

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
        null=True,          # ✅ Temporarily allow null for the migration
        blank=True,         # ✅ Temporarily allow blank in the form
        verbose_name=_("Customer Code"),
        help_text="Enter unique customer code manually (e.g., CUS-001, WALKIN)"
    )
    name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    
    
    # ✅ ADD THIS LINE
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name="Email")
   
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
        # ✅ If customer_code is empty, auto-generate it
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
                from . import CashBalance
                total_amount = self.total_amount()
                if total_amount > 0:
                    CashBalance.update_balance(
                        amount=total_amount,
                        transaction_type='sale',
                        user=self.created_by,
                        description=f"Sale #{self.bill_no} - {self.customer.name}"
                    )
            except Exception as e:
                # If the cash update fails, only log it; the sale must not stop
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
                pass  # If WhatsApp fails, the sale must not stop


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
    # FIFO cost of the goods at the moment of sale (Step 3: this is what the ledger books as Cost of Goods Sold).
    # NULL = old sale that has no saved cost yet -> run `manage.py post_ledger --backfill-cost`.
    cost_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, editable=False)

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
        
        # ✅ First check the available stock
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
    # ✅ SAVE METHOD (FIXED - FIFO first, stock after)
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

        # ✅ STEP 1: First calculate the FIFO price (before consuming stock)
        fifo_price = self.get_fifo_price()
        recommended_price = self.calculate_sale_price(fifo_price)
        
        # ✅ STEP 2: Now set the price
        if self.price and Decimal(self.price) > 0:
            self.price = Decimal(self.price)
        else:
            self.price = recommended_price

        # ✅ STEP 3: Now validate and update the stock
        total_cost, used_batches = self.validate_and_update_stock()
        self.cost_amount = Decimal(total_cost).quantize(Decimal('0.01'))
        
        # ✅ STEP 4: Batch selling price validation
        if used_batches:
            for batch in used_batches:
                if batch.selling_price and batch.selling_price > 0:
                    if self.price < batch.selling_price:
                        raise ValidationError(
                            f"Sale price (Rs. {self.price:,.2f}) for {self.product.name} "
                            f"cannot be lower than the batch selling price (Rs. {batch.selling_price:,.2f})!"
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
    
    def _original_unit_cost(self):
        """Unit cost the goods left stock at (saved on the sale item). None for old sales without a saved cost."""
        sale = self.sale_return.sale if self.sale_return_id else None
        if not sale:
            return None
        agg = SaleItem.objects.filter(sale=sale, product=self.product).aggregate(c=Sum('cost_amount'), q=Sum('qty'))
        if agg['c'] and agg['q']:
            return (Decimal(str(agg['c'])) / Decimal(str(agg['q']))).quantize(Decimal('0.01'))
        return None

    def _increase_stock(self, qty, warehouse):
        """Increase stock in batches - at the ORIGINAL COST (Step 3b), so stock value matches the ledger"""
        remaining = qty
        cost = self._original_unit_cost() or self.price      # old sale without a saved cost: previous behaviour
        
        # Try to find existing batch with same cost
        existing_batch = StockBatch.objects.filter(
            product=self.product,
            warehouse=warehouse,
            price=cost,
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
                price=cost
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
        
        if self.qty + Decimal(str(already_returned)) > Decimal(str(sale_item.qty)) + Decimal('0.005'):
            raise ValidationError(
                f"Quantity exceeds sale: Available {Decimal(str(sale_item.qty)) - Decimal(str(already_returned))}, "
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
        from . import SalePayment
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
