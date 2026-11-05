"""Price history (audit log) model.

One row = one price that changed: who changed it, when, the old and the new value, and why.
Rows are append-only: they can not be edited or deleted (not from code, not from the admin).
A bulk apply writes one row per batch, all sharing the same ``run_id`` - the later
"undo" step uses that id to roll a whole bulk run back.
"""
import uuid

from django.conf import settings
from django.db import models


class PriceChangeLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError('Price history is append-only: rows can not be updated.')

    def delete(self):
        raise PermissionError('Price history is append-only: rows can not be deleted.')


class PriceChangeLog(models.Model):
    FIELD_BATCH_SELLING = 'batch_selling_price'
    FIELD_PRODUCT_PRICE = 'product_price'
    FIELD_PRODUCT_DISCOUNT = 'product_discount'
    FIELD_CHOICES = [
        (FIELD_BATCH_SELLING, 'Batch selling price'),
        (FIELD_PRODUCT_PRICE, 'Product price'),
        (FIELD_PRODUCT_DISCOUNT, 'Product discount %'),
    ]

    SOURCE_SINGLE = 'single'
    SOURCE_BULK = 'bulk'
    SOURCE_UNDO = 'undo'
    SOURCE_APPROVAL = 'approval'
    SOURCE_SYSTEM = 'system'
    SOURCE_CHOICES = [
        (SOURCE_SINGLE, 'Single edit'),
        (SOURCE_BULK, 'Bulk apply'),
        (SOURCE_UNDO, 'Undo'),
        (SOURCE_APPROVAL, 'Approved request'),
        (SOURCE_SYSTEM, 'System'),
    ]

    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    price_field = models.CharField(max_length=30, choices=FIELD_CHOICES, default=FIELD_BATCH_SELLING, db_index=True)
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default=SOURCE_SINGLE, db_index=True)

    product = models.ForeignKey('app.Product', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='price_logs')
    batch = models.ForeignKey('app.StockBatch', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='price_logs')
    # Snapshots: the history stays readable even if the product / batch / user is deleted later.
    product_name = models.CharField(max_length=100, blank=True, default='')
    batch_ref = models.CharField(max_length=40, blank=True, default='')

    old_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                     help_text='Batch cost at the time of the change')

    run_id = models.UUIDField(null=True, blank=True, db_index=True,
                              help_text='Same id for every row of one bulk apply')
    rule = models.JSONField(null=True, blank=True, help_text='Bulk rule used: mode / value / rounding')
    reason = models.CharField(max_length=255, blank=True, default='')

    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='price_changes')
    changed_by_name = models.CharField(max_length=150, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = PriceChangeLogQuerySet.as_manager()

    class Meta:
        ordering = ['-changed_at', '-id']
        verbose_name = 'Price change'
        verbose_name_plural = 'Price history'
        indexes = [
            models.Index(fields=['product', '-changed_at']),
            models.Index(fields=['batch', '-changed_at']),
        ]

    def __str__(self):
        return f'{self.product_name or "?"} {self.old_value} -> {self.new_value} ({self.changed_at:%Y-%m-%d %H:%M})'

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise PermissionError('Price history is append-only: rows can not be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Price history is append-only: rows can not be deleted.')

    @property
    def difference(self):
        if self.old_value is None or self.new_value is None:
            return None
        return self.new_value - self.old_value

    @property
    def change_percent(self):
        if not self.old_value or self.new_value is None:
            return None
        return (self.new_value - self.old_value) / self.old_value * 100
