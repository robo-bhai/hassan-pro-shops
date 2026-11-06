"""
Purchase Orders (professional version).

This module is loaded AFTER `purchasing` (see _MODULES in views_frontend/__init__.py), so the
views below replace the old ones with the same names. No migration is needed.

Extra URLs (added by patch_po.py):
    orders/purchase/products/              purchase_order_products   (product search, JSON)
    orders/purchase/<pk>/edit/             purchase_order_edit
    orders/purchase/<pk>/print/            purchase_order_print
    orders/purchase/<pk>/duplicate/        purchase_order_duplicate
"""
import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, FloatField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST

from .. import store_access as _sa
from .. import store_receive as _sr
from ..models import (CompanyInfo, GoodsReceivedItem, GoodsReceivedNote, Product, PurchaseItem,
                      PurchaseOrder, PurchaseOrderItem, Vendor, Warehouse)

OPEN_STATUSES = ['pending', 'confirmed', 'processing', 'shipped', 'partially_received']
RECEIVABLE = ['confirmed', 'processing', 'shipped', 'partially_received']
EDITABLE = ['pending', 'confirmed']
EPS = 1e-9

# status -> [(next status, button label, bootstrap colour, icon)]
TRANSITIONS = {
    'pending': [('confirmed', 'Confirm order', 'success', 'bi-check2-circle'),
                ('cancelled', 'Cancel order', 'danger', 'bi-x-circle')],
    'confirmed': [('processing', 'Mark processing', 'primary', 'bi-gear'),
                  ('shipped', 'Mark shipped', 'info', 'bi-truck'),
                  ('cancelled', 'Cancel order', 'danger', 'bi-x-circle')],
    'processing': [('shipped', 'Mark shipped', 'info', 'bi-truck'),
                   ('cancelled', 'Cancel order', 'danger', 'bi-x-circle')],
    'shipped': [('cancelled', 'Cancel order', 'danger', 'bi-x-circle')],
    'partially_received': [('completed', 'Close order (short)', 'success', 'bi-flag')],
    'received': [('completed', 'Mark completed', 'success', 'bi-check-all')],
    'cancelled': [('pending', 'Reopen order', 'secondary', 'bi-arrow-counterclockwise')],
    'completed': [],
}

MONEY = DecimalField(max_digits=20, decimal_places=2)


# ---------------------------------------------------------------- helpers
def _company():
    return CompanyInfo.objects.first()


def _company_name():
    c = _company()
    return c.name if c else 'ERP System'


def _num(value, label, default='0'):
    raw = str(value if value not in (None, '') else default).strip().replace(',', '')
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}: invalid number.')
    if not d.is_finite():
        raise ValueError(f'{label}: invalid number.')
    return d


def _audit(request, order, action, changes=None):
    """Best effort audit trail (never breaks the page)."""
    try:
        from ..models import AuditTrail
        AuditTrail.objects.create(
            user=request.user, model_name='PurchaseOrder', record_id=str(order.pk), action=action,
            changes=changes or {}, ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:250])
    except Exception:
        pass


def _annotated(qs):
    """Add gross / net / ordered qty to a PurchaseOrder queryset (one query)."""
    return qs.annotate(
        gross=Coalesce(Sum('items__total_amt', output_field=MONEY), Value(Decimal('0.00'), output_field=MONEY),
                       output_field=MONEY),
        ordered_qty=Coalesce(Sum('items__qty'), Value(0.0), output_field=FloatField()),
        item_count=Count('items', distinct=True),
    ).annotate(net=ExpressionWrapper(F('gross') - F('discount_value'), output_field=MONEY))


def _received_map(order_ids):
    rows = (GoodsReceivedItem.objects.filter(grn__purchase_order_id__in=order_ids)
            .values('grn__purchase_order_id').annotate(s=Sum('qty')))
    return {r['grn__purchase_order_id']: r['s'] or 0 for r in rows}


def _received_by_product(order):
    rows = (GoodsReceivedItem.objects.filter(grn__purchase_order=order)
            .values('product_id').annotate(s=Sum('qty')))
    return {r['product_id']: r['s'] or 0 for r in rows}


def _is_overdue(order):
    return bool(order.expected_date and order.status in OPEN_STATUSES and order.expected_date < localdate())


def _percent(done, total):
    return min(100, round(done / total * 100)) if total and total > 0 else 0


# ---------------------------------------------------------------- list
@login_required
def purchase_order_list(request):
    today = localdate()
    base = _sa.hide_other_stores(request.user, PurchaseOrder.objects.all(), 'warehouse')

    # ----- KPI cards (whole store-visible data, not the filtered page)
    counts = base.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        confirmed=Count('id', filter=Q(status__in=['confirmed', 'processing', 'shipped'])),
        partial=Count('id', filter=Q(status='partially_received')),
        done=Count('id', filter=Q(status__in=['received', 'completed'])),
        overdue=Count('id', filter=Q(status__in=OPEN_STATUSES, expected_date__lt=today)),
    )
    open_value = Decimal('0.00')
    for gross, disc in (_annotated(base.filter(status__in=OPEN_STATUSES)).values_list('gross', 'discount_value')):
        open_value += (gross or 0) - (disc or 0)

    # ----- filters
    qs = _annotated(base.select_related('vendor', 'warehouse', 'created_by'))
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(order_no__icontains=search) | Q(vendor__name__icontains=search) |
                       Q(vendor__vendor_code__icontains=search) | Q(vendor_so_number__icontains=search))
    status = request.GET.get('status', '')
    if status == 'overdue':
        qs = qs.filter(status__in=OPEN_STATUSES, expected_date__lt=today)
    elif status == 'open':
        qs = qs.filter(status__in=OPEN_STATUSES)
    elif status:
        qs = qs.filter(status=status)
    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id.isdigit():
        qs = qs.filter(warehouse_id=int(warehouse_id))
    vendor_id = request.GET.get('vendor', '')
    if vendor_id.isdigit():
        qs = qs.filter(vendor_id=int(vendor_id))

    def _day(v):
        try:
            return datetime.strptime((v or '').strip(), '%Y-%m-%d').date()
        except ValueError:
            return None
    date_from, date_to = _day(request.GET.get('from')), _day(request.GET.get('to'))
    if date_from:
        qs = qs.filter(order_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(order_date__date__lte=date_to)

    sorts = {'date_desc': ('-order_date', '-id'), 'date_asc': ('order_date', 'id'),
             'amount_desc': ('-net', '-id'), 'expected': ('expected_date', '-id')}
    sort = request.GET.get('sort', 'date_desc')
    if sort not in sorts:
        sort = 'date_desc'
    qs = qs.order_by(*sorts[sort])

    # ----- CSV export (current filter)
    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="purchase_orders.csv"'
        w = csv.writer(resp)
        w.writerow(['PO No', 'Date', 'Vendor', 'Warehouse', 'Expected', 'Status', 'Items', 'Total', 'Discount',
                    'Net', 'Advance'])
        for o in qs:
            w.writerow([o.order_no, o.order_date.strftime('%d-%m-%Y'), o.vendor.name, o.warehouse.name,
                        o.expected_date or '', o.get_status_display(), o.item_count, o.gross, o.discount_value,
                        o.net, o.advance_payment])
        return resp

    filtered_value = sum(((g or 0) - (d or 0)) for g, d in qs.values_list('gross', 'discount_value'))
    page_obj = Paginator(qs, 25).get_page(request.GET.get('page', 1))

    received = _received_map([o.pk for o in page_obj])
    for o in page_obj:
        o.receive_percent = _percent(received.get(o.pk, 0), o.ordered_qty)
        o.is_overdue = _is_overdue(o)
        o.days_late = (today - o.expected_date).days if o.is_overdue else 0
        o.next_actions = TRANSITIONS.get(o.status, [])
        o.can_receive = o.status in RECEIVABLE

    keep = request.GET.copy()
    keep.pop('page', None)
    keep.pop('export', None)

    return render(request, 'orders/purchase_order_list.html', {
        'company_name': _company_name(),
        'page_obj': page_obj,
        'search': search, 'selected_status': status, 'selected_warehouse': warehouse_id,
        'selected_vendor': vendor_id, 'sort': sort,
        'date_from': request.GET.get('from', ''), 'date_to': request.GET.get('to', ''),
        'warehouses': _sa.hide_other_stores(request.user, Warehouse.objects.all()),
        'vendors': Vendor.objects.order_by('name'),
        'status_choices': PurchaseOrder.ORDER_STATUS,
        'counts': counts, 'open_value': open_value, 'filtered_value': filtered_value,
        'querystring': keep.urlencode(),
        'today': today,
    })


# ---------------------------------------------------------------- create / edit
def _read_items(request):
    """Rows from the form -> merged list of (Product, qty float, price Decimal)."""
    ids = request.POST.getlist('product_id[]')
    qtys = request.POST.getlist('qty[]')
    prices = request.POST.getlist('price[]')
    merged = {}
    for i, pid in enumerate(ids):
        if not pid:
            continue
        product = Product.objects.filter(pk=pid).first()
        if not product:
            raise ValueError('One of the products no longer exists.')
        qty = _num(qtys[i] if i < len(qtys) else 0, f'{product.name} quantity')
        price = _num(prices[i] if i < len(prices) else 0, f'{product.name} price')
        if qty <= 0:
            raise ValueError(f'{product.name}: quantity must be greater than zero.')
        if price <= 0:
            raise ValueError(f'{product.name}: enter the purchase price.')
        if product.pk in merged:          # same product twice -> merge, weighted average price
            p0, q0, pr0 = merged[product.pk]
            q = q0 + qty
            merged[product.pk] = (product, q, ((pr0 * q0) + (price * qty)) / q)
        else:
            merged[product.pk] = (product, qty, price)
    if not merged:
        raise ValueError('Add at least one product.')
    return [(p, float(q), pr.quantize(Decimal('0.01'))) for p, q, pr in merged.values()]


def _save_from_post(request, order=None):
    vendor = Vendor.objects.filter(pk=request.POST.get('vendor')).first()
    warehouse = Warehouse.objects.filter(pk=request.POST.get('warehouse')).first()
    if not vendor or not warehouse:
        raise ValueError('Vendor and warehouse are required.')
    if not _sr.can_receive(request.user, warehouse.pk):
        raise ValueError('You cannot create an order for this store.')

    status = request.POST.get('status', 'pending')
    if status not in ('pending', 'confirmed'):
        status = 'pending'
    expected = (request.POST.get('expected_date') or '').strip()
    expected_date = None
    if expected:
        try:
            expected_date = datetime.strptime(expected, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('Expected date is invalid.')

    items = _read_items(request)
    gross = sum((Decimal(str(q)) * pr for _, q, pr in items), Decimal('0'))
    discount = _num(request.POST.get('discount'), 'Discount')
    advance = _num(request.POST.get('advance'), 'Advance')
    if discount < 0 or discount > gross:
        raise ValueError('Discount must be between 0 and the order total.')
    if advance < 0 or advance > gross - discount:
        raise ValueError('Advance cannot be more than the net total.')

    fields = dict(vendor=vendor, warehouse=warehouse, expected_date=expected_date,
                  vendor_so_number=(request.POST.get('vendor_so') or '').strip()[:50],
                  notes=(request.POST.get('notes') or '').strip(),
                  discount_value=discount, advance_payment=advance)
    with transaction.atomic():
        if order is None:
            order = PurchaseOrder.objects.create(status=status, created_by=request.user, **fields)
            action = 'created'
        else:
            for k, v in fields.items():
                setattr(order, k, v)
            order.status = status
            order.save()
            order.items.all().delete()
            action = 'edited'
        for product, qty, price in items:
            PurchaseOrderItem.objects.create(order=order, product=product, qty=qty, price=price)
    _audit(request, order, action, {'total': str(gross - discount), 'items': len(items)})
    return order


def _form_context(request, order=None, rows=None, copy_of=None):
    return {
        'company_name': _company_name(),
        'order': order, 'copy_of': copy_of,
        'vendors': Vendor.objects.order_by('name'),
        'warehouses': _sr.receivable_warehouses(request.user),
        'rows': rows or [],
        'today': localdate(),
    }


def _rows_of(order):
    return [{'id': i.product_id, 'name': i.product.name, 'qty': i.qty, 'price': float(i.price),
             'unit': i.product.unit.name if i.product.unit_id else ''}
            for i in order.items.select_related('product', 'product__unit')]


@login_required
def purchase_order_create(request):
    if request.method == 'POST':
        try:
            order = _save_from_post(request)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(request.get_full_path())
        except Exception as e:
            messages.error(request, f'Could not save the order: {e}')
            return redirect(request.get_full_path())
        messages.success(request, f'Purchase order {order.order_no} created.')
        return redirect('purchase_order_detail', pk=order.pk)

    order_copy = None
    rows = []
    cp = request.GET.get('copy', '')
    if cp.isdigit():
        order_copy = PurchaseOrder.objects.filter(pk=int(cp)).first()
        if order_copy:
            rows = _rows_of(order_copy)
    return render(request, 'orders/purchase_order_create.html', _form_context(request, rows=rows, copy_of=order_copy))


@login_required
def purchase_order_edit(request, pk):
    order = get_object_or_404(_sa.hide_other_stores(request.user, PurchaseOrder.objects.all(), 'warehouse'), pk=pk)
    if order.status not in EDITABLE or order.grns.exists():
        messages.error(request, 'Only pending or confirmed orders without any GRN can be edited.')
        return redirect('purchase_order_detail', pk=order.pk)
    if request.method == 'POST':
        try:
            _save_from_post(request, order)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(request.get_full_path())
        except Exception as e:
            messages.error(request, f'Could not save the order: {e}')
            return redirect(request.get_full_path())
        messages.success(request, f'Purchase order {order.order_no} updated.')
        return redirect('purchase_order_detail', pk=order.pk)
    return render(request, 'orders/purchase_order_create.html', _form_context(request, order=order, rows=_rows_of(order)))


@login_required
def purchase_order_duplicate(request, pk):
    from django.urls import reverse
    return redirect(f"{reverse('purchase_order_create')}?copy={int(pk)}")


@login_required
def purchase_order_products(request):
    """Product search for the PO form (type-ahead). Returns last purchase price too."""
    q = (request.GET.get('q') or '').strip()
    qs = Product.objects.filter(is_active=True).select_related('unit')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(barcode__icontains=q) | Q(serial_no__icontains=q))
    products = list(qs.order_by('name')[:25])
    ids = [p.pk for p in products]
    last = {}
    for pid, price in (PurchaseItem.objects.filter(product_id__in=ids).order_by('-id')
                       .values_list('product_id', 'price')):
        last.setdefault(pid, float(price))
    return JsonResponse({'results': [{
        'id': p.pk, 'name': p.name, 'unit': p.unit.name if p.unit_id else '',
        'barcode': p.barcode or '', 'last_price': last.get(p.pk, 0),
    } for p in products]})


# ---------------------------------------------------------------- detail / print
def _detail_data(request, pk):
    order = get_object_or_404(
        _sa.hide_other_stores(request.user, PurchaseOrder.objects.all(), 'warehouse')
        .select_related('vendor', 'warehouse', 'created_by').prefetch_related('items__product__unit'), pk=pk)
    got = _received_by_product(order)
    rows, t_ord, t_rec = [], 0.0, 0.0
    gross = Decimal('0.00')
    for it in order.items.all():
        rec = got.get(it.product_id, 0)
        pending = max(0.0, it.qty - rec)
        rows.append({'item': it, 'received': rec, 'pending': pending, 'percent': _percent(rec, it.qty),
                     'over': rec - it.qty > EPS, 'total': it.total_amt,
                     'unit': it.product.unit.name if it.product.unit_id else ''})
        t_ord += it.qty
        t_rec += min(rec, it.qty)
        gross += it.total_amt
    net = gross - order.discount_value
    grns = list(order.grns.prefetch_related('items').order_by('-grn_date'))
    return order, {
        'company_name': _company_name(), 'company': _company(),
        'order': order, 'rows': rows, 'grns': grns,
        'gross': gross, 'net': net, 'balance': net - order.advance_payment,
        'total_ordered': t_ord, 'total_received': t_rec, 'total_pending': max(0.0, t_ord - t_rec),
        'receive_percent': _percent(t_rec, t_ord),
        'is_overdue': _is_overdue(order),
        'days_late': (localdate() - order.expected_date).days if _is_overdue(order) else 0,
        'can_edit': order.status in EDITABLE and not grns,
        'can_receive': order.status in RECEIVABLE and t_ord - t_rec > EPS,
        'actions': [a for a in TRANSITIONS.get(order.status, []) if not (a[0] == 'cancelled' and grns)],
        'today': localdate(),
    }


@login_required
def purchase_order_detail(request, pk):
    order, ctx = _detail_data(request, pk)
    return render(request, 'orders/purchase_order_detail.html', ctx)


@login_required
def purchase_order_print(request, pk):
    order, ctx = _detail_data(request, pk)
    return render(request, 'orders/purchase_order_print.html', ctx)


# ---------------------------------------------------------------- status
@login_required
@require_POST
def purchase_order_quick_status(request, pk, status):
    order = get_object_or_404(_sa.hide_other_stores(request.user, PurchaseOrder.objects.all(), 'warehouse'), pk=pk)
    allowed = {a[0] for a in TRANSITIONS.get(order.status, [])}
    back = request.POST.get('next') or ''
    target = back if back.startswith('/') and not back.startswith('//') else None

    def done():
        return redirect(target) if target else redirect('purchase_order_detail', pk=order.pk)

    if status not in allowed:
        messages.error(request, f'{order.order_no}: cannot change from {order.get_status_display()} to "{status}".')
        return done()
    if status == 'cancelled' and order.grns.exists():
        messages.error(request, f'{order.order_no} already has goods received, so it cannot be cancelled.')
        return done()
    old = order.status
    order.status = status
    order.save(update_fields=['status', 'updated_at'])
    _audit(request, order, 'status', {'from': old, 'to': status})
    messages.success(request, f'{order.order_no}: {dict(PurchaseOrder.ORDER_STATUS)[old]} to {order.get_status_display()}.')
    return done()


# ---------------------------------------------------------------- receive goods (GRN)
@login_required
def purchase_order_create_grn(request, pk):
    order = get_object_or_404(_sa.hide_other_stores(request.user, PurchaseOrder.objects.all(), 'warehouse'), pk=pk)
    if request.method != 'POST':
        return redirect(f"/orders/purchase/{order.pk}/#receive")
    if not _sr.can_receive(request.user, order.warehouse_id):
        messages.error(request, 'You do not have the right to receive goods in this store.')
        return redirect('purchase_order_detail', pk=order.pk)
    if order.status not in RECEIVABLE:
        messages.error(request, 'The order must be confirmed before goods can be received.')
        return redirect('purchase_order_detail', pk=order.pk)

    try:
        got = _received_by_product(order)
        lines = []
        for it in order.items.select_related('product'):
            pending = it.qty - got.get(it.product_id, 0)
            if pending <= EPS:
                continue
            raw = request.POST.get(f'recv_{it.pk}', '')
            if raw == '':
                continue
            q = float(_num(raw, f'{it.product.name} received qty'))
            if q < 0:
                raise ValueError(f'{it.product.name}: quantity cannot be negative.')
            if q == 0:
                continue
            if q - pending > EPS:
                raise ValueError(f'{it.product.name}: only {pending:g} still pending, you entered {q:g}.')
            lines.append((it, q))
        if not lines:
            raise ValueError('Enter a received quantity for at least one item.')
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.create(
                purchase_order=order, vendor=order.vendor, warehouse=order.warehouse, reason='purchase',
                invoice_no=(request.POST.get('invoice_no') or '').strip()[:50] or None,
                vehicle_no=(request.POST.get('vehicle_no') or '').strip()[:30] or None,
                driver_name=(request.POST.get('driver_name') or '').strip()[:100] or None,
                notes=(request.POST.get('notes') or '').strip() or None,
                created_by=request.user)
            for it, q in lines:
                GoodsReceivedItem.objects.create(grn=grn, product=it.product, order_qty=it.qty, qty=q, price=it.price)
            order.update_receive_status()
        _audit(request, order, 'grn', {'grn': grn.grn_no, 'lines': len(lines)})
        order.refresh_from_db()
        messages.success(request, f'GRN {grn.grn_no} created. Order is now: {order.get_status_display()}.')
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Could not create the GRN: {e}')
    return redirect('purchase_order_detail', pk=order.pk)
