import io
from .models import CompanyInfo
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from django.conf import settings
from django.core.files.storage import default_storage
import os
from datetime import datetime
from decimal import Decimal

def generate_share_certificate_pdf(share):
    """
    Generate professional share certificate PDF
    """
    buffer = io.BytesIO()
    
    # Page Setup - Landscape A4
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4),
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Company Info
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "YOUR COMPANY NAME"
    company_address = company.address if company else "Address"
    company_phone = company.contact_number if company else "Phone"
    company_email = company.email if company else "Email"
    
    # Certificate Border Frame
    frame_style = ParagraphStyle(
        'FrameStyle',
        parent=styles['Normal'],
        borderPadding=20,
        borderWidth=3,
        borderColor=colors.HexColor('#1a1a2e'),
        borderRadius=10,
    )
    
    # Title Style
    title_style = ParagraphStyle(
        'CertificateTitle',
        parent=styles['Heading1'],
        fontSize=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=5,
        fontName='Helvetica-Bold'
    )
    
    # Subtitle Style
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6c757d'),
        spaceAfter=3
    )
    
    # Body Style
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=10,
        fontName='Helvetica'
    )
    
    # Name Style
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )
    
    # Details Style
    details_style = ParagraphStyle(
        'Details',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1a1a2e'),
        fontName='Helvetica'
    )
    
    # ============================================
    # HEADER - Company Name
    # ============================================
    
    # Decorative Line
    story.append(Spacer(1, 0.1*inch))
    
    # Company Logo (if exists)
    if company and company.logo:
        try:
            from django.core.files.storage import default_storage
            logo_path = company.logo.path if hasattr(company.logo, 'path') else str(company.logo)
            if os.path.exists(logo_path):
                img = RLImage(logo_path, width=1.5*inch, height=0.8*inch)
                story.append(img)
        except:
            pass
    
    # Company Name
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"{company_address} | Phone: {company_phone} | Email: {company_email}", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Decorative Line
    line_table = Table([['']], colWidths=[8*inch])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#667eea')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # TITLE
    # ============================================
    story.append(Paragraph("SHARE CERTIFICATE", title_style))
    
    # Certificate Number
    cert_no = f"CERT-{share.certificate_number or share.id:06d}"
    story.append(Paragraph(f"Certificate No: <b>{cert_no}</b>", subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    
    # ============================================
    # BODY
    # ============================================
    story.append(Paragraph("THIS IS TO CERTIFY THAT", body_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Shareholder Name
    story.append(Paragraph(f"<b>{share.shareholder.name.upper()}</b>", name_style))
    story.append(Spacer(1, 0.1*inch))
    
    story.append(Paragraph("is the registered holder of", body_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Share Details - Table
    details_data = [
        ['Number of Shares', f"{share.quantity:,.0f}"],
        ['Share Type', share.get_share_type_display()],
        ['Certificate Number', cert_no],
        ['Issue Date', share.certificate_issue_date.strftime('%d-%B-%Y') if share.certificate_issue_date else datetime.now().strftime('%d-%B-%Y')],
        ['Face Value', f"Rs. {share.purchase_price:,.2f}"],
        ['Total Value', f"Rs. {share.quantity * share.purchase_price:,.2f}"],
    ]
    
    details_table = Table(details_data, colWidths=[3*inch, 2.5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e3eb')),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # SHAREHOLDER RIGHTS
    # ============================================
    rights_text = """
    <font size="8">The above named shareholder is entitled to all rights and privileges of a 
    shareholder of the company as per the Articles of Association. This certificate is issued 
    subject to the terms and conditions of the company.</font>
    """
    story.append(Paragraph(rights_text, details_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # SIGNATURES
    # ============================================
    sign_data = [
        [
            Paragraph("<b>For and on behalf of the Board</b>", details_style),
            Paragraph("<b>For and on behalf of the Board</b>", details_style),
        ],
        [
            Paragraph("_________________________", details_style),
            Paragraph("_________________________", details_style),
        ],
        [
            Paragraph("<b>Director</b>", details_style),
            Paragraph("<b>Director / Company Secretary</b>", details_style),
        ],
    ]
    
    sign_table = Table(sign_data, colWidths=[3.5*inch, 3.5*inch])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ============================================
    # QR CODE
    # ============================================
    try:
        import qrcode
        from io import BytesIO
        
        # Generate QR Code with certificate data
        qr_data = {
            'cert_no': cert_no,
            'shareholder': share.shareholder.name,
            'shares': str(share.quantity),
            'share_type': share.get_share_type_display(),
            'issue_date': datetime.now().strftime('%d-%m-%Y'),
        }
        qr_text = f"CERT-{cert_no}\n{share.shareholder.name}\n{share.quantity} shares"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Add QR Code to PDF
        qr_plot = RLImage(qr_buffer, width=1*inch, height=1*inch)
        qr_table = Table([[qr_plot, Paragraph(f"<font size='7'>Verify at: {company.website or 'company.com'}</font>", subtitle_style)]], colWidths=[1.2*inch, 5*inch])
        qr_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(qr_table)
    except:
        pass
    
    # ============================================
    # FOOTER
    # ============================================
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("_" * 80, subtitle_style))
    story.append(Paragraph(
        f"<font size='7' color='#8a8fa0'>This is a computer generated certificate. Generated on {datetime.now().strftime('%d-%m-%Y %H:%M')}</font>",
        subtitle_style
    ))
    story.append(Paragraph(
        f"<font size='7' color='#8a8fa0'>This certificate is subject to the Articles of Association of {company_name}</font>",
        subtitle_style
    ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_bulk_certificates(share_ids):
    """Generate certificates for multiple shares"""
    from .models import Share
    import zipfile
    from io import BytesIO
    
    shares = Share.objects.filter(id__in=share_ids)
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for share in shares:
            pdf_buffer = generate_share_certificate_pdf(share)
            filename = f"Certificate_{share.shareholder.name}_{share.id}.pdf"
            zip_file.writestr(filename, pdf_buffer.getvalue())
    
    zip_buffer.seek(0)
    return zip_buffer