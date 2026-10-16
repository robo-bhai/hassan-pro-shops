"""Admin: purchasing models."""
from ..models import *
import io
from django.contrib import admin, messages
from django.utils.timezone import now
from django.db.models import Sum, DecimalField, ExpressionWrapper
from datetime import datetime, timedelta
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from django.urls import reverse
from django.utils.html import format_html
from django.template.loader import render_to_string
from decimal import Decimal
from django.shortcuts import redirect


class PurchaseRetrnItemInline(admin.TabularInline):
    model = PurchaseRetrnItem
    extra = 1


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    fields = ('product', 'qty', 'price', 'total')
    extra = 1
    readonly_fields = ('total',)

    def total(self, obj):
        return Decimal(obj.qty) * Decimal(obj.price) if obj.qty and obj.price else 0
    total.short_description = 'Total'


# ============================================
# VENDOR GROUP ADMIN
# ============================================
@admin.register(VendorGroup, site=admin.site)
class VendorGroupAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    search_help_text = "Search by Vendor Group Name"
    list_display = ['name', 'description', 'total_outstanding_balance_display']
    change_list_template = "admin/button.html"
    actions = ['generate_html_report', 'generate_vendor_group_pdf']

    def total_outstanding_balance_display(self, obj):
        return f'{obj.total_outstanding_balance():,.2f}'
    total_outstanding_balance_display.short_description = 'Total Outstanding Balance'

    def generate_html_report(self, request, queryset):
        VendorGroups = queryset
        context = {'VendorGroups': VendorGroups, 'date': datetime.now()}
        html = render_to_string('admin/VendorGroup_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="VendorGroup_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_vendor_group_pdf(self, request, queryset):
        """Generate PDF report for Vendor Groups."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Vendor Group Report", title_style))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Group Name', 'Description', 'Outstanding Balance']]
        
        for group in queryset:
            table_data.append([
                group.name,
                group.description or '-',
                f"{group.total_outstanding_balance():,.2f}"
            ])
        
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="vendor_group_report.pdf"'
        return response
    generate_vendor_group_pdf.short_description = 'Generate PDF Report'


# ============================================
# VENDOR ADMIN
# ============================================
@admin.register(Vendor, site=admin.site)
class VendorAdmin(admin.ModelAdmin):
    search_fields = ('vendor_code', 'name')
    search_help_text = "Search by Vendor Code or Vendor Name"
    list_display = ('vendor_code', 'name', 'group', 'contact_number', 'address', 
                    'opening_balance', 'formatted_outstanding_balance')
    ordering = ('vendor_code',)
    change_list_template = "admin/button.html"
    actions = ['generate_html_report', 'generate_vendor_pdf']
    
    fieldsets = (
        ('Vendor Information', {
            'fields': ('vendor_code', 'name', 'group', 'address')
        }),
        ('Contact Details', {
            'fields': ('contact_number',)
        }),
        ('Financial Information', {
            'fields': ('opening_balance',),
            'description': '⚠️ Opening Balance: Previous outstanding amount before using this system (before software start)'
        }),
    )

    def formatted_outstanding_balance(self, obj):
        return f"{obj.outstanding_balance():,.2f} PKR"
    formatted_outstanding_balance.short_description = "Total Outstanding"

    def generate_html_report(self, request, queryset):
        vendors = queryset
        context = {'vendors': vendors, 'date': datetime.now()}
        html = render_to_string('admin/vendor_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="vendor_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_vendor_pdf(self, request, queryset):
        """Generate PDF report for Vendors."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, 
                                      alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Vendor Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Updated table header with Vendor Code + Opening Balance
        table_data = [['Code', 'Name', 'Group', 'Contact', 'Opening Balance', 'Outstanding']]
        
        total_opening = Decimal('0.0')
        total_outstanding = Decimal('0.0')
        
        for vendor in queryset:
            opening = vendor.opening_balance
            balance = vendor.outstanding_balance()
            table_data.append([
                vendor.vendor_code or '-',
                vendor.name,
                vendor.group.name if vendor.group else '-',
                vendor.contact_number or '-',
                f"{opening:,.2f}",
                f"{balance:,.2f}"
            ])
            total_opening += opening
            total_outstanding += balance
        
        table_data.append(['', '', '', '', 'TOTAL:', f"{total_outstanding:,.2f}"])
        
        table = Table(table_data, repeatRows=1, 
                      colWidths=[0.8*inch, 1.3*inch, 1*inch, 1*inch, 1*inch, 1.1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="vendor_report.pdf"'
        return response
    generate_vendor_pdf.short_description = 'Generate PDF Report'


# ============================================
# PURCHASE ORDER ITEM INLINE
# ============================================
class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    fields = ('product', 'qty', 'price', 'total_amt')
    readonly_fields = ('total_amt',)
    extra = 10


# ============================================
# PURCHASE ORDER ADMIN
# ============================================
@admin.register(PurchaseOrder, site=admin.site)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'order_date', 'vendor','vendor_so_number', 'warehouse', 'status',
                    'formatted_total', 'formatted_advance', 'formatted_outstanding',
                    'receive_status_display', 'converted_to_purchase')
    list_filter = ('status', 'order_date', 'warehouse', 'vendor__group')
    search_fields = ('order_no', 'vendor__name')
    search_help_text = "Search by PO Number or Vendor Name"
    inlines = [PurchaseOrderItemInline]
    change_list_template = "admin/button.html"
    actions = ['convert_to_purchase', 'create_grn', 'update_po_status', 'generate_po_pdf']
    
    readonly_fields = ('order_no', 'created_at', 'updated_at', 'converted_to_purchase', 'created_by')
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_no', 'vendor','vendor_so_number', 'warehouse', 'order_date', 'expected_date', 'status')
        }),
        ('Payment Information', {
            'fields': ('discount_value', 'advance_payment')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at', 'converted_to_purchase')
        }),
    )
    
    def formatted_total(self, obj):
        return f"Rs. {obj.total_amount():,.2f}"
    formatted_total.short_description = "Total"
    
    def formatted_advance(self, obj):
        return f"Rs. {obj.advance_payment:,.2f}"
    formatted_advance.short_description = "Advance"
    
    def formatted_outstanding(self, obj):
        return f"Rs. {obj.outstanding_advance():,.2f}"
    formatted_outstanding.short_description = "Outstanding"
    
    def receive_status_display(self, obj):
        if obj.status in ['pending', 'confirmed']:
            return "Not Received"
        elif obj.status == 'partially_received':
            total_items = obj.items.count()
            if total_items > 0:
                received_count = sum(1 for item in obj.items.all() if obj.received_qty(item.product) >= item.qty)
                percent = round((received_count / total_items) * 100)
                return format_html('<span style="color: #ff9800;">🟡 {}% Received</span>', percent)
            return "Partially Received"
        elif obj.status == 'received':
            return format_html('<span style="color: #28a745;">✅ Received</span>')
        elif obj.status == 'completed':
            return format_html('<span style="color: #007bff;">📋 Completed</span>')
        elif obj.status == 'cancelled':
            return format_html('<span style="color: #dc3545;">❌ Cancelled</span>')
        return obj.get_status_display()
    receive_status_display.short_description = "Receive Status"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def convert_to_purchase(self, request, queryset):
        """Convert selected POs to Purchase"""
        success_count = 0
        for order in queryset.filter(status__in=['received', 'partially_received'], converted_to_purchase__isnull=True):
            try:
                with transaction.atomic():
                    purchase = Purchase.objects.create(
                        warehouse=order.warehouse,
                        bill_no=f"BILL-{order.order_no}",
                        vendor=order.vendor,
                        pur_date=now(),
                        paid=order.advance_payment,
                        created_by=request.user
                    )
                    
                    for item in order.items.all():
                        PurchaseItem.objects.create(
                            purchase=purchase,
                            product=item.product,
                            qty=item.qty,
                            price=item.price
                        )
                    
                    order.status = 'completed'
                    order.converted_to_purchase = purchase
                    order.save()
                    success_count += 1
            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)
        
        if success_count:
            self.message_user(request, f"✅ {success_count} POs converted to purchase.")
    convert_to_purchase.short_description = "🔄 Convert to Purchase"
    
    def create_grn(self, request, queryset):
        """Create GRN from selected POs"""
        from django.db.models import Sum
        
        count = 0
        for order in queryset.filter(status__in=['confirmed', 'processing', 'shipped', 'partially_received']):
            try:
                with transaction.atomic():
                    grn = GoodsReceivedNote.objects.create(
                        purchase_order=order,
                        vendor=order.vendor,
                        warehouse=order.warehouse,
                        reason='purchase',
                        created_by=request.user
                    )
                    
                    for item in order.items.all():
                        already_received = GoodsReceivedItem.objects.filter(
                            grn__purchase_order=order,
                            product=item.product
                        ).aggregate(total=Sum('qty'))['total'] or 0
                        
                        pending = item.qty - already_received
                        
                        if pending > 0:
                            GoodsReceivedItem.objects.create(
                                grn=grn,
                                product=item.product,
                                order_qty=item.qty,
                                qty=pending,
                                price=item.price,
                                notes=f"PO: {order.order_no}"
                            )
                    
                    order.update_receive_status()
                    count += 1
            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)
        
        if count:
            self.message_user(request, f"✅ {count} GRNs created successfully.")
    create_grn.short_description = "📋 Create GRN (Receive Goods)"
    
    def update_po_status(self, request, queryset):
        selected_ids = queryset.values_list('id', flat=True)
        ids_str = ','.join(map(str, selected_ids))
        return redirect(f"/admin/app/purchaseorder/update-status/?ids={ids_str}")
    update_po_status.short_description = "📝 Update Status"
    
    def generate_po_pdf(self, request, queryset):
        """Generate PDF for POs"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        for order in queryset:
            story.append(Paragraph(f"Purchase Order - {order.order_no}", styles['Heading1']))
            story.append(Paragraph(f"Vendor: {order.vendor.name}", styles['Normal']))
            story.append(Paragraph(f"Status: {order.get_status_display()}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
            
            data = [['Product', 'Order Qty', 'Received', 'Pending', 'Price', 'Total']]
            for item in order.items.all():
                received = order.received_qty(item.product)
                data.append([item.product.name, str(item.qty), str(received), str(item.qty - received), f"{item.price:,.2f}", f"{item.total_amt:,.2f}"])
            
            data.append(['', '', '', '', 'Total:', f"{order.total_amount():,.2f}"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            story.append(table)
            story.append(Spacer(1, 0.5*inch))
        
        doc.build(story)
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')
    generate_po_pdf.short_description = "📄 Generate PO PDF"


# ============================================
# GRN ITEM INLINE
# ============================================
class GoodsReceivedItemInline(admin.TabularInline):
    model = GoodsReceivedItem
    fields = ('product', 'order_qty', 'qty', 'pending_qty', 'unit', 'price', 'total_amt', 'notes')
    readonly_fields = ('pending_qty', 'total_amt')
    extra = 10


# ============================================
# GRN ADMIN
# ============================================
@admin.register(GoodsReceivedNote, site=admin.site)
class GoodsReceivedNoteAdmin(admin.ModelAdmin):
    list_display = ('grn_no', 'grn_date', 'vendor', 'warehouse', 'po_link',
                    'reason', 'total_qty_display', 'total_items_display', 'converted_to_purchase', 'print_grn')
    list_filter = ('reason', 'grn_date', 'warehouse')
    search_fields = ('grn_no', 'vendor__name', 'purchase_order__order_no')
    inlines = [GoodsReceivedItemInline]
    change_list_template = "admin/button.html"
    actions = ['generate_grn_pdf', 'convert_grn_to_purchase']
    
    fieldsets = (
        ('GRN Information', {
            'fields': ('grn_no', 'purchase_order', 'vendor', 'warehouse', 'grn_date', 'reason')
        }),
        ('Supplier Invoice', {
            'fields': ('invoice_no',)
        }),
        ('Transport', {
            'fields': ('vehicle_no', 'driver_name'),
            'classes': ('collapse',)
        }),
        ('Remarks', {
            'fields': ('notes',)
        }),
    )
    
    readonly_fields = ('grn_no',)
    
    def po_link(self, obj):
        if obj.purchase_order:
            url = reverse('admin:app_purchaseorder_change', args=[obj.purchase_order.id])
            return format_html('<a href="{}">{}</a>', url, obj.purchase_order.order_no)
        return "-"
    po_link.short_description = "PO"
    
    def total_qty_display(self, obj):
        return f"{obj.total_qty():,.2f}"
    total_qty_display.short_description = "Total Qty"
    
    def total_items_display(self, obj):
        return obj.total_items()
    total_items_display.short_description = "Items"
    
    def print_grn(self, obj):
        url = reverse('admin:generate_grn_pdf', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">📄 Print</a>', url)
    print_grn.short_description = "Print"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        if obj.purchase_order and not obj.vendor_id:
            obj.vendor = obj.purchase_order.vendor
        if obj.purchase_order and not obj.warehouse_id:
            obj.warehouse = obj.purchase_order.warehouse
        super().save_model(request, obj, form, change)
    
    def generate_grn_pdf(self, request, queryset):
        """Generate PDF for GRNs"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.3*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        for grn in queryset:
            title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
            story.append(Paragraph(company_name, title_style))
            story.append(Paragraph("<b>GOODS RECEIVED NOTE (GRN)</b>", title_style))
            story.append(Spacer(1, 0.2*inch))
            
            details = [
                [Paragraph(f"<b>GRN No:</b> {grn.grn_no}"), Paragraph(f"<b>Date:</b> {grn.grn_date.strftime('%d-%m-%Y')}")],
                [Paragraph(f"<b>PO No:</b> {grn.purchase_order.order_no if grn.purchase_order else 'N/A'}"), Paragraph(f"<b>Invoice:</b> {grn.invoice_no or 'N/A'}")],
                [Paragraph(f"<b>Vendor:</b> {grn.vendor.name}"), Paragraph(f"<b>Vehicle:</b> {grn.vehicle_no or 'N/A'}")],
            ]
            t = Table(details, colWidths=[3.5*inch, 3.5*inch])
            story.append(t)
            story.append(Spacer(1, 0.2*inch))
            
            table_data = [['S.No', 'Product', 'Order Qty', 'Received', 'Pending', 'Unit']]
            total_order = 0
            total_rec = 0
            total_pend = 0
            
            for idx, item in enumerate(grn.items.all(), 1):
                table_data.append([str(idx), item.product.name, f"{item.order_qty:,.2f}", f"{item.qty:,.2f}", f"{item.pending_qty:,.2f}", item.unit or '-'])
                total_order += item.order_qty
                total_rec += item.qty
                total_pend += item.pending_qty
            
            table_data.append(['', 'TOTAL', f"{total_order:,.2f}", f"{total_rec:,.2f}", f"{total_pend:,.2f}", ''])
            
            items_table = Table(table_data, repeatRows=1)
            items_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            story.append(items_table)
            story.append(Spacer(1, 0.4*inch))
            
            sign = [
                [Paragraph("<b>Received by:</b> _________"), Paragraph("<b>Checked by:</b> _________")],
            ]
            story.append(Table(sign, colWidths=[3.5*inch, 3.5*inch]))
            story.append(Paragraph("<br/><br/>", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')
    generate_grn_pdf.short_description = "📄 Generate GRN PDF"
    
    def convert_grn_to_purchase(self, request, queryset):
        count = 0
        for grn in queryset.filter(converted_to_purchase=False):
            try:
                with transaction.atomic():
                    purchase = Purchase.objects.create(
                        warehouse=grn.warehouse,
                        bill_no=grn.invoice_no or f"BILL-{grn.grn_no}",
                        vendor=grn.vendor,
                        pur_date=now(),
                        created_by=request.user
                    )
                    for item in grn.items.all():
                        PurchaseItem.objects.create(purchase=purchase, product=item.product, qty=item.qty, price=item.price)
                    grn.converted_to_purchase = True
                    grn.save()
                    count += 1
            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)
        if count:
            self.message_user(request, f"✅ {count} GRNs converted to purchase.")
    convert_grn_to_purchase.short_description = "🔄 Convert to Purchase"


# ============================================
# PURCHASE ADMIN
# ============================================
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'formatted_pur_date', 'bill_status', 'created_by', 'vendor', 'warehouse',
        'get_vendor_group', 'formatted_previous_balance', 'formatted_total_amount',
        'formatted_paid', 'formatted_outstanding_balance', 'formatted_outstanding_with_previous',
    ]
    search_fields = ('vendor__name','bill_no')
    search_help_text = "Search by Bill No, Vendor Name"
    list_filter = ['pur_date','vendor__group','warehouse',]
    inlines = [PurchaseItemInline]
    list_per_page = 50
    change_list_template = "admin/button.html"
    actions = ['generate_html_report', 'generate_vendor_ledger', 'generate_aging_report', 'generate_purchase_pdf']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:  
            obj.created_by = request.user  
        super().save_model(request, obj, form, change)
    
    def formatted_pur_date(self, obj):
        return obj.pur_date.strftime('%d-%m-%Y')
    formatted_pur_date.short_description = 'Purchase Date'

    def formatted_previous_balance(self, obj):
        return f"{obj.previous_balance:,.2f} PKR"
    formatted_previous_balance.short_description = 'Previous Balance'

    def formatted_total_amount(self, obj):
        return f"{obj.total_amount():,.2f} PKR"
    formatted_total_amount.short_description = 'Total Amount'

    def formatted_paid(self, obj):
        return f"{obj.paid:,.2f} PKR"
    formatted_paid.short_description = 'Paid'

    def formatted_outstanding_balance(self, obj):
        return f"{obj.outstanding_balance():,.2f} PKR"
    formatted_outstanding_balance.short_description = 'Outstanding Balance'

    def formatted_outstanding_with_previous(self, obj):
        return f"{obj.outstanding_with_previous():,.2f} PKR"
    formatted_outstanding_with_previous.short_description = 'Outstanding (With Previous)'

    def get_vendor_group(self, obj):
        return obj.vendor.group.name if obj.vendor and obj.vendor.group else None
    get_vendor_group.short_description = 'Vendor Group'

    def generate_aging_report(self, request, queryset):
        today = datetime.now().date()
        aging_data = {
            '30_days': queryset.filter(pur_date__gte=today - timedelta(days=30)).aggregate(Sum('purchaseitem__total_amt'))['purchaseitem__total_amt__sum'] or 0,
            '60_days': queryset.filter(pur_date__gte=today - timedelta(days=60), pur_date__lt=today - timedelta(days=30)).aggregate(Sum('purchaseitem__total_amt'))['purchaseitem__total_amt__sum'] or 0,
            '90_days': queryset.filter(pur_date__lt=today - timedelta(days=60)).aggregate(Sum('purchaseitem__total_amt'))['purchaseitem__total_amt__sum'] or 0,
        }
        context = {'aging_data': aging_data, 'date': datetime.now()}
        html = render_to_string('admin/aging_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="aging_report.html"'
        return response
    generate_aging_report.short_description = "Generate Aging Report"

    def generate_vendor_ledger(self, request, queryset):
        total_outstanding = queryset.aggregate(
            total_outstanding=ExpressionWrapper(
            Sum('purchaseitem__total_amt') - Sum('paid'),
            output_field=DecimalField()
            )
            )['total_outstanding'] or 0
        context = {
        'purchases': queryset,
        'date': datetime.now(),
        'total_outstanding': total_outstanding
        }
        html = render_to_string('admin/vendor_ledger_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="vendor_ledger_report.html"'
        return response
    generate_vendor_ledger.short_description = "Generate Vendor Ledger Report"

    def generate_html_report(self, request, queryset):
        purchases = queryset
        context = {'purchases': purchases, 'date': datetime.now()}
        html = render_to_string('admin/purchase_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="purchase_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_purchase_pdf(self, request, queryset):
        """ReportLab use karke Purchase ka PDF report generate karein"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Purchase Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Date', 'Bill No', 'Vendor', 'Group', 'Total', 'Paid', 'Outstanding']]
        
        total_amount = Decimal('0.0')
        total_paid = Decimal('0.0')
        total_outstanding = Decimal('0.0')
        
        for purchase in queryset:
            pur_total = purchase.total_amount()
            pur_outstanding = purchase.outstanding_balance()
            table_data.append([
                purchase.pur_date.strftime('%d-%m-%Y'),
                purchase.bill_no or 'Pending',
                purchase.vendor.name,
                purchase.vendor.group.name if purchase.vendor.group else '-',
                f"{pur_total:,.2f}",
                f"{purchase.paid:,.2f}",
                f"{pur_outstanding:,.2f}"
            ])
            total_amount += pur_total
            total_paid += purchase.paid
            total_outstanding += pur_outstanding
        
        table_data.append(['', '', '', 'TOTAL:', f"{total_amount:,.2f}", f"{total_paid:,.2f}", f"{total_outstanding:,.2f}"])
        
        table = Table(table_data, repeatRows=1, colWidths=[1*inch, 1*inch, 1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="purchase_report.pdf"'
        return response
    generate_purchase_pdf.short_description = 'Generate PDF Report'


# ============================================
# PURCHASE ITEM ADMIN
# ============================================
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ('get_pur_date','get_bill_no','vendor','get_vendor_group', 'product','get_category', 'qty', 'formatted_price', 'formatted_total')
    list_per_page = 25
    change_list_template = "admin/button.html"
    search_fields = ('product__name', 'purchase__bill_no', 'purchase__vendor__name')
    search_help_text = "Search by Product Name, Bill Number, or Vendor Name"
    list_filter = ('purchase__pur_date',)
    actions = ['generate_html_report', 'generate_purchase_item_pdf']

    def has_add_permission(self, request):
        return False

    def get_pur_date(self, obj):
        return obj.purchase.pur_date if obj.purchase else 'N/A'
    get_pur_date.short_description = 'Date'

    def get_bill_no(self, obj):
        return obj.purchase.bill_no if obj.purchase and hasattr(obj.purchase, 'bill_no') else 'N/A'
    get_bill_no.short_description = 'Bill No'
    
    def vendor(self, obj):
        return obj.purchase.vendor
    vendor.short_description = 'Vendor'

    def get_vendor_group(self, obj):
        return obj.purchase.vendor.group.name if obj.purchase and obj.purchase.vendor and obj.purchase.vendor.group else None
    get_vendor_group.short_description = 'Vendor Group'

    def get_category(self, obj):
        return obj.product.category.name if obj.product and obj.product.category else 'N/A'
    get_category.short_description = 'Category'

    def formatted_price(self, obj):
        return f"{obj.price:,.2f} PKR"
    formatted_price.short_description = 'Price'

    def formatted_total(self, obj):
        total = Decimal(obj.qty) * obj.price
        return f"{total:,.2f} PKR"
    formatted_total.short_description = 'Total Amount'

    def generate_html_report(self, request, queryset):
        PurchaseItems = queryset
        context = {'PurchaseItems': PurchaseItems, 'date': datetime.now()}
        html = render_to_string('admin/PurchaseItem_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="PurchaseItem_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_purchase_item_pdf(self, request, queryset):
        """Generate PDF report for Purchase Items."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Purchase Items Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Date', 'Bill No', 'Vendor', 'Product', 'Qty', 'Price', 'Total']]
        
        total_qty = Decimal('0.0')
        total_amount = Decimal('0.0')
        
        for item in queryset:
            qty = Decimal(str(item.qty))
            total = qty * item.price
            table_data.append([
                item.purchase.pur_date.strftime('%d-%m-%Y') if item.purchase else 'N/A',
                item.purchase.bill_no if item.purchase else 'N/A',
                item.purchase.vendor.name if item.purchase else 'N/A',
                item.product.name,
                f"{qty:,.2f}",
                f"{item.price:,.2f}",
                f"{total:,.2f}"
            ])
            total_qty += qty
            total_amount += total
        
        table_data.append(['', '', '', 'TOTAL:', f"{total_qty:,.2f}", '', f"{total_amount:,.2f}"])
        
        table = Table(table_data, repeatRows=1, colWidths=[1*inch, 1*inch, 1.5*inch, 2*inch, 0.8*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="purchase_items_report.pdf"'
        return response
    generate_purchase_item_pdf.short_description = 'Generate PDF Report'


# ============================================
# PURCHASE RETURN ADMIN
# ============================================
class PurchaseRetrnAdmin(admin.ModelAdmin):
    inlines = [PurchaseRetrnItemInline]
    list_display = ('purchase_return_date','bill_no', 'purchase', 'vendor', 'created_by', 'return_reason')
    change_list_template = "admin/button.html"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:  
            obj.created_by = request.user  
        super().save_model(request, obj, form, change)


class PurchaseRetrnItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_return', 'product', 'qty', 'price', 'total_amt')
    change_list_template = "admin/button.html"

    def has_add_permission(self, request):
        return False


# ============================================
# PURCHASE QUOTATION ITEM INLINE
# ============================================
class PurchaseQuotationItemInline(admin.TabularInline):
    model = PurchaseQuotationItem
    fields = ('product', 'qty', 'price', 'total_amt')
    readonly_fields = ('total_amt',)
    extra = 10


# ============================================
# PURCHASE QUOTATION ADMIN
# ============================================
@admin.register(PurchaseQuotation, site=admin.site)
class PurchaseQuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_no', 'quotation_date', 'vendor', 'vendor_so_number',
                    'valid_until', 'status', 'formatted_total', 'converted_to_order')
    list_filter = ('status', 'quotation_date', 'vendor__group')
    search_fields = ('quotation_no', 'vendor__name')
    inlines = [PurchaseQuotationItemInline]
    change_list_template = "admin/button.html"
    actions = ['convert_to_purchase_order', 'generate_rfq_pdf']
    
    readonly_fields = ('quotation_no', 'created_at', 'updated_at', 'converted_to_order', 'created_by')
    
    fieldsets = (
        ('Quotation Information', {
            'fields': ('quotation_no', 'vendor', 'vendor_so_number', 'warehouse',
                       'quotation_date', 'valid_until', 'status')
        }),
        ('Vendor Details', {
            'fields': ('vendor_reference',)
        }),
        ('Payment & Terms', {
            'fields': ('discount_value', 'terms_conditions')
        }),
        ('Additional', {
            'fields': ('notes', 'converted_to_order', 'created_at')
        }),
    )
    
    def formatted_total(self, obj):
        return f"Rs. {obj.total_amount():,.2f}"
    formatted_total.short_description = "Total"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def convert_to_purchase_order(self, request, queryset):
        """Convert accepted quotations to Purchase Order"""
        count = 0
        for quote in queryset.filter(status__in=['accepted'], converted_to_order__isnull=True):
            try:
                with transaction.atomic():
                    order = PurchaseOrder.objects.create(
                        vendor=quote.vendor,
                        warehouse=quote.warehouse,
                        status='confirmed',
                        discount_value=quote.discount_value,
                        vendor_so_number=quote.vendor_so_number,
                        notes=f"Converted from {quote.quotation_no}",
                        created_by=request.user
                    )
                    for item in quote.items.all():
                        PurchaseOrderItem.objects.create(
                            order=order,
                            product=item.product,
                            qty=item.qty,
                            price=item.price
                        )
                    quote.status = 'converted'
                    quote.converted_to_order = order
                    quote.save()
                    count += 1
            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)
        
        if count:
            self.message_user(request, f"✅ {count} RFQs converted to Purchase Orders!")
    convert_to_purchase_order.short_description = "🔄 Convert to Purchase Order"
    
    def generate_rfq_pdf(self, request, queryset):
        """Generate PDF for RFQs"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        for quote in queryset:
            story.append(Paragraph(f"REQUEST FOR QUOTATION - {quote.quotation_no}", styles['Heading1']))
            story.append(Paragraph(f"Vendor: {quote.vendor.name}", styles['Normal']))
            story.append(Paragraph(f"Valid Until: {quote.valid_until}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
            
            data = [['Product', 'Qty', 'Price', 'Total']]
            for item in quote.items.all():
                data.append([item.product.name, str(item.qty), f"{item.price:,.2f}", f"{item.total_amt:,.2f}"])
            
            data.append(['', '', 'Total:', f"{quote.total_amount():,.2f}"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            story.append(table)
            story.append(Spacer(1, 0.5*inch))
        
        doc.build(story)
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')
    generate_rfq_pdf.short_description = "📄 Generate RFQ PDF"
