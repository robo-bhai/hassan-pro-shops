"""Store operations: settings, accounting mapping, approval requests, physical count, return to store."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


# ---------------------------------------------------------------------------
# Settings + accounting mapping
# ---------------------------------------------------------------------------
class StoreSetting(models.Model):
    """Ek hi row (pk=1): accounting on/off aur approval ka qaida."""
    APPROVAL_MODES = [
        ('off', 'No approval (issue immediately)'),
        ('above_limit', 'Approval on issues over the limit'),
        ('always', 'Approval on every issue (for the keeper)'),
    ]
    accounting_enabled = models.BooleanField(default=False,
                                             help_text="If ON, a journal entry is created automatically on issue / transfer / count / return")
    approval_mode = models.CharField(max_length=12, choices=APPROVAL_MODES, default='off')
    approval_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'),
                                         help_text="For 'Over the limit': estimated cost of the issue (Rs.)")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Store Settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class StoreAccountRule(models.Model):
    """Which account in the Chart of Accounts the store accounting should be linked to."""
    KINDS = [
        ('inventory', 'Inventory account (empty key = default for all stores, or a warehouse id)'),
        ('expense', 'Issue expense / WIP account (key = issue type, empty = default)'),
        ('transit', 'In-transit account (goods between stores)'),
        ('count_loss', 'Stock loss (count shortage)'),
        ('count_gain', 'Stock gain (count surplus)'),
        ('opening', 'Opening balance (equity)'),
    ]
    kind = models.CharField(max_length=12, choices=KINDS)
    key = models.CharField(max_length=30, blank=True, default='')
    account = models.ForeignKey('Account', on_delete=models.PROTECT, related_name='+')

    class Meta:
        unique_together = ('kind', 'key')
        verbose_name_plural = "Store Account Rules"

    def __str__(self):
        return f"{self.kind}[{self.key or 'default'}] -> {self.account}"


class StoreJournalLink(models.Model):
    """Which store document is linked to which journal entry (so a reverse entry can be made on cancel)."""
    doc_type = models.CharField(max_length=20)       # issue, return, transfer_send, transfer_receive, count, opening
    doc_id = models.PositiveIntegerField()
    journal_entry = models.ForeignKey('JournalEntry', on_delete=models.SET_NULL, null=True, related_name='+')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['doc_type', 'doc_id'])]


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------
class StoreIssueRequest(models.Model):
    STATUS = [('pending', 'Pending approval'), ('approved', 'Approved (issued)'),
              ('rejected', 'Rejected'), ('cancelled', 'Cancelled')]
    request_no = models.CharField(max_length=20, unique=True, editable=False)
    from_warehouse = models.ForeignKey('Warehouse', on_delete=models.PROTECT, related_name='store_issue_requests')
    issue_type = models.CharField(max_length=20)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    production_order = models.ForeignKey('ProductionOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    received_by = models.CharField(max_length=100, blank=True, default='')
    purpose = models.TextField(blank=True, default='')
    issue_date = models.DateTimeField(default=now)
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    est_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='store_requests')
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, default='')
    issue = models.OneToOneField('StoreIssue', on_delete=models.SET_NULL, null=True, blank=True, related_name='request')

    class Meta:
        ordering = ['-requested_at']
        verbose_name_plural = "Store Issue Requests"

    def __str__(self):
        return self.request_no

    def get_issue_type_label(self):
        from .store_issue import StoreIssue
        return dict(StoreIssue.ISSUE_TYPES).get(self.issue_type, self.issue_type)


class StoreIssueRequestItem(models.Model):
    request = models.ForeignKey(StoreIssueRequest, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='+')
    qty = models.FloatField()
    remarks = models.CharField(max_length=200, blank=True, default='')


# ---------------------------------------------------------------------------
# Physical count
# ---------------------------------------------------------------------------
class StoreCount(models.Model):
    STATUS = [('counting', 'Counting in progress'), ('submitted', 'Sent for review'),
              ('posted', 'Posted'), ('cancelled', 'Cancelled')]
    count_no = models.CharField(max_length=20, unique=True, editable=False)
    warehouse = models.ForeignKey('Warehouse', on_delete=models.PROTECT, related_name='store_counts')
    count_date = models.DateTimeField(default=now)
    notes = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS, default='counting')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='store_counts_created')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    submitted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    posted_at = models.DateTimeField(null=True, blank=True)
    loss_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    gain_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['-count_date', '-id']
        verbose_name_plural = "Store Counts"

    def __str__(self):
        return f"{self.count_no} ({self.warehouse})"


class StoreCountLine(models.Model):
    count = models.ForeignKey(StoreCount, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='+')
    system_qty = models.FloatField(default=0)              # how much was in the system when the count started
    counted_qty = models.FloatField(null=True, blank=True)  # asal ginti
    posted_system_qty = models.FloatField(null=True, blank=True)   # how much was in the system at the time of posting
    diff_qty = models.FloatField(default=0)                 # after posting: counted - posted_system
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    diff_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    reason = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['product__name']


# ---------------------------------------------------------------------------
# Return to store
# ---------------------------------------------------------------------------
class StoreReturn(models.Model):
    return_no = models.CharField(max_length=20, unique=True, editable=False)
    issue = models.ForeignKey('StoreIssue', on_delete=models.PROTECT, related_name='returns')
    return_date = models.DateTimeField(default=now)
    returned_by = models.CharField(max_length=100, blank=True, default='')      # who returned it
    notes = models.CharField(max_length=255, blank=True, default='')
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='store_returns_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-return_date', '-id']
        verbose_name_plural = "Store Returns"

    def __str__(self):
        return self.return_no


class StoreReturnLine(models.Model):
    ret = models.ForeignKey(StoreReturn, on_delete=models.CASCADE, related_name='lines')
    issue_item = models.ForeignKey('StoreIssueItem', on_delete=models.PROTECT, related_name='return_lines')
    qty = models.FloatField()
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    condition = models.CharField(max_length=100, blank=True, default='')


class StoreReturnBatch(models.Model):
    """Which batch the returned goods went into (the same batch they came from)."""
    line = models.ForeignKey(StoreReturnLine, on_delete=models.CASCADE, related_name='batches')
    usage = models.ForeignKey('StoreIssueBatchUsage', on_delete=models.PROTECT, related_name='returns')
    qty = models.FloatField()
