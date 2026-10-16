"""Frontend views: closing."""
from django.utils.timezone import localdate
from ..models import *
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, datetime
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from ..models import CompanyInfo, Sale, Purchase, Expense
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


@login_required
def monthly_closing_report(request):
    """Monthly Closing Report"""
    month_str = request.GET.get('month', date.today().strftime('%Y-%m'))
    month_date = datetime.strptime(month_str + '-01', '%Y-%m-%d').date()
    
    closing = MonthlyClosing.objects.filter(month=month_date).first()
    recent_closings = MonthlyClosing.objects.all().order_by('-month')[:12]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'selected_month': month_str,
        'closing': closing,
        'recent_closings': recent_closings,
    }
    return render(request, 'reports/monthly_closing.html', context)


# ========== DAILY CLOSING VIEWS ==========
@login_required
def daily_closing_index(request):
    """Daily Closing main page"""
    today = localdate()
    existing_closing = DailyClosing.objects.filter(closing_date=today, is_closed=True).first()
    
    # Get today's sales
    today_sales = Sale.objects.filter(sale_date__date=today)
    total_sales_amount = sum(s.total_amount() for s in today_sales)
    cash_sales = today_sales.aggregate(total=Sum('paid'))['total'] or 0
    
    # Get today's expenses from Expense model
    today_expenses = Expense.objects.filter(expense_date=today)
    expenses_total = today_expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'today': today,
        'is_closed': existing_closing is not None,
        'closing': existing_closing,
        'total_sales': total_sales_amount,
        'cash_sales': cash_sales,
        'today_expenses': today_expenses,
        'expenses_total': expenses_total,
    }
    return render(request, 'daily_closing/index.html', context)


@login_required
def daily_closing_create(request):
    """Create new daily closing report"""
    if request.method == 'POST':
        today = localdate()
        
        if DailyClosing.objects.filter(closing_date=today, is_closed=True).exists():
            messages.error(request, 'Today is already closed!')
            return redirect('daily_closing')
        
        opening_cash = Decimal(request.POST.get('opening_cash', 0))
        closing_cash = Decimal(request.POST.get('closing_cash', 0))
        notes = request.POST.get('notes', '')
        
        # Get today's sales
        today_sales = Sale.objects.filter(sale_date__date=today)
        
        # Create closing report
        closing = DailyClosing.objects.create(
            closing_date=today,
            opening_cash=opening_cash,
            closing_cash=closing_cash,
            notes=notes,
            is_closed=True,
            closed_by=request.user,
            closed_at=now()
        )
        
        # Calculate cash sales (simplified - adjust based on payment method tracking)
        closing.cash_sales = today_sales.aggregate(total=Sum('paid'))['total'] or 0
        
        # Calculate total expenses from Expense model
        total_expenses = Expense.objects.filter(expense_date=today).aggregate(total=Sum('amount'))['total'] or 0
        closing.total_expenses = total_expenses
        
        closing.save()
        
        messages.success(request, f'✅ Daily closing report for {today} created successfully!')
        return redirect('daily_closing_detail', pk=closing.id)
    
    return redirect('daily_closing')


@login_required
def daily_closing_detail(request, pk):
    """View daily closing report"""
    closing = get_object_or_404(DailyClosing, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'closing': closing,
    }
    return render(request, 'daily_closing/detail.html', context)


@login_required
def daily_closing_list(request):
    """List all daily closing reports"""
    closings = DailyClosing.objects.all().order_by('-closing_date')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'closings': closings,
    }
    return render(request, 'daily_closing/list.html', context)


@login_required
def daily_closing_pdf(request, pk):
    """Generate PDF for daily closing report"""
    closing = get_object_or_404(DailyClosing, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    company_address = company.address if company else ""
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    if company_address:
        story.append(Paragraph(company_address, styles['Normal']))
    story.append(Paragraph(f"Daily Closing Report", title_style))
    story.append(Paragraph(f"Date: {closing.closing_date.strftime('%d-%m-%Y')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Summary Table
    data = [
        ['Description', 'Amount (Rs.)'],
        ['Opening Cash', f'{closing.opening_cash:,.2f}'],
        ['', ''],
        ['SALES BREAKDOWN', ''],
        ['💵 Cash Sales', f'{closing.cash_sales:,.2f}'],
        ['💳 Card Sales', f'{closing.card_sales:,.2f}'],
        ['📱 JazzCash Sales', f'{closing.jazzcash_sales:,.2f}'],
        ['📱 EasyPaisa Sales', f'{closing.easypaisa_sales:,.2f}'],
        ['🏦 Bank Transfer Sales', f'{closing.bank_transfer_sales:,.2f}'],
        ['', ''],
        ['📊 Total Sales', f'{closing.total_sales_today():,.2f}'],
        ['📝 Total Expenses', f'({closing.total_expenses:,.2f})'],
        ['', ''],
        ['💰 Expected Cash', f'{closing.expected_cash():,.2f}'],
        ['💵 Actual Closing Cash', f'{closing.closing_cash:,.2f}'],
        ['📈 Difference', f'{closing.cash_difference:+,.2f}'],
    ]
    
    table = Table(data, colWidths=[3*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#e8ecf4')),
        ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#e8ecf4')),
        ('BACKGROUND', (0, 11), (-1, 11), colors.HexColor('#fff3cd')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fff3cd')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('SPAN', (0, 2), (-1, 2)),
        ('SPAN', (0, 8), (-1, 8)),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.3*inch))
    
    # Expenses Detail
    if closing.expenses.exists():
        story.append(Paragraph("Expenses Details:", styles['Heading2']))
        exp_data = [['Description', 'Amount (Rs.)']]
        for exp in closing.expenses.all():
            exp_data.append([exp.description, f'{exp.amount:,.2f}'])
        
        exp_table = Table(exp_data, colWidths=[3.5*inch, 1.5*inch])
        exp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ]))
        story.append(exp_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Footer
    story.append(Paragraph(f"Closed by: {closing.closed_by.username if closing.closed_by else 'System'}", styles['Normal']))
    story.append(Paragraph(f"Closed at: {closing.closed_at.strftime('%d-%m-%Y %H:%M') if closing.closed_at else 'N/A'}", styles['Normal']))
    if closing.notes:
        story.append(Paragraph(f"Notes: {closing.notes}", styles['Normal']))
    
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("This is a computer generated report.", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Daily_Closing_{closing.closing_date}.pdf"'
    return response


@login_required
def daily_closing_data(request):
    """AJAX: Get today's sales data for daily closing"""
    today = localdate()
    
    sales = Sale.objects.filter(sale_date__date=today)
    cash_sales = sales.aggregate(total=Sum('paid'))['total'] or 0
    total_sales = sum(s.total_amount() for s in sales)
    
    expenses = Expense.objects.filter(expense_date=today)
    expense_list = [{'description': exp.description, 'amount': float(exp.amount)} for exp in expenses]
    
    return JsonResponse({
        'success': True,
        'cash_sales': float(cash_sales),
        'card_sales': 0,
        'jazzcash_sales': 0,
        'easypaisa_sales': 0,
        'bank_transfer_sales': 0,
        'total_sales': float(total_sales),
        'expenses': expense_list
    })


@login_required
def monthly_closing(request):
    month_str = request.GET.get('month', localdate().strftime('%Y-%m'))
    month_date = datetime.strptime(month_str + '-01', '%Y-%m-%d').date()
    
    closing = MonthlyClosing.objects.filter(month=month_date).first()
    
    recent_closings = MonthlyClosing.objects.all().order_by('-month')[:12]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'selected_month': month_str,
        'closing': closing,
        'recent_closings': recent_closings,
    }
    return render(request, 'reports/monthly_closing.html', context)


@login_required
def lock_month(request, pk):
    if request.method == 'POST':
        closing = get_object_or_404(MonthlyClosing, pk=pk)
        closing.locked = True
        closing.save()
        messages.success(request, f'🔒 {closing.month.strftime("%B %Y")} has been locked!')
    return redirect('monthly_closing')


@login_required
def unlock_month(request, pk):
    if request.method == 'POST':
        closing = get_object_or_404(MonthlyClosing, pk=pk)
        closing.locked = False
        closing.save()
        messages.success(request, f'🔓 {closing.month.strftime("%B %Y")} has been unlocked!')
    return redirect('monthly_closing')


@login_required
def closing_pdf(request, pk):
    """Generate Premium Monthly Closing PDF"""
    closing = get_object_or_404(MonthlyClosing, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame
    from reportlab.platypus.frames import Frame
    
    buffer = BytesIO()
    
    # Page Setup
    page_width, page_height = A4
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontSize=20, textColor=colors.HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=5, fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=12, textColor=colors.HexColor('#6b7280'),
        alignment=TA_CENTER, spaceAfter=3
    )
    
    section_style = ParagraphStyle(
        'Section', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1a1a2e'),
        spaceBefore=15, spaceAfter=8, fontName='Helvetica-Bold',
        borderPadding=(0, 0, 2, 0)
    )
    
    normal_style = ParagraphStyle(
        'NormalStyle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#333333')
    )
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "Company Name"
    company_address = company.address if company else ""
    company_phone = company.contact_number if company else ""
    
    # Build Document
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.4*inch, bottomMargin=0.4*inch,
        leftMargin=0.5*inch, rightMargin=0.5*inch
    )
    
    story = []
    
    # ========== HEADER SECTION ==========
    # Company Name with decorative line
    header_data = [[
        Paragraph(f'<font size="22" color="#1a1a2e"><b>{company_name.upper()}</b></font>', title_style)
    ]]
    header_table = Table(header_data, colWidths=[page_width - 1*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#667eea')),
    ]))
    story.append(header_table)
    
    # Address line
    story.append(Paragraph(
        f'<font size="9" color="#6b7280">{company_address} | {company_phone}</font>',
        subtitle_style
    ))
    story.append(Spacer(1, 0.3*inch))
    
    # Report Title Box
    status_color = '#dc3545' if closing.locked else '#28a745'
    status_text = '🔒 LOCKED' if closing.locked else '🔓 OPEN'
    
    title_box_data = [[
        Paragraph(
            f'<font size="16" color="white"><b>MONTHLY CLOSING REPORT</b></font><br/>'
            f'<font size="13" color="#f0a500">{closing.month.strftime("%B %Y")}</font>',
            ParagraphStyle('box', alignment=TA_CENTER, fontSize=14, textColor=colors.white)
        ),
        Paragraph(
            f'<font size="11" color="white"><b>{status_text}</b></font><br/>'
            f'<font size="8" color="#cccccc">Generated: {now().strftime("%d-%m-%Y %H:%M")}</font>',
            ParagraphStyle('box2', alignment=TA_RIGHT, fontSize=10, textColor=colors.white)
        )
    ]]
    
    title_box = Table(title_box_data, colWidths=[3.5*inch, 2.5*inch])
    title_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a1d2e')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(title_box)
    story.append(Spacer(1, 0.3*inch))
    
    # ========== 5 KEY METRICS ==========
    metrics_data = [[
        Paragraph(
            f'<font size="9" color="#5a6070">TOTAL PURCHASES</font><br/>'
            f'<font size="14" color="#1a1a2e"><b>Rs. {closing.total_purchase_balance():,.0f}</b></font>',
            ParagraphStyle('m', alignment=TA_CENTER)
        ),
        Paragraph(
            f'<font size="9" color="#5a6070">TOTAL SALES</font><br/>'
            f'<font size="14" color="#1a1a2e"><b>Rs. {closing.total_sale_balance():,.0f}</b></font>',
            ParagraphStyle('m', alignment=TA_CENTER)
        ),
        Paragraph(
            f'<font size="9" color="#5a6070">GROSS PROFIT</font><br/>'
            f'<font size="14" color="#28a745"><b>Rs. {closing.total_sale_profit():,.0f}</b></font>',
            ParagraphStyle('m', alignment=TA_CENTER)
        ),
        Paragraph(
            f'<font size="9" color="#5a6070">NET MARGIN</font><br/>'
            f'<font size="14" color="#667eea"><b>{closing.net_profit_margin():.1f}%</b></font>',
            ParagraphStyle('m', alignment=TA_CENTER)
        ),
        Paragraph(
            f'<font size="9" color="#5a6070">ROI</font><br/>'
            f'<font size="14" color="#f2994a"><b>{closing.return_on_investment():.1f}%</b></font>',
            ParagraphStyle('m', alignment=TA_CENTER)
        ),
    ]]
    
    metrics_table = Table(metrics_data, colWidths=[1.2*inch]*5)
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fc')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBEFORE', (1, 0), (1, 0), 0.5, colors.HexColor('#e0e3eb')),
        ('LINEBEFORE', (2, 0), (2, 0), 0.5, colors.HexColor('#e0e3eb')),
        ('LINEBEFORE', (3, 0), (3, 0), 0.5, colors.HexColor('#e0e3eb')),
        ('LINEBEFORE', (4, 0), (4, 0), 0.5, colors.HexColor('#e0e3eb')),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.3*inch))
    
    # ========== FINANCIAL SUMMARY TABLE ==========
    story.append(Paragraph('<font size="12"><b>📊 Financial Summary</b></font>', section_style))
    
    fin_data = [
        ['Description', 'Amount (Rs.)'],
        ['Previous Month Balance', f'{closing.previous_balance:,.2f}'],
        ['(+) Total Purchases', f'{closing.total_purchase_balance():,.2f}'],
        ['(-) Purchase Returns', f'({closing.total_purchase_return():,.2f})'],
        ['(-) Total Sales (COGS)', f'({closing.total_sale_balance():,.2f})'],
        ['(+) Sale Returns', f'{closing.total_sale_return():,.2f}'],
    ]
    
    # Add profit line
    fin_data.append(['Gross Profit (Sales - COGS)', f'{closing.total_sale_profit():,.2f}'])
    
    fin_table = Table(fin_data, colWidths=[3.5*inch, 2.5*inch])
    fin_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e3eb')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ========== CLOSING BALANCE HIGHLIGHT ==========
    closing_data = [[
        Paragraph(
            f'<font size="11" color="white"><b>🏁 CLOSING BALANCE</b></font>',
            ParagraphStyle('cl', alignment=TA_LEFT)
        ),
        Paragraph(
            f'<font size="16" color="white"><b>Rs. {closing.closing_balance():,.2f}</b></font>',
            ParagraphStyle('cl2', alignment=TA_RIGHT)
        )
    ]]
    
    closing_table = Table(closing_data, colWidths=[3*inch, 3*inch])
    closing_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#667eea')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    story.append(closing_table)
    story.append(Spacer(1, 0.3*inch))
    
    # ========== PERFORMANCE METRICS ==========
    story.append(Paragraph('<font size="12"><b>📈 Performance Metrics</b></font>', section_style))
    
    perf_data = [
        ['Metric', 'Value', 'Status'],
        ['Net Profit Margin', f'{closing.net_profit_margin():.2f}%', 
         '✅ Good' if closing.net_profit_margin() > 10 else '⚠️ Low'],
        ['Return on Investment (ROI)', f'{closing.return_on_investment():.2f}%',
         '✅ Good' if closing.return_on_investment() > 15 else '⚠️ Low'],
        ['Days Inventory Outstanding', f'{closing.days_inventory_outstanding():.1f} days',
         '✅ Good' if closing.days_inventory_outstanding() < 30 else '⚠️ High'],
        ['Gross Profit', f'Rs. {closing.total_sale_profit():,.2f}', ''],
    ]
    
    perf_table = Table(perf_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
    perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e3eb')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(perf_table)
    
    # ========== FOOTER ==========
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph('_' * 80, normal_style))
    story.append(Paragraph(
        f'<font size="8" color="#8a8fa0">This is a computer generated report. Generated on {now().strftime("%d-%m-%Y %H:%M")}</font>',
        ParagraphStyle('footer', alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        f'<font size="8" color="#8a8fa0">{company_name} - Monthly Closing Report</font>',
        ParagraphStyle('footer2', alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Monthly_Closing_{closing.month.strftime("%B_%Y")}.pdf"'
    return response


@login_required
def closing_pnl(request, pk):
    """Generate P&L Statement PDF"""
    closing = get_object_or_404(MonthlyClosing, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "Company Name"
    
    # Calculate P&L
    income = closing.total_sale_profit()
    expenses = Expense.objects.filter(
        date__year=closing.month.year, 
        date__month=closing.month.month
    ).aggregate(total=Sum('amount'))['total'] or 0
    net_profit = income - expenses
    
    story.append(Paragraph(f'<font size="16"><b>{company_name}</b></font>', styles['Normal']))
    story.append(Paragraph(f'<font size="14"><b>Profit & Loss Statement</b></font>', styles['Normal']))
    story.append(Paragraph(f'<font size="11">{closing.month.strftime("%B %Y")}</font>', styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    data = [
        ['Description', 'Amount (Rs.)'],
        ['REVENUE', ''],
        ['Total Sales Profit', f'{income:,.2f}'],
        ['', ''],
        ['EXPENSES', ''],
        ['Total Expenses', f'{expenses:,.2f}'],
        ['', ''],
        ['NET PROFIT/LOSS', f'{net_profit:,.2f}'],
        ['Net Profit Margin', f'{closing.net_profit_margin():.2f}%'],
    ]
    
    table = Table(data, colWidths=[3.5*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
        ('FONTNAME', (0, 4), (0, 4), 'Helvetica-Bold'),
        ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 7), (-1, 7), 11),
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#e8ecf4')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f'<font size="8">Generated: {now().strftime("%d-%m-%Y %H:%M")}</font>', styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="PnL_{closing.month.strftime("%B_%Y")}.pdf"'
    return response


@login_required
def closing_cashflow(request, pk):
    """Generate Cash Flow PDF"""
    closing = get_object_or_404(MonthlyClosing, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "Company Name"
    
    cash_in = Sale.objects.filter(
        sale_date__year=closing.month.year,
        sale_date__month=closing.month.month
    ).aggregate(total=Sum('paid'))['total'] or 0
    
    cash_out = Purchase.objects.filter(
        pur_date__year=closing.month.year,
        pur_date__month=closing.month.month
    ).aggregate(total=Sum('paid'))['total'] or 0
    
    net_cash = cash_in - cash_out
    
    story.append(Paragraph(f'<font size="16"><b>{company_name}</b></font>', styles['Normal']))
    story.append(Paragraph(f'<font size="14"><b>Cash Flow Statement</b></font>', styles['Normal']))
    story.append(Paragraph(f'<font size="11">{closing.month.strftime("%B %Y")}</font>', styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    data = [
        ['Description', 'Amount (Rs.)'],
        ['Cash In (Sales Received)', f'{cash_in:,.2f}'],
        ['Cash Out (Purchases Paid)', f'({cash_out:,.2f})'],
        ['NET CASH FLOW', f'{net_cash:,.2f}'],
    ]
    
    table = Table(data, colWidths=[3.5*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 3), (-1, 3), 11),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#e8ecf4')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f'<font size="8">Generated: {now().strftime("%d-%m-%Y %H:%M")}</font>', styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="CashFlow_{closing.month.strftime("%B_%Y")}.pdf"'
    return response
