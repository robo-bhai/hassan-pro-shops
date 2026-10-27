"""Models: trade/purchase_returns (split from the former purchasing.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
import logging
from django.utils.translation import gettext_lazy as _
from ..inventory.catalog import Warehouse
logger = logging.getLogger(__name__)

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
                'date': ret.purchase_return_date.strftime('%d-%m-%Y %I:%M %p'),
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
        return self.purchase_return_date.strftime('%d-%m-%Y %I:%M %p')
    
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
                    self.adjust_batches(qty_diff, warehouse)  # ✅ Decimal is being passed
                    Inventory.update_stock(self.product, -float(qty_diff), warehouse)  # ✅ convert to float
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
        # ✅ Convert qty_diff to float for calculations
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
                    purchase_item=purchase_item,
                    batch_no=getattr(purchase_item, 'batch_no', None),      # [agri-edition:purchase-return]
                    expiry_date=getattr(purchase_item, 'expiry_date', None),
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

        if self.qty > Decimal(str(purchase_item.qty)) + Decimal('0.005'):
            raise ValidationError(
                f"Quantity exceeds purchase limit: Purchased quantity is {purchase_item.qty}, but return quantity is {self.qty}."
            )

    def __str__(self):
        return f"{self.qty} x {self.product.name}"

    class Meta:
        verbose_name_plural = '4.4. Purchase Return Items'
