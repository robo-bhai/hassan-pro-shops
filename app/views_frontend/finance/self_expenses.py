"""Frontend views: finance/self_expenses (split from the former expenses_budget.py)."""
from ...security.permissions import perm_required
from ...models import *
import json
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.http import HttpResponse
from io import BytesIO
from ...models import CompanyInfo, Sale, Expense, SaleItem
from django.db.models.functions import TruncMonth
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from openpyxl.utils import get_column_letter
from openpyxl.chart import PieChart, Reference


@login_required
@perm_required('view_financials')
def self_expense_report(request):
    """
    Self Expense Report - Complete analytics for self expenses
    """
    
    # Get filter parameters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    category_id = request.GET.get('category', '')
    search_product = request.GET.get('search_product', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ========================================== #
    # 1. GET SELF EXPENSE CATEGORY              #
    # ========================================== #
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={
            'category_type': 'operating',
            'is_active': True
        }
    )
    
    # ========================================== #
    # 2. GET ALL SELF EXPENSES                  #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    # Filter by sub-category if selected
    if category_id:
        expenses = expenses.filter(category_id=category_id)
    
    # ========================================== #
    # 3. CALCULATE STATISTICS                   #
    # ========================================== #
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_count = expenses.count()
    total_tax = expenses.aggregate(total=Sum('tax_amount'))['total'] or Decimal('0.00')
    avg_expense = expenses.aggregate(avg=Avg('amount'))['avg'] or Decimal('0.00')
    
    # ========================================== #
    # 4. CATEGORY WISE BREAKDOWN                #
    # ========================================== #
    category_breakdown = expenses.values(
        'category__name'
    ).annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Calculate percentage
    total_all = sum(item['total'] for item in category_breakdown) or 1
    for item in category_breakdown:
        item['percentage'] = (item['total'] / total_all) * 100
    
    # ========================================== #
    # 5. MONTHLY TREND                          #
    # ========================================== #
    monthly_trend = expenses.annotate(
        month=TruncMonth('expense_date')
    ).values('month').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('month')
    
    # ========================================== #
    # 6. DAILY BREAKDOWN (Last 30 Days)        #
    # ========================================== #
    daily_data = []
    current = from_date_obj
    while current <= to_date_obj:
        day_expenses = expenses.filter(expense_date=current)
        daily_data.append({
            'date': current.strftime('%d-%b'),
            'amount': day_expenses.aggregate(total=Sum('amount'))['total'] or 0,
            'count': day_expenses.count()
        })
        current += timedelta(days=1)
    
    # ========================================== #
    # 7. SELF SALES (Converted)                 #
    # ========================================== #
    self_sales = Sale.objects.filter(
        is_converted_to_expense=True,
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj
    ).select_related('customer')
    
    total_self_sales = self_sales.aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0.00')
    self_sales_count = self_sales.count()
    
    # ========================================== #
    # 8. PRODUCT DETAILS (NEW)                  #
    # ========================================== #
    
    # Get all products used in self expenses
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__id',
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name',
        'product__price'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_profit=Sum('profit'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    # Search filter for products
    if search_product:
        product_details = product_details.filter(
            Q(product__name__icontains=search_product) |
            Q(product__serial_no__icontains=search_product) |
            Q(product__barcode__icontains=search_product)
        )
    
    # Calculate total product value
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # Top 5 products by amount
    top_products = product_details[:5]
    
    # Product category breakdown
    product_category = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__category__isnull=False
    ).values('product__category__name').annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('-total_amount')
    
    # Product brand breakdown
    product_brand = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj,
        product__brand__isnull=False
    ).values('product__brand__name').annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('-total_amount')
    
    # Product monthly trend
    product_monthly = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).annotate(
        month=TruncMonth('sale__sale_date')
    ).values(
        'month',
        'product__name'
    ).annotate(
        total_amount=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('month', '-total_amount')
    
    # ========================================== #
    # 9. USER WISE SELF EXPENSES                #
    # ========================================== #
    user_wise = expenses.values('created_by__username').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # ========================================== #
    # 10. CHART DATA                            #
    # ========================================== #
    chart_labels = [d['date'] for d in daily_data]
    chart_amounts = [float(d['amount']) for d in daily_data]
    
    monthly_labels = [m['month'].strftime('%b %Y') for m in monthly_trend if m['month']]
    monthly_amounts = [float(m['total']) for m in monthly_trend]
    
    # Product chart data
    product_chart_labels = [p['product__name'][:20] for p in top_products]
    product_chart_amounts = [float(p['total_amount']) for p in top_products]
    
    # ========================================== #
    # 11. COMPARISON WITH PREVIOUS PERIOD       #
    # ========================================== #
    days_diff = (to_date_obj - from_date_obj).days
    prev_from = from_date_obj - timedelta(days=days_diff + 1)
    prev_to = to_date_obj - timedelta(days=days_diff + 1)
    
    prev_expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=prev_from,
        expense_date__lte=prev_to,
        status__in=['approved', 'paid']
    )
    prev_total = prev_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    growth_percent = 0
    if prev_total > 0:
        growth_percent = ((total_expenses - prev_total) / prev_total) * 100
    
    # ========================================== #
    # 12. PAGINATION FOR EXPENSES LIST          #
    # ========================================== #
    paginator = Paginator(expenses, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ========================================== #
    # 13. CONTEXT                               #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'expenses': page_obj,
        'from_date': from_date,
        'to_date': to_date,
        'total_expenses': total_expenses,
        'total_count': total_count,
        'total_tax': total_tax,
        'avg_expense': avg_expense,
        'category_breakdown': category_breakdown,
        'monthly_trend': monthly_trend,
        'daily_data': daily_data,
        'chart_labels': json.dumps(chart_labels),
        'chart_amounts': json.dumps(chart_amounts),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_amounts': json.dumps(monthly_amounts),
        'self_sales': self_sales[:20],
        'total_self_sales': total_self_sales,
        'self_sales_count': self_sales_count,
        'user_wise': user_wise,
        'prev_total': prev_total,
        'growth_percent': growth_percent,
        'category_id': category_id,
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'today': date.today(),
        # ✅ NEW: Product Details
        'product_details': product_details,
        'total_product_value': total_product_value,
        'top_products': top_products,
        'product_monthly': product_monthly,
        'product_category': product_category,
        'product_brand': product_brand,
        'total_products': product_details.count(),
        'search_product': search_product,
        'product_chart_labels': json.dumps(product_chart_labels),
        'product_chart_amounts': json.dumps(product_chart_amounts),
        'product_category_labels': json.dumps([cat['product__category__name'] for cat in product_category]),
        'product_category_amounts': json.dumps([float(cat['total_amount']) for cat in product_category]),
    }
    return render(request, 'reports/self_expense_report.html', context)


@login_required
@perm_required('view_financials')
def self_expense_report_pdf(request):
    """Generate PDF for Self Expense Report with Product Details"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={'category_type': 'operating', 'is_active': True}
    )
    
    # ========================================== #
    # GET EXPENSES                              #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # ========================================== #
    # GET PRODUCT DETAILS                       #
    # ========================================== #
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # ========================================== #
    # BUILD PDF                                 #
    # ========================================== #
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        topMargin=0.3*inch, 
        bottomMargin=0.3*inch,
        leftMargin=0.3*inch,
        rightMargin=0.3*inch
    )
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title Style
    title_style = ParagraphStyle(
        'Title', 
        parent=styles['Heading1'], 
        fontSize=16, 
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=3
    )
    
    # ========================================== #
    # HEADER                                    #
    # ========================================== #
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Self Expense Report", title_style))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # SUMMARY SECTION                           #
    # ========================================== #
    summary_data = [
        ['Metric', 'Value'],
        ['Total Self Expenses', f"Rs. {total_expenses:,.2f}"],
        ['Total Transactions', str(expenses.count())],
        ['Average Expense', f"Rs. {(total_expenses / expenses.count()):,.2f}" if expenses.count() > 0 else "Rs. 0.00"],
        ['Products Used', str(product_details.count())],
        ['Total Product Value', f"Rs. {total_product_value:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # PRODUCT DETAILS TABLE                     #
    # ========================================== #
    if product_details:
        story.append(Paragraph("<b>📦 Product Details</b>", styles['Heading3']))
        story.append(Spacer(1, 0.1*inch))
        
        product_data = [
            ['#', 'Product Name', 'Serial No', 'Barcode', 'Category', 'Brand', 'Qty', 'Unit', 'Total']
        ]
        
        for idx, product in enumerate(product_details, 1):
            product_data.append([
                str(idx),
                product['product__name'][:25] if product['product__name'] else '-',
                product['product__serial_no'] or '-',
                product['product__barcode'] or '-',
                product['product__category__name'] or '-',
                product['product__brand__name'] or '-',
                f"{product['total_qty']:,.0f}",
                product['product__unit__name'] or '-',
                f"Rs. {product['total_amount']:,.2f}",
            ])
        
        # Add total row
        product_data.append([
            '', '', '', '', '', '', '', 'TOTAL:',
            f"Rs. {total_product_value:,.2f}"
        ])
        
        product_table = Table(product_data, repeatRows=1)
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('FONTSIZE', (0, 1), (-1, -2), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fc')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (6, 1), (8, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(product_table)
        story.append(Spacer(1, 0.2*inch))
    
    # ========================================== #
    # EXPENSES TABLE                            #
    # ========================================== #
    story.append(Paragraph("<b>📋 Self Expenses List</b>", styles['Heading3']))
    story.append(Spacer(1, 0.1*inch))
    
    exp_data = [
        ['Date', 'Description', 'Category', 'Amount', 'Tax', 'Total', 'Created By', 'Status']
    ]
    
    for exp in expenses[:100]:  # Limit to 100 rows for PDF
        exp_data.append([
            exp.expense_date.strftime('%d-%m-%Y'),
            exp.description[:35],
            exp.category.name if exp.category else 'Self Expense',
            f"Rs. {exp.amount:,.2f}",
            f"Rs. {exp.tax_amount:,.2f}",
            f"Rs. {exp.total_amount:,.2f}",
            exp.created_by.username if exp.created_by else '-',
            exp.get_status_display()
        ])
    
    exp_table = Table(exp_data, repeatRows=1)
    exp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('ALIGN', (3, 1), (5, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(exp_table)
    
    # ========================================== #
    # FOOTER                                    #
    # ========================================== #
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "This is a computer generated report.",
        ParagraphStyle('Footer2', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Self_Expense_Report_{date.today()}.pdf"'
    return response


@login_required
@perm_required('view_financials')
def self_expense_export(request):
    """Export Self Expense Report to Excel with Product Details"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    self_category, _ = ExpenseCategory.objects.get_or_create(
        name='Self Sale / Personal Use',
        defaults={'category_type': 'operating', 'is_active': True}
    )
    
    # ========================================== #
    # GET DATA                                  #
    # ========================================== #
    expenses = Expense.objects.filter(
        category=self_category,
        expense_date__gte=from_date_obj,
        expense_date__lte=to_date_obj,
        status__in=['approved', 'paid']
    ).select_related('created_by', 'category')
    
    product_details = SaleItem.objects.filter(
        sale__is_converted_to_expense=True,
        sale__sale_date__date__gte=from_date_obj,
        sale__sale_date__date__lte=to_date_obj
    ).values(
        'product__name',
        'product__serial_no',
        'product__barcode',
        'product__category__name',
        'product__brand__name',
        'product__unit__name'
    ).annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('total_amt'),
        total_count=Count('id')
    ).order_by('-total_amount')
    
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_product_value = sum(item['total_amount'] for item in product_details) or 0
    
    # ========================================== #
    # CREATE WORKBOOK                           #
    # ========================================== #
    wb = openpyxl.Workbook()
    
    # ========================================== #
    # SHEET 1: SUMMARY                          #
    # ========================================== #
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Header
    ws_summary.merge_cells('A1:C1')
    ws_summary['A1'] = company_name
    ws_summary['A1'].font = Font(bold=True, size=16)
    ws_summary['A1'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A2:C2')
    ws_summary['A2'] = "Self Expense Report"
    ws_summary['A2'].font = Font(bold=True, size=14)
    ws_summary['A2'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A3:C3')
    ws_summary['A3'] = f"Period: {from_date} to {to_date}"
    ws_summary['A3'].alignment = Alignment(horizontal='center')
    
    # Summary Data
    summary_data = [
        ['Metric', 'Value'],
        ['Total Self Expenses', float(total_expenses)],
        ['Total Transactions', expenses.count()],
        ['Average Expense', float(total_expenses / expenses.count()) if expenses.count() > 0 else 0],
        ['Products Used', product_details.count()],
        ['Total Product Value', float(total_product_value)],
    ]
    
    row = 5
    for data in summary_data:
        ws_summary.cell(row=row, column=1, value=data[0])
        ws_summary.cell(row=row, column=2, value=data[1])
        if row == 5:
            ws_summary.cell(row=row, column=1).font = Font(bold=True)
            ws_summary.cell(row=row, column=2).font = Font(bold=True)
        row += 1
    
    # Format numbers
    for r in range(6, 11):
        cell = ws_summary.cell(row=r, column=2)
        if isinstance(cell.value, (int, float)):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20
    
    # ========================================== #
    # SHEET 2: PRODUCT DETAILS                  #
    # ========================================== #
    ws_product = wb.create_sheet("Product Details")
    
    # Product Headers
    product_headers = ['#', 'Product Name', 'Serial No', 'Barcode', 'Category', 'Brand', 'Qty', 'Unit', 'Total Amount', 'Transactions']
    for col, header in enumerate(product_headers, 1):
        cell = ws_product.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Product Data
    for idx, product in enumerate(product_details, 1):
        row = idx + 1
        ws_product.cell(row=row, column=1, value=idx)
        ws_product.cell(row=row, column=2, value=product['product__name'] or '-')
        ws_product.cell(row=row, column=3, value=product['product__serial_no'] or '-')
        ws_product.cell(row=row, column=4, value=product['product__barcode'] or '-')
        ws_product.cell(row=row, column=5, value=product['product__category__name'] or '-')
        ws_product.cell(row=row, column=6, value=product['product__brand__name'] or '-')
        ws_product.cell(row=row, column=7, value=float(product['total_qty']))
        ws_product.cell(row=row, column=8, value=product['product__unit__name'] or '-')
        ws_product.cell(row=row, column=9, value=float(product['total_amount']))
        ws_product.cell(row=row, column=10, value=product['total_count'])
        
        # Format numbers
        ws_product.cell(row=row, column=7).number_format = '#,##0.00'
        ws_product.cell(row=row, column=9).number_format = '#,##0.00'
        ws_product.cell(row=row, column=7).alignment = Alignment(horizontal='right')
        ws_product.cell(row=row, column=9).alignment = Alignment(horizontal='right')
        ws_product.cell(row=row, column=10).alignment = Alignment(horizontal='center')
    
    # Product Total Row
    if product_details:
        total_row = len(product_details) + 2
        ws_product.cell(row=total_row, column=1, value="TOTAL")
        ws_product.cell(row=total_row, column=8, value="TOTAL:")
        ws_product.cell(row=total_row, column=9, value=float(total_product_value))
        ws_product.cell(row=total_row, column=10, value=product_details.count())
        
        for col in [1, 8, 9, 10]:
            cell = ws_product.cell(row=total_row, column=col)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="e8ecf4", end_color="e8ecf4", fill_type="solid")
        
        ws_product.cell(row=total_row, column=9).number_format = '#,##0.00'
        ws_product.cell(row=total_row, column=9).alignment = Alignment(horizontal='right')
    
    # Product Column Widths
    product_widths = [5, 35, 15, 18, 20, 15, 10, 10, 15, 12]
    for i, width in enumerate(product_widths, 1):
        ws_product.column_dimensions[get_column_letter(i)].width = width
    
    # ========================================== #
    # SHEET 3: EXPENSES                         #
    # ========================================== #
    ws_expenses = wb.create_sheet("Expenses")
    
    # Expense Headers
    expense_headers = ['Date', 'Description', 'Category', 'Amount', 'Tax', 'Total', 'Created By', 'Status']
    for col, header in enumerate(expense_headers, 1):
        cell = ws_expenses.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Expense Data
    for idx, exp in enumerate(expenses, 1):
        row = idx + 1
        ws_expenses.cell(row=row, column=1, value=exp.expense_date.strftime('%d-%m-%Y'))
        ws_expenses.cell(row=row, column=2, value=exp.description[:50])
        ws_expenses.cell(row=row, column=3, value=exp.category.name if exp.category else 'Self Expense')
        ws_expenses.cell(row=row, column=4, value=float(exp.amount))
        ws_expenses.cell(row=row, column=5, value=float(exp.tax_amount))
        ws_expenses.cell(row=row, column=6, value=float(exp.total_amount))
        ws_expenses.cell(row=row, column=7, value=exp.created_by.username if exp.created_by else 'System')
        ws_expenses.cell(row=row, column=8, value=exp.get_status_display())
        
        # Format numbers
        for col in [4, 5, 6]:
            cell = ws_expenses.cell(row=row, column=col)
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    # Expense Column Widths
    expense_widths = [12, 40, 20, 12, 12, 12, 15, 12]
    for i, width in enumerate(expense_widths, 1):
        ws_expenses.column_dimensions[get_column_letter(i)].width = width
    
    # ========================================== #
    # CREATE CHART (Product Category)           #
    # ========================================== #
    try:
        # Get product category data
        product_category = SaleItem.objects.filter(
            sale__is_converted_to_expense=True,
            sale__sale_date__date__gte=from_date_obj,
            sale__sale_date__date__lte=to_date_obj,
            product__category__isnull=False
        ).values('product__category__name').annotate(
            total_amount=Sum('total_amt')
        ).order_by('-total_amount')
        
        if product_category:
            # Create a new sheet for chart
            ws_chart = wb.create_sheet("Category Chart")
            
            # Add data
            ws_chart.cell(row=1, column=1, value="Category")
            ws_chart.cell(row=1, column=2, value="Amount")
            ws_chart.cell(row=1, column=1).font = Font(bold=True)
            ws_chart.cell(row=1, column=2).font = Font(bold=True)
            
            for idx, cat in enumerate(product_category, 1):
                ws_chart.cell(row=idx+1, column=1, value=cat['product__category__name'] or 'Uncategorized')
                ws_chart.cell(row=idx+1, column=2, value=float(cat['total_amount']))
                ws_chart.cell(row=idx+1, column=2).number_format = '#,##0.00'
            
            # Create Pie Chart
            chart = PieChart()
            data = Reference(ws_chart, min_col=2, min_row=1, max_row=len(product_category)+1)
            labels = Reference(ws_chart, min_col=1, min_row=2, max_row=len(product_category)+1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(labels)
            chart.title = "Product Category Breakdown"
            
            ws_chart.add_chart(chart, "D2")
            ws_chart.column_dimensions['A'].width = 25
            ws_chart.column_dimensions['B'].width = 15
    except Exception as e:
        # Chart creation failed, continue without chart
        pass
    
    # ========================================== #
    # RESPONSE                                  #
    # ========================================== #
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Self_Expense_Report_{date.today()}.xlsx"'
    wb.save(response)
    return response
