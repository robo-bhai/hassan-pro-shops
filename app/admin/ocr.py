"""Admin: OCR scan log (view only) and alias suggestions (approve / reject)."""
from django.contrib import admin
from ..models import OcrAliasSuggestion, OcrScanLog, ProductAlias
from ..utils.pos import ocr_cache


@admin.register(OcrScanLog, site=admin.site)
class OcrScanLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'source', 'text', 'top_product', 'top_score', 'confident',
                    'outcome', 'chosen_product')
    list_filter = ('outcome', 'source', 'confident')
    search_fields = ('text', 'raw_text', 'top_product__name', 'chosen_product__name')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request, *a, **k):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OcrAliasSuggestion, site=admin.site)
class OcrAliasSuggestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'product', 'hits', 'status', 'last_seen')
    list_filter = ('status',)
    search_fields = ('text', 'product__name')
    actions = ['approve', 'reject']

    @admin.action(description='Approve selected (create product alias)')
    def approve(self, request, queryset):
        n = 0
        for s in queryset.exclude(status='approved'):
            clash = ProductAlias.objects.filter(alias__iexact=s.text).exclude(product=s.product).exists()
            if clash:
                continue
            ProductAlias.objects.get_or_create(product=s.product, alias=s.text,
                                               defaults={'created_by': request.user})
            s.status = 'approved'
            s.save(update_fields=['status', 'last_seen'])
            n += 1
        ocr_cache.invalidate_catalog()
        self.message_user(request, '%d alias(es) created.' % n)

    @admin.action(description='Reject selected (never suggest again)')
    def reject(self, request, queryset):
        queryset.update(status='rejected')
