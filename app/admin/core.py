"""Admin: core models."""
from ..models import *
from django.contrib import admin
from django.utils.html import format_html
from ..models import Department, Project


# ============================================
# LICENSE ADMIN
# ============================================
class LicenseAdmin(admin.ModelAdmin):
    list_display = ('key', 'expiry_date', 'created_at', 'is_valid')
    readonly_fields = ('created_at',)
    change_list_template = "admin/button.html"

    def is_valid(self, obj):
        return "✔ Active" if obj.is_valid() else "❌ Expired"
    is_valid.short_description = "Status"


# ============================================
# TRAINING ADMIN
# ============================================
class TrainingStepInline(admin.TabularInline):
    model = TrainingStep
    extra = 1
    fields = ['step_number', 'description', 'screenshot_preview']
    readonly_fields = ['screenshot_preview']

    def screenshot_preview(self, obj):
        if obj.screenshot:
            return format_html('<img src="{}" width="100" />', obj.screenshot.url)
        return "No Image"
    screenshot_preview.short_description = "Screenshot"


class TrainingTopicAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'order']
    ordering = ['category', 'order']
    search_fields = ['title']
    inlines = [TrainingStepInline]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class TrainingStepAdmin(admin.ModelAdmin):
    list_display = ['topic_name', 'step_number_display', 'short_description', 'has_screenshot']
    ordering = ['topic', 'step_number']
    list_display_links = None

    def topic_name(self, obj):
        return obj.topic.title
    topic_name.short_description = "Topic"
    topic_name.admin_order_field = "topic"

    def step_number_display(self, obj):
        return obj.step_number
    step_number_display.short_description = "Step #"
    step_number_display.admin_order_field = "step_number"

    def short_description(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description
    short_description.short_description = "Description"

    def has_screenshot(self, obj):
        return "✅" if obj.screenshot else "❌"
    has_screenshot.short_description = "Screenshot"

    def has_add_permission(self, request):
        return False


# ============================================
# COMPANY INFO ADMIN
# ============================================
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_number', 'email', 'website', 'updated_at']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        # Add only when there is no record yet
        if CompanyInfo.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        # Do not allow delete at all
        return False

    def has_change_permission(self, request, obj=None):
        return True
    
    def has_view_permission(self, request, obj=None):
        return True


@admin.register(Department, site=admin.site)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'description', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    list_editable = ('is_active',)


@admin.register(Project, site=admin.site)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'status', 'budget', 'total_expenses_display', 'is_active')
    list_filter = ('status', 'department', 'is_active')
    search_fields = ('name', 'code', 'description')
    list_editable = ('status', 'is_active')
    
    def total_expenses_display(self, obj):
        return f"Rs. {obj.total_expenses():,.2f}"
    total_expenses_display.short_description = "Total Expenses"
