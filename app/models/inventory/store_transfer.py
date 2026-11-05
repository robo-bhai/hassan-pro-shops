"""Sending goods from store to store (dispatch) and receiving them."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


class StoreTransfer(models.Model):
    """
    Goods from one store to another:  sent (in_transit)  ->  received (received).
    As soon as goods are sent they leave the source store (FIFO); they arrive in the destination only when the
    team there receives them. Goods on the way show as "in transit", they do not disappear.
    """
    PURPOSES = [
        ("production", "For production (raw material)"),
        ("packing", "For packing"),
        ("finished", "Tayyar maal (finished goods)"),
        ("technical", "Technical / maintenance saman"),
        ("return", "Wapsi"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("in_transit", "In transit (bheja gaya)"),
        ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]

    transfer_no = models.CharField(max_length=20, unique=True, editable=False)
    transfer_date = models.DateTimeField(default=now)
    from_warehouse = models.ForeignKey("Warehouse", on_delete=models.PROTECT, related_name="store_transfers_out")
    to_warehouse = models.ForeignKey("Warehouse", on_delete=models.PROTECT, related_name="store_transfers_in")
    purpose = models.CharField(max_length=20, choices=PURPOSES, default="production")
    production_order = models.ForeignKey("ProductionOrder", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="store_transfers")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="in_transit")
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), editable=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="store_transfers_sent")
    created_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="store_transfers_received")
    received_at = models.DateTimeField(null=True, blank=True)
    receive_notes = models.CharField(max_length=255, blank=True, default="")
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name_plural = "Store Transfers"
        ordering = ["-transfer_date", "-id"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["transfer_date"])]

    def __str__(self):
        return f"{self.transfer_no}: {self.from_warehouse} -> {self.to_warehouse}"


class StoreTransferItem(models.Model):
    transfer = models.ForeignKey(StoreTransfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("Product", on_delete=models.PROTECT, related_name="store_transfer_items")
    qty_sent = models.FloatField()
    qty_received = models.FloatField(null=True, blank=True)       # receive hone tak khali
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    short_reason = models.CharField(max_length=200, blank=True, default="")
    remarks = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        verbose_name_plural = "Store Transfer Items"

    @property
    def qty_short(self):
        if self.qty_received is None:
            return 0.0
        return round(self.qty_sent - self.qty_received, 6)


class StoreTransferBatchUsage(models.Model):
    """How much came out of which source batch; on receive a new batch with the same cost is created at the destination."""
    item = models.ForeignKey(StoreTransferItem, on_delete=models.CASCADE, related_name="usages")
    batch = models.ForeignKey("StockBatch", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="store_transfer_usages")
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    received_qty = models.FloatField(default=0)
    dest_batch = models.ForeignKey("StockBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name_plural = "Store Transfer Batch Usage"
