"""Admin: sales models."""
from ..models import *
import io
from django.contrib import admin, messages
from django.utils.timezone import now
from django.db.models import Sum, DecimalField, ExpressionWrapper
from datetime import datetime
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


# SALE ORDER ITEM INLINE
# ============================================
class SaleOrderItemInline(admin.TabularInline):
    model = SaleOrderItem
    fields = ('product', 'qty', 'price', 'total_amt', 'reserved')
    readonly_fields = ('total_amt',)
    extra = 10


# ============================================
# SALE ORDER ADMIN
# ============================================
# ============================================
# SALE ORDER ADMIN
# ============================================
@admin.register(SaleOrder, site=admin.site)
class SaleOrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'order_date', 'customer','customer_po_number','warehouse', 'status', 
                    'formatted_total', 'formatted_advance', 'formatted_outstanding', 
                    'delivery_status_display', 'converted_to_sale')
    list_filter = ('status', 'order_date', 'warehouse', 'customer__group')
    search_fields = ('order_no', 'customer__name', 'customer__contact_number')
    search_help_text = "Search by Order No, Customer Name, or Contact Number"
    inlines = [SaleOrderItemInline]
    change_list_template = "admin/button.html"
    actions = [
        'convert_to_sale', 
        'create_delivery_challan', 
        'update_status', 
        'generate_order_pdf', 
        'generate_order_html',
        'send_order_status_whatsapp',
    ]
    
    readonly_fields = ('order_no', 'created_at', 'updated_at', 'converted_to_sale', 'created_by')
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_no', 'customer','customer_po_number', 'warehouse', 'order_date', 'delivery_date', 'status')
        }),
        ('Payment Information', {
            'fields': ('discount_value', 'advance_payment')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at', 'converted_to_sale')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.status == 'invoiced':
            readonly.extend(['customer', 'warehouse', 'order_date', 'discount_value', 'advance_payment'])
        return readonly
    
    def formatted_total(self, obj):
        return f"Rs. {obj.total_amount():,.2f}"
    formatted_total.short_description = "Total"
    
    def formatted_advance(self, obj):
        return f"Rs. {obj.advance_payment:,.2f}"
    formatted_advance.short_description = "Advance"
    
    def formatted_outstanding(self, obj):
        return f"Rs. {obj.outstanding_advance():,.2f}"
    formatted_outstanding.short_description = "Outstanding"
    
    def delivery_status_display(self, obj):
        """Show delivery progress"""
        if obj.status in ['pending', 'confirmed']:
            return "Not Started"
        elif obj.status == 'partially_delivered':
            total_items = obj.items.count()
            if total_items > 0:
                delivered_count = 0
                for item in obj.items.all():
                    if obj.delivered_qty(item.product) >= item.qty:
                        delivered_count += 1
                percent = round((delivered_count / total_items) * 100)
                return format_html(
                    '<span style="color: #ff9800;">🟡 {}% Delivered</span>', percent
                )
            return "Partially Delivered"
        elif obj.status == 'delivered':
            return format_html('<span style="color: #28a745;">✅ Fully Delivered</span>')
        elif obj.status == 'invoiced':
            return format_html('<span style="color: #007bff;">📋 Invoiced</span>')
        elif obj.status == 'cancelled':
            return format_html('<span style="color: #dc3545;">❌ Cancelled</span>')
        return obj.get_status_display()
    delivery_status_display.short_description = "Delivery"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    # ============================================
    # CONVERT TO SALE
    # ============================================
    def convert_to_sale(self, request, queryset):
        """Convert selected orders to Sale/Invoice"""
        from django.db import transaction
        
        success_count = 0
        error_messages = []
        
        for order in queryset.filter(status__in=['confirmed', 'ready', 'delivered', 'partially_delivered'], 
                                     converted_to_sale__isnull=True):
            try:
                with transaction.atomic():
                    sale = Sale.objects.create(
                        warehouse=order.warehouse,
                        bill_no=f"INV-{order.order_no}",
                        customer=order.customer,
                        sale_date=now(),
                        paid=order.advance_payment,
                        discount_value=order.discount_value,
                        created_by=request.user
                    )
                    
                    for item in order.items.all():
                        sale_item = SaleItem.objects.create(
                            sale=sale,
                            product=item.product,
                            qty=item.qty,
                            price=item.price
                        )
                        
                        if item.reserved:
                            try:
                                inventory = Inventory.objects.get(
                                    product=item.product, 
                                    warehouse=order.warehouse
                                )
                                inventory.reserved_stock = max(0, inventory.reserved_stock - item.qty)
                                inventory.save()
                            except Inventory.DoesNotExist:
                                pass
                    
                    order.status = 'invoiced'
                    order.converted_to_sale = sale
                    order.save()
                    
                    success_count += 1
                    
            except Exception as e:
                error_messages.append(f"Order {order.order_no}: {str(e)}")
        
        if success_count:
            self.message_user(request, f"✅ {success_count} orders converted to sale successfully.")
        if error_messages:
            self.message_user(request, f"❌ Errors: {'; '.join(error_messages)}", level=messages.ERROR)
    
    convert_to_sale.short_description = "🔄 Convert to Sale/Invoice"
    
    # ============================================
    # CREATE DELIVERY CHALLAN
    # ============================================
    def create_delivery_challan(self, request, queryset):
        """Create Delivery Challan with Partial Delivery Support"""
        from django.db import transaction
        from django.db.models import Sum
        
        count = 0
        for order in queryset.filter(status__in=['confirmed', 'processing', 'ready', 'partially_delivered']):
            try:
                with transaction.atomic():
                    challan = DeliveryChallan.objects.create(
                        order=order,
                        customer=order.customer,
                        warehouse=order.warehouse,
                        reason='sale',
                        created_by=request.user
                    )
                    
                    for item in order.items.all():
                        already_delivered = DeliveryChallanItem.objects.filter(
                            challan__order=order,
                            product=item.product
                        ).aggregate(total=Sum('qty'))['total'] or 0
                        
                        pending = item.qty - already_delivered
                        
                        if pending > 0:
                            DeliveryChallanItem.objects.create(
                                challan=challan,
                                product=item.product,
                                order_qty=item.qty,
                                qty=pending,
                                price=item.price,
                                notes=f"Order: {order.order_no}"
                            )
                    
                    order.update_delivery_status()
                    count += 1
                    
            except Exception as e:
                self.message_user(request, f"Error for {order.order_no}: {e}", level=messages.ERROR)
        
        if count:
            self.message_user(request, f"✅ {count} delivery challans created successfully.")
    
    create_delivery_challan.short_description = "📋 Create Delivery Challan"
    
    # ============================================
    # UPDATE STATUS
    # ============================================
    def update_status(self, request, queryset):
        """Bulk update order status"""
        selected_ids = queryset.values_list('id', flat=True)
        ids_str = ','.join(map(str, selected_ids))
        return redirect(f"/admin/app/saleorder/update-status/?ids={ids_str}")
    update_status.short_description = "📝 Update Status"
    
    # ============================================
    # GENERATE ORDER PDF
    # ============================================
    def generate_order_pdf(self, request, queryset):
        """Generate PDF for selected orders"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        
        for order in queryset:
            story.append(Paragraph(f"Sale Order - {order.order_no}", styles['Heading1']))
            story.append(Paragraph(f"Customer: {order.customer.name}", styles['Normal']))
            story.append(Paragraph(f"Order Date: {order.order_date.strftime('%d-%m-%Y')}", styles['Normal']))
            story.append(Paragraph(f"Status: {order.get_status_display()}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
            
            data = [['Product', 'Order Qty', 'Delivered', 'Pending', 'Price', 'Total']]
            
            for item in order.items.all():
                delivered = order.delivered_qty(item.product)
                pending_qty = item.qty - delivered
                data.append([
                    item.product.name,
                    str(item.qty),
                    str(delivered),
                    str(pending_qty),
                    f"{item.price:,.2f}",
                    f"{item.total_amt:,.2f}"
                ])
            
            data.append(['', '', '', '', 'Total:', f"{order.total_amount():,.2f}"])
            data.append(['', '', '', '', 'Discount:', f"{order.discount_value:,.2f}"])
            data.append(['', '', '', '', 'Grand Total:', f"{order.total_after_discount():,.2f}"])
            
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 0.5*inch))
        
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="sale_orders.pdf"'
        return response
    generate_order_pdf.short_description = "📄 Generate Order PDF"
    
    # ============================================
    # GENERATE ORDER HTML
    # ============================================
    def generate_order_html(self, request, queryset):
        """Generate HTML report"""
        context = {'orders': queryset, 'date': datetime.now()}
        html = render_to_string('admin/sale_order_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="sale_orders.html"'
        return response
    generate_order_html.short_description = "🌐 Generate HTML Report"
    
    # ============================================
    # WHATSAPP - SEND ORDER STATUS
    # ============================================
    def send_order_status_whatsapp(self, request, queryset):
        """Send the order status on WhatsApp"""
        from ..whatsapp_utils import WhatsAppSender
        
        count = 0
        links = []
        for order in queryset:
            if order.customer.contact_number:
                result = WhatsAppSender.send_order_status(
                    order.customer.contact_number,
                    order.customer.name,
                    order.order_no,
                    order.status
                )
                if result.get('success'):
                    count += 1
                    links.append({
                        'order': order.order_no,
                        'customer': order.customer.name,
                        'status': order.get_status_display(),
                        'url': result['url']
                    })
        
        if count > 0:
            msg = f"✅ {count} order status links generated!<br><br>"
            for link in links:
                msg += f"📋 {link['order']} ({link['status']}) - {link['customer']}<br>"
            if links:
                msg += f"<br><a href='{links[0]['url']}' target='_blank' style='background:#25D366; color:white; padding:8px 15px; border-radius:5px; text-decoration:none;'>📱 Send First Update</a>"
            self.message_user(request, format_html(msg))
        else:
            self.message_user(request, "❌ The customers of the selected orders have no phone number!", level=messages.WARNING)
    
    send_order_status_whatsapp.short_description = "📱 Send Order Status on WhatsApp"


class SaleRetrnItemInline(admin.TabularInline):
    model = SaleRetrnItem
    extra = 1


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    fields = ('product', 'qty', 'price')
    extra = 1
    autocomplete_fields =['product']


# ============================================
# DELIVERY CHALLAN ITEM INLINE
# ============================================
class DeliveryChallanItemInline(admin.TabularInline):
    model = DeliveryChallanItem
    fields = ('product', 'order_qty', 'qty', 'pending_qty', 'unit', 'price', 'total_amt', 'notes')
    readonly_fields = ('pending_qty', 'total_amt')
    extra = 10


# ============================================
# DELIVERY CHALLAN ADMIN
# ============================================
@admin.register(DeliveryChallan, site=admin.site)
class DeliveryChallanAdmin(admin.ModelAdmin):
    list_display = ('challan_no', 'challan_date', 'customer', 'warehouse', 'order_link', 
                    'reason', 'total_qty_display', 'total_items_display', 'converted_to_sale', 'print_challan')
    list_filter = ('reason', 'challan_date', 'warehouse', 'converted_to_sale')
    search_fields = ('challan_no', 'customer__name', 'order__order_no')
    search_help_text = "Search by Challan No, Customer, or Order No"
    inlines = [DeliveryChallanItemInline]
    change_list_template = "admin/button.html"
    actions = ['generate_challan_pdf', 'convert_challan_to_sale']
    
    fieldsets = (
        ('Challan Information', {
            'fields': ('challan_no', 'order', 'customer', 'warehouse', 'challan_date', 'reason')
        }),
        ('Transport Details', {
            'fields': ('vehicle_no', 'transport_name', 'driver_name', 'driver_contact'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    
    readonly_fields = ('challan_no',)
    
    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:app_saleorder_change', args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_no)
        return "-"
    order_link.short_description = "Order"
    
    def total_qty_display(self, obj):
        return f"{obj.total_qty():,.2f}"
    total_qty_display.short_description = "Total Qty"
    
    def total_items_display(self, obj):
        return obj.total_items()
    total_items_display.short_description = "Items"
    
    def print_challan(self, obj):
        url = reverse('admin:generate_challan_pdf', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">📄 Print</a>', url)
    print_challan.short_description = "Print"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        if obj.order and not obj.customer_id:
            obj.customer = obj.order.customer
        if obj.order and not obj.warehouse_id:
            obj.warehouse = obj.order.warehouse
        super().save_model(request, obj, form, change)
    
    def generate_challan_pdf(self, request, queryset):
        """Generate PDF for selected challans with Order Qty + Deliver Qty + Pending"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.3*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        company_address = company.address if company else "Address"
        company_phone = company.contact_number if company else "Phone"
        
        for challan in queryset:
            title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER, spaceAfter=5)
            story.append(Paragraph(company_name, title_style))
            story.append(Paragraph(company_address, styles['Normal']))
            story.append(Paragraph(f"Phone: {company_phone}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
            
            story.append(Paragraph("<b>DELIVERY CHALLAN</b>", title_style))
            story.append(Spacer(1, 0.15*inch))
            
            details_data = [
                [Paragraph(f"<b>Challan No:</b> {challan.challan_no}", styles['Normal']),
                 Paragraph(f"<b>Date:</b> {challan.challan_date.strftime('%d-%m-%Y')}", styles['Normal'])],
                [Paragraph(f"<b>Order No:</b> {challan.order.order_no if challan.order else 'N/A'}", styles['Normal']),
                 Paragraph(f"<b>Vehicle No:</b> {challan.vehicle_no or '_________'}", styles['Normal'])],
                [Paragraph(f"<b>Reason:</b> {challan.get_reason_display()}", styles['Normal']),
                 Paragraph(f"<b>Transport:</b> {challan.transport_name or '_________'}", styles['Normal'])],
            ]
            
            details_table = Table(details_data, colWidths=[3.5*inch, 3.5*inch])
            details_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(details_table)
            
            from_to_data = [
                [Paragraph("<b>From:</b>", styles['Normal']), Paragraph("<b>To:</b>", styles['Normal'])],
                [Paragraph(company_name + "<br/>" + company_address + "<br/>Phone: " + company_phone, styles['Normal']),
                 Paragraph(f"{challan.customer.name}<br/>{challan.customer.address or ''}<br/>Contact: {challan.customer.contact_number or ''}", styles['Normal'])],
            ]
            
            from_to_table = Table(from_to_data, colWidths=[3.5*inch, 3.5*inch])
            from_to_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LINEBELOW', (0, 1), (-1, 1), 0.5, colors.grey),
            ]))
            story.append(from_to_table)
            story.append(Spacer(1, 0.2*inch))
            
            # ✅ Updated Items Table with Order Qty + Deliver Qty + Pending
            table_data = [['S.No', 'Product', 'Order Qty', 'Deliver Qty', 'Pending', 'Unit', 'Remarks']]
            
            total_order = 0
            total_deliver = 0
            total_pending = 0
            
            for idx, item in enumerate(challan.items.all(), 1):
                table_data.append([
                    str(idx),
                    item.product.name,
                    f"{item.order_qty:,.2f}",
                    f"{item.qty:,.2f}",
                    f"{item.pending_qty:,.2f}",
                    item.unit or '-',
                    item.notes or ''
                ])
                total_order += item.order_qty
                total_deliver += item.qty
                total_pending += item.pending_qty
            
            table_data.append(['', 'TOTAL', f"{total_order:,.2f}", f"{total_deliver:,.2f}", f"{total_pending:,.2f}", '', f"{challan.total_items()} items"])
            
            col_widths = [0.4*inch, 1.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.7*inch, 1.2*inch]
            items_table = Table(table_data, repeatRows=1, colWidths=col_widths)
            
            items_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -2), 'LEFT'),
                ('ALIGN', (2, 1), (4, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.black),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ]))
            
            story.append(items_table)
            story.append(Spacer(1, 0.4*inch))
            
            sign_data = [
                [Paragraph("<b>Received by:</b> _________________", styles['Normal']),
                 Paragraph("<b>Dispatched by:</b> _________________", styles['Normal'])],
                [Paragraph("Signature: _________________", styles['Normal']),
                 Paragraph("Signature: _________________", styles['Normal'])],
                [Paragraph("Date: _________________", styles['Normal']),
                 Paragraph("Date: _________________", styles['Normal'])],
            ]
            
            sign_table = Table(sign_data, colWidths=[3.5*inch, 3.5*inch])
            sign_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(sign_table)
            
            story.append(Spacer(1, 0.3*inch))
            story.append(Paragraph("This is a computer generated challan - no signature required.", styles['Normal']))
            story.append(Paragraph("<br/><br/>", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="delivery_challan.pdf"'
        return response
    generate_challan_pdf.short_description = "📄 Generate Challan PDF"
    
    def convert_challan_to_sale(self, request, queryset):
        """Convert challan to Sale/Invoice"""
        from django.db import transaction
        
        count = 0
        for challan in queryset.filter(converted_to_sale=False):
            try:
                with transaction.atomic():
                    sale = Sale.objects.create(
                        warehouse=challan.warehouse,
                        bill_no=f"INV-{challan.challan_no}",
                        customer=challan.customer,
                        sale_date=now(),
                        created_by=request.user
                    )
                    
                    for item in challan.items.all():
                        SaleItem.objects.create(
                            sale=sale,
                            product=item.product,
                            qty=item.qty,
                            price=item.price
                        )
                    
                    challan.converted_to_sale = True
                    challan.save()
                    count += 1
            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)
        
        if count:
            self.message_user(request, f"✅ {count} challans converted to sale.")
    convert_challan_to_sale.short_description = "🔄 Convert to Sale/Invoice"


# ============================================
# CUSTOMER GROUP ADMIN
# ============================================
@admin.register(CustomerGroup, site=admin.site)
class CustomerGroupAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    change_list_template = "admin/button.html"
    search_help_text = "Search by Customer Group Name"
    list_display = ['name', 'description', 'total_outstanding_balance_display']
    actions = ['generate_html_report', 'generate_customer_group_pdf']
    
    def total_outstanding_balance_display(self, obj):
        return f'{obj.total_outstanding_balance():,.2f}'
    total_outstanding_balance_display.short_description = 'Total Outstanding Balance'

    def generate_html_report(self, request, queryset):
        CustomerGroups = queryset
        context = {'CustomerGroups': CustomerGroups, 'date': datetime.now()}
        html = render_to_string('admin/CustomerGroup_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="CustomerGroup_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_customer_group_pdf(self, request, queryset):
        """Generate PDF report for Customer Groups."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Customer Group Report", title_style))
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
        response['Content-Disposition'] = 'attachment; filename="customer_group_report.pdf"'
        return response
    generate_customer_group_pdf.short_description = 'Generate PDF Report'


# ============================================
# CUSTOMER ADMIN
# ============================================
class CustomerAdmin(admin.ModelAdmin):
    search_fields = ('customer_code', 'name', 'contact_number')
    search_help_text = "Search by Customer Code, Name, or Contact Number"
    list_display = ('customer_code', 'name', 'group', 'contact_number', 'address', 
                    'adjusted_outstanding_balance', 'profit_margin')
    list_editable = ('profit_margin',)
    ordering = ('customer_code',)
    change_list_template = "admin/button.html"
    actions = ['generate_html_report', 'generate_customer_pdf']
    readonly_fields = ('adjusted_outstanding_balance',)
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('customer_code', 'name', 'group', 'address', 'profit_margin')
        }),
        ('Contact Details', {
            'fields': ('contact_number', 
                       ('ref_name_1', 'ref_contact_number_1'),
                       ('ref_name_2', 'ref_contact_number_2'))
        }),
        ('Farmer (Agri)', {      # [agri-edition:admin-customer]
            'fields': ('village', 'main_crop', 'credit_limit'),
        }),
    )

    def adjusted_outstanding_balance(self, obj):
        return f'{obj.adjusted_outstanding_balance():,.2f}'
    adjusted_outstanding_balance.short_description = 'Total Outstanding Balance'

    def generate_html_report(self, request, queryset):
        customers = queryset
        context = {'customers': customers, 'date': datetime.now()}
        html = render_to_string('admin/customer_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="customer_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_customer_pdf(self, request, queryset):
        """Generate PDF report for Customers."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, 
                                      alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Customer Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Updated table header with Customer Code
        table_data = [['Code', 'Name', 'Group', 'Address', 'Contact', 'Margin %', 'Outstanding']]
        
        total_outstanding = Decimal('0.0')
        for customer in queryset:
            balance = customer.adjusted_outstanding_balance()
            table_data.append([
                customer.customer_code or '-',
                customer.name,
                customer.group.name if customer.group else '-',
                (customer.address[:30] + '...') if customer.address and len(customer.address) > 30 
                    else (customer.address or '-'),
                customer.contact_number or '-',
                f"{customer.profit_margin:.2f}%",
                f"{balance:,.2f}"
            ])
            total_outstanding += balance
        
        table_data.append(['', '', '', '', '', 'TOTAL:', f"{total_outstanding:,.2f}"])
        
        table = Table(table_data, repeatRows=1, 
                      colWidths=[0.8*inch, 1.3*inch, 1*inch, 1.5*inch, 1*inch, 0.8*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (5, 1), (6, -1), 'RIGHT'),
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
        response['Content-Disposition'] = 'attachment; filename="customer_report.pdf"'
        return response
    generate_customer_pdf.short_description = 'Generate PDF Report'


# ============================================
# SALE ITEM ADMIN
# ============================================
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('get_sale_date', 'get_bill_no','customer', 'get_customer_group', 'product','get_unit', 'get_category', 'qty', 'formatted_price', 'discount_applied', 'formatted_total', 'discounted_total', 'formatted_profit', 'get_purchase_bill_no')
    list_per_page = 25
    change_list_template = "admin/button.html"
    search_fields = ('product__name', 'sale__bill_no', 'sale__customer__name')
    search_help_text = "Search by Product Name, Bill Number, or Customer Name"
    list_filter = ('sale__sale_date', 'product__category', 'sale__customer')
    actions = ['generate_html_report', 'generate_sale_item_pdf']

    def has_add_permission(self, request):
        return False

    def get_purchase_bill_no(self, obj):
        if not obj.batches_used.exists():
            return "N/A"
        bill_nos = set(
            batch.purchase_item.purchase.bill_no 
            for batch in obj.batches_used.all() 
            if batch.purchase_item and batch.purchase_item.purchase.bill_no
        )
        return ", ".join(bill_nos) if bill_nos else "Waiting for Bill"
    get_purchase_bill_no.short_description = "Purchase Bill No"

    def discount_applied(self, obj):
        total_sale_amount = obj.sale.total_without_discount()
        if total_sale_amount > 0:
            discount_ratio = obj.total_amt / total_sale_amount
            discount = discount_ratio * obj.sale.discount_value
            return round(discount, 2)
        return 0.00

    def discounted_total(self, obj):
        return round(obj.total_amt - self.discount_applied(obj), 2)

    discount_applied.short_description = "Discount Applied"
    discounted_total.short_description = "Discounted Total"

    def customer(self, obj):
        return obj.sale.customer
    customer.short_description = 'Customer'

    def formatted_price(self, obj):
        return f"{obj.price:,.2f} PKR"
    formatted_price.short_description = 'Price'

    def formatted_total(self, obj):
        total = Decimal(obj.qty) * obj.price
        return f"{total:,.2f} PKR"
    formatted_total.short_description = 'Total Amount'

    def formatted_profit(self, obj):
        adjusted_profit = obj.profit - self.discount_applied(obj)
        return f"{adjusted_profit:,.2f} PKR"
    formatted_profit.short_description = 'Profit (Adjusted)'

    def get_sale_date(self, obj):
        return obj.sale.sale_date if obj.sale else 'N/A'
    get_sale_date.short_description = 'Date'

    def get_bill_no(self, obj):
        return obj.sale.bill_no if obj.sale and hasattr(obj.sale, 'bill_no') else 'N/A'
    get_bill_no.short_description = 'Bill No'

    def get_category(self, obj):
        return obj.product.category.name if obj.product and obj.product.category else 'N/A'
    get_category.short_description = 'Category'

    def get_unit(self, obj):
        return obj.product.unit
    get_unit.short_description = 'Unit'

    def generate_html_report(self, request, queryset):
        SaleItems = queryset
        context = {'SaleItems': SaleItems, 'date': datetime.now()}
        html = render_to_string('admin/SaleItem_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="SaleItem_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'

    def view_invoice(self, obj):
        url = reverse('generate_invoice', args=[obj.sale.pk])
        return format_html(f'<a href="{url}" target="_blank">View Invoice</a>')
    view_invoice.short_description = 'Invoice'

    def get_customer_group(self, obj):
        return obj.sale.customer.group.name if obj.sale and obj.sale.customer and obj.sale.customer.group else None
    get_customer_group.short_description = 'Customer Group'
    
    def generate_sale_item_pdf(self, request, queryset):
        """Generate PDF report for Sale Items."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Sale Items Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Date', 'Bill No', 'Customer', 'Product', 'Qty', 'Price', 'Total', 'Profit']]
        
        total_qty = Decimal('0.0')
        total_amount = Decimal('0.0')
        total_profit = Decimal('0.0')
        
        for item in queryset:
            qty = Decimal(str(item.qty))
            total = qty * item.price
            profit = item.profit - item.discount if hasattr(item, 'discount') else item.profit
            table_data.append([
                item.sale.sale_date.strftime('%d-%m-%Y') if item.sale else 'N/A',
                item.sale.bill_no if item.sale else 'N/A',
                item.sale.customer.name if item.sale else 'N/A',
                item.product.name,
                f"{qty:,.2f}",
                f"{item.price:,.2f}",
                f"{total:,.2f}",
                f"{profit:,.2f}"
            ])
            total_qty += qty
            total_amount += total
            total_profit += profit
        
        table_data.append(['', '', '', 'TOTAL:', f"{total_qty:,.2f}", '', f"{total_amount:,.2f}", f"{total_profit:,.2f}"])
        
        table = Table(table_data, repeatRows=1, colWidths=[1*inch, 0.9*inch, 1.3*inch, 1.8*inch, 0.7*inch, 0.9*inch, 0.9*inch, 0.9*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="sale_items_report.pdf"'
        return response
    generate_sale_item_pdf.short_description = 'Generate PDF Report'


# ============================================
# SALE ADMIN
# ============================================
class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_date','customer', 'warehouse', 'get_customer_group','bill_no','created_by',
                    'formatted_previous_balance', 'formatted_total_without_discount', 'discount_value', 
                    'formatted_total_amount', 'formatted_paid', 'formatted_total_outstanding_with_previous',
                    'formatted_total_profit', 'view_invoice')
    search_fields = ('customer__name','bill_no')
    search_help_text = "Search by Bill No, Customer Name"
    list_filter = ('sale_date','customer__group','warehouse',)
    change_form_template = "admin/barcode_sale.html"
    change_list_template = "admin/button.html"
    inlines = [SaleItemInline]
    actions = [
        'generate_html_report', 
        'generate_customer_ledger', 
        'generate_sales_profit_analysis', 
        'generate_sale_pdf',
        'send_whatsapp_invoice',
        'send_pdf_invoice_whatsapp',
        'send_payment_reminders',
    ]
    list_per_page = 50

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['warehouse'].required = True
        if not Warehouse.objects.exists():
            form.base_fields['warehouse'].help_text = "کوئی ویئرہاؤس موجود نہیں۔ براہ کرم پہلے ایک بنائیں۔"
        return form

    def formatted_sale_date(self, obj):
        return obj.sale_date.strftime('%d-%m-%y')
    formatted_sale_date.short_description = 'Sale Date'

    def formatted_total_without_discount(self, obj):
        return f"{obj.total_without_discount():,.2f} PKR"
    formatted_total_without_discount.short_description = 'Total_without_Discount'

    def formatted_total_amount(self, obj):
        return f"{obj.total_amount():,.2f} PKR"
    formatted_total_amount.short_description = 'Total Amount'

    def formatted_total_profit(self, obj):
        return f"{obj.total_profit():,.2f} PKR"
    formatted_total_profit.short_description = 'Total Profit'

    def formatted_paid(self, obj):
        return f"{obj.paid:,.2f} PKR"
    formatted_paid.short_description = 'Paid'

    def formatted_previous_balance(self, obj):
        return f"{obj.previous_balance:,.2f} PKR"
    formatted_previous_balance.short_description = 'Previous Balance'

    def formatted_total_outstanding_with_previous(self, obj):
        return f"{obj.total_outstanding_with_previous:,.2f} PKR"
    formatted_total_outstanding_with_previous.short_description = 'Total_Outstanding_With_Previous'

    def generate_sales_profit_analysis(self, request, queryset):
        profit_data = queryset.aggregate(
            total_sales=Sum('saleitem__total_amt'),
            total_profit=Sum('saleitem__profit')
        )
        context = {'profit_data': profit_data, 'date': datetime.now()}
        html = render_to_string('admin/sales_profit_analysis.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="sales_profit_analysis.html"'
        return response
    generate_sales_profit_analysis.short_description = "Generate Sales & Profit Analysis"

    def generate_html_report(self, request, queryset):
        sales = queryset
        context = {'sales': sales, 'date': datetime.now()}
        html = render_to_string('admin/sale_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="sale_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'

    def generate_customer_ledger(self, request, queryset):
        total_outstanding = queryset.aggregate(
            total_outstanding=ExpressionWrapper(
            Sum('saleitem__total_amt') - Sum('paid'),
            output_field=DecimalField()
            )
            )['total_outstanding'] or 0
        context = {'sales': queryset, 'date': datetime.now(), 'total_outstanding': total_outstanding}
        html = render_to_string('admin/customer_ledger_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="customer_ledger_report.html"'
        return response
    generate_customer_ledger.short_description = "Generate Customer Ledger Report"

    def view_invoice(self, obj):
        url = reverse('admin:generate_invoice', args=[obj.pk])
        return format_html(f'<a href="{url}" target="_blank">View Invoice</a>')
    view_invoice.short_description = 'Invoice'

    def get_customer_group(self, obj):
        return obj.customer.group.name if obj.customer and obj.customer.group else None
    get_customer_group.short_description = 'Customer Group'

    def save_model(self, request, obj, form, change):
        if not obj.created_by:  
            obj.created_by = request.user 
        if not obj.warehouse:
            default_warehouse = Warehouse.objects.first()
            if default_warehouse:
                obj.warehouse = default_warehouse
            else:
                self.message_user(request, "کوئی ویئرہاؤس موجود نہیں۔ براہ کرم پہلے ایک بنائیں۔", level=messages.ERROR)
                return
        super().save_model(request, obj, form, change)
    
    def generate_sale_pdf(self, request, queryset):
        """Generate the Sale PDF report"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Sale Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Date', 'Bill No', 'Customer', 'Group', 'Total', 'Discount', 'Paid', 'Profit']]
        
        total_amount = Decimal('0.0')
        total_discount = Decimal('0.0')
        total_paid = Decimal('0.0')
        total_profit = Decimal('0.0')
        
        for sale in queryset:
            total_amt = sale.total_without_discount()
            table_data.append([
                sale.sale_date.strftime('%d-%m-%Y'),
                sale.bill_no,
                sale.customer.name,
                sale.customer.group.name if sale.customer.group else '-',
                f"{total_amt:,.2f}",
                f"{sale.discount_value:,.2f}",
                f"{sale.paid:,.2f}",
                f"{sale.total_profit():,.2f}"
            ])
            total_amount += total_amt
            total_discount += sale.discount_value
            total_paid += sale.paid
            total_profit += sale.total_profit()
        
        table_data.append(['', '', '', 'TOTAL:', f"{total_amount:,.2f}", f"{total_discount:,.2f}", f"{total_paid:,.2f}", f"{total_profit:,.2f}"])
        
        table = Table(table_data, repeatRows=1, colWidths=[1*inch, 1*inch, 1.5*inch, 1*inch, 1*inch, 0.9*inch, 0.9*inch, 0.9*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
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
        response['Content-Disposition'] = 'attachment; filename="sale_report.pdf"'
        return response
    generate_sale_pdf.short_description = 'Generate PDF Report'

    # ============================================
    # WHATSAPP - TEXT INVOICE
    # ============================================
    def send_whatsapp_invoice(self, request, queryset):
        """Send the TEXT invoice of the selected sales on WhatsApp"""
        from ..whatsapp_utils import WhatsAppSender
        
        count = 0
        links = []
        for sale in queryset:
            if sale.customer.contact_number:
                result = WhatsAppSender.send_invoice(
                    sale.customer.contact_number,
                    sale.bill_no,
                    sale.total_amount()
                )
                if result.get('success'):
                    count += 1
                    links.append({
                        'bill': sale.bill_no,
                        'customer': sale.customer.name,
                        'url': result['url']
                    })
        
        if count > 0:
            msg = f"✅ {count} WhatsApp links generated!<br><br>"
            for link in links[:5]:
                msg += f"📋 {link['bill']} - {link['customer']}<br>"
            if len(links) > 5:
                msg += f"... and {len(links)-5} more<br>"
            if links:
                msg += f"<br><a href='{links[0]['url']}' target='_blank' style='background:#25D366; color:white; padding:8px 15px; border-radius:5px; text-decoration:none;'>📱 Send First Invoice</a>"
            
            self.message_user(request, format_html(msg))
        else:
            self.message_user(request, "❌ Selected customers don't have phone numbers!", level=messages.WARNING)

    send_whatsapp_invoice.short_description = "📱 Send TEXT Invoice on WhatsApp"

    # ============================================
    # WHATSAPP - PDF INVOICE
    # ============================================
    def send_pdf_invoice_whatsapp(self, request, queryset):
        """Send the PDF invoice of the selected sales on WhatsApp"""
        from ..whatsapp_utils import WhatsAppSender
        
        count = 0
        links = []
        for sale in queryset:
            if sale.customer.contact_number:
                result = WhatsAppSender.send_pdf_invoice_link(sale)
                if result.get('success'):
                    count += 1
                    links.append({
                        'bill': sale.bill_no,
                        'customer': sale.customer.name,
                        'url': result['url'],
                        'filepath': result.get('filepath', '')
                    })
        
        if count > 0:
            msg = f"✅ {count} PDF invoices generated!<br><br>"
            for link in links[:5]:
                msg += f"📋 {link['bill']} - {link['customer']}<br>"
            if links:
                msg += f"<br><a href='{links[0]['url']}' target='_blank' style='background:#25D366; color:white; padding:8px 15px; border-radius:5px; text-decoration:none;'>📱 Send First PDF Invoice</a>"
            self.message_user(request, format_html(msg))
        else:
            self.message_user(request, "❌ Selected customers don't have phone numbers!", level=messages.WARNING)

    send_pdf_invoice_whatsapp.short_description = "📄 Send PDF Invoice on WhatsApp"

    # ============================================
    # WHATSAPP - PAYMENT REMINDERS
    # ============================================
    def send_payment_reminders(self, request, queryset):
        """Send a reminder to outstanding customers"""
        from ..whatsapp_utils import WhatsAppBulkSender
        
        links = WhatsAppBulkSender.generate_reminder_links()
        
        if links:
            msg = f"✅ {len(links)} payment reminder links generated!<br><br>"
            msg += f"<a href='/admin/whatsapp/reminders/' style='background:#25D366; color:white; padding:8px 15px; border-radius:5px; text-decoration:none;'>📱 View All Reminders & Send</a>"
            self.message_user(request, format_html(msg))
        else:
            self.message_user(request, "🎉 All payments clear! No reminders needed.")

    send_payment_reminders.short_description = "💰 Send Payment Reminders"


# ============================================
# SALE RETURN ADMIN
# ============================================
class SaleRetrnAdmin(admin.ModelAdmin):
    inlines = [SaleRetrnItemInline]
    list_display = ('sale_return_date','bill_no', 'sale', 'customer', 'created_by', 'return_reason')
    change_list_template = "admin/button.html"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:  
            obj.created_by = request.user  
        super().save_model(request, obj, form, change)


class SaleRetrnItemAdmin(admin.ModelAdmin):
    list_display = ('sale_return', 'product', 'qty', 'price', 'total_amt')
    change_list_template = "admin/button.html"

    def has_add_permission(self, request):
        return False


# ============================================
# SALE QUOTATION ITEM INLINE
# ============================================
class SaleQuotationItemInline(admin.TabularInline):
    model = SaleQuotationItem
    fields = ('product', 'qty', 'price', 'total_amt')
    readonly_fields = ('total_amt',)
    extra = 10


# ============================================
# SALE QUOTATION ADMIN
# ============================================
@admin.register(SaleQuotation, site=admin.site)
class SaleQuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_no', 'quotation_date', 'customer', 'customer_po_number',
                    'valid_until', 'status', 'formatted_total', 'converted_to_order')
    list_filter = ('status', 'quotation_date', 'customer__group')
    search_fields = ('quotation_no', 'customer__name')
    inlines = [SaleQuotationItemInline]
    change_list_template = "admin/button.html"
    actions = ['convert_to_sale_order', 'generate_quotation_pdf']
    
    readonly_fields = ('quotation_no', 'created_at', 'updated_at', 'converted_to_order', 'created_by')
    
    fieldsets = (
        ('Quotation Information', {
            'fields': ('quotation_no', 'customer', 'customer_po_number', 'warehouse', 
                       'quotation_date', 'valid_until', 'status')
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
    
    def convert_to_sale_order(self, request, queryset):
        """Convert accepted quotations to Sale Order"""
        count = 0
        for quote in queryset.filter(status__in=['accepted'], converted_to_order__isnull=True):
            try:
                with transaction.atomic():
                    order = SaleOrder.objects.create(
                        customer=quote.customer,
                        warehouse=quote.warehouse,
                        status='confirmed',
                        discount_value=quote.discount_value,
                        customer_po_number=quote.customer_po_number,
                        notes=f"Converted from {quote.quotation_no}",
                        created_by=request.user
                    )
                    for item in quote.items.all():
                        SaleOrderItem.objects.create(
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
            self.message_user(request, f"✅ {count} quotations converted to Sale Orders!")
    convert_to_sale_order.short_description = "🔄 Convert to Sale Order"
    
    def generate_quotation_pdf(self, request, queryset):
        """Generate PDF for quotations"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        for quote in queryset:
            story.append(Paragraph(f"QUOTATION - {quote.quotation_no}", styles['Heading1']))
            story.append(Paragraph(f"Customer: {quote.customer.name}", styles['Normal']))
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
    generate_quotation_pdf.short_description = "📄 Generate Quotation PDF"


@admin.register(SalesTarget, site=admin.site)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_type', 'target_amount', 'start_date', 'end_date', 
                    'current_progress_display', 'achieved_display', 'is_active', 'status_badge')
    list_filter = ('target_type', 'is_active', 'start_date')
    search_fields = ('salesman__username', 'product__name')
    list_editable = ('is_active',)  # ✅ This is correct now because is_active is in list_display
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('target_type', 'target_amount', 'start_date', 'end_date')
        }),
        ('Target Specific', {
            'fields': ('salesman', 'product'),
            'classes': ('collapse',)
        }),
        ('Bonus Settings', {
            'fields': ('bonus_percentage', 'bonus_amount'),
            'description': 'Set bonus percentage or fixed amount for achieving target'
        }),
        ('Status', {
            'fields': ('is_active', 'created_by')
        }),
    )
    
    def current_progress_display(self, obj):
        progress = obj.current_progress()
        if progress >= 100:
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ {}%</span>', round(progress, 1))
        elif progress >= 80:
            return format_html('<span style="color: #ff9800; font-weight: bold;">🟡 {}%</span>', round(progress, 1))
        else:
            return format_html('<span style="color: #dc3545; font-weight: bold;">🔴 {}%</span>', round(progress, 1))
    current_progress_display.short_description = 'Progress'
    
    def achieved_display(self, obj):
        achieved = obj.achieved_amount()
        target = obj.target_amount
        return format_html('<strong>Rs. {:,}</strong> / Rs. {:,}', achieved, target)
    achieved_display.short_description = 'Achieved / Target'
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 12px;">Active</span>')
        return format_html('<span style="background: #6c757d; color: white; padding: 2px 8px; border-radius: 12px;">Inactive</span>')
    status_badge.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['send_target_report']
    
    def send_target_report(self, request, queryset):
        """Send target report via WhatsApp"""
        from ..whatsapp_utils import WhatsAppSender
        
        count = 0
        for target in queryset:
            if target.salesman and hasattr(target.salesman, 'profile') and target.salesman.profile.phone:
                message = f"🎯 *TARGET REPORT*\n\n"
                message += f"Target: Rs. {target.target_amount:,.0f}\n"
                message += f"Achieved: Rs. {target.achieved_amount():,.0f}\n"
                message += f"Progress: {target.current_progress():.0f}%\n"
                message += f"Days Left: {target.days_remaining()}\n"
                message += f"Daily Needed: Rs. {target.daily_needed():,.0f}"
                
                # WhatsAppSender.send_message(target.salesman.profile.phone, message)
                count += 1
        
        self.message_user(request, f"Report sent to {count} salesmen")
    send_target_report.short_description = "📱 Send Target Report via WhatsApp"


class SaleRangeReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'from_date', 'to_date', 'report_type', 'generated_at')
    list_filter = ('report_type',)
    search_fields = ('name',)
    readonly_fields = ('generated_at', 'generated_by')
    
    def save_model(self, request, obj, form, change):
        if not obj.generated_by:
            obj.generated_by = request.user
        super().save_model(request, obj, form, change)
