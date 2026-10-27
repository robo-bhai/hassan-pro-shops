"""Admin: store transfers (view only - stock moves only through the service)."""
from django.contrib import admin

from ..models import StoreTransfer, StoreTransferItem


class StoreTransferItemInline(admin.TabularInline):
    model = StoreTransferItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'qty_sent', 'qty_received', 'unit_cost', 'total_cost', 'short_reason', 'remarks')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StoreTransfer, site=admin.site)
class StoreTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_no', 'transfer_date', 'from_warehouse', 'to_warehouse', 'purpose', 'total_cost', 'status')
    list_filter = ('status', 'purpose', 'from_warehouse', 'to_warehouse')
    search_fields = ('transfer_no',)
    date_hierarchy = 'transfer_date'
    inlines = [StoreTransferItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
