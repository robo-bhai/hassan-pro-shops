"""Admin classes for shareholders, installments, daily closing, payments, cash and system settings.

Imported AFTER site.py, so they register on the custom admin site (in the original admin.py they were
decorated before the site swap and ended up on an unused default site)."""
from ..models import *
import openpyxl
from django.contrib import admin
from django.utils.timezone import now
from io import BytesIO
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from django.urls import reverse
from django.utils.html import format_html
from datetime import timedelta
from openpyxl.styles import Font, Alignment
from ..models import SystemSetting


class ShareInline(admin.TabularInline):
    model = Share
    fields = ('share_type', 'quantity', 'purchase_price', 'certificate_number', 'issue_date')
    extra = 0
    readonly_fields = ('issue_date',)


class DividendPaymentInline(admin.TabularInline):
    model = DividendPayment
    fields = ('dividend', 'shares_held', 'amount', 'status', 'payment_date')
    readonly_fields = ('dividend', 'shares_held', 'amount')
    extra = 0


class MeetingAttendanceInline(admin.TabularInline):
    """Inline for managing meeting attendance"""
    model = MeetingAttendance
    fields = ('shareholder', 'status', 'check_in_time', 'check_out_time', 'notes')
    extra = 1
    autocomplete_fields = ['shareholder']
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "shareholder":
            kwargs["queryset"] = Shareholder.objects.filter(status='active')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Shareholder, site=admin.site)
class ShareholderAdmin(admin.ModelAdmin):
    list_display = ('shareholder_code', 'name', 'shareholder_type', 'phone', 'email', 'total_shares_display', 'total_investment_display', 'status_badge')
    list_filter = ('shareholder_type', 'status', 'is_founder', 'is_board_member')
    search_fields = ('shareholder_code', 'name', 'email', 'phone', 'cnic')
    inlines = [ShareInline, DividendPaymentInline]
    readonly_fields = ('shareholder_code', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('shareholder_code', 'name', 'shareholder_type', 'status')
        }),
        ('Contact Details', {
            'fields': ('email', 'phone', 'address')
        }),
        ('Identification', {
            'fields': ('cnic', 'passport_no')
        }),
        ('Company Details', {
            'fields': ('company_name', 'registration_no'),
            'classes': ('collapse',)
        }),
        ('Banking Details', {
            'fields': ('bank_name', 'account_number', 'account_title', 'iban'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('is_founder', 'is_board_member', 'notes')
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_shares_display(self, obj):
        return f"{obj.total_shares():,}"
    total_shares_display.short_description = "Total Shares"
    
    def total_investment_display(self, obj):
        return f"Rs. {obj.total_investment():,.2f}"
    total_investment_display.short_description = "Total Investment"
    
    def status_badge(self, obj):
        return obj.status_badge
    status_badge.short_description = "Status"
    status_badge.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['generate_dividend_report', 'export_shareholders_excel']
    
    def generate_dividend_report(self, request, queryset):
        """Generate dividend report for selected shareholders"""
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        story.append(Paragraph("Shareholder Dividend Report", styles['Heading1']))
        story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        data = [['Code', 'Name', 'Total Shares', 'Total Investment', 'Total Dividends']]
        for shareholder in queryset:
            data.append([
                shareholder.shareholder_code,
                shareholder.name,
                f"{shareholder.total_shares():,}",
                f"Rs. {shareholder.total_investment():,.2f}",
                f"Rs. {shareholder.total_dividends():,.2f}"
            ])
        
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="shareholder_dividend_report.pdf"'
        return response
    generate_dividend_report.short_description = "📄 Generate Dividend Report (PDF)"
    
    def export_shareholders_excel(self, request, queryset):
        """Export shareholders to Excel"""
        import openpyxl
        from openpyxl.styles import Font, Alignment
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shareholders"
        
        headers = ['Code', 'Name', 'Type', 'Email', 'Phone', 'Status', 'Total Shares', 'Total Investment']
        ws.append(headers)
        
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        
        for shareholder in queryset:
            ws.append([
                shareholder.shareholder_code,
                shareholder.name,
                shareholder.get_shareholder_type_display(),
                shareholder.email or '',
                shareholder.phone or '',
                shareholder.status,
                shareholder.total_shares(),
                float(shareholder.total_investment())
            ])
        
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col_letter].width = min(max_length + 2, 30)
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="shareholders_export.xlsx"'
        wb.save(response)
        return response
    export_shareholders_excel.short_description = "📊 Export to Excel"


# (old decorator removed: this model is registered by a newer admin class below)
class ShareAdmin(admin.ModelAdmin):
    list_display = ('id', 'shareholder', 'share_type', 'quantity', 'purchase_price', 'total_value_display', 'issue_date')
    list_filter = ('share_type', 'is_locked', 'issue_date')
    search_fields = ('shareholder__name', 'shareholder__shareholder_code', 'certificate_number')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Share Information', {
            'fields': ('shareholder', 'share_type', 'quantity', 'purchase_price', 'certificate_number')
        }),
        ('Issue Details', {
            'fields': ('issue_date', 'is_locked')
        }),
        ('Transfer Tracking', {
            'fields': ('transferred_from', 'transfer_date', 'transfer_notes'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_value_display(self, obj):
        return f"Rs. {obj.total_value():,.2f}"
    total_value_display.short_description = "Total Value"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SharePrice, site=admin.site)
class SharePriceAdmin(admin.ModelAdmin):
    list_display = ('price', 'date', 'is_active', 'created_at')
    list_filter = ('is_active', 'date')
    search_fields = ('notes',)
    list_editable = ('is_active',)
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class DividendPaymentInline(admin.TabularInline):
    model = DividendPayment
    fields = ('shareholder', 'shares_held', 'amount', 'status', 'payment_date')
    readonly_fields = ('shareholder', 'shares_held', 'amount')
    extra = 0
    can_delete = False


@admin.register(Dividend, site=admin.site)
class DividendAdmin(admin.ModelAdmin):
    list_display = ('dividend_no', 'amount_per_share', 'total_amount', 'declaration_date', 'record_date', 'payment_date', 'status')
    list_filter = ('status', 'is_interim', 'declaration_date')
    search_fields = ('dividend_no', 'notes')
    inlines = [DividendPaymentInline]
    readonly_fields = ('dividend_no', 'total_amount', 'created_at')
    actions = ['generate_dividend_payments', 'mark_paid_bulk']
    
    fieldsets = (
        ('Dividend Information', {
            'fields': ('dividend_no', 'amount_per_share', 'total_amount', 'is_interim')
        }),
        ('Dates', {
            'fields': ('declaration_date', 'record_date', 'payment_date')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Additional', {
            'fields': ('notes',)
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def generate_dividend_payments(self, request, queryset):
        """Generate dividend payments for all shareholders"""
        count = 0
        for dividend in queryset.filter(status='declared'):
            shareholders = Shareholder.objects.filter(status='active')
            for shareholder in shareholders:
                shares = shareholder.total_shares()
                if shares > 0:
                    amount = shares * dividend.amount_per_share
                    DividendPayment.objects.get_or_create(
                        dividend=dividend,
                        shareholder=shareholder,
                        defaults={
                            'shares_held': shares,
                            'amount': amount,
                            'status': 'pending'
                        }
                    )
                    count += 1
            dividend.status = 'approved'
            dividend.save()
        
        self.message_user(request, f"✅ {count} dividend payments generated for {queryset.count()} dividends!")
    generate_dividend_payments.short_description = "💰 Generate Dividend Payments"
    
    def mark_paid_bulk(self, request, queryset):
        """Mark selected dividend payments as paid"""
        count = 0
        for dividend in queryset:
            payments = dividend.payments.filter(status='pending')
            for payment in payments:
                payment.mark_paid(payment_method='Bank Transfer', processed_by=request.user)
                count += 1
        self.message_user(request, f"✅ {count} payments marked as paid!")
    mark_paid_bulk.short_description = "✅ Mark Payments as Paid"


@admin.register(ShareTransfer, site=admin.site)
class ShareTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_no', 'from_shareholder', 'to_shareholder', 'quantity', 'transfer_price', 'total_value_display', 'status_badge', 'transfer_date')
    list_filter = ('status', 'transfer_date')
    search_fields = ('transfer_no', 'from_shareholder__name', 'to_shareholder__name')
    readonly_fields = ('transfer_no', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Transfer Information', {
            'fields': ('transfer_no', 'from_shareholder', 'to_shareholder')
        }),
        ('Share Details', {
            'fields': ('quantity', 'transfer_price')
        }),
        ('Shares Selection', {
            'fields': ('shares',),
            'description': 'Select the shares to transfer'
        }),
        ('Dates', {
            'fields': ('transfer_date',)
        }),
        ('Status', {
            'fields': ('status', 'approved_by', 'approved_at', 'completed_at')
        }),
        ('Notes', {
            'fields': ('reason', 'notes')
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ Use filter_horizontal with ManyToManyField
    filter_horizontal = ('shares',)
    
    def total_value_display(self, obj):
        return f"Rs. {obj.total_value():,.2f}"
    total_value_display.short_description = "Total Value"
    
    def status_badge(self, obj):
        return obj.status_badge
    status_badge.short_description = "Status"
    status_badge.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['approve_transfers', 'complete_transfers', 'reject_transfers']
    
    def approve_transfers(self, request, queryset):
        count = 0
        for transfer in queryset.filter(status='pending'):
            transfer.approve(request.user)
            count += 1
        self.message_user(request, f"✅ {count} transfers approved!")
    approve_transfers.short_description = "✅ Approve Selected Transfers"
    
    def complete_transfers(self, request, queryset):
        count = 0
        for transfer in queryset.filter(status='approved'):
            transfer.complete(request.user)
            count += 1
        self.message_user(request, f"✅ {count} transfers completed!")
    complete_transfers.short_description = "✅ Complete Selected Transfers"
    
    def reject_transfers(self, request, queryset):
        count = 0
        for transfer in queryset.filter(status='pending'):
            transfer.reject(request.user)
            count += 1
        self.message_user(request, f"❌ {count} transfers rejected!")
    reject_transfers.short_description = "❌ Reject Selected Transfers"


@admin.register(ShareholderMeeting, site=admin.site)
class ShareholderMeetingAdmin(admin.ModelAdmin):
    """Shareholder Meeting Admin - Fixed for custom through model"""
    list_display = ('meeting_no', 'title', 'meeting_type', 'date', 'status', 'total_attendees')
    list_filter = ('meeting_type', 'status', 'date')
    search_fields = ('meeting_no', 'title', 'agenda')
    readonly_fields = ('meeting_no', 'created_at', 'updated_at', 'total_attendees')
    
    fieldsets = (
        ('Meeting Information', {
            'fields': ('meeting_no', 'title', 'meeting_type', 'date', 'time', 'venue', 'status')
        }),
        ('Agenda & Minutes', {
            'fields': ('agenda', 'minutes')
        }),
        # ✅ attendees removed from fieldsets - using inline instead
        ('Resolutions', {
            'fields': ('resolutions', 'resolutions_passed'),
            'classes': ('collapse',)
        }),
        ('Additional', {
            'fields': ('notes',)
        }),
        ('System Fields', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ Use inline for attendance management
    inlines = [MeetingAttendanceInline]
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MeetingAttendance, site=admin.site)
class MeetingAttendanceAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'shareholder', 'status', 'check_in_time', 'check_out_time')
    list_filter = ('status', 'meeting')
    search_fields = ('shareholder__name', 'shareholder__shareholder_code')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False  # Attendance created via meeting


@admin.register(CashTransaction, site=admin.site)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'transaction_type', 'amount', 'description', 'created_by')
    list_filter = ('transaction_type', 'date')
    search_fields = ('description', 'reference_no')
    readonly_fields = ('created_at',)


# Register at bottom with other admin registrations
@admin.register(SystemSetting, site=admin.site)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('setting_key', 'setting_value', 'description', 'updated_at')
    list_editable = ('setting_value',)
    list_filter = ('setting_key',)
    search_fields = ('setting_key', 'description')
    
    fieldsets = (
        ('Module Visibility Settings', {
            'fields': ('setting_key', 'setting_value', 'description'),
            'description': '📌 Set "true" to show module, "false" to hide module'
        }),
    )
    
    def has_add_permission(self, request):
        # Only superuser can add new settings
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        # Only superuser can delete
        return request.user.is_superuser


class EmiPaymentInline(admin.TabularInline):
    model = EmiPayment
    fields = ('installment_number', 'due_date', 'amount_due', 'amount_paid', 'status', 'payment_date', 'reference_no')
    readonly_fields = ('installment_number', 'due_date', 'amount_due')
    extra = 0
    can_delete = False
    
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == 'paid':
            return self.readonly_fields + ('amount_paid', 'status')
        return self.readonly_fields


@admin.register(InstallmentPlan, site=admin.site)
class InstallmentPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_months', 'down_payment_percent', 'interest_rate', 'late_fee_per_day', 'is_active', 'created_at')
    list_editable = ('is_active',)
    list_filter = ('is_active', 'duration_months')
    search_fields = ('name',)
    ordering = ('duration_months',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'duration_months', 'is_active')
        }),
        ('Payment Terms', {
            'fields': ('down_payment_percent', 'interest_rate', 'late_fee_per_day'),
            'description': 'Down payment % of total amount | Interest rate % per annum | Late fee Rs. per day'
        }),
    )


@admin.register(SaleInstallment, site=admin.site)
class SaleInstallmentAdmin(admin.ModelAdmin):
    list_display = ('sale_bill_no', 'customer_name', 'plan', 'total_amount_display', 
                    'down_payment_status', 'total_paid_display', 'remaining_display', 
                    'status', 'next_due_date', 'payment_progress_bar')
    list_filter = ('status', 'plan', 'down_payment_paid', 'start_date')
    search_fields = ('sale__bill_no', 'sale__customer__name', 'sale__customer__customer_code')
    inlines = [EmiPaymentInline]
    readonly_fields = ('total_amount', 'loan_amount', 'emi_amount', 'total_interest', 
                       'total_payable', 'late_fee_accrued', 'created_at', 'updated_at')
    actions = ['generate_emi_schedule', 'send_payment_reminders', 'mark_as_defaulted', 'export_installment_report']
    change_list_template = "admin/button.html"
    
    fieldsets = (
        ('Sale Information', {
            'fields': ('sale', 'plan', 'status')
        }),
        ('Amount Breakdown', {
            'fields': ('total_amount', 'down_payment_amount', 'down_payment_paid', 
                      'loan_amount', 'emi_amount', 'total_interest', 'total_payable')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date', 'next_due_date')
        }),
        ('Late Fees', {
            'fields': ('late_fee_accrued', 'late_fee_paid'),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def sale_bill_no(self, obj):
        url = reverse('admin:app_sale_change', args=[obj.sale.id])
        return format_html('<a href="{}">{}</a>', url, obj.sale.bill_no)
    sale_bill_no.short_description = "Bill No"
    
    def customer_name(self, obj):
        return obj.sale.customer.name
    customer_name.short_description = "Customer"
    
    def total_amount_display(self, obj):
        return f"Rs. {obj.total_amount:,.2f}"
    total_amount_display.short_description = "Total Amount"
    
    def down_payment_status(self, obj):
        if obj.down_payment_paid:
            return format_html('<span style="color: #28a745;">✅ Paid</span>')
        return format_html('<span style="color: #dc3545;">❌ Pending</span>')
    down_payment_status.short_description = "Down Payment"
    
    def total_paid_display(self, obj):
        return f"Rs. {obj.total_paid():,.2f}"
    total_paid_display.short_description = "Total Paid"
    
    def remaining_display(self, obj):
        remaining = obj.remaining_amount()
        if remaining <= 0:
            return format_html('<span style="color: #28a745;">Rs. 0.00</span>')
        elif remaining > 0:
            return format_html('<span style="color: #dc3545;">Rs. {:.2f}</span>', remaining)
        return f"Rs. {remaining:,.2f}"
    remaining_display.short_description = "Remaining"
    
    def payment_progress_bar(self, obj):
        """Show payment progress bar"""
        if obj.total_payable > 0:
            percent = (obj.total_paid() / obj.total_payable) * 100
            color = '#28a745' if percent >= 100 else '#ffc107' if percent >= 50 else '#dc3545'
            return format_html(
                '<div style="width:100px; background:#e0e0e0; border-radius:10px; overflow:hidden;">'
                '<div style="width:{}%; background:{}; height:8px; border-radius:10px;"></div>'
                '</div><small>{}%</small>',
                percent, color, round(percent, 1)
            )
        return "-"
    payment_progress_bar.short_description = "Progress"
    
    # ============================================
    # ACTIONS
    # ============================================
    
    def generate_emi_schedule(self, request, queryset):
        """Generate EMI schedule for selected installments"""
        count = 0
        for installment in queryset:
            if not installment.emi_payments.exists() and installment.plan:
                for i in range(1, installment.plan.duration_months + 1):
                    due_date = installment.start_date + timedelta(days=30 * i)
                    EmiPayment.objects.create(
                        installment=installment,
                        installment_number=i,
                        due_date=due_date,
                        amount_due=installment.emi_amount
                    )
                count += 1
        self.message_user(request, f"✅ EMI schedules generated for {count} installments!")
    generate_emi_schedule.short_description = "📅 Generate EMI Schedule"
    
    def send_payment_reminders(self, request, queryset):
        """Send WhatsApp payment reminders"""
        from ..whatsapp_utils import WhatsAppSender
        
        count = 0
        for installment in queryset:
            pending_emi = installment.next_emi_due()
            if pending_emi and pending_emi.status == 'pending' and installment.sale.customer.contact_number:
                message = f"""📱 *EMI REMINDER*

Customer: {installment.sale.customer.name}
Bill No: {installment.sale.bill_no}
EMI #{pending_emi.installment_number} Due: Rs. {pending_emi.amount_due:,.2f}
Due Date: {pending_emi.due_date}
Remaining Balance: Rs. {installment.remaining_amount():,.2f}

⚠️ Late fee of Rs. {installment.plan.late_fee_per_day}/day will apply after due date.

Please clear your payment on time!"""
                
                result = WhatsAppSender.send_direct_message(
                    installment.sale.customer.contact_number,
                    message
                )
                if result.get('success'):
                    count += 1
        
        self.message_user(request, f"✅ {count} reminders sent!")
    send_payment_reminders.short_description = "📱 Send Payment Reminders"
    
    def mark_as_defaulted(self, request, queryset):
        """Mark selected installments as defaulted"""
        count = queryset.update(status='defaulted')
        self.message_user(request, f"⚠️ {count} installments marked as defaulted!")
    mark_as_defaulted.short_description = "⚠️ Mark as Defaulted"
    
    def export_installment_report(self, request, queryset):
        """Export installment report as Excel"""
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from django.http import HttpResponse
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Installment Report"
        
        # Headers
        headers = ['Bill No', 'Customer', 'Plan', 'Total Amount', 'Down Payment', 
                   'EMI Amount', 'Total Paid', 'Remaining', 'Status', 'Start Date', 'Next Due']
        ws.append(headers)
        
        # Style headers
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        
        # Add data
        for inst in queryset:
            ws.append([
                inst.sale.bill_no,
                inst.sale.customer.name,
                inst.plan.name if inst.plan else '-',
                float(inst.total_amount),
                float(inst.down_payment_amount),
                float(inst.emi_amount),
                float(inst.total_paid()),
                float(inst.remaining_amount()),
                inst.get_status_display(),
                inst.start_date.strftime('%d-%m-%Y'),
                inst.next_due_date.strftime('%d-%m-%Y') if inst.next_due_date else '-',
            ])
        
        # Adjust column widths
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            ws.column_dimensions[col_letter].width = adjusted_width
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="installment_report.xlsx"'
        wb.save(response)
        return response
    export_installment_report.short_description = "📊 Export to Excel"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EmiPayment, site=admin.site)
class EmiPaymentAdmin(admin.ModelAdmin):
    list_display = ('installment_sale_bill', 'installment_number', 'due_date', 'amount_due_display', 
                    'amount_paid_display', 'status', 'payment_date', 'is_overdue_display')
    list_filter = ('status', 'payment_date', 'due_date')
    search_fields = ('installment__sale__bill_no', 'installment__sale__customer__name')
    readonly_fields = ('installment', 'installment_number', 'due_date', 'amount_due')
    actions = ['mark_as_paid']
    
    fieldsets = (
        ('EMI Information', {
            'fields': ('installment', 'installment_number', 'due_date', 'amount_due')
        }),
        ('Payment Details', {
            'fields': ('amount_paid', 'payment_date', 'payment_method', 'reference_no', 'status', 'notes')
        }),
        ('Late Fee', {
            'fields': ('late_fee_charged',),
            'classes': ('collapse',)
        }),
    )
    
    def installment_sale_bill(self, obj):
        return obj.installment.sale.bill_no
    installment_sale_bill.short_description = "Bill No"
    
    def amount_due_display(self, obj):
        return f"Rs. {obj.amount_due:,.2f}"
    amount_due_display.short_description = "Amount Due"
    
    def amount_paid_display(self, obj):
        if obj.amount_paid >= obj.amount_due:
            return format_html('<span style="color: #28a745;">Rs. {:.2f}</span>', obj.amount_paid)
        elif obj.amount_paid > 0:
            return format_html('<span style="color: #ff9800;">Rs. {:.2f}</span>', obj.amount_paid)
        return f"Rs. {obj.amount_paid:,.2f}"
    amount_paid_display.short_description = "Amount Paid"
    
    def is_overdue_display(self, obj):
        if obj.is_overdue():
            days = (now().date() - obj.due_date).days
            return format_html('<span style="color: #dc3545;">⚠️ {} days overdue</span>', days)
        return format_html('<span style="color: #28a745;">✅ On time</span>')
    is_overdue_display.short_description = "Overdue"
    
    def mark_as_paid(self, request, queryset):
        """Mark selected EMIs as paid"""
        count = 0
        for emi in queryset.filter(status='pending'):
            emi.mark_paid(emi.amount_due)
            count += 1
        self.message_user(request, f"✅ {count} EMIs marked as paid!")
    mark_as_paid.short_description = "✅ Mark as Paid"
    
    def has_add_permission(self, request):
        return False  # EMIs are auto-generated from installment


@admin.register(DailyClosing, site=admin.site)
class DailyClosingAdmin(admin.ModelAdmin):
    list_display = ('closing_date', 'opening_cash', 'cash_sales', 'total_sales', 'closing_cash', 'cash_difference', 'is_closed')
    list_filter = ('is_closed', 'closing_date')
    readonly_fields = ('cash_sales', 'card_sales', 'jazzcash_sales', 'easypaisa_sales', 'bank_transfer_sales', 'cash_difference', 'total_sales_today')
    
    def total_sales(self, obj):
        return f"Rs. {obj.total_sales_today():,.2f}"
    total_sales.short_description = 'Total Sales'


@admin.register(DailyClosingExpense, site=admin.site)
class DailyClosingExpenseAdmin(admin.ModelAdmin):
    list_display = ('closing', 'description', 'amount', 'category')


@admin.register(PaymentMethod, site=admin.site)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_editable = ('is_active',)


@admin.register(SalePayment, site=admin.site)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = ('sale', 'method', 'amount', 'payment_date', 'created_by')
    list_filter = ('method', 'payment_date')
    readonly_fields = ('payment_date',)
