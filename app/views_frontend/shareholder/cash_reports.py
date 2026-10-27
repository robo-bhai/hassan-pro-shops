"""Frontend views: shareholder/cash_reports (split from the former shareholder_cash.py)."""
from ...security.permissions import perm_required
from django.db.models.functions import Coalesce
from ...models import *
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Value, DecimalField
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from ...models import Shareholder, ShareholderCashTransaction, CompanyInfo
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from openpyxl.utils import get_column_letter


@login_required
@perm_required('view_shareholders')
def shareholder_cash_report(request):
    """
    Shareholder Cash Report - FULLY OPTIMIZED (400+ → 2 queries)
    """
    from django.db.models import Sum, Q, F, Value, DecimalField, Count
    from django.db.models.functions import Coalesce
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Date filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    shareholder_id = request.GET.get('shareholder', '')
    transaction_type = request.GET.get('type', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ✅ STEP 1: Base queryset
    shareholders = Shareholder.objects.filter(status='active')
    
    if shareholder_id:
        shareholders = shareholders.filter(id=shareholder_id)
    
    # ✅ STEP 2: Filter for transactions
    transaction_filter = Q(
        cash_transactions__created_at__date__gte=from_date_obj,
        cash_transactions__created_at__date__lte=to_date_obj
    )
    
    if transaction_type:
        transaction_filter &= Q(cash_transactions__transaction_type=transaction_type)
    
    # ✅ STEP 3: ✅ CRITICAL FIX - ALL the data in one query!
    shareholders = shareholders.annotate(
        annotated_deposits=Coalesce(
            Sum(
                'cash_transactions__amount',
                filter=transaction_filter & Q(
                    cash_transactions__transaction_type__in=[
                        'deposit', 'dividend', 'balance_dividend', 'transfer_in'
                    ]
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        annotated_withdrawals=Coalesce(
            Sum(
                'cash_transactions__amount',
                filter=transaction_filter & Q(
                    cash_transactions__transaction_type__in=[
                        'withdraw', 'share_purchase', 'transfer_out'
                    ]
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        annotated_balance=Coalesce(
            Sum('cash_balance__balance', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        ),
        annotated_transaction_count=Count(
            'cash_transactions',
            filter=transaction_filter,
            distinct=True
        ),
    )
    
    # ✅ STEP 4: Build report data (NO queries!)
    report_data = []
    total_deposits = Decimal('0.00')
    total_withdrawals = Decimal('0.00')
    total_balance = Decimal('0.00')
    total_transactions = 0
    
    for shareholder in shareholders:
        deposits = shareholder.annotated_deposits
        withdrawals = shareholder.annotated_withdrawals
        balance = shareholder.annotated_balance
        tx_count = shareholder.annotated_transaction_count
        
        if deposits > 0 or withdrawals > 0:
            report_data.append({
                'shareholder': shareholder,
                'deposits': deposits,
                'withdrawals': withdrawals,
                'balance': balance,
                'transaction_count': tx_count,
            })
            
            total_deposits += deposits
            total_withdrawals += withdrawals
            total_balance += balance
            total_transactions += tx_count
    
    report_data.sort(key=lambda x: x['deposits'], reverse=True)
    
    # ✅ STEP 5: Stats (Python calculation)
    stats = {
        'total_shareholders': len(report_data),
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'total_balance': total_balance,
        'total_transactions': total_transactions,
        'net_cash': total_deposits - total_withdrawals,
        'avg_deposit': total_deposits / len(report_data) if report_data else 0,
        'avg_withdrawal': total_withdrawals / len(report_data) if report_data else 0,
    }
    
    # ✅ STEP 6: Type breakdown (1 query)
    type_breakdown_raw = ShareholderCashTransaction.objects.filter(
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).values('transaction_type').annotate(
        count=Count('id'),
        amount=Sum('amount')
    )
    
    type_breakdown = {}
    type_labels = dict(ShareholderCashTransaction.TRANSACTION_TYPES)
    for item in type_breakdown_raw:
        type_breakdown[item['transaction_type']] = {
            'label': type_labels.get(item['transaction_type'], item['transaction_type']),
            'count': item['count'],
            'amount': item['amount'] or Decimal('0.00')
        }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_data': report_data,
        'stats': stats,
        'type_breakdown': type_breakdown,
        'shareholders': Shareholder.objects.filter(status='active'),
        'selected_shareholder': shareholder_id,
        'selected_type': transaction_type,
        'from_date': from_date,
        'to_date': to_date,
        'today': date.today().strftime('%Y-%m-%d'),
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/cash_report.html', context)


@login_required
@perm_required('view_shareholders')
def shareholder_cash_report_detail(request, pk):
    """
    Detailed cash report for a single shareholder
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Get filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    transaction_type = request.GET.get('type', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=90)
        to_date_obj = date.today()
    
    # Get transactions
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder,
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).order_by('-created_at')
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    # Calculate running balance
    running_balance = shareholder.get_balance()
    for trans in transactions.reverse():
        if trans.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']:
            running_balance -= trans.amount
        else:
            running_balance += trans.amount
        trans.running_balance = running_balance
    
    # Summary
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'transactions': transactions,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'current_balance': shareholder.get_balance(),
        'from_date': from_date,
        'to_date': to_date,
        'selected_type': transaction_type,
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/cash_report_detail.html', context)


@login_required
@perm_required('view_shareholders')
def shareholder_cash_report_export(request):
    """
    Export shareholder cash report to Excel
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # Get all transactions
    transactions = ShareholderCashTransaction.objects.filter(
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).select_related('shareholder').order_by('-created_at')
    
    # Create Excel
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    
    wb = openpyxl.Workbook()
    
    # Sheet 1: Summary
    ws = wb.active
    ws.title = "Summary"
    
    # Title
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    ws.merge_cells('A1:F1')
    ws['A1'] = company_name
    ws['A1'].font = Font(bold=True, size=16)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:F2')
    ws['A2'] = "Shareholder Deposit Withdraw Report"
    ws['A2'].font = Font(bold=True, size=14)
    ws['A2'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A3:F3')
    ws['A3'] = f"Period: {from_date} to {to_date}"
    ws['A3'].alignment = Alignment(horizontal='center')
    
    # Summary Data
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    row = 5
    summary_data = [
        ['Metric', 'Amount (Rs.)'],
        ['Total Deposits', float(total_deposits)],
        ['Total Withdrawals', float(total_withdrawals)],
        ['Net Cash Flow', float(total_deposits - total_withdrawals)],
        ['Total Transactions', transactions.count()],
        ['Unique Shareholders', transactions.values('shareholder').distinct().count()],
    ]
    
    for data in summary_data:
        ws.cell(row=row, column=1, value=data[0])
        ws.cell(row=row, column=2, value=data[1])
        if row == 5:
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=2).font = Font(bold=True)
        row += 1
    
    for r in range(6, 10):
        cell = ws.cell(row=r, column=2)
        if isinstance(cell.value, (int, float)):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    # Sheet 2: Transaction Details
    ws2 = wb.create_sheet("Transactions")
    
    headers = ['Date', 'Shareholder', 'Type', 'Amount', 'Balance After', 'Description', 'Reference No']
    for col, header in enumerate(headers, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    row = 2
    for trans in transactions[:500]:  # Limit to 500 rows
        ws2.cell(row=row, column=1, value=trans.created_at.strftime('%d-%m-%Y %I:%M %p'))
        ws2.cell(row=row, column=2, value=trans.shareholder.name)
        ws2.cell(row=row, column=3, value=trans.get_transaction_type_display())
        ws2.cell(row=row, column=4, value=float(trans.amount))
        ws2.cell(row=row, column=4).number_format = '#,##0.00'
        ws2.cell(row=row, column=5, value=float(trans.balance_after))
        ws2.cell(row=row, column=5).number_format = '#,##0.00'
        ws2.cell(row=row, column=6, value=trans.description or '')
        ws2.cell(row=row, column=7, value=trans.reference_no or '')
        row += 1
    
    # Auto-fit columns
    for ws_sheet in [ws, ws2]:
        for col in ws_sheet.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 40)
            ws_sheet.column_dimensions[col_letter].width = adjusted_width
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"Shareholder_Cash_Report_{date.today().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
@perm_required('view_shareholders')
def shareholder_cash_report_pdf(request, pk):
    """
    Generate PDF report for single shareholder cash transactions
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=90)
        to_date_obj = date.today()
    
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder,
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).order_by('-created_at')
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"<b>Shareholder deposit withdraw Report</b>", styles['Heading2']))
    story.append(Paragraph(f"{shareholder.name} ({shareholder.shareholder_code})", styles['Normal']))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Summary
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    summary_data = [
        ['Current Balance:', f"Rs. {shareholder.get_balance():,.2f}"],
        ['Total Deposits:', f"Rs. {total_deposits:,.2f}"],
        ['Total Withdrawals:', f"Rs. {total_withdrawals:,.2f}"],
        ['Net Cash Flow:', f"Rs. {total_deposits - total_withdrawals:,.2f}"],
        ['Total Transactions:', str(transactions.count())],
    ]
    
    summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Transactions Table
    data = [['Date', 'Type', 'Amount', 'Balance After', 'Description']]
    
    for trans in transactions[:100]:
        amount_str = f"+Rs. {trans.amount:,.2f}" if trans.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in'] else f"-Rs. {trans.amount:,.2f}"
        data.append([
            trans.created_at.strftime('%d-%m-%Y %I:%M %p'),
            trans.get_transaction_type_display()[:20],
            amount_str,
            f"Rs. {trans.balance_after:,.2f}",
            (trans.description or '')[:30]
        ])
    
    trans_table = Table(data, repeatRows=1)
    trans_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f6fa')]),
        ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
    ]))
    
    story.append(trans_table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Cash_Report_{shareholder.shareholder_code}.pdf"'
    return response


@login_required
@perm_required('view_shareholders')
def shareholder_cash_stats_api(request):
    """
    AJAX API: Get shareholder cash statistics
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        transactions = ShareholderCashTransaction.objects.filter(
            created_at__date__gte=from_date_obj,
            created_at__date__lte=to_date_obj
        )
        
        total_deposits = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_withdrawals = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Daily trend
        daily_data = []
        current = from_date_obj
        while current <= to_date_obj:
            day_transactions = transactions.filter(created_at__date=current)
            day_deposits = day_transactions.filter(
                transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            day_withdrawals = day_transactions.filter(
                transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            daily_data.append({
                'date': current.strftime('%d-%b'),
                'deposits': float(day_deposits),
                'withdrawals': float(day_withdrawals)
            })
            current += timedelta(days=1)
        
        # Top shareholders
        top_depositors = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).values('shareholder__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]
        
        top_withdrawers = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).values('shareholder__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_deposits': float(total_deposits),
                'total_withdrawals': float(total_withdrawals),
                'net_cash': float(total_deposits - total_withdrawals),
                'total_transactions': transactions.count(),
                'unique_shareholders': transactions.values('shareholder').distinct().count(),
                'daily_data': daily_data,
                'top_depositors': list(top_depositors),
                'top_withdrawers': list(top_withdrawers),
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@perm_required('view_shareholders')
def shareholder_cash_report_all_pdf(request):
    """
    Generate PDF report for ALL shareholders cash transactions
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    shareholder_id = request.GET.get('shareholder', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # Get shareholders
    shareholders = Shareholder.objects.filter(status='active')
    if shareholder_id:
        shareholders = shareholders.filter(id=shareholder_id)
    
    # Build report data
    report_data = []
    total_deposits = Decimal('0.00')
    total_withdrawals = Decimal('0.00')
    total_balance = Decimal('0.00')
    
    for shareholder in shareholders:
        transactions = ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            created_at__date__gte=from_date_obj,
            created_at__date__lte=to_date_obj
        )
        
        deposits = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        withdrawals = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        balance = shareholder.get_balance()
        
        if deposits > 0 or withdrawals > 0 or balance > 0:
            report_data.append({
                'shareholder': shareholder,
                'deposits': deposits,
                'withdrawals': withdrawals,
                'balance': balance,
                'transaction_count': transactions.count(),
                'latest_transaction': transactions.first(),
            })
            
            total_deposits += deposits
            total_withdrawals += withdrawals
            total_balance += balance
    
    # Sort by balance (highest first)
    report_data.sort(key=lambda x: x['balance'], reverse=True)
    
    # Generate PDF
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    
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
    
    # ==========================================
    # HEADER
    # ==========================================
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Shareholder Deposit Withdraw Report ", title_style))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", subtitle_style))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # SUMMARY SECTION
    # ==========================================
    summary_data = [
        ['Metric', 'Value'],
        ['Total Shareholders', str(len(report_data))],
        ['Total Deposits', f"Rs. {total_deposits:,.2f}"],
        ['Total Withdrawals', f"Rs. {total_withdrawals:,.2f}"],
        ['Net Cash Flow', f"Rs. {total_deposits - total_withdrawals:,.2f}"],
        ['Total Balance', f"Rs. {total_balance:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # MAIN TABLE
    # ==========================================
    story.append(Paragraph("<b>Shareholder Summary</b>", styles['Heading3']))
    story.append(Spacer(1, 0.1*inch))
    
    data = [
        ['#', 'Shareholder', 'Code', 'Deposits', 'Withdrawals', 'Net', 'Balance', 'Transactions']
    ]
    
    for idx, item in enumerate(report_data, 1):
        net = item['deposits'] - item['withdrawals']
        data.append([
            str(idx),
            item['shareholder'].name[:25],
            item['shareholder'].shareholder_code,
            f"Rs. {item['deposits']:,.2f}",
            f"Rs. {item['withdrawals']:,.2f}",
            f"Rs. {net:,.2f}",
            f"Rs. {item['balance']:,.2f}",
            str(item['transaction_count'])
        ])
    
    # Add total row
    data.append([
        '', '', 'TOTAL',
        f"Rs. {total_deposits:,.2f}",
        f"Rs. {total_withdrawals:,.2f}",
        f"Rs. {total_deposits - total_withdrawals:,.2f}",
        f"Rs. {total_balance:,.2f}",
        str(sum(item['transaction_count'] for item in report_data))
    ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -2), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fc')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (3, 0), (7, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # FOOTER
    # ==========================================
    story.append(Paragraph(
        f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "This is a computer generated report.",
        ParagraphStyle('Footer2', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    
    # Build document
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Shareholder_Cash_Report_{date.today().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
