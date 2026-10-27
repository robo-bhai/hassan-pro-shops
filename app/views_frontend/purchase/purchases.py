"""Frontend views: purchase/purchases (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from ...models import *
import logging
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Value, DecimalField, Avg
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ...models import CashBalance, Location, CompanyInfo, Purchase, PurchaseRetrnItem, Product
from ...store import store_access as _sa
from ...store import store_receive as _sr
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


@login_required
@perm_required('view_purchases')
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related(
            'vendor', 'warehouse', 'vendor__group',
            'created_by', 'monthly_purchase'
        ).prefetch_related(
            'purchaseitem_set__product',
            'purchaseitem_set__product__unit',
            'returns__return_items__product'
        ),
        pk=pk
    )
    
    items = purchase.purchaseitem_set.select_related('product', 'product__unit').all()
    
    returns = PurchaseRetrn.objects.filter(purchase=purchase)
    for ret in returns:
        ret.total_return_amount = sum(item.total_amt for item in ret.return_items.all())
    
    total_return_amount = returns.aggregate(
        total=Sum('return_items__total_amt')
    )['total'] or Decimal('0.0')
    
    related_grns = []
    try:
        if hasattr(purchase, 'converted_from_grn'):
            grn = purchase.converted_from_grn
            related_grns = [grn]
    except:
        pass
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'purchase': purchase,
        'items': items,
        'related_grns': related_grns,
        'returns': returns,
        'total_return_amount': total_return_amount,
        'vendor': purchase.vendor,
        'warehouse': purchase.warehouse,
        'total_amount': purchase.total_amount(),
        'outstanding_balance': purchase.outstanding_balance(),
        'total_paid': purchase.paid,
        'item_count': items.count(),
        'total_qty': items.aggregate(total=Sum('qty'))['total'] or 0,
        # ✅ NEW: Cash balance for payment modal
        'cash_balance': CashBalance.get_balance(),
    }
    return render(request, 'purchases/purchase_detail.html', context)


@login_required
@perm_required('create_purchases')
def purchase_create(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                vendor_id = request.POST.get('vendor')
                warehouse_id = request.POST.get('warehouse')
                bill_no = request.POST.get('bill_no', '')
                paid = Decimal(request.POST.get('paid', 0))
                
                # ✅ NEW: Cash payment fields
                payment_type = request.POST.get('payment_type', 'credit')
                cash_used = Decimal(request.POST.get('cash_used', 0))
                
                # ✅ FIX: Purchase date field - THIS IS IMPORTANT
                pur_date = request.POST.get('pur_date')
                if pur_date:
                    pur_date_obj = datetime.strptime(pur_date, '%Y-%m-%d').date()
                else:
                    pur_date_obj = now().date()
                
                if not vendor_id:
                    messages.error(request, 'Please select a vendor!')
                    return redirect('purchase_create')
                if not warehouse_id:
                    messages.error(request, 'Please select a warehouse!')
                    return redirect('purchase_create')
                if not _sr.can_receive(request.user, warehouse_id):
                    messages.error(request, '❌ You cannot receive goods in this store (you are not a keeper/manager of that store team).')
                    return redirect('purchase_create')
                
                product_ids = request.POST.getlist('product_id[]')
                if not product_ids or not any(product_ids):
                    messages.error(request, 'Please add at least one product!')
                    return redirect('purchase_create')
                
                # ✅ CASH BALANCE VALIDATION - STRICT CHECK
                current_balance = CashBalance.get_balance()
                
                # If the payment type is cash or mixed and cash_used > 0
                if payment_type == 'cash':
                    if cash_used <= 0:
                        messages.error(request, '❌ Cash payment selected but cash amount is 0!')
                        return redirect('purchase_create')
                    if cash_used > current_balance:
                        messages.error(request, f'❌ Insufficient cash balance! Available: Rs. {current_balance:,.2f}, Required: Rs. {cash_used:,.2f}')
                        return redirect('purchase_create')
                    if cash_used > paid:
                        messages.error(request, f'❌ Cash used cannot be more than total paid amount!')
                        return redirect('purchase_create')
                        
                elif payment_type == 'mixed':
                    if cash_used > 0:
                        if cash_used > current_balance:
                            messages.error(request, f'❌ Insufficient cash balance for cash payment! Available: Rs. {current_balance:,.2f}, Required: Rs. {cash_used:,.2f}')
                            return redirect('purchase_create')
                        if cash_used > paid:
                            messages.error(request, f'❌ Cash used cannot be more than total paid amount!')
                            return redirect('purchase_create')
                
                # ✅ FIX: set pur_date on the purchase
                purchase = Purchase(
                    vendor_id=vendor_id,
                    warehouse_id=warehouse_id,
                    bill_no=bill_no if bill_no else None,
                    paid=paid,
                    payment_type=payment_type,
                    cash_used=cash_used,
                    pur_date=pur_date_obj  # ✅ ADD THIS LINE
                )
                purchase.created_by = request.user
                purchase.save()
                
                qtys = request.POST.getlist('qty[]')
                prices = request.POST.getlist('price[]')
                batch_nos = request.POST.getlist('batch_no[]')  # [agri-edition:view-lists]
                expiry_dates = request.POST.getlist('expiry_date[]')

                def _agri_exp(i):
                    v = (expiry_dates[i] if i < len(expiry_dates) else '').strip()
                    return datetime.strptime(v, '%Y-%m-%d').date() if v else None

                
                for i in range(len(product_ids)):
                    if product_ids[i]:
                        PurchaseItem.objects.create(
                            purchase=purchase,
                            product_id=product_ids[i],
                            qty=float(qtys[i]),
                            price=Decimal(prices[i]),
                            batch_no=((batch_nos[i] if i < len(batch_nos) else '').strip()[:50] or None),  # [agri-edition:view-create]
                            expiry_date=_agri_exp(i),
                        )
                
                # ✅ If cash was used, deduct the cash balance
                if cash_used > 0:
                    CashBalance.update_balance(
                        amount=cash_used,
                        transaction_type='purchase',
                        user=request.user,
                        description=f"Purchase #{purchase.bill_no or purchase.id} - {purchase.vendor.name}"
                    )
                    messages.info(request, f'💰 Rs. {cash_used:,.2f} deducted from cash balance!')
                
                messages.success(request, f'✅ Purchase #{purchase.bill_no or purchase.id} created! Date: {pur_date_obj.strftime("%d-%m-%Y")}')
                return redirect('purchase_list')
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('purchase_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendors': Vendor.objects.all().order_by('vendor_code'),
        'warehouses': _sr.receivable_warehouses(request.user),
        'products': Product.objects.all().order_by('name')[:50],
        'cash_balance': CashBalance.get_balance(),
        'today': date.today(),  
        'vendor_groups': VendorGroup.objects.all(),
        'locations': Location.objects.all(),
    }
    return render(request, 'purchases/create.html', context)


@login_required
@perm_required('view_purchases')
def purchase_tax_summary(request):
    """Purchase Tax Summary Report"""
    from decimal import Decimal
    from datetime import date, timedelta, datetime
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date_obj,
        pur_date__date__lte=to_date_obj
    )
    
    total_purchases = sum(p.total_amount() for p in purchases)
    tax_rate = Decimal('16')  # ✅ Convert to Decimal
    tax_percent = tax_rate / Decimal('100')
    total_tax = total_purchases * tax_percent  # ✅ This will work now
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_purchases': total_purchases,
        'total_tax': total_tax,
        'tax_rate': tax_rate,
    }
    return render(request, 'reports/purchase_tax_summary.html', context)


@login_required
@perm_required('view_purchases', 'create_purchases', 'edit_purchases')
def get_purchase_products(request):
    """
    AJAX: Show all products of the Purchase, only those whose remaining quantity is > 0
    Also shows return history for each product
    """
    purchase_id = request.GET.get('purchase_id')
    
    if not purchase_id:
        return JsonResponse({
            'success': False, 
            'message': 'Purchase ID required'
        })
    
    try:
        purchase = Purchase.objects.get(id=purchase_id)
        products = {}
        total_remaining = 0
        total_returned = 0
        
        # ✅ Loop over all purchase items
        for item in purchase.purchaseitem_set.all():
            # ✅ Calculate total returned quantity for this product (across all returns)
            returned_qty = PurchaseRetrnItem.objects.filter(
                purchase_return__purchase=purchase,
                product=item.product
            ).aggregate(total=Sum('qty'))['total'] or Decimal('0.00')
            
            # ✅ Remaining quantity calculate karein
            original_qty = Decimal(str(item.qty))
            remaining_qty = original_qty - returned_qty
            
            # ✅ Show only products whose remaining quantity > 0
            if remaining_qty > 0:
                products[str(item.product.id)] = {
                    'name': item.product.name,
                    'price': float(item.price),
                    'original_qty': float(original_qty),
                    'returned_qty': float(returned_qty),
                    'remaining_qty': float(remaining_qty),
                    'unit': item.product.unit.name if item.product.unit else '',
                    'product_id': item.product.id,
                    'barcode': item.product.barcode or '',
                    'serial_no': item.product.serial_no or '',
                    'fully_returned': False
                }
                total_remaining += remaining_qty
            else:
                # ✅ Product fully returned - still show in history
                if returned_qty > 0:
                    products[str(item.product.id)] = {
                        'name': item.product.name,
                        'price': float(item.price),
                        'original_qty': float(original_qty),
                        'returned_qty': float(returned_qty),
                        'remaining_qty': 0,
                        'unit': item.product.unit.name if item.product.unit else '',
                        'product_id': item.product.id,
                        'barcode': item.product.barcode or '',
                        'serial_no': item.product.serial_no or '',
                        'fully_returned': True
                    }
            
            total_returned += returned_qty
        
        # ✅ Get all returns for this purchase
        returns = PurchaseRetrn.objects.filter(purchase=purchase)
        return_history = []
        for ret in returns:
            ret_items = []
            for r_item in ret.return_items.all():
                ret_items.append({
                    'product_name': r_item.product.name,
                    'product_id': r_item.product.id,
                    'qty': float(r_item.qty),
                    'amount': float(r_item.total_amt),
                    'price': float(r_item.price)
                })
            return_history.append({
                'id': ret.id,
                'date': ret.purchase_return_date.strftime('%d-%m-%Y %I:%M %p'),
                'reason': ret.get_return_reason_display(),
                'bill_no': ret.bill_no or 'N/A',
                'items': ret_items,
                'total_amount': float(sum(item['amount'] for item in ret_items)),
                'total_items': len(ret_items)
            })
        
        # ✅ Sort return history by date (newest first)
        return_history.sort(key=lambda x: x['date'], reverse=True)
        
        # ✅ Available products count
        available_count = len([p for p in products.values() if p['remaining_qty'] > 0])
        
        return JsonResponse({
            'success': True,
            'products': products,
            'total_remaining': float(total_remaining),
            'total_returned': float(total_returned),
            'return_history': return_history,
            'purchase_bill_no': purchase.bill_no or 'Pending',
            'purchase_date': purchase.pur_date.strftime('%d-%m-%Y'),
            'vendor_name': purchase.vendor.name,
            'vendor_id': purchase.vendor.id,
            'total_products': len(products),
            'available_products': available_count,
            'fully_returned_products': len(products) - available_count,
            'message': f'{available_count} products available for return'
        })
        
    except Purchase.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'message': 'Purchase not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e)
        })


@login_required
@perm_required('view_purchases')
def purchase_pdf(request, pk):
    """Generate Simple Professional Purchase PDF"""
    purchase = get_object_or_404(
        Purchase.objects.select_related('vendor', 'warehouse').prefetch_related('purchaseitem_set__product'), 
        pk=pk
    )
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from django.utils.timezone import localtime, now
    from decimal import Decimal
    from io import BytesIO
    from django.http import HttpResponse
    
    buffer = BytesIO()
    
    # ========================================== #
    # STYLES                                     #
    # ========================================== #
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=5,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=11,
        fontName='Helvetica-Bold',
        spaceAfter=6
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=9,
        leading=14
    )
    
    small_style = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey
    )
    
    # Get Company Info
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "Company Name"
    company_address = company.address if company else ""
    company_phone = company.contact_number if company else ""
    
    # ========================================== #
    # BUILD DOCUMENT                            #
    # ========================================== #
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )
    
    story = []
    
    # ========================================== #
    # HEADER                                     #
    # ========================================== #
    
    # Company Name
    story.append(Paragraph(f'<b>{company_name.upper()}</b>', title_style))
    
    # Company Address
    if company_address:
        story.append(Paragraph(company_address, normal_style))
    if company_phone:
        story.append(Paragraph(f'Phone: {company_phone}', normal_style))
    
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph('-' * 80, small_style))
    story.append(Spacer(1, 0.15*inch))
    
    # ========================================== #
    # INVOICE TITLE                              #
    # ========================================== #
    
    story.append(Paragraph(f'<b>PURCHASE INVOICE</b>', heading_style))
    story.append(Paragraph(f'Bill No: {purchase.bill_no or "Pending"}', normal_style))
    story.append(Paragraph(f'Date: {localtime(purchase.pur_date).strftime("%d-%m-%Y") if purchase.pur_date else "-"}', normal_style))
    story.append(Spacer(1, 0.1*inch))
    
    # ========================================== #
    # VENDOR & PURCHASE INFO                     #
    # ========================================== #
    
    # Vendor Info
    vendor_text = f"""
    <b>VENDOR DETAILS</b><br/>
    Name: {purchase.vendor.name}<br/>
    Code: {purchase.vendor.vendor_code or "N/A"}<br/>
    Contact: {purchase.vendor.contact_number or "Not provided"}<br/>
    Address: {purchase.vendor.address or "Not provided"}
    """
    story.append(Paragraph(vendor_text, normal_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Purchase Info
    purchase_text = f"""
    <b>PURCHASE INFO</b><br/>
    Warehouse: {purchase.warehouse.name if purchase.warehouse else "-"}<br/>
    Payment Type: {purchase.get_payment_type_display() if hasattr(purchase, "get_payment_type_display") else purchase.payment_type}
    """
    story.append(Paragraph(purchase_text, normal_style))
    story.append(Spacer(1, 0.15*inch))
    
    # ========================================== #
    # ITEMS TABLE                                #
    # ========================================== #
    
    story.append(Paragraph('<b>ITEMS DETAIL</b>', heading_style))
    story.append(Spacer(1, 0.05*inch))
    
    # Get items
    items = purchase.purchaseitem_set.all()
    total_amount = Decimal('0.00')
    
    # Table Data
    data = [
        ['#', 'Product Name', 'Qty', 'Price', 'Total']
    ]
    
    for idx, item in enumerate(items, 1):
        qty = item.qty
        price = item.price
        total = item.total_amt
        
        data.append([
            str(idx),
            item.product.name,
            f"{qty:,.2f}",
            f"{price:,.2f}",
            f"{total:,.2f}"
        ])
        total_amount += total
    
    # Add total row
    data.append(['', '', '', 'TOTAL:', f'{total_amount:,.2f}'])
    
    # Table styling
    table = Table(data, colWidths=[0.3*inch, 3.2*inch, 0.8*inch, 1.0*inch, 1.5*inch], repeatRows=1)
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        # Body
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('TOPPADDING', (0, 1), (-1, -2), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -2), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.lightgrey]),
        # Total Row
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, -1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 6),
        # Alignment
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (4, -2), 'RIGHT'),
        ('ALIGN', (4, -1), (4, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.15*inch))
    
    # ========================================== #
    # PAYMENT SUMMARY                            #
    # ========================================== #
    
    summary_text = f"""
    <b>PAYMENT SUMMARY</b><br/>
    Total Amount: Rs. {total_amount:,.2f}<br/>
    Amount Paid: Rs. {purchase.paid:,.2f}<br/>
    Cash Used: Rs. {purchase.cash_used:,.2f}<br/>
    <b>Outstanding: Rs. {purchase.outstanding_balance():,.2f}</b>
    """
    story.append(Paragraph(summary_text, normal_style))
    story.append(Spacer(1, 0.15*inch))
    
    # ========================================== #
    # FOOTER                                     #
    # ========================================== #
    
    story.append(Paragraph('-' * 80, small_style))
    story.append(Spacer(1, 0.05*inch))
    story.append(Paragraph("This is a computer generated invoice. Valid without signature.", small_style))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", small_style))
    
    # ========================================== #
    # BUILD PDF                                  #
    # ========================================== #
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Purchase_Invoice_{purchase.bill_no or purchase.id}.pdf"'
    return response


@login_required
@perm_required('view_purchases')
def purchase_list(request):
    """
    Purchases list: search, filters (status / vendor / warehouse / payment type / dates), sorting,
    KPI cards, aging (overdue) and Excel / PDF / CSV export.
    Total, paid and due come from ONE annotated query (no per-row queries).
    """
    from django.db.models import ExpressionWrapper
    from ...store import store_exports as _ex

    money = DecimalField(max_digits=20, decimal_places=2)
    purchases = Purchase.objects.select_related(
        'vendor', 'warehouse', 'created_by'
    ).annotate(
        cached_total=Coalesce(Sum('purchaseitem__total_amt', output_field=money),
                              Value(Decimal('0.00'), output_field=money), output_field=money),
        item_count=Count('purchaseitem', distinct=True),
    ).annotate(
        due=ExpressionWrapper(F('cached_total') - F('paid'), output_field=money),
    )

    # --- store-wise access + filters -------------------------------------------------
    purchases = _sa.hide_other_stores(request.user, purchases, 'warehouse')

    search = (request.GET.get('search') or '').strip()
    if search:
        purchases = purchases.filter(
            Q(bill_no__icontains=search) | Q(vendor__name__icontains=search) |
            Q(vendor__vendor_code__icontains=search)
        )

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id.isdigit():
        purchases = purchases.filter(warehouse_id=int(warehouse_id))

    vendor_id = request.GET.get('vendor', '')
    if vendor_id.isdigit():
        purchases = purchases.filter(vendor_id=int(vendor_id))

    ptype = request.GET.get('ptype', '')
    if ptype in ('cash', 'credit', 'mixed'):
        purchases = purchases.filter(payment_type=ptype)

    def _day(value):
        try:
            return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
        except ValueError:
            return None

    date_from, date_to = _day(request.GET.get('from')), _day(request.GET.get('to'))
    if date_from:
        purchases = purchases.filter(pur_date__date__gte=date_from)
    if date_to:
        purchases = purchases.filter(pur_date__date__lte=date_to)

    # status: paid | partial | credit (nothing paid) | pending (anything still due, old name)
    status = request.GET.get('status', '')
    if status == 'paid':
        purchases = purchases.filter(due__lte=0)
    elif status == 'partial':
        purchases = purchases.filter(due__gt=0, paid__gt=0)
    elif status == 'credit':
        purchases = purchases.filter(due__gt=0, paid__lte=0)
    elif status in ('pending', 'due'):
        purchases = purchases.filter(due__gt=0)
    elif status == 'overdue':
        purchases = purchases.filter(due__gt=0, pur_date__lt=now() - timedelta(days=30))

    sorts = {
        'date_desc': ('-pur_date', '-id'), 'date_asc': ('pur_date', 'id'),
        'amount_desc': ('-cached_total', '-id'), 'due_desc': ('-due', '-id'),
        'vendor': ('vendor__name', '-pur_date'),
    }
    sort = request.GET.get('sort', 'date_desc')
    if sort not in sorts:
        sort = 'date_desc'
    purchases = purchases.order_by(*sorts[sort])

    # --- KPI totals: computed once in Python from the same filtered query -------------
    cutoff = now() - timedelta(days=30)
    total_amount = total_paid = total_due = Decimal('0.00')
    overdue_amount, overdue_count, total_count = Decimal('0.00'), 0, 0
    for amt, paid, due, pur_date in purchases.values_list('cached_total', 'paid', 'due', 'pur_date'):
        total_count += 1
        total_amount += amt or 0
        total_paid += paid or 0
        if due and due > 0:
            total_due += due
            if pur_date and pur_date < cutoff:
                overdue_amount += due
                overdue_count += 1

    # --- Export (all filtered rows, not just the page) --------------------------------
    fmt = request.GET.get('export', '')
    if fmt in ('xlsx', 'pdf', 'csv'):
        rows = []
        for p in purchases[:5000]:
            rows.append([
                p.pur_date.strftime('%Y-%m-%d'), p.bill_no or 'Pending', p.vendor.name,
                p.warehouse.name if p.warehouse else '', p.item_count, float(p.cached_total),
                float(p.paid), float(p.due), {'cash': 'Cash', 'credit': 'Credit', 'mixed': 'Mixed'}.get(p.payment_type, p.payment_type),
                'Paid' if p.due <= 0 else ('Partial' if p.paid > 0 else 'Unpaid'),
            ])
        return _ex.export_response(
            fmt, f'purchases_{date.today()}', 'Purchases',
            ['Date', 'Bill No', 'Vendor', 'Warehouse', 'Items', 'Total', 'Paid', 'Due', 'Type', 'Status'], rows,
            totals=['TOTAL', '', '', '', '', float(total_amount), float(total_paid), float(total_due), '', ''],
            subtitle=f'{total_count} purchases', number_cols=(4, 5, 6, 7))

    # --- Pagination + per-row display values ------------------------------------------
    try:
        per_page = int(request.GET.get('per_page', 25))
    except ValueError:
        per_page = 25
    per_page = per_page if per_page in (10, 25, 50, 100) else 25
    page_obj = Paginator(purchases, per_page).get_page(request.GET.get('page', 1))
    for p in page_obj:
        p.total_value = p.cached_total
        p.due_value = max(p.due, Decimal('0.00'))
        p.pay_state = 'paid' if p.due <= 0 else ('partial' if p.paid > 0 else 'credit')
        p.age_days = (now() - p.pur_date).days if p.pur_date else 0
        p.is_overdue = p.due > 0 and p.age_days > 30
        p.paid_percent = int(min(100, (p.paid / p.cached_total) * 100)) if p.cached_total else 0

    filters_active = any([search, warehouse_id, vendor_id, ptype, date_from, date_to, status])
    keep = request.GET.copy()
    keep.pop('page', None)
    keep.pop('export', None)
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'warehouses': _sa.hide_other_stores(request.user, Warehouse.objects.all()),
        'vendors': Vendor.objects.order_by('name').only('id', 'name', 'vendor_code'),
        'selected_warehouse': warehouse_id,
        'selected_vendor': vendor_id,
        'selected_ptype': ptype,
        'selected_status': status,
        'selected_sort': sort,
        'selected_per_page': per_page,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'filters_active': filters_active,
        'qs': keep.urlencode(),
        'total_count': total_count,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_outstanding': total_due,
        'overdue_amount': overdue_amount,
        'overdue_count': overdue_count,
        'paid_percent': int(min(100, (total_paid / total_amount) * 100)) if total_amount else 0,
    }
    return render(request, 'purchases/list.html', context)


@login_required
@perm_required('view_purchases', 'create_purchases', 'edit_purchases')
def search_products_purchase(request):
    """
    AJAX: Product search for PURCHASE module only
    - Stock check (shows current stock)
    - Latest batch price (recommended price)
    - No selling price check
    """
    query = request.GET.get('q', '').strip()
    warehouse_id = request.GET.get('warehouse_id', '')
    
    if len(query) < 1:
        return JsonResponse({'success': True, 'products': []})
    
    # Search products
    products = Product.objects.filter(
        Q(name__icontains=query) |
        Q(serial_no__icontains=query) |
        Q(barcode__icontains=query)
    ).distinct()[:20]
    
    result = []
    for product in products:
        # ✅ Get stock
        stock = 0
        if warehouse_id:
            inventory = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first()
            stock = inventory.stock if inventory else 0
        else:
            # Total stock across all warehouses
            stock = Inventory.objects.filter(product=product).aggregate(
                total=Sum('stock')
            )['total'] or 0
        
        # ✅ Get latest batch price (most recent StockBatch)
        latest_batch_price = 0
        latest_batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0  # Only active batches with stock
        ).order_by('-id').first()  # Most recent batch first
        
        if latest_batch:
            latest_batch_price = float(latest_batch.price)
        
        # ✅ Get product's default price (fallback)
        default_price = float(product.price) if product.price else 0
        
        # ✅ Get average price from all batches
        avg_price = 0
        all_batches = StockBatch.objects.filter(product=product)
        if all_batches.exists():
            avg_price = float(all_batches.aggregate(
                avg=Avg('price')
            )['avg'] or 0)
        
        # ✅ RECOMMENDED PRICE: Latest batch price first, then default
        recommended_price = latest_batch_price if latest_batch_price > 0 else default_price
        
        result.append({
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode or '',
            'serial_no': product.serial_no or '',
            'price': str(recommended_price),
            'latest_batch_price': str(latest_batch_price),  # ✅ Latest batch price
            'default_price': str(default_price),
            'avg_price': str(avg_price),
            'stock': stock,
            'unit': product.unit.name if product.unit else '',
            'has_batch': latest_batch_price > 0,
            'batch_count': all_batches.count(),
        })
    
    return JsonResponse({'success': True, 'products': result})


@login_required
@perm_required('edit_purchases')
@require_POST
def purchase_pay(request, pk):
    """
    Pay vendor for a specific purchase
    Credit → Paid
    """
    from decimal import Decimal
    from ...models import VendorPayment, PaymentMethod, CashBalance
    
    purchase = get_object_or_404(Purchase, pk=pk)
    
    # ========================================== #
    # Validation                                 #
    # ========================================== #
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'message': '❌ Access denied!'
        })
    
    if purchase.outstanding_balance() <= 0:
        return JsonResponse({
            'success': False,
            'message': '⚠️ This purchase is already fully paid!'
        })
    
    try:
        # Get form data
        amount = Decimal(request.POST.get('amount', 0))
        payment_method_name = request.POST.get('payment_method', 'Cash')
        reference_no = request.POST.get('reference_no', '')
        notes = request.POST.get('notes', '')
        
        # ========================================== #
        # Amount validation                          #
        # ========================================== #
        if amount <= 0:
            return JsonResponse({
                'success': False,
                'message': '❌ Amount must be greater than zero!'
            })
        
        if amount > purchase.outstanding_balance():
            return JsonResponse({
                'success': False,
                'message': f'❌ Amount exceeds outstanding: Rs. {purchase.outstanding_balance():,.2f}'
            })
        
        # ========================================== #
        # Cash balance check                         #
        # ========================================== #
        current_cash = CashBalance.get_balance()
        if amount > current_cash:
            return JsonResponse({
                'success': False,
                'message': f'❌ Insufficient cash! Available: Rs. {current_cash:,.2f}'
            })
        
        # ========================================== #
        # Get or create PaymentMethod                #
        # ========================================== #
        method, _ = PaymentMethod.objects.get_or_create(
            name=payment_method_name,
            defaults={'is_active': True}
        )
        
        # ========================================== #
        # Process payment (atomic)                   #
        # ========================================== #
        with transaction.atomic():
            # 1. Update purchase paid amount
            purchase.paid += amount
            purchase.save(update_fields=['paid'])
            
            # 2. Create vendor payment record
            vendor_payment = VendorPayment.objects.create(
                vendor=purchase.vendor,
                purchase=purchase,
                amount=amount,
                payment_date=now(),
                payment_method=method,
                reference_no=reference_no,
                notes=notes or f"Payment for {purchase.bill_no}",
                created_by=request.user,
            )
            
            # 3. Deduct from cash balance
            CashBalance.update_balance(
                amount=amount,
                transaction_type='withdraw',
                user=request.user,
                description=f"Vendor payment: {purchase.vendor.name} - {purchase.bill_no}"
            )
        
        # ========================================== #
        # Success response                           #
        # ========================================== #
        new_outstanding = purchase.outstanding_balance()
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Payment of Rs. {amount:,.2f} successful!',
            'new_paid': float(purchase.paid),
            'new_outstanding': float(new_outstanding),
            'is_fully_paid': new_outstanding <= 0,
            'payment_id': vendor_payment.id,
        })
    
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Purchase payment error: {e}")
        
        return JsonResponse({
            'success': False,
            'message': f'❌ Error: {str(e)}'
        })
