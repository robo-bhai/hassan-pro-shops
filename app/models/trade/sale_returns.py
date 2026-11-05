"""Models: trade/sale_returns (split from the former sales.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from ..inventory.catalog import MonthlyClosing, Warehouse
from .customers import Customer
from .sales import Sale
logger = logging.getLogger(__name__)

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

    def _agri_source_batch(self):
        """[agri-edition:sale-return] The batch this product was sold from on the original bill (None if unknown)."""
        sale = self.sale_return.sale if self.sale_return_id else None
        if not sale:
            return None
        return (StockBatch.objects.filter(sale_items__sale=sale, product=self.product)
                .order_by('id').first())

    def _increase_stock(self, qty, warehouse):
        """Increase stock in batches - at the ORIGINAL COST (Step 3b), so stock value matches the ledger"""
        remaining = qty
        cost = self._original_unit_cost() or self.price      # old sale without a saved cost: previous behaviour
        src = self._agri_source_batch()
        
        # Try to find existing batch with same cost (and, if known, the same batch no / expiry)
        _qs = StockBatch.objects.filter(
            product=self.product,
            warehouse=warehouse,
            price=cost,
            remaining_qty__gt=0
        )
        if src is not None:
            _qs = _qs.filter(expiry_date=src.expiry_date, batch_no=src.batch_no)
        existing_batch = _qs.order_by('id').first()
        
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
                price=cost,
                batch_no=src.batch_no if src is not None else None,        # [agri-edition:sale-return]
                expiry_date=src.expiry_date if src is not None else None,
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
