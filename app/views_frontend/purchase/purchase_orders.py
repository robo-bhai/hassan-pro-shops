"""Frontend views: purchase/purchase_orders (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import transaction
from ...models import CompanyInfo, Product
from ...store import store_access as _sa
from ...store import store_receive as _sr


# ============================================
# PURCHASE ORDERS
# ============================================
# ✅ NEW CODE
@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def purchase_order_list(request):
    orders = PurchaseOrder.objects.select_related(
        'vendor',
        'warehouse',
        'vendor__group',
        'created_by'
    ).prefetch_related(
        'items__product',
        'items__product__unit',
        'grns',
        'converted_to_purchase'
    ).order_by('-order_date')
    
    search = request.GET.get('search', '')
    if search:
        orders = orders.filter(
            Q(order_no__icontains=search) |
            Q(vendor__name__icontains=search) |
            Q(vendor__vendor_code__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        orders = orders.filter(status=status)
    
    orders = _sa.hide_other_stores(request.user, orders, 'warehouse')
    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        orders = orders.filter(warehouse_id=warehouse_id)
    
    # Stats
    total_orders = orders.count()
    pending_count = PurchaseOrder.objects.filter(status='pending').count()
    confirmed_count = PurchaseOrder.objects.filter(status='confirmed').count()
    received_count = PurchaseOrder.objects.filter(status__in=['received', 'partially_received']).count()
    completed_count = PurchaseOrder.objects.filter(status='completed').count()
    
    # Calculate receive progress
    for order in orders:
        items = order.items.all()
        if items:
            received = sum(order.received_qty(item.product) for item in items)
            ordered = sum(item.qty for item in items)
            order.receive_percent = round((received / ordered) * 100) if ordered > 0 else 0
        else:
            order.receive_percent = 0
    
    paginator = Paginator(orders, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'selected_status': status,
        'selected_warehouse': warehouse_id,
        'warehouses': _sa.hide_other_stores(request.user, Warehouse.objects.all()),
        'total_orders': total_orders,
        'pending_count': pending_count,
        'confirmed_count': confirmed_count,
        'received_count': received_count,
        'completed_count': completed_count,
    }
    return render(request, 'orders/purchase_order_list.html', context)


@login_required
@perm_required('manage_purchase_orders')
def purchase_order_create(request):
    if request.method == 'POST':
        try:
            vendor_id = request.POST.get('vendor')
            warehouse_id = request.POST.get('warehouse')
            status = request.POST.get('status', 'pending')
            expected_date = request.POST.get('expected_date', '')
            vendor_so = request.POST.get('vendor_so', '')
            notes = request.POST.get('notes', '')
            advance = request.POST.get('advance', 0)
            discount = request.POST.get('discount', 0)
            
            if not vendor_id or not warehouse_id:
                messages.error(request, 'Vendor and Warehouse required!')
                return redirect('purchase_order_create')
            if not _sr.can_receive(request.user, warehouse_id):
                messages.error(request, '❌ You cannot create an order for this store (you are not a keeper/manager of that store team).')
                return redirect('purchase_order_create')
            
            product_ids = request.POST.getlist('product_id[]')
            if not product_ids or not any(product_ids):
                messages.error(request, 'Add at least one product!')
                return redirect('purchase_order_create')
            
            order = PurchaseOrder.objects.create(
                vendor_id=vendor_id,
                warehouse_id=warehouse_id,
                status=status,
                expected_date=expected_date if expected_date else None,
                vendor_so_number=vendor_so,
                notes=notes,
                advance_payment=Decimal(advance),
                discount_value=Decimal(discount),
                created_by=request.user
            )
            
            qtys = request.POST.getlist('qty[]')
            prices = request.POST.getlist('price[]')
            
            for i in range(len(product_ids)):
                if product_ids[i]:
                    PurchaseOrderItem.objects.create(
                        order=order,
                        product_id=product_ids[i],
                        qty=float(qtys[i]),
                        price=Decimal(prices[i])
                    )
            
            messages.success(request, f'✅ PO #{order.order_no} created!')
            return redirect('purchase_order_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('purchase_order_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendors': Vendor.objects.all().order_by('vendor_code'),
        'warehouses': _sr.receivable_warehouses(request.user),
        'products': Product.objects.all().order_by('name')[:50],
    }
    return render(request, 'orders/purchase_order_create.html', context)


@login_required
@perm_required('view_purchases', 'manage_purchase_orders')
def purchase_order_detail(request, pk):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related('vendor', 'warehouse')
        .prefetch_related('items', 'items__product', 'grns'), 
        pk=pk
    )
    
    items = order.items.all()
    total_ordered = sum(item.qty for item in items)
    total_received = sum(order.received_qty(item.product) for item in items)
    total_pending = total_ordered - total_received
    receive_percent = round((total_received / total_ordered) * 100) if total_ordered > 0 else 0
    
    for item in items:
        item.received = order.received_qty(item.product)
        item.pending = item.qty - item.received
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'items': items,
        'grns': order.grns.all(),
        'total_ordered': total_ordered,
        'total_received': total_received,
        'total_pending': total_pending,
        'receive_percent': receive_percent,
    }
    return render(request, 'orders/purchase_order_detail.html', context)


@login_required
@perm_required('manage_purchase_orders')
def purchase_order_quick_status(request, pk, status):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    valid_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'partially_received', 'received', 'completed', 'cancelled']
    
    if status in valid_statuses:
        order.status = status
        order.save()
        messages.success(request, f'✅ PO #{order.order_no} → {order.get_status_display()}')
    else:
        messages.error(request, 'Invalid status!')
    
    return redirect('purchase_order_list')


@login_required
@perm_required('manage_purchase_orders')
def purchase_order_create_grn(request, pk):
    """Create GRN from Purchase Order"""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    if not _sr.can_receive(request.user, order.warehouse_id):
        messages.error(request, '❌ You do not have the right to receive goods in this store.')
        return redirect('purchase_order_detail', pk=order.pk)
    
    if order.status not in ['confirmed', 'processing', 'shipped', 'partially_received']:
        messages.error(request, '❌ Order must be Confirmed to create GRN!')
        return redirect('purchase_order_detail', pk=order.pk)
    
    try:
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.create(
                purchase_order=order,
                vendor=order.vendor,
                warehouse=order.warehouse,
                reason='purchase',
                created_by=request.user
            )
            
            for item in order.items.all():
                already_received = GoodsReceivedItem.objects.filter(
                    grn__purchase_order=order,
                    product=item.product
                ).aggregate(total=Sum('qty'))['total'] or 0
                
                pending = item.qty - already_received
                
                if pending > 0:
                    GoodsReceivedItem.objects.create(
                        grn=grn,
                        product=item.product,
                        order_qty=item.qty,
                        qty=pending,
                        price=item.price
                    )
            
            order.update_receive_status()
            messages.success(request, f'✅ GRN #{grn.grn_no} created! Status: {order.get_status_display()}')
            
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('purchase_order_detail', pk=order.pk)
