"""Models: trade/shop_banner - Talabat jaise promo banners (stores page ke upar slider).

Admin panel se banner upload karte hain. Har banner ek store ya kisi link par ja sakta hai,
aur date range (start/end) ke andar hi shop par nazar aata hai.
"""
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

# Sirf apni site ka path (/...) ya https:// link. "javascript:" jaisa link allow nahi.
_safe_link = RegexValidator(
    r'^(/(?!/)|https://)',
    message="Link '/' se (apni site ka path, jaise /shop/stores/?free=1) ya 'https://' se shuru hona chahiye."
)


class ShopBanner(models.Model):
    title = models.CharField(max_length=100, help_text="Sirf admin ke liye naam; image ka alt text bhi yahi banta hai")
    image = models.ImageField(
        upload_to='shop_banners/',
        help_text="Behtareen size: 1200 x 400 px (3:1), JPG ya PNG"
    )
    store = models.ForeignKey(
        'VendorProfile', null=True, blank=True, on_delete=models.SET_NULL, related_name='banners',
        help_text="Optional: banner par click karne se is store ka page khulega"
    )
    link_url = models.CharField(
        max_length=300, blank=True, default='', validators=[_safe_link],
        help_text="Optional: apni site ka path (/shop/stores/?free=1) ya https:// link. "
                  "Store select ho to uska page pehle aata hai"
    )
    is_active = models.BooleanField(default=True)
    starts_on = models.DateField(null=True, blank=True, help_text="Khali = abhi se")
    ends_on = models.DateField(null=True, blank=True, help_text="Khali = hamesha")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chota number pehle dikhta hai")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Shop Banner'
        verbose_name_plural = 'Shop Banners'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return self.title

    @classmethod
    def live(cls):
        """Aaj shop par dikhne wale banners."""
        today = timezone.localdate()
        return (cls.objects.filter(is_active=True)
                .filter(Q(starts_on__isnull=True) | Q(starts_on__lte=today))
                .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today))
                .select_related('store'))

    @property
    def status(self):
        """'live' | 'scheduled' | 'expired' | 'off' (admin list ke badge ke liye)."""
        today = timezone.localdate()
        if not self.is_active:
            return 'off'
        if self.starts_on and self.starts_on > today:
            return 'scheduled'
        if self.ends_on and self.ends_on < today:
            return 'expired'
        return 'live'

    def get_link(self):
        """Click par kahan jaana hai ('' = kahin nahi)."""
        if self.store_id and self.store and self.store.is_approved:
            try:
                return reverse('store_detail', args=[self.store_id])
            except NoReverseMatch:
                pass
        return self.link_url or ''
