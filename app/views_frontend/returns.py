"""Frontend views: returns."""
from ..models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from ..models import CompanyInfo, Sale, Purchase, PurchaseRetrnItem
import logging

logger = logging.getLogger(__name__)


@login_required
def purchase_return_analysis(request):
    """Purchase Return Analysis Report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    returns = PurchaseRetrn.objects.filter(
        purchase_return_date__date__gte=from_date_obj,
        purchase_return_date__date__lte=to_date_obj
    )
    
    total_returns = 0
    return_reasons = {}
    
    for ret in returns:
        amount = sum(item.total_amt for item in ret.return_items.all())
        total_returns += amount
        
        if ret.return_reason not in return_reasons:
            return_reasons[ret.return_reason] = 0
        return_reasons[ret.return_reason] += amount
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_returns': total_returns,
        'return_reasons': return_reasons,
        'returns_count': returns.count(),
    }
    return render(request, 'reports/purchase_return_analysis.html', context)


# ✅ NEW CODE
@login_required
def purchase_return_list(request):
    returns = PurchaseRetrn.objects.select_related(
        'vendor',
        'purchase',
        'warehouse',
        'created_by',
        'vendor__group'
    ).prefetch_related(
        'return_items__product',
        'return_items__product__unit'
    ).order_by('-purchase_return_date')
    
    # ✅ Filters
    search = request.GET.get('search', '')
    if search:
        returns = returns.filter(
            Q(vendor__name__icontains=search) |
            Q(purchase__bill_no__icontains=search) |
            Q(bill_no__icontains=search) |
            Q(return_reason__icontains=search)
        )
    
    reason = request.GET.get('reason', '')
    if reason:
        returns = returns.filter(return_reason=reason)
    
    date_from = request.GET.get('date_from', '')
    if date_from:
        returns = returns.filter(purchase_return_date__date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if date_to:
        returns = returns.filter(purchase_return_date__date__lte=date_to)
    
    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        returns = returns.filter(vendor_id=vendor_id)
    
    # ✅ Calculate totals
    total_amount = Decimal('0.00')
    total_qty = Decimal('0.00')
    
    for return_obj in returns:
        ret_total = return_obj.total_return_amount()
        ret_qty = return_obj.total_return_qty()
        return_obj.total_amount = ret_total
        return_obj.total_qty = ret_qty
        total_amount += ret_total
        total_qty += ret_qty
    
    # ✅ Statistics
    total_returns = returns.count()
    unique_vendors = returns.values('vendor').distinct().count()
    
    # ✅ Reason-wise stats
    reason_stats = {}
    for reason_code, reason_label in PurchaseRetrn._meta.get_field('return_reason').choices:
        count = returns.filter(return_reason=reason_code).count()
        if count > 0:
            amount = returns.filter(return_reason=reason_code).aggregate(
                total=Sum('return_items__total_amt')
            )['total'] or Decimal('0.00')
            reason_stats[reason_code] = {
                'label': reason_label,
                'count': count,
                'amount': amount
            }
    
    # ✅ Pagination
    paginator = Paginator(returns, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'returns': page_obj,
        'total_amount': total_amount,
        'total_qty': total_qty,
        'total_returns': total_returns,
        'unique_vendors': unique_vendors,
        'reason_stats': reason_stats,
        'search': search,
        'reason': reason,
        'date_from': date_from,
        'date_to': date_to,
        'vendor_id': vendor_id,
        'vendors': Vendor.objects.all().order_by('name'),
        'return_reasons': PurchaseRetrn._meta.get_field('return_reason').choices,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'returns/purchase_return_list.html', context)


@login_required
def purchase_return_create(request):
    """Create new purchase return - OPTIMIZED"""
    
    if request.method == 'POST':
        try:
            purchase_id = request.POST.get('purchase')
            vendor_id = request.POST.get('vendor')
            bill_no = request.POST.get('bill_no', '')
            return_reason = request.POST.get('return_reason')
            
            if not purchase_id or not vendor_id:
                messages.error(request, 'Please select purchase and vendor!')
                return redirect('purchase_return_create')
            
            purchase = get_object_or_404(Purchase, id=purchase_id)
            vendor = get_object_or_404(Vendor, id=vendor_id)
            
            # ✅ FIX: Pre-fetch data PEHLE
            purchase_items_map = {
                item.product_id: item
                for item in purchase.purchaseitem_set.select_related('product').all()
            }
            
            # ✅ FIX: Already returned quantities - ek query
            returned_qtys = dict(
                PurchaseRetrnItem.objects.filter(
                    purchase_return__purchase=purchase
                ).values_list('product_id').annotate(
                    total=Sum('qty')
                )
            )
            
            purchase_return = PurchaseRetrn.objects.create(
                purchase=purchase,
                vendor=vendor,
                bill_no=bill_no if bill_no else f"RET-{datetime.now().strftime('%Y%m%d')}-{purchase.id}",
                purchase_return_date=now(),
                return_reason=return_reason,
                warehouse=purchase.warehouse,
                created_by=request.user,
                notes=request.POST.get('notes', '')
            )
            
            product_ids = request.POST.getlist('product[]')
            qtys = request.POST.getlist('qty[]')
            prices = request.POST.getlist('price[]')
            
            items_to_create = []
            items_added = 0
            
            for i in range(len(product_ids)):
                if not product_ids[i] or float(qtys[i]) <= 0:
                    continue
                
                product_id = int(product_ids[i])
                
                # ✅ From dict - NO query
                purchase_item = purchase_items_map.get(product_id)
                if not purchase_item:
                    continue
                
                product = purchase_item.product
                qty_decimal = Decimal(str(qtys[i]))
                price_decimal = Decimal(str(prices[i]))
                
                # Check remaining
                original_qty = Decimal(str(purchase_item.qty))
                already_returned = returned_qtys.get(product_id, Decimal('0.00'))
                remaining = original_qty - already_returned
                
                if qty_decimal > remaining:
                    messages.warning(
                        request, 
                        f'⚠️ For "{product.name}", max {remaining} units can be returned.'
                    )
                    continue
                
                # ✅ Collect for bulk create
                items_to_create.append(
                    PurchaseRetrnItem(
                        purchase_return=purchase_return,
                        product=product,
                        qty=qty_decimal,
                        price=price_decimal
                    )
                )
                items_added += 1
            
            # ✅ Bulk create
            if items_to_create:
                PurchaseRetrnItem.objects.bulk_create(items_to_create)
            else:
                messages.error(request, '❌ No valid items added!')
                purchase_return.delete()
                return redirect('purchase_return_create')
            
            messages.success(
                request, 
                f'✅ Purchase return created! {items_added} items. '
                f'Total: Rs. {purchase_return.total_return_amount():,.2f}'
            )
            return redirect('purchase_return_detail', pk=purchase_return.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('purchase_return_create')
    
    purchases = Purchase.objects.filter(
        purchaseitem__isnull=False
    ).distinct().order_by('-pur_date')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'purchases': purchases,
    }
    return render(request, 'returns/purchase_return_create.html', context)


@login_required
def sale_return_create(request):
    """Create new sale return - OPTIMIZED (30+ queries → 5 queries)"""
    from django.utils.timezone import now
    from django.db.models import Sum
    
    if request.method == 'POST':
        try:
            sale_id = request.POST.get('sale')
            customer_id = request.POST.get('customer')
            bill_no = request.POST.get('bill_no', '')
            return_reason = request.POST.get('return_reason')
            notes = request.POST.get('notes', '')
            
            # Validation
            if not sale_id:
                messages.error(request, 'Please select a sale!')
                return redirect('sale_return_create')
            
            if not customer_id:
                messages.error(request, 'Please select a customer!')
                return redirect('sale_return_create')
            
            if not return_reason:
                messages.error(request, 'Please select a return reason!')
                return redirect('sale_return_create')
            
            sale = get_object_or_404(Sale, id=sale_id)
            customer = get_object_or_404(Customer, id=customer_id)
            
            if not sale.saleitem_set.exists():
                messages.error(request, '❌ This sale has no items to return!')
                return redirect('sale_return_create')
            
            # ✅ FIX: Pre-fetch saara data PEHLE (bulk queries)
            sale_items_map = {
                item.product_id: item
                for item in sale.saleitem_set.select_related('product').all()
            }
            
            # ✅ FIX: Already returned quantities - ek query
            returned_qtys = dict(
                SaleRetrnItem.objects.filter(
                    sale_return__sale=sale
                ).values_list('product_id').annotate(
                    total=Sum('qty')
                )
            )
            
            # ✅ Create return
            sale_return = SaleRetrn.objects.create(
                sale=sale,
                customer=customer,
                bill_no=bill_no if bill_no else f"SRET-{now().strftime('%Y%m%d')}-{sale.id}",
                sale_return_date=now(),
                return_reason=return_reason,
                warehouse=sale.warehouse,
                created_by=request.user,
                notes=notes
            )
            
            product_ids = request.POST.getlist('product[]')
            qtys = request.POST.getlist('qty[]')
            prices = request.POST.getlist('price[]')
            
            items_to_create = []
            items_added = 0
            errors = []
            
            for i in range(len(product_ids)):
                if not product_ids[i]:
                    continue
                
                try:
                    qty_val = float(qtys[i]) if qtys[i] else 0
                    if qty_val <= 0:
                        continue
                    
                    product_id = int(product_ids[i])
                    product = sale_items_map[product_id].product  # ✅ From dict, no query
                    
                    qty_decimal = Decimal(str(qty_val))
                    price_decimal = Decimal(str(prices[i])) if prices[i] else Decimal('0.00')
                    
                    if price_decimal <= 0:
                        errors.append(f"Price for {product.name} must be greater than zero!")
                        continue
                    
                    # ✅ Check remaining quantity
                    sale_item = sale_items_map.get(product_id)
                    if sale_item:
                        original_qty = Decimal(str(sale_item.qty))
                        already_returned = returned_qtys.get(product_id, Decimal('0.00'))
                        remaining = original_qty - already_returned
                        
                        if qty_decimal > remaining:
                            errors.append(
                                f'For "{product.name}", max {remaining} units can be returned.'
                            )
                            continue
                    
                    # ✅ Collect for bulk create
                    items_to_create.append(
                        SaleRetrnItem(
                            sale_return=sale_return,
                            product=product,
                            qty=qty_decimal,
                            price=price_decimal
                        )
                    )
                    items_added += 1
                    
                except KeyError:
                    errors.append(f"Product ID {product_ids[i]} not in sale!")
                    continue
                except Exception as e:
                    errors.append(f"Error for product: {str(e)}")
                    continue
            
            # ✅ Bulk create (1 query instead of N)
            if items_to_create:
                SaleRetrnItem.objects.bulk_create(items_to_create)
            else:
                messages.error(request, '❌ No valid items added to return!')
                if errors:
                    for err in errors[:3]:
                        messages.error(request, err)
                sale_return.delete()
                return redirect('sale_return_create')
            
            # Success
            success_msg = f'✅ Sale return created! {items_added} items. Total: Rs. {sale_return.total_return_amount():,.2f}'
            if errors:
                success_msg += f' ⚠️ {len(errors)} warnings'
            
            messages.success(request, success_msg)
            return redirect('sale_return_detail', pk=sale_return.pk)
            
        except ValidationError as e:
            messages.error(request, f'❌ Validation Error: {str(e)}')
            return redirect('sale_return_create')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            logger.error(f"Sale return creation error: {e}")
            return redirect('sale_return_create')
    
    # GET request
    sales = Sale.objects.filter(
        saleitem__isnull=False
    ).distinct().order_by('-sale_date')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'sales': sales,
        'customers': Customer.objects.all().order_by('name'),
        'return_reasons': SaleRetrn._meta.get_field('return_reason').choices,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'returns/sale_return_create.html', context)


@login_required
def purchase_return_detail(request, pk):
    """View purchase return details with full information"""
    
    purchase_return = get_object_or_404(
        PurchaseRetrn.objects.select_related(
            'vendor', 'purchase', 'warehouse', 'created_by'
        ),
        pk=pk
    )
    
    items = purchase_return.return_items.all().select_related('product', 'product__unit')
    
    # ✅ Calculate totals
    total_amount = sum(item.total_amt for item in items)
    total_qty = sum(item.qty for item in items)
    
    # ✅ Get purchase info
    purchase = purchase_return.purchase
    if purchase:
        purchase_items = purchase.purchaseitem_set.all()
        purchase_total = purchase.total_amount()
        purchase_paid = purchase.paid
        purchase_outstanding = purchase.outstanding_balance()
    else:
        purchase_items = []
        purchase_total = Decimal('0.00')
        purchase_paid = Decimal('0.00')
        purchase_outstanding = Decimal('0.00')
    
    # ✅ Get all returns for this purchase
    all_returns = []
    if purchase:
        all_returns = PurchaseRetrn.objects.filter(purchase=purchase).exclude(pk=pk)
    
    # ✅ Vendor info
    vendor = purchase_return.vendor
    vendor_total_purchases = Purchase.objects.filter(vendor=vendor).count()
    vendor_total_returns = PurchaseRetrn.objects.filter(vendor=vendor).count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'return': purchase_return,
        'items': items,
        'total_amount': total_amount,
        'total_qty': total_qty,
        'total_items': items.count(),
        'purchase': purchase,
        'purchase_items': purchase_items,
        'purchase_total': purchase_total,
        'purchase_paid': purchase_paid,
        'purchase_outstanding': purchase_outstanding,
        'vendor': vendor,
        'vendor_total_purchases': vendor_total_purchases,
        'vendor_total_returns': vendor_total_returns,
        'all_returns': all_returns,
        'warehouse': purchase_return.warehouse,
        'created_by': purchase_return.created_by,
        'can_edit': purchase_return.can_edit,
        'can_delete': purchase_return.can_delete,
        'return_reason_display': purchase_return.get_return_reason_display(),
        'return_reason_color': purchase_return.reason_color,
        'return_reason_icon': purchase_return.reason_icon,
    }
    return render(request, 'returns/purchase_return_detail.html', context)


# ✅ NEW CODE
@login_required
def sale_return_list(request):
    returns = SaleRetrn.objects.select_related(
        'customer',
        'sale',
        'warehouse',
        'created_by',
        'customer__group'
    ).prefetch_related(
        'return_items__product',
        'return_items__product__unit'
    ).order_by('-sale_return_date')
    
    # ✅ Filters
    search = request.GET.get('search', '')
    if search:
        returns = returns.filter(
            Q(customer__name__icontains=search) |
            Q(sale__bill_no__icontains=search) |
            Q(bill_no__icontains=search) |
            Q(return_reason__icontains=search)
        )
    
    reason = request.GET.get('reason', '')
    if reason:
        returns = returns.filter(return_reason=reason)
    
    date_from = request.GET.get('date_from', '')
    if date_from:
        returns = returns.filter(sale_return_date__date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if date_to:
        returns = returns.filter(sale_return_date__date__lte=date_to)
    
    customer_id = request.GET.get('customer', '')
    if customer_id:
        returns = returns.filter(customer_id=customer_id)
    
    # ✅ Calculate totals
    total_amount = Decimal('0.00')
    total_qty = Decimal('0.00')
    
    for return_obj in returns:
        ret_total = return_obj.total_return_amount()
        ret_qty = return_obj.total_return_qty()
        return_obj.total_amount = ret_total
        return_obj.total_qty = ret_qty
        total_amount += ret_total
        total_qty += ret_qty
    
    # ✅ Statistics
    total_returns = returns.count()
    unique_customers = returns.values('customer').distinct().count()
    
    # ✅ Reason-wise stats
    reason_stats = {}
    for reason_code, reason_label in SaleRetrn._meta.get_field('return_reason').choices:
        count = returns.filter(return_reason=reason_code).count()
        if count > 0:
            amount = returns.filter(return_reason=reason_code).aggregate(
                total=Sum('return_items__total_amt')
            )['total'] or Decimal('0.00')
            reason_stats[reason_code] = {
                'label': reason_label,
                'count': count,
                'amount': amount
            }
    
    # ✅ Pagination
    paginator = Paginator(returns, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'returns': page_obj,
        'total_amount': total_amount,
        'total_qty': total_qty,
        'total_returns': total_returns,
        'unique_customers': unique_customers,
        'reason_stats': reason_stats,
        'search': search,
        'reason': reason,
        'date_from': date_from,
        'date_to': date_to,
        'customer_id': customer_id,
        'customers': Customer.objects.all().order_by('name'),
        'return_reasons': SaleRetrn._meta.get_field('return_reason').choices,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'returns/sale_return_list.html', context)


@login_required
def sale_return_detail(request, pk):
    """View sale return details with full information"""
    
    sale_return = get_object_or_404(
        SaleRetrn.objects.select_related(
            'customer', 'sale', 'warehouse', 'created_by'
        ),
        pk=pk
    )
    
    items = sale_return.return_items.all().select_related('product', 'product__unit')
    
    # ✅ Calculate totals
    total_amount = sum(item.total_amt for item in items)
    total_qty = sum(item.qty for item in items)
    
    # ✅ Get sale info
    sale = sale_return.sale
    if sale:
        sale_items = sale.saleitem_set.all()
        sale_total = sale.total_amount()
        sale_paid = sale.paid
        sale_outstanding = sale.outstanding_balance()
    else:
        sale_items = []
        sale_total = Decimal('0.00')
        sale_paid = Decimal('0.00')
        sale_outstanding = Decimal('0.00')
    
    # ✅ Get all returns for this sale
    all_returns = []
    if sale:
        all_returns = SaleRetrn.objects.filter(sale=sale).exclude(pk=pk)
    
    # ✅ Customer info
    customer = sale_return.customer
    customer_total_sales = Sale.objects.filter(customer=customer).count()
    customer_total_returns = SaleRetrn.objects.filter(customer=customer).count()
    
    # ✅ FIX: Calculate return percentage properly
    total_original_qty = Decimal('0.00')
    for item in sale_items:
        total_original_qty += Decimal(str(item.qty))
    
    total_returned_qty = Decimal('0.00')
    for item in items:
        total_returned_qty += item.qty
    
    # ✅ FIX: Decimal division
    if total_original_qty > 0:
        return_percent = float((total_returned_qty / total_original_qty) * 100)
    else:
        return_percent = 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'return': sale_return,
        'items': items,
        'total_amount': total_amount,
        'total_qty': total_qty,
        'total_items': items.count(),
        'sale': sale,
        'sale_items': sale_items,
        'sale_total': sale_total,
        'sale_paid': sale_paid,
        'sale_outstanding': sale_outstanding,
        'customer': customer,
        'customer_total_sales': customer_total_sales,
        'customer_total_returns': customer_total_returns,
        'all_returns': all_returns,
        'warehouse': sale_return.warehouse,
        'created_by': sale_return.created_by,
        'return_percent': return_percent,
        'return_reason_display': sale_return.get_return_reason_display(),
        'reason_color': sale_return.reason_color,
        'can_edit': sale_return.can_edit,
        'can_delete': sale_return.can_delete,
    }
    return render(request, 'returns/sale_return_detail.html', context)


@login_required
def get_purchase_return_history(request):
    """
    AJAX: Get return history for a specific purchase
    Returns detailed history of all returns
    """
    purchase_id = request.GET.get('purchase_id')
    
    if not purchase_id:
        return JsonResponse({
            'success': False, 
            'message': 'Purchase ID required'
        })
    
    try:
        purchase = Purchase.objects.get(id=purchase_id)
        returns = PurchaseRetrn.objects.filter(purchase=purchase).order_by('-purchase_return_date')
        
        history = []
        total_returned_amount = Decimal('0.00')
        total_returned_items = 0
        
        for ret in returns:
            items = []
            ret_total = Decimal('0.00')
            ret_items_count = 0
            
            for item in ret.return_items.all():
                items.append({
                    'product_name': item.product.name,
                    'product_id': item.product.id,
                    'qty': float(item.qty),
                    'amount': float(item.total_amt),
                    'price': float(item.price),
                    'unit': item.product.unit.name if item.product.unit else ''
                })
                ret_total += item.total_amt
                ret_items_count += 1
            
            history.append({
                'id': ret.id,
                'date': ret.purchase_return_date.strftime('%d-%m-%Y %H:%M'),
                'date_short': ret.purchase_return_date.strftime('%d %b, %Y'),
                'time': ret.purchase_return_date.strftime('%I:%M %p'),
                'reason': ret.get_return_reason_display(),
                'reason_code': ret.return_reason,
                'bill_no': ret.bill_no or 'N/A',
                'items': items,
                'total_amount': float(ret_total),
                'total_items': ret_items_count,
                'created_by': ret.created_by.username if ret.created_by else 'System',
                'warehouse': ret.warehouse.name if ret.warehouse else 'N/A'
            })
            
            total_returned_amount += ret_total
            total_returned_items += ret_items_count
        
        # ✅ Product-wise return summary
        product_summary = {}
        for ret in returns:
            for item in ret.return_items.all():
                key = item.product.id
                if key not in product_summary:
                    product_summary[key] = {
                        'name': item.product.name,
                        'total_returned': Decimal('0.00'),
                        'total_amount': Decimal('0.00'),
                        'return_count': 0,
                        'unit': item.product.unit.name if item.product.unit else ''
                    }
                product_summary[key]['total_returned'] += item.qty
                product_summary[key]['total_amount'] += item.total_amt
                product_summary[key]['return_count'] += 1
        
        # ✅ Reason-wise summary
        reason_summary = {}
        for ret in returns:
            reason = ret.return_reason
            if reason not in reason_summary:
                reason_summary[reason] = {
                    'label': ret.get_return_reason_display(),
                    'count': 0,
                    'amount': Decimal('0.00')
                }
            reason_summary[reason]['count'] += 1
            reason_summary[reason]['amount'] += sum(item.total_amt for item in ret.return_items.all())
        
        return JsonResponse({
            'success': True,
            'returns': history,
            'product_summary': {
                str(k): {
                    'name': v['name'],
                    'total_returned': float(v['total_returned']),
                    'total_amount': float(v['total_amount']),
                    'return_count': v['return_count'],
                    'unit': v['unit']
                } for k, v in product_summary.items()
            },
            'reason_summary': {
                k: {
                    'label': v['label'],
                    'count': v['count'],
                    'amount': float(v['amount'])
                } for k, v in reason_summary.items()
            },
            'total_returns': len(history),
            'total_returned_amount': float(total_returned_amount),
            'total_returned_items': total_returned_items,
            'purchase_bill_no': purchase.bill_no or 'Pending',
            'purchase_date': purchase.pur_date.strftime('%d-%m-%Y'),
            'vendor_name': purchase.vendor.name,
            'vendor_id': purchase.vendor.id
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
def purchase_return_delete(request, pk):
    """Delete purchase return with confirmation"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can delete returns.')
        return redirect('purchase_return_detail', pk=pk)
    
    purchase_return = get_object_or_404(PurchaseRetrn, pk=pk)
    
    if not purchase_return.can_delete:
        messages.error(request, '❌ This return cannot be deleted (more than 7 days old)!')
        return redirect('purchase_return_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            return_id = purchase_return.id
            vendor_name = purchase_return.vendor.name
            total_amount = purchase_return.total_return_amount()
            
            # ✅ Delete will restore stock (via model delete method)
            purchase_return.delete()
            
            messages.success(
                request, 
                f'✅ Purchase Return #{return_id} deleted successfully!\n'
                f'Vendor: {vendor_name}\n'
                f'Amount: Rs. {total_amount:,.2f}'
            )
            return redirect('purchase_return_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error deleting return: {str(e)}')
            return redirect('purchase_return_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'return': purchase_return,
        'total_amount': purchase_return.total_return_amount(),
        'total_items': purchase_return.total_items_returned(),
    }
    return render(request, 'returns/purchase_return_delete.html', context)


@login_required
def get_sale_return_history(request):
    """
    AJAX: Get return history for a specific sale
    Returns detailed history of all returns with product summaries
    """
    sale_id = request.GET.get('sale_id')
    
    if not sale_id:
        return JsonResponse({
            'success': False, 
            'message': 'Sale ID required'
        })
    
    try:
        sale = Sale.objects.get(id=sale_id)
        returns = SaleRetrn.objects.filter(sale=sale).order_by('-sale_return_date')
        
        history = []
        total_returned_amount = Decimal('0.00')
        total_returned_items = 0
        
        # ✅ Build return history
        for ret in returns:
            items = []
            ret_total = Decimal('0.00')
            ret_items_count = 0
            
            for item in ret.return_items.all():
                items.append({
                    'product_name': item.product.name,
                    'product_id': item.product.id,
                    'qty': float(item.qty),
                    'amount': float(item.total_amt),
                    'price': float(item.price),
                    'unit': item.product.unit.name if item.product.unit else ''
                })
                ret_total += item.total_amt
                ret_items_count += 1
            
            history.append({
                'id': ret.id,
                'date': ret.sale_return_date.strftime('%d-%m-%Y %H:%M'),
                'date_short': ret.sale_return_date.strftime('%d %b, %Y'),
                'time': ret.sale_return_date.strftime('%I:%M %p'),
                'reason': ret.get_return_reason_display(),
                'reason_code': ret.return_reason,
                'bill_no': ret.bill_no or 'N/A',
                'items': items,
                'total_amount': float(ret_total),
                'total_items': ret_items_count,
                'created_by': ret.created_by.username if ret.created_by else 'System',
                'warehouse': ret.warehouse.name if ret.warehouse else 'N/A'
            })
            
            total_returned_amount += ret_total
            total_returned_items += ret_items_count
        
        # ✅ Product-wise return summary
        product_summary = {}
        for ret in returns:
            for item in ret.return_items.all():
                key = item.product.id
                if key not in product_summary:
                    product_summary[key] = {
                        'name': item.product.name,
                        'total_returned': Decimal('0.00'),
                        'total_amount': Decimal('0.00'),
                        'return_count': 0,
                        'unit': item.product.unit.name if item.product.unit else ''
                    }
                product_summary[key]['total_returned'] += item.qty
                product_summary[key]['total_amount'] += item.total_amt
                product_summary[key]['return_count'] += 1
        
        # ✅ Reason-wise summary
        reason_summary = {}
        for ret in returns:
            reason = ret.return_reason
            if reason not in reason_summary:
                reason_summary[reason] = {
                    'label': ret.get_return_reason_display(),
                    'count': 0,
                    'amount': Decimal('0.00')
                }
            reason_summary[reason]['count'] += 1
            reason_summary[reason]['amount'] += sum(item.total_amt for item in ret.return_items.all())
        
        # ✅ Get sale items for available products
        sale_items = []
        for item in sale.saleitem_set.all():
            already_returned = Decimal('0.00')
            for ret in returns:
                for r_item in ret.return_items.all():
                    if r_item.product.id == item.product.id:
                        already_returned += r_item.qty
            
            available = Decimal(str(item.qty)) - already_returned
            
            sale_items.append({
                'product_id': item.product.id,
                'product_name': item.product.name,
                'original_qty': float(item.qty),
                'already_returned': float(already_returned),
                'available': float(available),
                'price': float(item.price),
                'unit': item.product.unit.name if item.product.unit else ''
            })
        
        return JsonResponse({
            'success': True,
            'returns': history,
            'sale_items': sale_items,
            'product_summary': {
                str(k): {
                    'name': v['name'],
                    'total_returned': float(v['total_returned']),
                    'total_amount': float(v['total_amount']),
                    'return_count': v['return_count'],
                    'unit': v['unit']
                } for k, v in product_summary.items()
            },
            'reason_summary': {
                k: {
                    'label': v['label'],
                    'count': v['count'],
                    'amount': float(v['amount'])
                } for k, v in reason_summary.items()
            },
            'total_returns': len(history),
            'total_returned_amount': float(total_returned_amount),
            'total_returned_items': total_returned_items,
            'sale_bill_no': sale.bill_no,
            'sale_date': sale.sale_date.strftime('%d-%m-%Y'),
            'customer_name': sale.customer.name,
            'customer_id': sale.customer.id,
            'warehouse_name': sale.warehouse.name if sale.warehouse else 'N/A',
        })
        
    except Sale.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'message': 'Sale not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e)
        })


@login_required
def sale_return_delete(request, pk):
    """Delete sale return with confirmation"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can delete returns.')
        return redirect('sale_return_detail', pk=pk)
    
    sale_return = get_object_or_404(SaleRetrn, pk=pk)
    
    if not sale_return.can_delete:
        messages.error(request, '❌ This return cannot be deleted (more than 7 days old)!')
        return redirect('sale_return_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            return_id = sale_return.id
            customer_name = sale_return.customer.name
            total_amount = sale_return.total_return_amount()
            total_items = sale_return.total_items_returned()
            
            # ✅ Delete will restore stock (via model delete method)
            sale_return.delete()
            
            messages.success(
                request, 
                f'✅ Sale Return #{return_id} deleted successfully!\n'
                f'Customer: {customer_name}\n'
                f'Items: {total_items}\n'
                f'Amount: Rs. {total_amount:,.2f}'
            )
            return redirect('sale_return_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error deleting return: {str(e)}')
            return redirect('sale_return_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'return': sale_return,
        'total_amount': sale_return.total_return_amount(),
        'total_items': sale_return.total_items_returned(),
        'return_reason_display': sale_return.get_return_reason_display(),
    }
    return render(request, 'returns/sale_return_delete.html', context)
