"""Models: trade/sales (split from the former sales.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from datetime import timedelta
from django.utils.timezone import now
from django.utils.timezone import localdate
from django.db.models import Sum
from django.db.models import F
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from ..inventory.catalog import MonthlyClosing, Product, Warehouse
from .customers import Customer

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
    # [agri-edition:sale] promised repayment date (harvest) for credit sales
    harvest_due_date = models.DateField(null=True, blank=True, db_index=True)
    harvest_note = models.CharField(max_length=200, blank=True, default='')

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
                from .. import CashBalance
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
                from ..whatsapp_utils import WhatsAppSender
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
        batches = StockBatch.get_batches_for_sale(self.product, self.qty, warehouse, skip_expired=True)  # [agri-edition:sale-fifo]
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
        
        batches = StockBatch.get_batches_for_sale(self.product, self.qty, warehouse, skip_expired=True)  # [agri-edition:sale-stock]
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
