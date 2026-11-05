"""Admin: price history (read-only - nobody can add, edit or delete a row)."""
from django.contrib import admin

from ..models import PriceChangeLog


@admin.register(PriceChangeLog, site=admin.site)
class PriceChangeLogAdmin(admin.ModelAdmin):
    list_display = ('changed_at', 'product_name', 'batch_ref', 'price_field', 'old_value', 'new_value',
                    'changed_by_name', 'source')
    list_filter = ('price_field', 'source', 'changed_at')
    search_fields = ('product_name', 'changed_by_name', 'reason')
    date_hierarchy = 'changed_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
