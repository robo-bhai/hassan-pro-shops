"""Admin: shareholders models."""
from ..models import *
from django.contrib import admin
from django.utils.timezone import now
from django.http import HttpResponse


@admin.register(Share, site=admin.site)
class ShareAdmin(admin.ModelAdmin):
    list_display = ('id', 'shareholder', 'share_type', 'quantity', 'purchase_price', 
                    'certificate_number', 'certificate_printed', 'issue_date')
    list_filter = ('share_type', 'is_locked', 'certificate_printed', 'issue_date')
    search_fields = ('shareholder__name', 'shareholder__shareholder_code', 'certificate_number')
    readonly_fields = ('created_at', 'updated_at', 'certificate_printed_at', 'certificate_printed_by')
    
    fieldsets = (
        ('Share Information', {
            'fields': ('shareholder', 'share_type', 'quantity', 'purchase_price')
        }),
        ('Certificate Information', {
            'fields': ('certificate_number', 'certificate_issue_date', 'certificate_printed', 
                       'certificate_printed_at', 'certificate_printed_by', 'certificate_template')
        }),
        ('Issue Details', {
            'fields': ('issue_date', 'is_locked')
        }),
        ('Transfer Tracking', {
            'fields': ('transferred_from', 'transfer_date', 'transfer_notes'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes', 'certificate_notes')
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['generate_certificate', 'print_selected_certificates']
    
    def generate_certificate(self, request, queryset):
        """Generate certificate for selected shares"""
        count = 0
        for share in queryset:
            if not share.certificate_number:
                share.certificate_number = f"CERT-{share.id:06d}"
                share.certificate_issue_date = now().date()
                share.certificate_printed = True
                share.certificate_printed_at = now()
                share.certificate_printed_by = request.user
                share.save()
                count += 1
        self.message_user(request, f"✅ {count} certificates generated!")
    generate_certificate.short_description = "📄 Generate Certificates"
    
    def print_selected_certificates(self, request, queryset):
        """Print certificates for selected shares"""
        from ..certificate_utils import generate_bulk_certificates
        share_ids = list(queryset.values_list('id', flat=True))
        zip_buffer = generate_bulk_certificates(share_ids)
        response = HttpResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="share_certificates.zip"'
        return response
    print_selected_certificates.short_description = "🖨️ Print Selected Certificates"


@admin.register(DividendReinvestmentPlan, site=admin.site)
class DividendReinvestmentPlanAdmin(admin.ModelAdmin):
    list_display = ('dividend', 'plan_name', 'discount_type', 'discount_value', 'status', 'is_auto_enroll')
    list_filter = ('status', 'discount_type', 'is_auto_enroll')
    search_fields = ('plan_name', 'dividend__dividend_no')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('dividend', 'plan_name', 'status')
        }),
        ('Pricing Settings', {
            'fields': ('discount_type', 'discount_value', 'admin_fee')
        }),
        ('Share Limits', {
            'fields': ('min_shares', 'max_shares', 'fractional_shares_allowed', 'round_down_to_nearest')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date')
        }),
        ('Enrollment', {
            'fields': ('is_auto_enroll', 'is_default')
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate', 'deactivate', 'auto_enroll']
    
    def activate(self, request, queryset):
        queryset.update(status='active')
        self.message_user(request, f"✅ {queryset.count()} DRIP plans activated")
    activate.short_description = "Activate Selected Plans"
    
    def deactivate(self, request, queryset):
        queryset.update(status='inactive')
        self.message_user(request, f"⚠️ {queryset.count()} DRIP plans deactivated")
    deactivate.short_description = "Deactivate Selected Plans"
    
    def auto_enroll(self, request, queryset):
        count = 0
        for drip in queryset:
            if drip.is_auto_enroll:
                shareholders = Shareholder.objects.filter(status='active')
                for shareholder in shareholders:
                    ShareholderDRIPEnrollment.objects.get_or_create(
                        shareholder=shareholder,
                        drip=drip,
                        defaults={'status': 'active', 'created_by': request.user}
                    )
                    count += 1
        self.message_user(request, f"✅ {count} shareholders auto-enrolled")
    auto_enroll.short_description = "Auto-Enroll All Shareholders"


@admin.register(ShareholderDRIPEnrollment, site=admin.site)
class ShareholderDRIPEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('shareholder', 'drip', 'status', 'enrollment_date', 'auto_reinvest')
    list_filter = ('status', 'auto_reinvest', 'enrollment_date')
    search_fields = ('shareholder__name', 'drip__plan_name')
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['activate_enrollments', 'deactivate_enrollments']
    
    def activate_enrollments(self, request, queryset):
        queryset.update(status='active')
        self.message_user(request, f"✅ {queryset.count()} enrollments activated")
    activate_enrollments.short_description = "Activate Selected"
    
    def deactivate_enrollments(self, request, queryset):
        queryset.update(status='inactive')
        self.message_user(request, f"⚠️ {queryset.count()} enrollments deactivated")
    deactivate_enrollments.short_description = "Deactivate Selected"


@admin.register(DRIPTransaction, site=admin.site)
class DRIPTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference_no', 'dividend_payment', 'shares_purchased', 'purchase_price', 'total_cost', 'status')
    list_filter = ('status', 'processed_at')
    search_fields = ('reference_no', 'dividend_payment__shareholder__name')
    readonly_fields = ('reference_no', 'created_at')


@admin.register(ShareBuyback, site=admin.site)
class ShareBuybackAdmin(admin.ModelAdmin):
    list_display = ('buyback_no', 'buyback_type', 'total_amount', 'shares_bought', 'progress_percent', 'status')
    list_filter = ('status', 'buyback_type')
    search_fields = ('buyback_no', 'description')
    readonly_fields = ('buyback_no', 'created_at', 'updated_at')
    
    actions = ['approve_buyback', 'complete_buyback']
    
    def approve_buyback(self, request, queryset):
        queryset.update(status='approved', approved_by=request.user, approved_at=now())
        self.message_user(request, f"✅ {queryset.count()} buybacks approved")
    approve_buyback.short_description = "Approve Selected Buybacks"
    
    def complete_buyback(self, request, queryset):
        queryset.update(status='completed', completed_at=now())
        self.message_user(request, f"✅ {queryset.count()} buybacks completed")
    complete_buyback.short_description = "Complete Selected Buybacks"


@admin.register(ShareholderDiscountProgram, site=admin.site)
class ShareholderDiscountProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'discount_value', 'min_shares_required', 'is_active', 'priority')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('name',)
    filter_horizontal = ('products', 'categories')


@admin.register(ShareholderLoan, site=admin.site)
class ShareholderLoanAdmin(admin.ModelAdmin):
    list_display = ('loan_no', 'shareholder', 'principal', 'outstanding', 'status', 'get_ltv_percent')
    list_filter = ('status', 'loan_type')
    search_fields = ('loan_no', 'shareholder__name')
    readonly_fields = ('loan_no', 'created_at', 'updated_at')
    
    actions = ['approve_loans', 'disburse_loans']
    
    def approve_loans(self, request, queryset):
        queryset.update(status='approved', approved_by=request.user, approved_at=now())
        self.message_user(request, f"✅ {queryset.count()} loans approved")
    approve_loans.short_description = "Approve Selected Loans"
    
    def disburse_loans(self, request, queryset):
        queryset.update(status='active', disbursement_date=now().date())
        self.message_user(request, f"✅ {queryset.count()} loans disbursed")
    disburse_loans.short_description = "Disburse Selected Loans"
