"""Frontend views: purchase/grn (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from ...models import *
import logging
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import HttpResponse
from io import BytesIO
from django.db import transaction
from ...models import CompanyInfo, Purchase
from ...store import store_access as _sa
from ...store import store_receive as _sr
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
logger = logging.getLogger(__name__)


# ============================================
# GRN
# ============================================
@login_required
@perm_required('view_purchases', 'receive_goods')
def grn_list(request):
    """GRN List with filters and stats"""
    
    grns = GoodsReceivedNote.objects.select_related(
        'vendor', 'warehouse', 'purchase_order'
    ).prefetch_related('items').order_by('-grn_date')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        grns = grns.filter(
            Q(grn_no__icontains=search) |
            Q(vendor__name__icontains=search) |
            Q(invoice_no__icontains=search) |
            Q(purchase_order__order_no__icontains=search)
        )
    
    # Status filter
    selected_status = request.GET.get('status', '')
    if selected_status == 'converted':
        grns = grns.filter(converted_to_purchase=True)
    elif selected_status == 'pending':
        grns = grns.filter(converted_to_purchase=False)
    
    # Warehouse filter
    grns = _sa.hide_other_stores(request.user, grns, 'warehouse')
    selected_warehouse = request.GET.get('warehouse', '')
    if selected_warehouse:
        grns = grns.filter(warehouse_id=selected_warehouse)
    
    # Stats
    total_grns = GoodsReceivedNote.objects.count()
    converted_count = GoodsReceivedNote.objects.filter(converted_to_purchase=True).count()
    pending_count = GoodsReceivedNote.objects.filter(converted_to_purchase=False).count()
    
    # Total items across all GRNs
    total_items = GoodsReceivedItem.objects.count()
    
    # Pagination
    paginator = Paginator(grns, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'selected_status': selected_status,
        'selected_warehouse': selected_warehouse,
        'warehouses': _sa.hide_other_stores(request.user, Warehouse.objects.all()),
        'total_grns': total_grns,
        'converted_count': converted_count,
        'pending_count': pending_count,
        'total_items': total_items,
    }
    return render(request, 'orders/grn_list.html', context)


@login_required
@perm_required('view_purchases', 'receive_goods')
def grn_detail(request, pk):
    """GRN Detail View"""
    grn = get_object_or_404(
        GoodsReceivedNote.objects.select_related(
            'vendor', 'warehouse', 'purchase_order', 'created_by'
        ).prefetch_related('items__product'),
        pk=pk
    )
    
    items = grn.items.all()
    total_amount = sum(item.total_amt for item in items)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'grn': grn,
        'items': items,
        'total_amount': total_amount,
    }
    return render(request, 'orders/grn_detail.html', context)


@login_required
@perm_required('receive_goods', 'manage_purchase_orders')
@transaction.atomic
def grn_convert_to_purchase(request, pk):
    """
    Convert Goods Received Note (GRN) to Purchase
    - Creates a Purchase record from GRN
    - Copies all items
    - Links GRN to Purchase (BOTH fields set)
    - Updates GRN status
    """
    from django.db import transaction as db_transaction
    from django.utils.timezone import now
    
    grn = get_object_or_404(
        GoodsReceivedNote.objects.select_related('vendor', 'warehouse'),
        pk=pk
    )
    
    # ========================================== #
    # ✅ CHECK 1: Already converted?            #
    # ========================================== #
    if grn.converted_to_purchase:
        messages.warning(
            request, 
            f'⚠️ GRN {grn.grn_no} is already converted to purchase!'
        )
        return redirect('grn_detail', pk=grn.pk)
    
    # ========================================== #
    # ✅ CHECK 2: Does GRN have items?          #
    # ========================================== #
    if not grn.items.exists():
        messages.error(
            request, 
            f'❌ Cannot convert! GRN {grn.grn_no} has no items.'
        )
        return redirect('grn_detail', pk=grn.pk)
    
    # ========================================== #
    # ✅ CHECK 3: Permission check              #
    # ========================================== #
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can convert GRN.')
        return redirect('grn_detail', pk=grn.pk)

    if not _sr.can_receive(request.user, grn.warehouse_id):
        messages.error(request, f'❌ You do not have the right to add stock to {grn.warehouse.name} (you are not a keeper/manager of that store team).')
        return redirect('grn_detail', pk=grn.pk)
    
    try:
        with db_transaction.atomic():
            # ========================================== #
            # STEP 1: Create Purchase                   #
            # ========================================== #
            purchase = Purchase.objects.create(
                vendor=grn.vendor,
                warehouse=grn.warehouse,
                bill_no=grn.invoice_no or f"BILL-{grn.grn_no}",
                pur_date=now(),
                paid=0,
                previous_balance=0,
                payment_type='credit',
                cash_used=0,
                created_by=request.user,
                waiting_for_bill=False,
            )
            
            # ========================================== #
            # STEP 2: Copy all items                    #
            # ========================================== #
            items_created = 0
            for item in grn.items.all():
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=item.product,
                    qty=float(item.qty),
                    price=item.price,
                    batch_no=item.batch_no,          # [agri-edition:grn-convert]
                    expiry_date=item.expiry_date,
                )
                items_created += 1
            
            # ========================================== #
            # STEP 3: ✅ CRITICAL — Set BOTH fields!   #
            # ========================================== #
            grn.purchase = purchase              # ← Purchase object link
            grn.converted_to_purchase = True     # ← Conversion flag
            grn.save()                            # ← Save both together
            
            # ========================================== #
            # STEP 4: Update PO status if linked        #
            # ========================================== #
            if grn.purchase_order:
                try:
                    grn.purchase_order.update_receive_status()
                except Exception as e:
                    # Not critical — log and continue
                    import logging
                    logging.getLogger(__name__).warning(
                        f"PO status update failed: {e}"
                    )
            
            # ========================================== #
            # STEP 5: Create notification               #
            # ========================================== #
            try:
                from ...models import Notification
                Notification.send(
                    user=request.user,
                    title="✅ GRN Converted to Purchase",
                    message=(
                        f"GRN {grn.grn_no} converted to Purchase "
                        f"#{purchase.bill_no} — "
                        f"Amount: Rs. {purchase.total_amount():,.2f}"
                    ),
                    notification_type='success',
                    category='purchases',
                    link=f"/purchases/{purchase.pk}/"
                )
            except Exception:
                pass  # Keep working even if the notification fails
            
            # ========================================== #
            # STEP 6: Success message                   #
            # ========================================== #
            messages.success(
                request,
                f'✅ GRN {grn.grn_no} successfully converted!\n'
                f'📦 Purchase: #{purchase.bill_no}\n'
                f'💰 Amount: Rs. {purchase.total_amount():,.2f}\n'
                f'📋 Items: {items_created}'
            )
            
            return redirect('purchase_detail', pk=purchase.pk)
    
    except Exception as e:
        # ========================================== #
        # Error handling — atomic rollback happens  #
        # ========================================== #
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"GRN conversion error for {grn.grn_no}: {e}")
        
        messages.error(
            request,
            f'❌ Failed to convert GRN {grn.grn_no}: {str(e)}'
        )
        return redirect('grn_detail', pk=grn.pk)


@login_required
@perm_required('delete_purchases')
def grn_delete(request, pk):
    """Delete GRN"""
    grn = get_object_or_404(GoodsReceivedNote, pk=pk)
    
    if grn.converted_to_purchase:
        messages.error(request, '❌ Cannot delete a GRN that is already converted to purchase!')
        return redirect('grn_detail', pk=grn.pk)
    
    if request.method == 'POST':
        grn_no = grn.grn_no
        grn.delete()
        messages.success(request, f'🗑️ GRN {grn_no} deleted successfully!')
        return redirect('grn_list')
    
    return redirect('grn_detail', pk=grn.pk)


@login_required
@perm_required('view_purchases', 'receive_goods')
def grn_pdf(request, pk):
    """Generate GRN PDF - Simple version"""
    grn = get_object_or_404(GoodsReceivedNote, pk=pk)
    items = grn.items.all()
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("GOODS RECEIVED NOTE (GRN)", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # GRN Info
    info_data = [
        ['GRN No:', grn.grn_no, 'Date:', grn.grn_date.strftime('%d-%m-%Y')],
        ['Vendor:', grn.vendor.name, 'Warehouse:', grn.warehouse.name],
        ['PO No:', grn.purchase_order.order_no if grn.purchase_order else 'N/A', 'Invoice:', grn.invoice_no or 'N/A'],
    ]
    
    info_table = Table(info_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Items Table
    data = [['#', 'Product', 'Order Qty', 'Received', 'Unit Price', 'Total']]
    total_amount = 0
    
    for idx, item in enumerate(items, 1):
        data.append([
            str(idx),
            item.product.name[:30],
            f"{item.order_qty:,.2f}",
            f"{item.qty:,.2f}",
            f"Rs. {item.price:,.2f}",
            f"Rs. {item.total_amt:,.2f}"
        ])
        total_amount += item.total_amt
    
    data.append(['', '', '', '', 'TOTAL:', f"Rs. {total_amount:,.2f}"])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.5*inch))
    
    # Signatures
    story.append(Paragraph("Received by: _________________    Checked by: _________________", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="GRN_{grn.grn_no}.pdf"'
    return response


@login_required
@perm_required('view_purchases', 'receive_goods')
def grn_barcode_labels(request, pk):
    """Generate barcode labels for GRN items"""
    grn = get_object_or_404(GoodsReceivedNote, pk=pk)
    items = grn.items.all()
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from io import BytesIO
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph(f"Barcode Labels - GRN {grn.grn_no}", styles['Heading1']))
    story.append(Spacer(1, 0.2*inch))
    
    for item in items:
        story.append(Paragraph(f"<b>{item.product.name}</b>", styles['Heading3']))
        story.append(Paragraph(f"Barcode: {item.product.barcode or 'N/A'}", styles['Normal']))
        story.append(Paragraph(f"Serial: {item.product.serial_no or 'N/A'}", styles['Normal']))
        story.append(Paragraph(f"Qty: {item.qty}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="GRN_Barcodes_{grn.grn_no}.pdf"'
    return response


@login_required
@perm_required('receive_goods', 'manage_purchase_orders')
def grn_reset_conversion(request, pk):
    """Reset GRN conversion status if data inconsistency detected"""
    grn = get_object_or_404(GoodsReceivedNote, pk=pk)
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('grn_detail', pk=pk)
    
    if request.method == 'POST':
        old_status = grn.converted_to_purchase
        grn.converted_to_purchase = False
        grn.purchase = None
        grn.save()
        
        messages.success(
            request, 
            f'✅ GRN {grn.grn_no} reset to Pending!\n'
            f'You can convert it again now.'
        )
        return redirect('grn_detail', pk=pk)
    
    return redirect('grn_detail', pk=pk)
