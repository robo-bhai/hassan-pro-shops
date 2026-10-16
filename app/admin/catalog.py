"""Admin: catalog models."""
from import_export.admin import ImportExportModelAdmin
from ..models import *
import io
from django.contrib import admin
from django.db.models import Sum
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
from django.db import models
from decimal import Decimal
from django.shortcuts import redirect
from ..barcode_utils import generate_barcode_image, generate_multiple_labels
from ..models import Expense


@admin.register(Warehouse, site=admin.site)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'description')
    search_fields = ('name',)
    list_filter = ('location',)
    change_list_template = "admin/button.html"


@admin.register(WarehouseTransfer, site=admin.site)
class WarehouseTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_date', 'product', 'from_warehouse', 'to_warehouse', 'qty', 'created_by')
    list_filter = ('from_warehouse', 'to_warehouse', 'transfer_date')
    search_fields = ('product__name',)
    change_list_template = "admin/button.html"
    actions = ['generate_transfer_report', 'generate_transfer_pdf']

    def generate_transfer_report(self, request, queryset):
        """Generate HTML report for selected transfers."""
        context = {
            'transfers': queryset,
            'date': datetime.now()
        }
        html = render_to_string('admin/warehouse_transfer_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="warehouse_transfer_report.html"'
        return response
    generate_transfer_report.short_description = "Generate Transfer Report (HTML)"
    
    def generate_transfer_pdf(self, request, queryset):
        """Generate PDF report for warehouse transfers."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Warehouse Transfer Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Date', 'Product', 'From Warehouse', 'To Warehouse', 'Quantity', 'Transferred By']]
        
        for transfer in queryset:
            table_data.append([
                transfer.transfer_date.strftime('%d-%m-%Y'),
                transfer.product.name,
                transfer.from_warehouse.name,
                transfer.to_warehouse.name,
                f"{transfer.qty:,.2f}",
                transfer.created_by.username if transfer.created_by else '-'
            ])
        
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="warehouse_transfer_report.pdf"'
        return response
    generate_transfer_pdf.short_description = "Generate Transfer Report (PDF)"


@admin.register(Product, site=admin.site)

class ProductAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ('serial_no', 'name', 'barcode')
    search_help_text = "Search by Serial No, Product Name, Barcode"
    list_display = ('serial_no', 'name', 'barcode', 'barcode_preview', 'use_custom_barcode', 
                    'description', 'unit', 'location', 'price', 'used', 'brand', 'category', 
                    'types', 'low_stock_threshold')
    ordering = ('serial_no',)
    change_list_template = "admin/button.html"
    actions = ['generate_barcodes', 'print_barcode_labels', 'print_selected_labels', 'print_single_labels', 'scan_supplier_barcode']
    
    # Fieldsets - price hataya gaya kyunke editable=False hai
    fieldsets = (
        ('Basic Information', {
            'fields': ('serial_no', 'name', 'description', 'used')
        }),
        ('Barcode Information', {
            'fields': ('use_custom_barcode', 'barcode'),
            'description': 'Check "Use Custom/Supplier Barcode" to manually enter supplier barcode instead of auto-generating.'
        }),
        ('Categorization', {
            'fields': ('unit', 'brand', 'category', 'types', 'location')
        }),
        ('Stock Settings', {
            'fields': ('low_stock_threshold',),
            'description': 'Set minimum stock level for alerts.'
        }),
    )
    
    # Price ko readonly_fields mein add karein
    readonly_fields = ('price',)
    
    def get_readonly_fields(self, request, obj=None):
        """Make barcode readonly if use_custom_barcode is False"""
        readonly = list(self.readonly_fields)
        if obj and not obj.use_custom_barcode:
            readonly.append('barcode')
        return readonly
    
    def changelist_view(self, request, extra_context=None):
        """Add has_barcode_action flag to context"""
        extra_context = extra_context or {}
        extra_context['has_barcode_action'] = True
        return super().changelist_view(request, extra_context=extra_context)
    
    def barcode_preview(self, obj):
        """Show barcode image in admin list"""
        if obj.barcode:
            try:
                barcode_img = generate_barcode_image(obj.barcode)
                if barcode_img:
                    return format_html('<img src="{}" width="150" height="50">', barcode_img)
                return obj.barcode
            except Exception as e:
                return obj.barcode
        return "No Barcode"
    barcode_preview.short_description = "Barcode Preview"
    
    def generate_barcodes(self, request, queryset):
        """Generate barcodes for selected products that don't have one AND don't use custom barcode"""
        count = 0
        for product in queryset.filter(barcode__isnull=True, use_custom_barcode=False):
            product.save()
            count += 1
        self.message_user(request, f"Generated barcodes for {count} products.")
    generate_barcodes.short_description = "🔄 Generate Barcodes for Selected"
    
    def scan_supplier_barcode(self, request, queryset):
        """Action to open barcode scanner for supplier barcode"""
        selected_ids = queryset.values_list('id', flat=True)
        ids_str = ','.join(map(str, selected_ids))
        return redirect(f"/admin/app/product/supplier-barcode/?ids={ids_str}")
    scan_supplier_barcode.short_description = "🏷️ Scan/Set Supplier Barcode"
    
    def print_barcode_labels(self, request, queryset):
        """Generate PDF with barcode labels for selected products"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.3*inch, bottomMargin=0.3*inch)
        styles = getSampleStyleSheet()
        story = []
        
        story.append(Paragraph("Barcode Labels", styles['Heading1']))
        story.append(Spacer(1, 0.2*inch))
        
        table_data = []
        row = []
        
        for i, product in enumerate(queryset):
            if not product.barcode:
                product.save()
            
            barcode_img_data = generate_barcode_image(product.barcode)
            
            if not barcode_img_data:
                barcode_img_data = ""
            
            cell_content = Paragraph(
                f"<b>{product.name[:20]}</b><br/>"
                f"<img src='{barcode_img_data}' width='120' height='40'/><br/>"
                f"{product.barcode}<br/>"
                f"Rs. {product.price:,.2f}",
                styles['Normal']
            )
            
            row.append(cell_content)
            
            if len(row) == 3 or i == queryset.count() - 1:
                while len(row) < 3:
                    row.append("")
                table_data.append(row)
                row = []
        
        if table_data:
            table = Table(table_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
            table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            
            story.append(table)
        
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="barcode_labels.pdf"'
        return response
    print_barcode_labels.short_description = "📄 Print Barcode Labels (PDF)"
    
    def print_selected_labels(self, request, queryset):
        """Print labels as PNG image sheet"""
        products_data = []
        for product in queryset:
            if not product.barcode:
                product.save()
            products_data.append({
                'barcode': product.barcode,
                'name': product.name,
                'price': str(product.price)
            })
        
        buffer = generate_multiple_labels(products_data)
        
        response = HttpResponse(buffer, content_type='image/png')
        response['Content-Disposition'] = 'attachment; filename="barcode_labels_sheet.png"'
        return response
    print_selected_labels.short_description = "🖼️ Print Labels Sheet (PNG)"
    
    def print_single_labels(self, request, queryset):
        """Print individual labels one per page"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        for product in queryset:
            if not product.barcode:
                product.save()
            
            barcode_img = generate_barcode_image(product.barcode)
            
            story.append(Paragraph(f"<b>{product.name}</b>", styles['Heading2']))
            if barcode_img:
                story.append(Paragraph(f"<img src='{barcode_img}' width='200' height='60'/>", styles['Normal']))
            story.append(Paragraph(f"Barcode: {product.barcode}", styles['Normal']))
            story.append(Paragraph(f"Price: Rs. {product.price:,.2f}", styles['Normal']))
            story.append(Spacer(1, 0.5*inch))
            story.append(Paragraph("- - - - - - - - - - - - - - - - - - - -", styles['Normal']))
            story.append(Spacer(1, 0.3*inch))
        
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="single_barcode_labels.pdf"'
        return response
    print_single_labels.short_description = "🏷️ Print Single Labels (One per page)"


# Product Alias Admin
@admin.register(ProductAlias, site=admin.site)
class ProductAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'product', 'created_by', 'created_at')
    list_filter = ('created_by',)
    search_fields = ('alias', 'product__name')
    autocomplete_fields = ['product', 'created_by']
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Alias Information', {
            'fields': ('product', 'alias', 'created_by')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ============================================
# INVENTORY ADMIN
# ============================================
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'get_description', 'get_unit', 'get_location', 'get_used', 'get_brand', 
                    'get_category', 'get_types', 'warehouse', 'stock', 'stock_value_display', 'low_stock_alert')
    ordering = ('product',)
    change_list_template = "admin/button.html"
    actions = ['send_bulk_low_stock_alerts', 'generate_html_report', 'generate_inventory_pdf']
    search_fields = (
        'product__name', 'warehouse__name', 'product__unit__name', 'product__location__name',
        'product__used', 'product__brand__name', 'product__category__name', 'product__types__name',
        'product__description',
    )
    search_help_text = 'Search by Product Name, Warehouse, Unit, Location, Used, Brand, Category, Type'

    def has_add_permission(self, request):
        return False

    def send_bulk_low_stock_alerts(self, request, queryset):
        Inventory.send_bulk_low_stock_alert()
        self.message_user(request, "Low stock alert email sent successfully.")
    send_bulk_low_stock_alerts.short_description = "Send Low Stock Alert"
    
    def stock_value_display(self, obj):
        stock_value = obj.stock_value()
        return f"{stock_value:,.2f} PKR"
    stock_value_display.short_description = 'Stock Value'

    def low_stock_alert(self, obj):
        if obj.check_low_stock():
            return format_html('<span style="color: red;">Low Stock</span>')
        return "OK"
    low_stock_alert.short_description = "Stock Alert"

    def get_description(self, obj):
        return obj.product.description if obj.product.description else "N/A"
    get_description.short_description = "Description"
    
    def get_unit(self, obj):
        return obj.product.unit.name if obj.product.unit else "N/A"
    get_unit.short_description = "Unit"

    def get_location(self, obj):
        return obj.product.location.name if obj.product.location else "N/A"
    get_location.short_description = "Location"

    def get_used(self, obj):
        return obj.product.used if obj.product.used else "N/A"
    get_used.short_description = "Used"

    def get_brand(self, obj):
        return obj.product.brand.name if obj.product.brand else "N/A"
    get_brand.short_description = "Brand"

    def get_category(self, obj):
        return obj.product.category.name if obj.product.category else "N/A"
    get_category.short_description = "Category"

    def get_types(self, obj):
        return obj.product.types.name if obj.product.types else "N/A"
    get_types.short_description = "Type"

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        qs = self.get_queryset(request)
        total_stock_value = sum(item.stock_value() for item in qs) or Decimal('0.0')
        summary_data = {'total_stock_value': f"{total_stock_value:,.2f} PKR"}
        if hasattr(response, 'context_data'):
            response.context_data['summary_data'] = summary_data
        return response

    def generate_html_report(self, request, queryset):
        inventorys = queryset
        context = {'inventorys': inventorys, 'date': datetime.now()}
        html = render_to_string('admin/inventory_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="inventory_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_inventory_pdf(self, request, queryset):
        """Inventory stock ka PDF report"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        story.append(Paragraph(company_name, title_style))
        story.append(Paragraph("Inventory Stock Report", title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        table_data = [['Product', 'Warehouse', 'Stock', 'Price', 'Stock Value', 'Status']]
        
        total_value = Decimal('0.0')
        
        for idx, inv in enumerate(queryset, start=1):
            stock_value = inv.stock_value()
            status = "LOW STOCK!" if inv.check_low_stock() else "OK"
            table_data.append([
                inv.product.name[:30],
                inv.warehouse.name,
                f"{inv.stock:,.2f}",
                f"{inv.product.price:,.2f}",
                f"{stock_value:,.2f}",
                status
            ])
            total_value += Decimal(str(stock_value))
        
        table_data.append(['', '', '', 'TOTAL VALUE:', f"{total_value:,.2f}", ''])
        
        table = Table(table_data, repeatRows=1, colWidths=[2*inch, 1.2*inch, 0.8*inch, 1*inch, 1.2*inch, 1*inch])
        
        # Pehle base style apply karein
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (4, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]
        
        # Low stock rows ko highlight karein
        row_idx = 1
        for inv in queryset:
            if inv.check_low_stock():
                table_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.lightpink))
                table_style.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.red))
            row_idx += 1
        
        table.setStyle(TableStyle(table_style))
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="inventory_report.pdf"'
        return response
    generate_inventory_pdf.short_description = 'Generate PDF Report'


# ============================================
# STOCK BATCH ADMIN
# ============================================
# ============================================
# STOCK BATCH ADMIN
# ============================================
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'qty', 'price', 'selling_price', 
                    'profit_display', 'profit_percent_display', 'remaining_qty', 
                    'batch_value_display', 'selling_value_display',
                    'get_purchase_bill_no', 'get_sale_bill_no')
    list_editable = ('selling_price',)
    search_fields = (
        'product__name', 'purchase_item__purchase__bill_no', 
        'sale_items__sale__bill_no', 'warehouse__name',
    )
    search_help_text = "Search by Product Name, Warehouse, Purchase Bill No, or Sale Bill No"
    list_filter = ('warehouse',)
    change_list_template = "admin/button.html"
    
    fields = ('product', 'warehouse', 'qty', 'price', 'selling_price', 'remaining_qty', 'purchase_item')
    readonly_fields = ('product', 'warehouse', 'qty', 'price', 'remaining_qty', 'purchase_item')

    def has_add_permission(self, request):
        return False

    # ============================================
    # DISPLAY FIELDS
    # ============================================
    def batch_value_display(self, obj):
        """Purchase price pe total value"""
        return f"Rs. {Decimal(obj.remaining_qty) * obj.price:,.2f}"
    batch_value_display.short_description = '📦 Stock Value'

    def selling_value_display(self, obj):
        """Selling price pe total value"""
        val = obj.selling_value()
        if obj.selling_price > 0:
            return f"Rs. {val:,.2f}"
        return "-"
    selling_value_display.short_description = '💰 Selling Value'

    def profit_display(self, obj):
        """Profit per unit with color"""
        profit = obj.profit_per_unit()
        if profit > 0:
            return format_html(
                '<span style="color:#28a745;font-weight:bold;">+Rs. {}</span>', 
                round(profit, 2)
            )
        elif obj.selling_price > 0 and profit == 0:
            return format_html('<span style="color:#ff9800;">Rs. 0 (No Profit)</span>')
        return "-"
    profit_display.short_description = '💰 Profit/Unit'
    
    def profit_percent_display(self, obj):
        """Profit margin percentage"""
        percent = obj.profit_margin_percent()
        if percent > 0:
            return format_html(
                '<span style="color:#28a745;font-weight:bold;">{}% ↑</span>', 
                round(percent, 1)
            )
        elif obj.selling_price > 0 and percent == 0:
            return format_html('<span style="color:#ff9800;">0%</span>')
        return "-"
    profit_percent_display.short_description = '📈 Margin %'

    def get_purchase_bill_no(self, obj):
        if obj.purchase_item and obj.purchase_item.purchase:
            return obj.purchase_item.purchase.bill_no if obj.purchase_item.purchase.bill_no else "Waiting for Bill"
        return "N/A"
    get_purchase_bill_no.short_description = "Purchase Bill No"

    def get_sale_bill_no(self, obj):
        if not obj.sale_items.exists():
            return "Not Sold Yet"
        bill_nos = set(
            sale_item.sale.bill_no 
            for sale_item in obj.sale_items.all() 
            if sale_item.sale and sale_item.sale.bill_no
        )
        return ", ".join(bill_nos) if bill_nos else "N/A"
    get_sale_bill_no.short_description = "Sale Bill No"


# ============================================
# MONTHLY CLOSING ADMIN
# ============================================
class MonthlyClosingAdmin(admin.ModelAdmin):
    list_display = ['month', 'previous_balance_display','total_purchase_balance_display',
                    'total_sale_balance_display', 'closing_balance_display',
                    'total_sale_profit_display', 'total_purchase_return_display',
                    'total_sale_return_display', 'net_profit_margin_display', 
                    'return_on_investment_display', 'locked']
    actions = ['lock_month', 'unlock_month', 'generate_html_report', 'generate_pnl', 
               'generate_cash_flow', 'generate_saving', 'generate_closing_pdf']
    ordering = ('-month',)
    change_list_template = "admin/button.html"

    def lock_month(self, request, queryset):
        queryset.update(locked=True)
        self.message_user(request, "Selected months have been locked.")
    lock_month.short_description = "Lock selected months"

    def unlock_month(self, request, queryset):
        queryset.update(locked=False)
        self.message_user(request, "Selected months have been unlocked.")
    unlock_month.short_description = "Unlock selected months"

    def total_purchase_return_display(self, obj):
        return f'{obj.total_purchase_return():,.2f}'
    total_purchase_return_display.short_description = 'Purchase Returns'

    def total_sale_return_display(self, obj):
        return f'{obj.total_sale_return():,.2f}'
    total_sale_return_display.short_description = 'Sale Returns'

    def total_purchase_balance_display(self, obj):
        return f'{obj.total_purchase_balance():,.2f}'
    total_purchase_balance_display.short_description = 'Total Purchase'

    def total_sale_profit_display(self, obj):
        return f'{obj.total_sale_profit():,.2f}'
    total_sale_profit_display.short_description = 'Total Profit'

    def total_sale_balance_display(self, obj):
        return f'{obj.total_sale_balance():,.2f}'
    total_sale_balance_display.short_description = 'Total Sale (COGS)'

    def closing_balance_display(self, obj):
        return f'{obj.closing_balance():,.2f}'
    closing_balance_display.short_description = 'Closing Balance'
    
    def previous_balance_display(self, obj):
        return f"{obj.get_previous_month_closing():,.2f}"
    previous_balance_display.short_description = "Previous Balance"

    def net_profit_margin_display(self, obj):
        return f"{obj.net_profit_margin():.2f}%"
    net_profit_margin_display.short_description = "Net Profit Margin"

    def return_on_investment_display(self, obj):
        return f"{obj.return_on_investment():.2f}%"
    return_on_investment_display.short_description = "ROI"

    def generate_pnl(self, request, queryset):
        for closing in queryset:
            income = closing.total_sale_profit()
            expenses = (Expense.objects.filter(expense_date__month=closing.month.month).aggregate(Sum('amount'))['amount__sum'] or 0)
            profit = income - expenses
            context = {'income': income, 'expenses': expenses, 'profit': profit, 'month': closing.month}
            html = render_to_string('admin/pnl_report.html', context)
            response = HttpResponse(html, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="pnl_{closing.month}.html"'
            return response
    generate_pnl.short_description = "Generate Profit & Loss Statement"

    def generate_saving(self, request, queryset):
        for closing in queryset:
            savings = (Saving.objects.filter(date__month=closing.month.month).aggregate(Sum('amount'))['amount__sum'] or 0)
            context = {'savings': savings, 'month': closing.month}
            html = render_to_string('admin/saving_report.html', context)
            response = HttpResponse(html, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="saving_{closing.month}.html"'
            return response
    generate_saving.short_description = "Generate Saving"

    def generate_cash_flow(self, request, queryset):
        for closing in queryset:
            cash_in = Sale.objects.filter(sale_date__month=closing.month.month).aggregate(Sum('paid'))['paid__sum'] or 0
            cash_out = Purchase.objects.filter(pur_date__month=closing.month.month).aggregate(Sum('paid'))['paid__sum'] or 0
            net_cash = cash_in - cash_out
            context = {'cash_in': cash_in, 'cash_out': cash_out, 'net_cash': net_cash, 'month': closing.month}
            html = render_to_string('admin/cash_flow_report.html', context)
            response = HttpResponse(html, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="cash_flow_{closing.month}.html"'
            return response
    generate_cash_flow.short_description = "Generate Cash Flow Statement"

    def generate_html_report(self, request, queryset):
        MonthlyClosings = queryset
        context = {'MonthlyClosings': MonthlyClosings, 'date': datetime.now()}
        html = render_to_string('admin/MonthlyClosing_report.html', context)
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="MonthlyClosing_report.html"'
        return response
    generate_html_report.short_description = 'Generate HTML Report'
    
    def generate_closing_pdf(self, request, queryset):
        """Monthly closing ka PDF report"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        
        for closing in queryset:
            story.append(Paragraph(company_name, title_style))
            story.append(Paragraph(f"Monthly Closing Report - {closing.month.strftime('%B %Y')}", title_style))
            story.append(Spacer(1, 0.2*inch))
            
            data = [
                ['Description', 'Amount (PKR)'],
                ['Previous Balance', f"{closing.previous_balance:,.2f}"],
                ['Total Purchases', f"{closing.total_purchase_balance():,.2f}"],
                ['Purchase Returns', f"{closing.total_purchase_return():,.2f}"],
                ['Total Sales (COGS)', f"{closing.total_sale_balance():,.2f}"],
                ['Sale Returns', f"{closing.total_sale_return():,.2f}"],
                ['Total Profit', f"{closing.total_sale_profit():,.2f}"],
                ['Closing Balance', f"{closing.closing_balance():,.2f}"],
                ['Net Profit Margin', f"{closing.net_profit_margin():.2f}%"],
                ['Return on Investment (ROI)', f"{closing.return_on_investment():.2f}%"],
            ]
            
            table = Table(data, colWidths=[3*inch, 2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('FONTNAME', (0, -2), (0, -1), 'Helvetica-Bold'),
            ]))
            
            story.append(table)
            story.append(Spacer(1, 0.5*inch))
        
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="monthly_closing.pdf"'
        return response
    generate_closing_pdf.short_description = 'Generate PDF Report'


# ============================================
# STOCK ADJUSTMENT ADMIN
# ============================================
@admin.register(StockAdjustmentItem, site=admin.site)
class StockAdjustmentItemAdmin(admin.ModelAdmin):
    list_display = ('adjustment', 'product', 'qty', 'price', 'total_value')
    search_fields = ('product__name',)
    readonly_fields = ('total_value',)
    change_list_template = "admin/button.html"

    def has_add_permission(self, request):
        return False


class StockAdjustmentItemInline(admin.TabularInline):
    model = StockAdjustmentItem
    extra = 1
    fields = ('product', 'qty', 'price', 'total_value')
    readonly_fields = ('total_value',)


@admin.register(StockAdjustment, site=admin.site)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_type', 'reason', 'adjustment_date', 'created_by')
    change_list_template = "admin/button.html"
    search_fields = ('reason', 'created_by__username')
    inlines = [StockAdjustmentItemInline]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class StockAuditItemInline(admin.TabularInline):
    model = StockAuditItem
    fields = ('product', 'system_qty', 'physical_qty', 'variance_display', 'variance_value_display', 'unit', 'adjusted', 'notes')
    readonly_fields = ('system_qty', 'variance_display', 'variance_value_display', 'unit')
    extra = 0
    
    def variance_display(self, obj):
        if obj and obj.pk:
            return obj.variance_display()
        return "-"
    variance_display.short_description = "Variance"
    
    def variance_value_display(self, obj):
        if obj and obj.pk:
            return obj.variance_value_display()
        return "-"
    variance_value_display.short_description = "Variance Value"


@admin.register(StockAudit, site=admin.site)
class StockAuditAdmin(admin.ModelAdmin):
    list_display = ('audit_no', 'audit_date', 'warehouse', 'status', 'total_items_display', 
                    'variance_items_count', 'total_variance_value_display', 'print_audit')
    list_filter = ('status', 'audit_date', 'warehouse')
    search_fields = ('audit_no', 'warehouse__name')
    inlines = [StockAuditItemInline]
    change_list_template = "admin/button.html"
    actions = ['generate_audit_sheet', 'mark_completed', 'adjust_stock', 'generate_audit_pdf']
    
    fieldsets = (
        ('Audit Information', {
            'fields': ('audit_no', 'warehouse', 'audit_date', 'status')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    readonly_fields = ('audit_no', 'total_variance_value')
    
    def total_items_display(self, obj):
        return obj.total_items()
    total_items_display.short_description = "Items"
    
    def variance_items_count(self, obj):
        count = obj.items.filter(physical_qty__isnull=False).filter(
            models.Q(variance__gt=0) | models.Q(variance__lt=0)
        ).count()
        if count > 0:
            return format_html('<span style="color: red;">⚠ {} variance(s)</span>', count)
        return "0"
    variance_items_count.short_description = "Variances"
    
    def total_variance_value_display(self, obj):
        val = obj.total_variance_value
        if val < 0:
            return format_html('<span style="color: red;">Rs. ({})</span>', str(round(abs(val), 2)))
        elif val > 0:
            return format_html('<span style="color: green;">Rs. {}</span>', str(round(val, 2)))
        return "Rs. 0.00"
    total_variance_value_display.short_description = "Net Variance"
    
    def print_audit(self, obj):
        url = reverse('admin:generate_audit_pdf', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">📄 Print</a>', url)
    print_audit.short_description = "Print"
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if instance.pk is None:
                inventory = Inventory.objects.filter(
                    product=instance.product, 
                    warehouse=formset.instance.warehouse
                ).first()
                instance.system_qty = inventory.stock if inventory else 0
            instance.save()
        formset.save_m2m()
    
    def generate_audit_sheet(self, request, queryset):
        """Auto-populate audit with all warehouse products"""
        for audit in queryset.filter(status='draft'):
            inventories = Inventory.objects.filter(warehouse=audit.warehouse)
            for inv in inventories:
                if not StockAuditItem.objects.filter(audit=audit, product=inv.product).exists():
                    StockAuditItem.objects.create(
                        audit=audit,
                        product=inv.product,
                        system_qty=inv.stock,
                        unit=inv.product.unit.name if inv.product.unit else ''
                    )
            audit.status = 'in_progress'
            audit.save()
        self.message_user(request, f"✅ Audit sheets generated with products.")
    generate_audit_sheet.short_description = "📋 Generate Audit Sheet (Add All Products)"
    
    def mark_completed(self, request, queryset):
        """Mark audit as completed and calculate total variance"""
        for audit in queryset.filter(status='in_progress'):
            total_var = audit.items.aggregate(t=Sum('variance_value'))['t'] or Decimal('0.0')
            audit.total_variance_value = total_var
            audit.status = 'completed'
            audit.save()
        self.message_user(request, f"✅ Audits marked as completed.")
    mark_completed.short_description = "✅ Mark as Completed"
    
    def adjust_stock(self, request, queryset):
        """Adjust stock based on audit variance"""
        count = 0
        for audit in queryset.filter(status='completed'):
            with transaction.atomic():
                for item in audit.items.filter(physical_qty__isnull=False, adjusted=False):
                    if item.variance != 0:
                        adj_type = 'increase' if item.variance > 0 else 'decrease'
                        adjustment = StockAdjustment.objects.create(
                            adjustment_type=adj_type,
                            reason=f"Audit {audit.audit_no}: Variance for {item.product.name}",
                            created_by=request.user
                        )
                        StockAdjustmentItem.objects.create(
                            adjustment=adjustment,
                            product=item.product,
                            qty=abs(item.variance),
                            price=item.price
                        )
                        item.adjusted = True
                        item.save()
                        count += 1
        if count:
            self.message_user(request, f"✅ {count} variances adjusted. Stock updated!")
        else:
            self.message_user(request, "No variances to adjust.")
    adjust_stock.short_description = "🔄 Adjust Stock (Fix Variances)"
    
    def generate_audit_pdf(self, request, queryset):
        """Generate PDF for audit with brackets for negative values"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.3*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "Company Name"
        
        for audit in queryset:
            title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
            story.append(Paragraph(company_name, title_style))
            story.append(Paragraph("<b>STOCK AUDIT REPORT</b>", title_style))
            story.append(Spacer(1, 0.2*inch))
            
            details = [
                [Paragraph(f"<b>Audit No:</b> {audit.audit_no}"), 
                 Paragraph(f"<b>Date:</b> {audit.audit_date.strftime('%d-%m-%Y')}")],
                [Paragraph(f"<b>Warehouse:</b> {audit.warehouse.name}"), 
                 Paragraph(f"<b>Status:</b> {audit.get_status_display()}")],
            ]
            story.append(Table(details, colWidths=[3.5*inch, 3.5*inch]))
            story.append(Spacer(1, 0.2*inch))
            
            table_data = [['Product', 'System Qty', 'Physical Qty', 'Variance', 'Unit', 'Value']]
            total_var_value = Decimal('0.0')
            
            for item in audit.items.all():
                # Physical qty
                if item.physical_qty is not None:
                    physical = f"{item.physical_qty:,.0f}"
                else:
                    physical = '?'
                
                # ✅ Variance quantity with brackets for negative
                if item.physical_qty is not None:
                    if item.variance < 0:
                        var_str = f"({abs(item.variance):,.0f})"
                    elif item.variance > 0:
                        var_str = f"{item.variance:+,.0f}"
                    else:
                        var_str = "0"
                else:
                    var_str = '-'
                
                # ✅ Variance value with brackets for negative
                if item.physical_qty is not None:
                    if item.variance_value < 0:
                        val_str = f"Rs. ({abs(item.variance_value):,.2f})"
                    elif item.variance_value > 0:
                        val_str = f"Rs. {item.variance_value:,.2f}"
                    else:
                        val_str = "Rs. 0.00"
                else:
                    val_str = '-'
                
                table_data.append([
                    item.product.name[:25],
                    f"{item.system_qty:,.0f}",
                    physical,
                    var_str,
                    item.unit or '-',
                    val_str
                ])
                total_var_value += item.variance_value
            
            # ✅ Total row with brackets for negative
            if total_var_value < 0:
                total_str = f"Rs. ({abs(total_var_value):,.2f})"
            elif total_var_value > 0:
                total_str = f"Rs. {total_var_value:,.2f}"
            else:
                total_str = "Rs. 0.00"
            
            table_data.append(['', '', '', '', 'NET:', total_str])
            
            items_table = Table(table_data, repeatRows=1)
            items_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            story.append(items_table)
            
            story.append(Spacer(1, 0.5*inch))
            sign = [
                [Paragraph("<b>Counted by:</b> _________"), Paragraph("<b>Verified by:</b> _________")],
                [Paragraph("Date: _________"), Paragraph("Date: _________")],
            ]
            story.append(Table(sign, colWidths=[3.5*inch, 3.5*inch]))
            story.append(Paragraph("<br/><br/>", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')
    generate_audit_pdf.short_description = "📄 Generate Audit PDF"
