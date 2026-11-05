"""Admin: vendor portal (vendor accounts + vendor product approvals)."""
from ..models import *
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.timezone import now


@admin.register(VendorProfile, site=admin.site)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'vendor', 'user', 'city', 'is_approved', 'store_status', 'created_at', 'last_login_at')
    list_filter = ('is_approved', 'store_status', 'city')
    search_fields = ('business_name', 'vendor__name', 'vendor__contact_number', 'user__email')
    readonly_fields = ('vendor', 'user', 'approved_at', 'last_login_at', 'created_at')
    actions = ['approve_accounts', 'suspend_accounts']

    @admin.action(description='Approve selected vendors')
    def approve_accounts(self, request, queryset):
        n = queryset.filter(is_approved=False).update(is_approved=True, approved_at=now())
        self.message_user(request, f'{n} vendor(s) approved.', messages.SUCCESS)

    @admin.action(description='Suspend selected vendors (aur unke products shop se hatao)')
    def suspend_accounts(self, request, queryset):
        vendor_ids = list(queryset.values_list('vendor_id', flat=True))
        queryset.update(is_approved=False)
        hidden = Product.objects.filter(vendor_id__in=vendor_ids).update(is_active=False)
        self.message_user(
            request, f'{len(vendor_ids)} vendor(s) suspended, {hidden} product(s) hidden.',
            messages.WARNING
        )


@admin.register(VendorSubmission, site=admin.site)
class VendorSubmissionAdmin(admin.ModelAdmin):
    """Vendors ke products: review, approve ya reject."""
    list_display = ('name', 'vendor', 'category', 'price', 'approval_status', 'is_active', 'created_at')
    list_filter = ('approval_status', 'vendor', 'category')
    search_fields = ('name', 'vendor__name', 'barcode')
    actions = ['approve_products', 'reject_products']
    fields = ('name', 'description', 'vendor', 'category', 'brand', 'unit', 'image',
              'original_price', 'discount_percentage', 'price', 'approval_status',
              'rejection_reason', 'is_active')
    # Sirf approval wale fields badal sakte hain (image dobara process na ho).
    readonly_fields = ('name', 'description', 'vendor', 'category', 'brand', 'unit', 'image',
                       'original_price', 'discount_percentage', 'price', 'is_active')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(vendor__isnull=False).select_related('vendor', 'category')

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        obj._image_processed = True  # Product.save() ka image API call skip
        if obj.approval_status == 'approved':
            if 'approval_status' in form.changed_data:
                obj.is_active = True
            obj.rejection_reason = ''
        else:
            obj.is_active = False
        super().save_model(request, obj, form, change)

    @admin.action(description='Approve selected products (shop par live karo)')
    def approve_products(self, request, queryset):
        n = queryset.exclude(approval_status='approved').update(
            approval_status='approved', is_active=True, rejection_reason='')
        self.message_user(request, f'{n} product(s) approved aur shop par live.', messages.SUCCESS)

    @admin.action(description='Reject selected products')
    def reject_products(self, request, queryset):
        n = queryset.update(
            approval_status='rejected', is_active=False,
            rejection_reason='Listing guidelines par poora nahi utarta. Edit karke dobara bhejein.')
        self.message_user(request, f'{n} product(s) rejected.', messages.WARNING)


@admin.register(ShopBanner, site=admin.site)
class ShopBannerAdmin(admin.ModelAdmin):
    """Stores page ke upar wale promo banners: upload, order, on/off, date range."""
    list_display = ('preview', 'title', 'store', 'is_active', 'sort_order', 'starts_on', 'ends_on')
    list_display_links = ('preview', 'title')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active', 'store')
    search_fields = ('title', 'store__business_name')
    fields = ('title', 'image', 'store', 'link_url', 'is_active', 'sort_order', 'starts_on', 'ends_on')

    @admin.display(description='Banner')
    def preview(self, obj):
        if not obj.image:
            return '-'
        return format_html('<img src="{}" style="height:48px;border-radius:6px;">', obj.image.url)
