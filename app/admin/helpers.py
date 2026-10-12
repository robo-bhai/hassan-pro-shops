"""Shared helpers: default system settings (created after migrate), invoice PDF builder."""
from ..models import *
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from decimal import Decimal
from ..models import SystemSetting
import logging
from django.db.models.signals import post_migrate
from django.dispatch import receiver


# Create default settings after migration
def create_default_system_settings():
    defaults = [
        ('show_hr_module', 'true', 'Show/Hide HR Module (Employees, Attendance, Payroll, Leaves, Salary Slips)'),
        ('show_production_module', 'true', 'Show/Hide Production Module (Production Orders, BOM, Operations)'),
        ('show_installment_module', 'true', 'Show/Hide Installment Module (Installment Plans, EMI Payments)'),
        ('show_reports_module', 'true', 'Show/Hide Reports Module (All Reports)'),
        ('show_whatsapp_module', 'true', 'Show/Hide WhatsApp Module (Messages, Reminders)'),
        ('show_inventory_module', 'true', 'Show/Hide Inventory Module (Stock, Batches, Transfers)'),
        ('show_purchase_module', 'true', 'Show/Hide Purchase Module (Purchases, Purchase Orders, GRN)'),
        ('show_sales_module', 'true', 'Show/Hide Sales Module (Sales, Sale Orders, Challans)'),
        ('show_accounts_module', 'true', 'Show/Hide Accounts Module (Expenses, Savings, Debts)'),
        ('show_backup_module', 'true', 'Show/Hide Database Backup Module'),
    ]
    
    for key, value, desc in defaults:
        SystemSetting.objects.get_or_create(
            setting_key=key,
            defaults={'setting_value': value, 'description': desc}
        )


def generate_invoice_pdf(sale_obj):
    """
    Premium Professional Invoice PDF with Amount in Words
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch, mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io
    from datetime import datetime
    import os
    
    buffer = io.BytesIO()
    
    # Page Setup
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        topMargin=0.4*inch,
        bottomMargin=0.4*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Company Info
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "MY SUPER STORE"
    company_address = company.address if company else "Khanewal"
    company_phone = company.contact_number if company else "0300 0000000"
    company_email = company.email if company else "info@mysuperstore.com"
    company_tagline = company.tagline if company and company.tagline else "Quality Products, Best Service"
    
    # ============================================
    # CUSTOM STYLES
    # ============================================
    
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=3,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6c757d'),
        spaceAfter=3
    )
    
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#6c757d'),
        fontName='Helvetica'
    )
    
    value_style = ParagraphStyle(
        'Value',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#1a1a2e'),
        fontName='Helvetica-Bold'
    )
    
    # ============================================
    # HEADER SECTION
    # ============================================
    
    # Company Logo (storage se bytes parh kar lagate hain, URL ya path par depend nahi)
    try:
        if company and company.logo:
            from reportlab.lib.utils import ImageReader
            company.logo.open('rb')
            try:
                logo_bytes = company.logo.read()
            finally:
                company.logo.close()
            iw, ih = ImageReader(io.BytesIO(logo_bytes)).getSize()
            scale = min((2.2 * inch) / iw, (0.8 * inch) / ih)
            logo_img = Image(io.BytesIO(logo_bytes), width=iw * scale, height=ih * scale, mask='auto')
            logo_img.hAlign = 'CENTER'
            story.append(logo_img)
            story.append(Spacer(1, 0.05 * inch))
    except Exception as e:
        # Logo na lage to bhi invoice ban jaye
        logging.getLogger(__name__).warning("Invoice logo skipped: %s", e)
    
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(company_tagline, subtitle_style))
    story.append(Paragraph(f"{company_address} | Phone: {company_phone}", subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Decorative Line
    line_table = Table([['']], colWidths=[6.5*inch])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#667eea')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 0.1*inch))
    
    # ============================================
    # INVOICE TITLE
    # ============================================
    
    invoice_title_style = ParagraphStyle(
        'InvoiceTitle2',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )
    story.append(Paragraph("INVOICE", invoice_title_style))
    story.append(Spacer(1, 0.1*inch))
    
    # ============================================
    # INVOICE DETAILS (Two Column)
    # ============================================
    
    # Left Column
    left_data = [
        [Paragraph("<b>Invoice No:</b>", label_style), Paragraph(f"<b>{sale_obj.bill_no}</b>", value_style)],
        [Paragraph("<b>Invoice Date:</b>", label_style), Paragraph(sale_obj.sale_date.strftime('%d %B, %Y'), value_style)],
    ]
    
    # Right Column
    right_data = [
        [Paragraph("<b>Customer Name:</b>", label_style), Paragraph(sale_obj.customer.name, value_style)],
        [Paragraph("<b>Customer Code:</b>", label_style), Paragraph(sale_obj.customer.customer_code or 'N/A', value_style)],
    ]
    
    if sale_obj.customer.address:
        left_data.append([Paragraph("<b>Address:</b>", label_style), Paragraph(sale_obj.customer.address[:50], label_style)])
    
    left_table = Table(left_data, colWidths=[1.2*inch, 2.5*inch])
    right_table = Table(right_data, colWidths=[1.2*inch, 2.5*inch])
    
    left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    right_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    info_table = Table([[left_table, right_table]], colWidths=[4*inch, 3.5*inch])
    info_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.15*inch))
    
    # ============================================
    # ITEMS TABLE
    # ============================================
    
    table_data = [['#', 'Product', 'Qty', 'Unit', 'Unit Price', 'Total']]
    
    total_before_discount = Decimal('0.0')
    
    for idx, item in enumerate(sale_obj.saleitem_set.all(), 1):
        item_total = item.total_amt
        table_data.append([
            str(idx),
            item.product.name,
            f"{item.qty:,.2f}",
            item.product.unit.name if item.product.unit else '-',
            f"Rs. {item.price:,.2f}",
            f"Rs. {item_total:,.2f}"
        ])
        total_before_discount += item_total
    
    discount_value = sale_obj.discount_value
    total_amount = sale_obj.total_amount()
    paid_amount = sale_obj.paid
    outstanding = sale_obj.outstanding_balance()
    
    table_data.append(['', '', '', '', 'Subtotal:', f"Rs. {total_before_discount:,.2f}"])
    if discount_value > 0:
        table_data.append(['', '', '', '', 'Discount:', f"Rs. {discount_value:,.2f}"])
    table_data.append(['', '', '', '', 'Grand Total:', f"Rs. {total_amount:,.2f}"])
    
    # Payment Methods
    payments = sale_obj.payments.all()
    if payments.exists():
        table_data.append(['', '', '', '', '', ''])
        table_data.append(['', '', '', '', 'Payment Details:', ''])
        for payment in payments:
            method_name = payment.method.get_name_display() if payment.method else str(payment.method)
            ref_text = f" (Ref: {payment.reference_no})" if payment.reference_no else ""
            table_data.append(['', '', '', '', f'{method_name}{ref_text}:', f"Rs. {payment.amount:,.2f}"])
        table_data.append(['', '', '', '', 'Total Paid:', f"Rs. {paid_amount:,.2f}"])
        if outstanding > 0:
            table_data.append(['', '', '', '', 'Outstanding:', f"Rs. {outstanding:,.2f}"])
        elif outstanding < 0:
            change_amount = abs(outstanding)
            table_data.append(['', '', '', '', 'Change Return:', f"Rs. {change_amount:,.2f}"])
    else:
        table_data.append(['', '', '', '', 'Paid:', f"Rs. {paid_amount:,.2f}"])
        table_data.append(['', '', '', '', 'Outstanding:', f"Rs. {outstanding:,.2f}"])
    
    col_widths = [0.4*inch, 2.2*inch, 0.6*inch, 0.6*inch, 0.9*inch, 1.2*inch]
    
    items_table = Table(table_data, repeatRows=1, colWidths=col_widths)
    
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        
        ('FONTSIZE', (0, 1), (-1, -5), 8),
        ('VALIGN', (0, 1), (-1, -5), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -5), [colors.white, colors.HexColor('#f8f9fc')]),
        
        ('GRID', (0, 0), (-1, -5), 0.5, colors.HexColor('#e0e3eb')),
        
        ('ALIGN', (2, 1), (5, -5), 'RIGHT'),
        ('ALIGN', (0, 1), (0, -5), 'CENTER'),
        
        ('LINEABOVE', (4, -5), (5, -5), 1, colors.HexColor('#dee2e6')),
        ('FONTNAME', (4, -4), (5, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (4, -1), (5, -1), colors.HexColor('#e8ecf4')),
    ]
    
    items_table.setStyle(TableStyle(table_style))
    story.append(items_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # ✅ AMOUNT IN WORDS (ADDED)
    # ============================================
    
    def number_to_words(amount):
        """Convert number to words"""
        try:
            from num2words import num2words
            return num2words(amount, lang='en').title()
        except ImportError:
            # Simple conversion if num2words not installed
            return f"{amount:,.2f}"
        except:
            return f"{amount:,.2f}"
    
    amount_in_words = number_to_words(total_amount)
    
    # Amount in Words Box
    words_style = ParagraphStyle(
        'WordsStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#28a745'),
        fontName='Helvetica-Bold',
        backColor=colors.HexColor('#e8f5e9'),
        borderPadding=5,
        borderWidth=1,
        borderColor=colors.HexColor('#28a745'),
        borderRadius=5
    )
    
    story.append(Paragraph(f"<b>Amount in Words:</b> {amount_in_words} Only.", words_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # FOOTER SECTION
    # ============================================
    
    footer_line = Table([['']], colWidths=[6.5*inch])
    footer_line.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#667eea')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(footer_line)
    
    thank_style = ParagraphStyle(
        'ThankYou',
        parent=styles['Normal'],
        fontSize=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#667eea'),
        fontName='Helvetica-Bold',
        spaceAfter=5
    )
    story.append(Paragraph("Thank you for your business!", thank_style))
    
    footer_note = company.footer_note if company and company.footer_note else "This is a computer generated invoice. No signature required."
    story.append(Paragraph(footer_note, subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    
    story.append(Paragraph("<b>Terms & Conditions:</b>", label_style))
    story.append(Paragraph("1. Goods once sold will not be taken back.", label_style))
    story.append(Paragraph("2. All disputes subject to local jurisdiction.", label_style))
    story.append(Paragraph("3. Please retain this invoice for warranty claims.", label_style))
    story.append(Spacer(1, 0.1*inch))
    
    generated_date = datetime.now().strftime('%d %B, %Y at %I:%M %p')
    story.append(Paragraph(f"<font size='7' color='#adb5bd'>Generated on: {generated_date}</font>", subtitle_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer



_log = logging.getLogger(__name__)


@receiver(post_migrate)
def _create_default_settings_after_migrate(sender, **kwargs):
    """Create the default module on/off settings after `migrate` (replaces the old
    import-time database query, which failed silently on a fresh database)."""
    if getattr(sender, "label", None) != "app":
        return
    try:
        if SystemSetting.objects.count() == 0:
            create_default_system_settings()
    except Exception:
        _log.exception("Could not create default system settings")
