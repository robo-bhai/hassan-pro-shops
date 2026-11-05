"""Models: trade/vendor_portal - vendor self-service login (shop par products list karne ke liye)."""
from datetime import time

from django.db import models
from django.utils import timezone

from ..inventory.catalog import Product


class VendorProfile(models.Model):
    """Portal account of a Vendor. Customer side ke CustomerProfile jaisa."""
    vendor = models.OneToOneField(
        'Vendor', on_delete=models.CASCADE, related_name='portal_profile'
    )
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='vendor_profile'
    )
    business_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100, blank=True, default='')
    is_approved = models.BooleanField(
        default=False,
        verbose_name="Approved",
        help_text="Approved vendor hi products list kar sakta hai"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Commission %",
        help_text="Shop is vendor ki har bikri par itna % rakhta hai. Khali = default "
                  "(settings.VENDOR_DEFAULT_COMMISSION_PERCENT, warna 10%)"
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ---- Store page (Talabat jaisi shop ki apni page) ----
    STORE_STATUS = [('open', 'Open'), ('busy', 'Busy'), ('closed', 'Closed')]
    store_description = models.TextField(blank=True, default='', max_length=1000)
    logo = models.ImageField(upload_to='vendor_stores/logos/', null=True, blank=True)
    cover_image = models.ImageField(upload_to='vendor_stores/covers/', null=True, blank=True)
    store_status = models.CharField(
        max_length=6, choices=STORE_STATUS, default='open',
        help_text="Closed = customer is store se order nahi de sakta. Busy = order milte hain, par der ho sakti ha."
    )
    opens_at = models.TimeField(null=True, blank=True, help_text="Khali = hamesha khula (status ke mutabiq)")
    closes_at = models.TimeField(null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delivery_time_min = models.PositiveSmallIntegerField(default=30, help_text="Minutes")
    delivery_time_max = models.PositiveSmallIntegerField(default=45, help_text="Minutes")
    delivery_areas = models.TextField(
        blank=True, default='', max_length=1000,
        help_text="Wo shehar/area jahan ye store deliver karta hai, comma se alag (jaise: Gulberg, DHA, Johar Town). "
                  "Khali = sirf store ke shehar mein."
    )

    class Meta:
        verbose_name_plural = '3.2 Vendor Portal Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} ({'approved' if self.is_approved else 'pending'})"

    MAX_AREAS = 50
    MAX_AREA_LEN = 60

    @classmethod
    def clean_areas(cls, text):
        """'Gulberg,  dha\nGulberg' -> ['Gulberg', 'dha'] (khali/dohraye hue hata kar, lambai/ginti ki had ke saath)."""
        import re
        seen, out = set(), []
        for part in re.split(r'[,\n;]+', text or ''):
            name = ' '.join(part.split())[:cls.MAX_AREA_LEN]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out[:cls.MAX_AREAS]

    @property
    def delivery_area_list(self):
        return self.clean_areas(self.delivery_areas)

    @property
    def is_within_hours(self):
        """Opening/closing time ke andar? (raat ko paar hone wale time bhi theek: 18:00 -> 02:00)"""
        if not self.opens_at or not self.closes_at:
            return True
        t = timezone.localtime().time()
        if self.opens_at <= self.closes_at:
            return self.opens_at <= t <= self.closes_at
        return t >= self.opens_at or t <= self.closes_at

    @property
    def is_open_now(self):
        """Customer abhi order de sakta ha?"""
        return self.is_approved and self.store_status != 'closed' and self.is_within_hours

    @property
    def status_label(self):
        if not self.is_open_now:
            return 'closed'
        return 'busy' if self.store_status == 'busy' else 'open'



class VendorSubmission(Product):
    """Proxy: admin ke liye vendors ke jama kiye hue products ki alag list."""

    class Meta:
        proxy = True
        verbose_name = 'Vendor Product Submission'
        verbose_name_plural = '3.3 Vendor Product Submissions'
