"""Admin: store ops (view only; stock moves only through the service)."""
from django.contrib import admin

from ..models import (StoreAccountRule, StoreCount, StoreCountLine, StoreIssueRequest, StoreIssueRequestItem,
                      StoreReturn, StoreReturnLine, StoreSetting)


@admin.register(StoreSetting, site=admin.site)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ('accounting_enabled', 'approval_mode', 'approval_limit', 'updated_by', 'updated_at')


@admin.register(StoreAccountRule, site=admin.site)
class StoreAccountRuleAdmin(admin.ModelAdmin):
    list_display = ('kind', 'key', 'account')
    list_filter = ('kind',)


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request, *a, **k):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RequestItemInline(admin.TabularInline):
    model = StoreIssueRequestItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'qty', 'remarks')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StoreIssueRequest, site=admin.site)
class StoreIssueRequestAdmin(_ReadOnly):
    list_display = ('request_no', 'from_warehouse', 'issue_type', 'est_cost', 'status', 'requested_by', 'decided_by')
    list_filter = ('status', 'from_warehouse')
    inlines = [RequestItemInline]


class CountLineInline(admin.TabularInline):
    model = StoreCountLine
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'system_qty', 'counted_qty', 'posted_system_qty', 'diff_qty', 'unit_cost', 'diff_value', 'reason')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StoreCount, site=admin.site)
class StoreCountAdmin(_ReadOnly):
    list_display = ('count_no', 'warehouse', 'count_date', 'status', 'loss_value', 'gain_value')
    list_filter = ('status', 'warehouse')
    inlines = [CountLineInline]


class ReturnLineInline(admin.TabularInline):
    model = StoreReturnLine
    extra = 0
    can_delete = False
    readonly_fields = ('issue_item', 'qty', 'total_cost', 'condition')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StoreReturn, site=admin.site)
class StoreReturnAdmin(_ReadOnly):
    list_display = ('return_no', 'issue', 'return_date', 'total_cost', 'created_by')
    inlines = [ReturnLineInline]
