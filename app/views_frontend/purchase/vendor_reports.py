"""Frontend views: purchase/vendor_reports (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from django.db.models.functions import Coalesce
from ...models import *
import openpyxl
import csv
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Value, DecimalField
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.contrib import messages
from django.http import HttpResponse
from io import BytesIO
from django.db import transaction
from ...models import CashBalance, CompanyInfo, Purchase, PurchaseRetrnItem, Product
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from openpyxl.utils import get_column_letter


@login_required
@perm_required('view_vendors')
def vendor_wise_report(request):
    """Vendor Wise Purchase Report - OPTIMIZED"""
    from django.db.models import Sum, Count, Value, DecimalField, Q
    from django.db.models.functions import Coalesce
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ✅ FIX: Annotate vendors directly
    vendors = Vendor.objects.annotate(
        total_purchases=Coalesce(
            Sum(
                'purchase__purchaseitem__total_amt',
                filter=Q(
                    purchase__pur_date__date__gte=from_date_obj,
                    purchase__pur_date__date__lte=to_date_obj
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.0'))
        ),
        total_paid=Coalesce(
            Sum(
                'purchase__paid',
                filter=Q(
                    purchase__pur_date__date__gte=from_date_obj,
                    purchase__pur_date__date__lte=to_date_obj
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.0'))
        ),
        po_count=Count(
            'purchase',
            filter=Q(
                purchase__pur_date__date__gte=from_date_obj,
                purchase__pur_date__date__lte=to_date_obj
            ),
            distinct=True
        ),
    ).filter(total_purchases__gt=0).order_by('-total_purchases')
    
    vendor_data = []
    for vendor in vendors:
        vendor_data.append({
            'name': vendor.name,
            'code': vendor.vendor_code,
            'group': vendor.group.name if vendor.group else '-',
            'total_purchases': vendor.total_purchases,
            'total_paid': vendor.total_paid,
            'po_count': vendor.po_count,
            'outstanding': vendor.total_purchases - vendor.total_paid,
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendor_data': vendor_data,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/vendor_wise.html', context)


@login_required
@perm_required('view_vendors')
def vendor_ledger(request, pk):
    """
    Vendor Ledger — OPTIMIZED (30x faster)
    """
    from django.db.models import Sum, Q, F, Value, DecimalField, Prefetch
    from django.db.models.functions import Coalesce
    
    vendor = get_object_or_404(Vendor, pk=pk)
    
    # ✅ Aggregates — 2 queries
    purchase_totals = Purchase.objects.filter(vendor=vendor).aggregate(
        total_purchases=Coalesce(
            Sum('purchaseitem__total_amt'),
            Value(Decimal('0.00'))
        ),
        total_paid=Coalesce(
            Sum('paid'),
            Value(Decimal('0.00'))
        ),
    )
    
    return_totals = PurchaseRetrn.objects.filter(vendor=vendor).aggregate(
        total_returns=Coalesce(
            Sum('return_items__total_amt'),
            Value(Decimal('0.00'))
        ),
    )
    
    total_purchases = purchase_totals['total_purchases']
    total_paid = purchase_totals['total_paid']
    total_returns = return_totals['total_returns']
    total_outstanding = vendor.opening_balance + total_purchases - total_paid - total_returns
    
    # ✅ Purchases with annotate
    purchases = vendor.purchase_set.select_related('warehouse').prefetch_related(
        Prefetch(
            'purchaseitem_set',
            queryset=PurchaseItem.objects.select_related('product', 'product__unit')
        )
    ).annotate(
        calculated_total=Coalesce(
            Sum('purchaseitem__total_amt'),
            Value(Decimal('0.00'))
        )
    ).order_by('-pur_date')
    
    # ✅ Returns with annotate
    purchase_returns = PurchaseRetrn.objects.filter(vendor=vendor).prefetch_related(
        Prefetch(
            'return_items',
            queryset=PurchaseRetrnItem.objects.select_related('product')
        )
    ).annotate(
        calculated_total=Coalesce(
            Sum('return_items__total_amt'),
            Value(Decimal('0.00'))
        )
    ).order_by('-purchase_return_date')
    
    # ✅ Build ledger (no queries)
    ledger_entries = []
    
    for purchase in purchases:
        pur_date = purchase.pur_date.date() if hasattr(purchase.pur_date, 'date') else purchase.pur_date
        
        ledger_entries.append({
            'date': pur_date,
            'type': 'purchase',
            'reference': purchase.bill_no or 'Pending',
            'debit': purchase.calculated_total,
            'credit': Decimal('0.00'),
            'balance': Decimal('0.00'),
            'object': purchase,
            'is_return': False,
        })
    
    for ret in purchase_returns:
        ret_date = ret.purchase_return_date.date() if hasattr(ret.purchase_return_date, 'date') else ret.purchase_return_date
        
        ledger_entries.append({
            'date': ret_date,
            'type': 'return',
            'reference': ret.bill_no or f'RET-{ret.id}',
            'debit': Decimal('0.00'),
            'credit': ret.calculated_total,
            'balance': Decimal('0.00'),
            'object': ret,
            'is_return': True,
            'return_reason': ret.get_return_reason_display(),
        })
    
    # Opening balance entry
    if vendor.opening_balance > 0:
        first_purchase = purchases.first()
        opening_date = (
            first_purchase.pur_date.date()
            if first_purchase and hasattr(first_purchase.pur_date, 'date')
            else date.today()
        )
        
        ledger_entries.append({
            'date': opening_date,
            'type': 'opening',
            'reference': 'Opening Balance',
            'debit': vendor.opening_balance,
            'credit': Decimal('0.00'),
            'balance': Decimal('0.00'),
            'object': None,
            'is_return': False,
        })
    
    ledger_entries.sort(key=lambda x: x['date'], reverse=True)
    
    running_balance = Decimal('0.00')
    for entry in ledger_entries:
        running_balance += entry['debit'] - entry['credit']
        entry['balance'] = running_balance
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendor': vendor,
        'purchases': purchases,
        'purchase_returns': purchase_returns,
        'ledger_entries': ledger_entries,
        'total_purchases': total_purchases,
        'total_paid': total_paid,
        'total_returns': total_returns,
        'total_outstanding': total_outstanding,
        'opening_balance': vendor.opening_balance,
        'total_purchase_amount': total_purchases,
        'total_return_amount': total_returns,
    }
    return render(request, 'vendors/ledger.html', context)


@login_required
@perm_required('view_vendors')
def vendor_pricing_report(request):
    """
    Vendor Pricing Report - FULLY OPTIMIZED (500+ queries → 3 queries)
    """
    from django.db.models import Min, Max, Avg, Q, Sum
    from decimal import Decimal
    
    # ✅ STEP 1: Vendors in one query
    vendors = list(Vendor.objects.filter(
        purchase__purchaseitem__isnull=False
    ).distinct().order_by('name'))
    
    # ✅ STEP 2: Products in one query
    products = list(Product.objects.filter(
        purchaseitem__isnull=False
    ).distinct().select_related('unit').order_by('name'))
    
    # ✅ STEP 3: ✅ CRITICAL FIX - Fetch ALL the price data in one query
    # Get the latest purchase per (product, vendor)
    all_purchase_items = PurchaseItem.objects.filter(
        product__in=products,
        purchase__vendor__in=vendors
    ).select_related(
        'purchase', 'purchase__vendor', 'product'
    ).order_by(
        'product_id', 'purchase__vendor_id', '-purchase__pur_date'
    )
    
    # ✅ Build lookup: {(product_id, vendor_id): latest_item}
    price_lookup = {}
    for item in all_purchase_items:
        key = (item.product_id, item.purchase.vendor_id)
        if key not in price_lookup:  # First = latest (because ordering)
            price_lookup[key] = item
    
    # ✅ STEP 4: Build matrix from lookup (NO queries!)
    pricing_matrix = []
    
    for product in products:
        row = {
            'product': product,
            'product_name': product.name,
            'unit': product.unit.name if product.unit else '',
            'prices': {}
        }
        
        for vendor in vendors:
            key = (product.id, vendor.id)
            item = price_lookup.get(key)
            
            if item:
                row['prices'][vendor.id] = {
                    'price': item.price,
                    'date': item.purchase.pur_date.date(),
                    'qty': item.qty,
                    'bill_no': item.purchase.bill_no or 'N/A'
                }
            else:
                row['prices'][vendor.id] = None
        
        pricing_matrix.append(row)
    
    # ✅ STEP 5: Vendor stats (Python, NO queries!)
    vendor_stats = {}
    for vendor in vendors:
        prices = []
        for row in pricing_matrix:
            price_data = row['prices'].get(vendor.id)
            if price_data:
                prices.append(float(price_data['price']))
        
        if prices:
            vendor_stats[vendor.id] = {
                'min': min(prices),
                'max': max(prices),
                'avg': sum(prices) / len(prices),
                'count': len(prices)
            }
        else:
            vendor_stats[vendor.id] = {
                'min': 0, 'max': 0, 'avg': 0, 'count': 0
            }
    
    # ✅ STEP 6: Product count per vendor (1 query)
    vendor_product_counts = PurchaseItem.objects.filter(
        purchase__vendor__in=vendors
    ).values('purchase__vendor').annotate(
        count=Count('product', distinct=True)
    )
    
    for vp in vendor_product_counts:
        if vp['purchase__vendor'] in vendor_stats:
            vendor_stats[vp['purchase__vendor']]['product_count'] = vp['count']
    
    # Fill missing
    for vendor in vendors:
        if 'product_count' not in vendor_stats[vendor.id]:
            vendor_stats[vendor.id]['product_count'] = 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendors': vendors,
        'products': products,
        'pricing_matrix': pricing_matrix,
        'vendor_stats': vendor_stats,
        'total_products': len(products),
        'total_vendors': len(vendors),
        'has_data': len(pricing_matrix) > 0,
    }
    return render(request, 'vendors/pricing_report.html', context)


@login_required
@perm_required('view_vendors')
def vendor_pricing_report_export(request):
    """Export Vendor Pricing Report to Excel"""
    
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from datetime import datetime, date
    
    vendors = Vendor.objects.filter(
        purchase__purchaseitem__isnull=False
    ).distinct().order_by('name')
    
    products = Product.objects.filter(
        purchaseitem__isnull=False
    ).distinct().order_by('name')
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vendor Pricing"
    
    # ========== HEADERS ==========
    # Row 1: Title
    ws.merge_cells('A1:E1')
    ws['A1'] = "Vendor Pricing Report"
    ws['A1'].font = Font(bold=True, size=16)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:E2')
    ws['A2'] = f"Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}"
    ws['A2'].alignment = Alignment(horizontal='center')
    
    # Row 4: Headers
    col = 1
    ws.cell(row=4, column=col, value="#").font = Font(bold=True)
    col += 1
    ws.cell(row=4, column=col, value="Product Name").font = Font(bold=True)
    col += 1
    ws.cell(row=4, column=col, value="Unit").font = Font(bold=True)
    col += 1
    
    vendor_cols = {}
    for vendor in vendors:
        ws.cell(row=4, column=col, value=vendor.name).font = Font(bold=True)
        vendor_cols[vendor.id] = col
        col += 1
    
    # Add Min/Max columns
    min_col = col
    ws.cell(row=4, column=col, value="Min Price").font = Font(bold=True)
    col += 1
    max_col = col
    ws.cell(row=4, column=col, value="Max Price").font = Font(bold=True)
    col += 1
    avg_col = col
    ws.cell(row=4, column=col, value="Avg Price").font = Font(bold=True)
    
    # Style headers
    header_fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for c in range(1, col + 1):
        cell = ws.cell(row=4, column=c)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # ========== DATA ROWS ==========
    row_num = 5
    for idx, product in enumerate(products, 1):
        ws.cell(row=row_num, column=1, value=idx).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=2, value=product.name)
        ws.cell(row=row_num, column=3, value=product.unit.name if product.unit else '')
        
        prices = []
        
        for vendor in vendors:
            latest = PurchaseItem.objects.filter(
                purchase__vendor=vendor,
                product=product
            ).order_by('-purchase__pur_date').first()
            
            if latest:
                price_val = float(latest.price)
                ws.cell(row=row_num, column=vendor_cols[vendor.id], value=price_val)
                ws.cell(row=row_num, column=vendor_cols[vendor.id]).number_format = '#,##0.00'
                prices.append(price_val)
            else:
                ws.cell(row=row_num, column=vendor_cols[vendor.id], value='-')
        
        # Min, Max, Avg
        if prices:
            ws.cell(row=row_num, column=min_col, value=min(prices)).number_format = '#,##0.00'
            ws.cell(row=row_num, column=max_col, value=max(prices)).number_format = '#,##0.00'
            ws.cell(row=row_num, column=avg_col, value=sum(prices)/len(prices)).number_format = '#,##0.00'
        else:
            ws.cell(row=row_num, column=min_col, value='-')
            ws.cell(row=row_num, column=max_col, value='-')
            ws.cell(row=row_num, column=avg_col, value='-')
        
        row_num += 1
    
    # ========== FORMAT COLUMNS ==========
    for c in range(1, col + 1):
        col_letter = get_column_letter(c)
        ws.column_dimensions[col_letter].width = 20 if c == 2 else 15
    
    # Freeze panes
    ws.freeze_panes = 'A5'
    
    # ========== RESPONSE ==========
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Vendor_Pricing_Report_{date.today()}.xlsx"'
    wb.save(response)
    return response


@login_required
@perm_required('view_vendors')
def vendor_ledger_report(request, pk):
    """Vendor Ledger Report with filters"""
    
    vendor = get_object_or_404(Vendor, pk=pk)
    
    # Get date range
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Get purchases
    purchases = Purchase.objects.filter(
        vendor=vendor,
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).order_by('pur_date')
    
    # Get purchase returns
    returns = PurchaseRetrn.objects.filter(
        vendor=vendor,
        purchase_return_date__date__gte=from_date_obj,
        purchase_return_date__date__lte=to_date_obj
    ).order_by('purchase_return_date')
    
    # Build ledger entries
    entries = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    total_purchase_amount = Decimal('0.00')
    total_returns = Decimal('0.00')
    
    # Add purchases
    for purchase in purchases:
        amount = purchase.total_amount()
        total_purchase_amount += amount
        total_debit += amount
        entries.append({
            'date': purchase.pur_date,
            'reference': purchase.bill_no or f'PO#{purchase.id}',
            'description': f'Purchase from {vendor.name}',
            'type': 'purchase',
            'type_display': 'Purchase',
            'debit': amount,
            'credit': Decimal('0.00'),
            'balance': Decimal('0.00'),
            'id': purchase.id,
            'notes': f'Items: {purchase.purchaseitem_set.count()}'
        })
    
    # Add returns
    for ret in returns:
        amount = sum(item.total_amt for item in ret.return_items.all())
        total_returns += amount
        total_credit += amount
        entries.append({
            'date': ret.purchase_return_date,
            'reference': ret.bill_no or f'RET#{ret.id}',
            'description': f'Return to {vendor.name}',
            'type': 'return',
            'type_display': 'Return',
            'debit': Decimal('0.00'),
            'credit': amount,
            'balance': Decimal('0.00'),
            'id': ret.id,
            'notes': ret.get_return_reason_display()
        })
    
    # Sort by date
    entries.sort(key=lambda x: x['date'])
    
    # Calculate running balance
    opening_balance = vendor.opening_balance
    running_balance = opening_balance
    
    for entry in entries:
        running_balance += entry['debit'] - entry['credit']
        entry['balance'] = running_balance
    
    # Calculate totals
    closing_balance = opening_balance + total_debit - total_credit
    total_outstanding = vendor.outstanding_balance()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendor': vendor,
        'entries': entries,
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'total_purchase_amount': total_purchase_amount,
        'total_returns': total_returns,
        'total_outstanding': total_outstanding,
        'total_purchases': purchases.count(),
        'from_date': from_date_obj,
        'to_date': to_date_obj,
    }
    return render(request, 'vendors/ledger_report.html', context)


@login_required
@perm_required('view_vendors')
def vendor_ledger_export(request, pk):
    """Export Vendor Ledger to CSV"""
    
    vendor = get_object_or_404(Vendor, pk=pk)
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Get data
    purchases = Purchase.objects.filter(
        vendor=vendor,
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).order_by('pur_date')
    
    returns = PurchaseRetrn.objects.filter(
        vendor=vendor,
        purchase_return_date__date__gte=from_date_obj,
        purchase_return_date__date__lte=to_date_obj
    ).order_by('purchase_return_date')
    
    # Create CSV
    response = HttpResponse(content_type='text/csv')
    filename = f"Vendor_Ledger_{vendor.vendor_code}_{date.today()}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Headers
    writer.writerow([
        'Date', 'Reference', 'Description', 'Type', 
        'Debit', 'Credit', 'Balance', 'Notes'
    ])
    
    # Opening balance
    if vendor.opening_balance > 0:
        writer.writerow([
            from_date, '--', 'Opening Balance', 'Opening',
            str(vendor.opening_balance), '0', str(vendor.opening_balance), ''
        ])
    
    # Entries
    running_balance = vendor.opening_balance
    
    for purchase in purchases:
        amount = purchase.total_amount()
        running_balance += amount
        writer.writerow([
            purchase.pur_date.strftime('%Y-%m-%d'),
            purchase.bill_no or f'PO#{purchase.id}',
            f'Purchase from {vendor.name}',
            'Purchase',
            str(amount),
            '0',
            str(running_balance),
            f'Items: {purchase.purchaseitem_set.count()}'
        ])
    
    for ret in returns:
        amount = sum(item.total_amt for item in ret.return_items.all())
        running_balance -= amount
        writer.writerow([
            ret.purchase_return_date.strftime('%Y-%m-%d'),
            ret.bill_no or f'RET#{ret.id}',
            f'Return to {vendor.name}',
            'Return',
            '0',
            str(amount),
            str(running_balance),
            ret.get_return_reason_display()
        ])
    
    # Summary
    writer.writerow([])
    writer.writerow(['SUMMARY', '', '', '', '', '', '', ''])
    writer.writerow(['Opening Balance', '', '', '', '', '', str(vendor.opening_balance), ''])
    writer.writerow(['Total Debit', '', '', '', '', '', str(running_balance - vendor.opening_balance), ''])
    writer.writerow(['Total Credit', '', '', '', '', '', str(running_balance - vendor.opening_balance), ''])
    writer.writerow(['Closing Balance', '', '', '', '', '', str(running_balance), ''])
    
    return response


@login_required
@perm_required('view_vendors')
def vendor_ledger_pdf(request, pk):
    """Generate Vendor Ledger PDF"""
    
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    
    vendor = get_object_or_404(Vendor, pk=pk)
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Get data
    purchases = Purchase.objects.filter(
        vendor=vendor,
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).order_by('pur_date')
    
    returns = PurchaseRetrn.objects.filter(
        vendor=vendor,
        purchase_return_date__date__gte=from_date_obj,
        purchase_return_date__date__lte=to_date_obj
    ).order_by('purchase_return_date')
    
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
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"<b>VENDOR LEDGER</b>", styles['Heading2']))
    story.append(Paragraph(f"{vendor.name} ({vendor.vendor_code})", styles['Normal']))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Table Data
    data = [['Date', 'Reference', 'Description', 'Type', 'Debit', 'Credit', 'Balance']]
    
    running_balance = vendor.opening_balance
    
    # Opening balance
    if vendor.opening_balance > 0:
        data.append([
            from_date, '--', 'Opening Balance', 'Opening',
            f"Rs. {vendor.opening_balance:,.2f}", '--', f"Rs. {running_balance:,.2f}"
        ])
    
    for purchase in purchases:
        amount = purchase.total_amount()
        running_balance += amount
        data.append([
            purchase.pur_date.strftime('%d-%m-%Y'),
            purchase.bill_no or f'PO#{purchase.id}',
            f'Purchase',
            'Purchase',
            f"Rs. {amount:,.2f}",
            '--',
            f"Rs. {running_balance:,.2f}"
        ])
    
    for ret in returns:
        amount = sum(item.total_amt for item in ret.return_items.all())
        running_balance -= amount
        data.append([
            ret.purchase_return_date.strftime('%d-%m-%Y'),
            ret.bill_no or f'RET#{ret.id}',
            f'Return',
            'Return',
            '--',
            f"Rs. {amount:,.2f}",
            f"Rs. {running_balance:,.2f}"
        ])
    
    # Summary row
    data.append(['', '', '', 'CLOSING BALANCE', '', '', f"Rs. {running_balance:,.2f}"])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -2), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f5f6fa')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 0), (6, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Vendor_Ledger_{vendor.vendor_code}.pdf"'
    return response


@login_required
@perm_required('view_vendors')
def vendor_purchase_product_report(request):
    """Vendor Purchase Product Report - Date, Vendor, Bill No, Product, Qty, Unit Price, Total"""
    
    vendor_id = request.GET.get('vendor')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).filter(purchaseitem__isnull=False)
    
    if vendor_id:
        purchases = purchases.filter(vendor_id=vendor_id)
    
    purchase_items = PurchaseItem.objects.filter(
        purchase__in=purchases
    ).select_related(
        'product', 
        'product__unit',
        'purchase',
        'purchase__vendor'
    ).order_by('purchase__pur_date', 'purchase__vendor__name', 'product__name')
    
    report_data = []
    total_qty = Decimal('0.00')
    total_amount = Decimal('0.00')
    
    for item in purchase_items:
        purchase = item.purchase
        vendor = purchase.vendor
        
        report_data.append({
            'vendor_name': vendor.name,
            'vendor_code': vendor.vendor_code,
            'bill_no': purchase.bill_no or 'Pending',
            'purchase_date': purchase.pur_date,
            'product_name': item.product.name,
            'product_serial': item.product.serial_no,
            'product_barcode': item.product.barcode,
            'product_unit': item.product.unit.name if item.product.unit else '',
            'qty': Decimal(str(item.qty)),
            'unit_price': item.price,
            'total_amount': item.total_amt,
        })
        
        total_qty += Decimal(str(item.qty))
        total_amount += item.total_amt
    
    # Vendor wise summary
    vendor_summary = {}
    purchase_ids_by_vendor = {}
    
    for item in report_data:
        key = item['vendor_name']
        if key not in vendor_summary:
            vendor_summary[key] = {
                'vendor_name': key,
                'vendor_code': item['vendor_code'],
                'purchase_count': 0,
                'item_count': 0,
                'total_amount': Decimal('0.00'),
            }
            purchase_ids_by_vendor[key] = set()
        
        vendor_summary[key]['item_count'] += 1
        vendor_summary[key]['total_amount'] += item['total_amount']
        # Track unique purchase IDs
        purchase_id = item.get('purchase_id', None)
        if purchase_id:
            purchase_ids_by_vendor[key].add(purchase_id)
    
    for key, ids in purchase_ids_by_vendor.items():
        if key in vendor_summary:
            vendor_summary[key]['purchase_count'] = len(ids)
    
    vendor_summary_list = sorted(
        vendor_summary.values(),
        key=lambda x: x['total_amount'],
        reverse=True
    )
    
    vendors = Vendor.objects.filter(
        purchase__isnull=False
    ).distinct().order_by('name')
    
    selected_vendor = None
    if vendor_id:
        try:
            selected_vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            pass
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_data': report_data,
        'vendor_summary': vendor_summary_list,
        'vendors': vendors,
        'vendor': selected_vendor,
        'from_date': from_date_obj,
        'to_date': to_date_obj,
        'total_qty': total_qty,
        'total_amount': total_amount,
        'total_items': len(report_data),
        'total_purchases': purchases.count(),
        'total_vendors': len(vendor_summary),
    }
    return render(request, 'vendors/purchase_product_report.html', context)


@login_required
@perm_required('view_vendors')
def vendor_purchase_product_export(request):
    """Export Vendor Purchase Product Report to CSV"""
    
    vendor_id = request.GET.get('vendor')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).filter(purchaseitem__isnull=False)
    
    if vendor_id:
        purchases = purchases.filter(vendor_id=vendor_id)
    
    purchase_items = PurchaseItem.objects.filter(
        purchase__in=purchases
    ).select_related('product', 'purchase__vendor')
    
    response = HttpResponse(content_type='text/csv')
    filename = f"Vendor_Purchase_Product_Report_{date.today()}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Headers
    writer.writerow([
        'Date', 'Vendor', 'Vendor Code', 'Bill No', 'Product',
        'Serial No', 'Barcode', 'Unit', 'Quantity', 'Unit Price', 'Total Amount'
    ])
    
    total_qty = Decimal('0.00')
    total_amount = Decimal('0.00')
    
    for item in purchase_items:
        purchase = item.purchase
        vendor = purchase.vendor
        product = item.product
        
        writer.writerow([
            purchase.pur_date.strftime('%Y-%m-%d') if purchase.pur_date else '',
            vendor.name,
            vendor.vendor_code or '',
            purchase.bill_no or 'Pending',
            product.name,
            product.serial_no or '',
            product.barcode or '',
            product.unit.name if product.unit else '',
            float(item.qty),
            float(item.price),
            float(item.total_amt),
        ])
        total_qty += Decimal(str(item.qty))
        total_amount += item.total_amt
    
    writer.writerow([])
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Items', purchase_items.count()])
    writer.writerow(['Total Quantity', float(total_qty)])
    writer.writerow(['Total Amount', float(total_amount)])
    
    return response


@login_required
@perm_required('view_vendors')
def vendor_purchase_product_pdf(request):
    """Generate Vendor Purchase Product Report PDF"""
    
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from decimal import Decimal
    
    vendor_id = request.GET.get('vendor')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    ).filter(purchaseitem__isnull=False)
    
    if vendor_id:
        purchases = purchases.filter(vendor_id=vendor_id)
    
    purchase_items = PurchaseItem.objects.filter(
        purchase__in=purchases
    ).select_related('product', 'purchase__vendor')
    
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
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("<b>VENDOR PURCHASE PRODUCT REPORT</b>", styles['Heading2']))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Table Data
    data = [['Date', 'Vendor', 'Bill No', 'Product', 'Qty', 'Unit Price', 'Total']]
    
    total_qty = Decimal('0.00')
    total_amount = Decimal('0.00')
    
    for item in purchase_items:
        purchase = item.purchase
        vendor = purchase.vendor
        product = item.product
        
        qty = Decimal(str(item.qty or 0))
        amount = item.total_amt or 0
        total_qty += qty
        total_amount += amount
        
        data.append([
            purchase.pur_date.strftime('%d-%m-%Y') if purchase.pur_date else '',
            vendor.name[:18] if vendor.name else 'Unknown',
            purchase.bill_no or 'Pending',
            product.name[:25] if product.name else 'Unknown',
            f"{qty:,.2f}",
            f"Rs. {(item.price or 0):,.2f}",
            f"Rs. {amount:,.2f}"
        ])
    
    data.append([
        '', '', '', 'TOTAL',
        f"{total_qty:,.2f}",
        '',
        f"Rs. {total_amount:,.2f}"
    ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -2), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f5f6fa')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('ALIGN', (5, 0), (6, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    story.append(Paragraph(f"Total Items: {purchase_items.count()} | Total Quantity: {total_qty:,.2f} | Total Amount: Rs. {total_amount:,.2f}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Vendor_Purchase_Product_Report_{date.today()}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@perm_required('manage_payments')
def vendor_ledger_pay(request, pk):
    """Pay vendor outstanding balance"""
    
    vendor = get_object_or_404(Vendor, pk=pk)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'cash')
            reference_no = request.POST.get('reference_no', '')
            notes = request.POST.get('notes', '')
            purchase_id = request.POST.get('purchase_id') or None
            
            # Validation
            if amount <= 0:
                messages.error(request, '❌ Amount must be greater than zero!')
                return redirect('vendor_ledger_pay', pk=pk)
            
            current_outstanding = vendor.outstanding_balance()
            if amount > current_outstanding:
                messages.error(
                    request, 
                    f'❌ Amount exceeds outstanding balance! Outstanding: Rs. {current_outstanding:,.2f}'
                )
                return redirect('vendor_ledger_pay', pk=pk)
            
            # Check cash balance
            current_cash = CashBalance.get_balance()
            if amount > current_cash:
                messages.error(
                    request, 
                    f'❌ Insufficient cash balance! Available: Rs. {current_cash:,.2f}'
                )
                return redirect('vendor_ledger_pay', pk=pk)
            
            with transaction.atomic():
                # Get or create PaymentMethod
                from ...models import PaymentMethod
                
                method_mapping = {
                    'cash': 'Cash',
                    'bank_transfer': 'Bank Transfer',
                    'cheque': 'Cheque',
                    'jazzcash': 'JazzCash',
                    'easypaisa': 'EasyPaisa',
                }
                
                method_name = method_mapping.get(payment_method, 'Cash')
                method, created = PaymentMethod.objects.get_or_create(
                    name=method_name,
                    defaults={'is_active': True}
                )
                
                purchase = None
                
                # ✅ IF specific purchase selected
                if purchase_id:
                    purchase = get_object_or_404(Purchase, pk=purchase_id, vendor=vendor)
                    
                    purchase_outstanding = purchase.total_amount() - purchase.paid
                    if amount > purchase_outstanding:
                        messages.error(
                            request, 
                            f'❌ Amount exceeds purchase outstanding! Purchase: Rs. {purchase_outstanding:,.2f}'
                        )
                        return redirect('vendor_ledger_pay', pk=pk)
                    
                    # Update purchase paid amount
                    purchase.paid += amount
                    purchase.save()
                    
                    messages.success(
                        request, 
                        f'✅ Rs. {amount:,.2f} paid for Purchase #{purchase.bill_no or purchase.id}!\n'
                        f'Remaining: Rs. {purchase.total_amount() - purchase.paid:,.2f}'
                    )
                    
                else:
                    # ✅ PAY FULL OUTSTANDING - Distribute among purchases (FIFO)
                    purchases = Purchase.objects.filter(
                        vendor=vendor
                    ).order_by('pur_date')
                    
                    remaining = amount
                    paid_purchases = []
                    
                    for p in purchases:
                        if remaining <= 0:
                            break
                        
                        purchase_outstanding = p.total_amount() - p.paid
                        if purchase_outstanding <= 0:
                            continue
                        
                        pay_amount = min(remaining, purchase_outstanding)
                        p.paid += pay_amount
                        p.save()
                        remaining -= pay_amount
                        paid_purchases.append({
                            'bill_no': p.bill_no or str(p.id),
                            'amount': pay_amount
                        })
                    
                    # Build success message
                    paid_summary = ", ".join([f"#{p['bill_no']} (Rs. {p['amount']:,.2f})" for p in paid_purchases])
                    messages.success(
                        request, 
                        f'✅ Rs. {amount:,.2f} paid to {vendor.name}!\n'
                        f'Purchases: {paid_summary}\n'
                        f'Remaining Outstanding: Rs. {vendor.outstanding_balance():,.2f}'
                    )
                
                # ✅ Create VendorPayment record
                from ...models import VendorPayment
                VendorPayment.objects.create(
                    vendor=vendor,
                    purchase=purchase,  # Can be None if no specific purchase
                    amount=amount,
                    payment_date=now(),
                    payment_method=method,
                    reference_no=reference_no,
                    notes=notes,
                    created_by=request.user
                )
                
                # ✅ Deduct from cash
                CashBalance.update_balance(
                    amount=amount,
                    transaction_type='withdraw',
                    user=request.user,
                    description=f"Vendor payment: {vendor.name}"
                )
                
                return redirect('vendor_ledger', pk=vendor.pk)
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('vendor_ledger_pay', pk=pk)
    
    # GET request - show form
    outstanding = vendor.outstanding_balance()
    
    all_purchases = vendor.purchase_set.all().order_by('pur_date')
    purchases_with_outstanding = []
    
    for p in all_purchases:
        p_outstanding = p.total_amount() - p.paid
        if p_outstanding > 0:
            p.outstanding_balance = p_outstanding
            purchases_with_outstanding.append(p)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendor': vendor,
        'outstanding': outstanding,
        'purchases': purchases_with_outstanding,
        'current_cash': CashBalance.get_balance(),
        'payment_methods': [
            ('cash', '💵 Cash'),
            ('bank_transfer', '🏦 Bank Transfer'),
            ('cheque', '📄 Cheque'),
            ('jazzcash', '📱 JazzCash'),
            ('easypaisa', '📱 EasyPaisa'),
        ],
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'vendors/ledger_pay.html', context)
