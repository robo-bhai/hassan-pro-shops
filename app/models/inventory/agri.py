"""Agri Edition: write-off of expired / damaged stock (kept as a record, one row per batch written off)."""
from decimal import Decimal

from django.conf import settings
from django.db import models


class ExpiryWriteOff(models.Model):
    REASONS = [
        ('expired', 'Expired'),
        ('damaged', 'Damaged / spoiled'),
        ('vendor_return', 'Sent back to supplier'),
    ]
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='agri_writeoffs')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='agri_writeoffs')
    batch = models.ForeignKey('StockBatch', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    batch_no = models.CharField(max_length=50, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    qty = models.FloatField()
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    reason = models.CharField(max_length=20, choices=REASONS, default='expired')
    note = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Agri: Expiry write-offs'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.product} x {self.qty:g} ({self.get_reason_display()})"
