"""Admin: stores + store issues (read-only, stock moves only through the service)."""
from django import forms
from django.contrib import admin

from ..models import StoreIssue, StoreIssueBatchUsage, StoreIssueItem, StoreMember, StoreProfile
from ..module_catalog import STORE_TYPE_MODULES, get_store_module_choices


@admin.register(StoreMember, site=admin.site)
class StoreMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'warehouse', 'level', 'is_active', 'added_by', 'created_at')
    list_filter = ('level', 'is_active', 'warehouse')
    search_fields = ('user__username', 'warehouse__name')


class StoreProfileForm(forms.ModelForm):
    modules = forms.MultipleChoiceField(
        label="Allowed modules", required=False, choices=get_store_module_choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="If you select nothing, the default modules for the store type will apply "
                  "(the defaults for PMS/RMS/FGS/Technical/General are in the code in module_catalog.py).")

    class Meta:
        model = StoreProfile
        exclude = ('allowed_modules',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['modules'] = [k.strip() for k in (self.instance.allowed_modules or '').split(',') if k.strip()]

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.allowed_modules = ','.join(self.cleaned_data.get('modules') or [])
        if commit:
            obj.save()
        return obj


@admin.register(StoreProfile, site=admin.site)
class StoreProfileAdmin(admin.ModelAdmin):
    form = StoreProfileForm
    list_display = ('code', 'warehouse', 'store_type', 'unit_shown', 'modules_shown', 'can_issue', 'keeper', 'is_active')

    @admin.display(description='Company type')
    def unit_shown(self, obj):
        return dict(StoreProfile.BUSINESS_UNIT_CHOICES).get(obj.effective_unit()) or obj.effective_unit()

    @admin.display(description='Modules (visible to the team)')
    def modules_shown(self, obj):
        keys = sorted(obj.effective_modules())
        return ', '.join(keys) + ('' if obj.allowed_modules else '  (default)')
    list_filter = ('store_type', 'business_unit', 'can_issue', 'is_active')
    search_fields = ('code', 'warehouse__name')


class StoreIssueItemInline(admin.TabularInline):
    model = StoreIssueItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'qty', 'unit_cost', 'total_cost', 'remarks')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StoreIssue, site=admin.site)
class StoreIssueAdmin(admin.ModelAdmin):
    list_display = ('issue_no', 'issue_date', 'from_warehouse', 'issue_type', 'department', 'received_by',
                    'total_cost', 'status')
    list_filter = ('status', 'issue_type', 'from_warehouse', 'department')
    search_fields = ('issue_no', 'received_by', 'purpose')
    date_hierarchy = 'issue_date'
    inlines = [StoreIssueItemInline]

    # Add/edit/delete are disabled in admin to protect the stock accounts from going wrong
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
