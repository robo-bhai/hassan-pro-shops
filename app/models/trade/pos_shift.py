"""Cashier shift (counter shift) and its cash accounting."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now

from ..inventory.catalog import Warehouse


class CashierShift(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed')]

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cashier_shifts')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='cashier_shifts')
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='open')
    opened_at = models.DateTimeField(default=now)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    # Frozen on close (so the shift report stays the same even if sales change later)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='cashier_shifts_closed')
    sales_count = models.PositiveIntegerField(default=0)
    total_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    credit_given = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cash_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    card_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    wallet_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    bank_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cash_in = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cash_out = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name_plural = "Cashier Shifts"
        ordering = ['-opened_at', '-id']
        indexes = [models.Index(fields=['status'], name='app_cashier_status_a1b2c3_idx'),
                   models.Index(fields=['opened_at'], name='app_cashier_opened__d4e5f6_idx')]

    def __str__(self):
        return f"Shift #{self.pk} {self.user.get_username()} @ {self.warehouse.name}"


class ShiftCashMovement(models.Model):
    """Shift ke dauran drawer me paisay daalna (in) ya nikalna (out: chai, rickshaw, bank jama...)."""
    KIND_CHOICES = [('in', 'Cash in'), ('out', 'Cash out')]

    shift = models.ForeignKey(CashierShift, on_delete=models.CASCADE, related_name='movements')
    kind = models.CharField(max_length=3, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Shift Cash Movements"
        ordering = ['created_at', 'id']
