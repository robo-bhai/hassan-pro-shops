"""Admin: auth admin models."""
from ..models import *
from django.contrib import admin
from django.utils.html import format_html
from django.contrib.admin import SimpleListFilter


# ============================================
# LOG ENTRY ADMIN
# ============================================
class ActionFlagFilter(SimpleListFilter):
    title = "Action Type"
    parameter_name = "action_flag"

    def lookups(self, request, model_admin):
        return [(1, "Added"), (2, "Changed"), (3, "Deleted")]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(action_flag=self.value())


class ContentTypeFilter(SimpleListFilter):
    title = "Content Type"
    parameter_name = "content_type"

    def lookups(self, request, model_admin):
        content_types = set(model_admin.get_queryset(request).values_list("content_type__id", "content_type__model"))
        return [(ct_id, model.replace("_", " ").title()) for ct_id, model in content_types]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(content_type__id=self.value())


class LogEntryAdmin(admin.ModelAdmin):
    change_list_template = "admin/button.html"
    list_display = ['action_time', 'user', 'content_type_display', 'action']
    list_filter = ['action_time', 'user', ActionFlagFilter, ContentTypeFilter]

    @admin.display(description="Action", ordering="action_flag")
    def action(self, obj):
        if obj.action_flag == 1:
            return format_html('<span style="color: blue; font-weight: bold;">Added</span>')
        elif obj.action_flag == 2:
            return format_html('<span style="color: orange; font-weight: bold;">Changed</span>')
        elif obj.action_flag == 3:
            return format_html('<span style="color: red; font-weight: bold;">Deleted</span>')
        return "Unknown"

    @admin.display(description="Content Type")
    def content_type_display(self, obj):
        return obj.content_type.model_class()._meta.verbose_name.title()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
