"""Internal stock issue (non-sale) + store profiles (PMS / RMS / FGS / Technical)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


class StoreProfile(models.Model):
    """Marks a Warehouse as a named store (PMS, RMS, FGS, Technical...)."""
    STORE_TYPES = [
        ('PMS', 'Packing Material Store'),
        ('RMS', 'Raw Material Store'),
        ('FGS', 'Finished Goods Store'),
        ('TECH', 'Technical Store'),
        ('GEN', 'General Store'),
    ]
    warehouse = models.OneToOneField('Warehouse', on_delete=models.CASCADE, related_name='store_profile')
    code = models.CharField(max_length=10, unique=True)
    store_type = models.CharField(max_length=5, choices=STORE_TYPES, default='GEN')
    can_issue = models.BooleanField(default=True, help_text="Internal issue is allowed from this store")
    keeper = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='kept_stores', verbose_name="Store keeper")
    BUSINESS_UNIT_CHOICES = [('', 'Store type ka default'), ('shop', 'Shop'), ('factory', 'Factory'),
                             ('both', 'Shop + Factory')]
    business_unit = models.CharField(
        max_length=10, blank=True, default='', choices=BUSINESS_UNIT_CHOICES,
        help_text="Which company type this store is for. Empty = the store type default.")
    allowed_modules = models.CharField(
        max_length=500, blank=True, default='',
        help_text="Which modules this store team gets in the sidebar (comma separated keys). "
                  "Empty = the store type default.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Store Profiles"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.warehouse.name}"

    def effective_unit(self):
        from ..module_catalog import STORE_TYPE_UNITS
        return self.business_unit or STORE_TYPE_UNITS.get(self.store_type, 'both')

    def available_in(self, mode):
        """Should this store run in the current business mode (shop / factory / both)?"""
        unit = self.effective_unit()
        return mode == 'both' or unit == 'both' or unit == mode

    def effective_modules(self):
        """Set of module keys for this store team (custom if set, otherwise the type default)."""
        from ..module_catalog import STORE_TYPE_MODULES, get_module_keys
        valid = set(get_module_keys())
        custom = {k.strip() for k in (self.allowed_modules or '').split(',') if k.strip()}
        if custom:
            return custom & valid
        return set(STORE_TYPE_MODULES.get(self.store_type, STORE_TYPE_MODULES['GEN'])) & valid


class StoreIssue(models.Model):
    """Issuing stock inside the company (not a sale): production, packing, maintenance, ..."""
    ISSUE_TYPES = [
        ('production', 'Production / Manufacturing'),
        ('packing', 'Packing'),
        ('maintenance', 'Maintenance & Repair'),
        ('technical', 'Technical / Workshop Use'),
        ('office', 'Office / Internal Use'),
        ('sample', 'Sample / Testing'),
        ('damage', 'Damage / Wastage / Write-off'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [('issued', 'Issued'), ('cancelled', 'Cancelled')]

    issue_no = models.CharField(max_length=20, unique=True, editable=False)
    issue_date = models.DateTimeField(default=now)
    from_warehouse = models.ForeignKey('Warehouse', on_delete=models.PROTECT, related_name='store_issues')
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPES, default='production')
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='store_issues')
    production_order = models.ForeignKey('ProductionOrder', on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='store_issues')
    received_by = models.CharField(max_length=100, blank=True, default='')
    purpose = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='issued')
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), editable=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='store_issues_created')
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='store_issues_cancelled')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name_plural = "Store Issues"
        ordering = ['-issue_date', '-id']
        indexes = [
            models.Index(fields=['issue_date']),
            models.Index(fields=['status']),
            models.Index(fields=['issue_type']),
        ]

    def __str__(self):
        return f"{self.issue_no} ({self.from_warehouse})"

    @property
    def is_cancelled(self):
        return self.status == 'cancelled'


class StoreIssueItem(models.Model):
    issue = models.ForeignKey(StoreIssue, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='store_issue_items')
    qty = models.FloatField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    remarks = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        verbose_name_plural = "Store Issue Items"

    def __str__(self):
        return f"{self.product.name} x {self.qty}"


class StoreIssueBatchUsage(models.Model):
    """How much came out of which batch (FIFO) - on cancel it goes back to exactly the same place."""
    item = models.ForeignKey(StoreIssueItem, on_delete=models.CASCADE, related_name='usages')
    batch = models.ForeignKey('StockBatch', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='store_issue_usages')
    qty = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name_plural = "Store Issue Batch Usage"


class StoreMember(models.Model):
    """Which user is in which store team, and their level (only a superuser can see all stores)."""
    LEVELS = [
        ('viewer', 'Viewer (can only view)'),
        ('keeper', 'Store keeper (can issue)'),
        ('manager', 'Store manager (issue + cancel)'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='store_memberships')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.CASCADE, related_name='members')
    level = models.CharField(max_length=10, choices=LEVELS, default='keeper')
    is_active = models.BooleanField(default=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'warehouse')
        verbose_name_plural = "Store Team Members"
        ordering = ['warehouse__name', 'user__username']

    def __str__(self):
        return f"{self.user.get_username()} -> {self.warehouse.name} ({self.level})"
