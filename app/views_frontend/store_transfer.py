"""Frontend views: store-to-store transfer (bhejna / receive karna) + Store Receipts (purchase / GRN)."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import (CompanyInfo, GoodsReceivedNote, Product, ProductionOrder, Purchase,
                      StoreTransfer, Warehouse)
from .. import store_access as _sa
from .. import store_transfer_service as _sts


# ---------------------------------------------------------------------------
# helpers (prefix _st_ so they do not clash with other modules)
# ---------------------------------------------------------------------------
def _st_company():
    info = CompanyInfo.objects.first()
    return info.name if info else 'ERP System'


def _st_deny(request, what='view this page'):
    messages.error(request, f'Access denied! You are not allowed to {what}.')
    return redirect('dashboard')


def _st_no_store(request):
    messages.error(request, 'You do not have access to any store yet. Ask a superuser to add you to a store team.')
    return redirect('dashboard')


def _st_date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _st_stores_qs(ids=None):
    qs = Warehouse.objects.select_related('store_profile').order_by('name')
    qs = qs.exclude(pk__in=_sa.unavailable_warehouse_ids())
    return qs if ids is None else qs.filter(pk__in=ids)


def _st_send_stores(user):
    """Stores from which this user can send goods (keeper+ and the store has can_issue)."""
    ids = _sa.allowed_ids(user, 'keeper')
    qs = _st_stores_qs(ids).filter(Q(store_profile__isnull=True) |
                                   Q(store_profile__is_active=True, store_profile__can_issue=True))
    return list(qs)


def _st_dest_stores():
    """Goods can be sent to any active store (even a store of another team - they are the ones who will receive)."""
    return list(_st_stores_qs().filter(Q(store_profile__isnull=True) | Q(store_profile__is_active=True)))


def _st_can_see(user, transfer):
    return (_sa.can(user, transfer.from_warehouse_id, 'viewer') or
            _sa.can(user, transfer.to_warehouse_id, 'viewer'))


def _st_get(request, pk):
    t = get_object_or_404(
        StoreTransfer.objects.select_related('from_warehouse', 'to_warehouse', 'created_by', 'received_by',
                                             'cancelled_by', 'production_order'), pk=pk)
    if not _st_can_see(request.user, t):
        raise Http404('Transfer not found')
    return t


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
@login_required
def store_transfer_list(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _st_no_store(request)

    qs = StoreTransfer.objects.select_related('from_warehouse', 'to_warehouse', 'created_by')
    if view_ids is not None:
        qs = qs.filter(Q(from_warehouse_id__in=view_ids) | Q(to_warehouse_id__in=view_ids))

    status = request.GET.get('status', '')
    q = (request.GET.get('q') or '').strip()
    store = request.GET.get('store', '')
    d_from, d_to = _st_date(request.GET.get('from')), _st_date(request.GET.get('to'))
    if status in ('in_transit', 'received', 'cancelled'):
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(transfer_no__icontains=q) | Q(items__product__name__icontains=q)).distinct()
    if store.isdigit():
        qs = qs.filter(Q(from_warehouse_id=int(store)) | Q(to_warehouse_id=int(store)))
    if d_from:
        qs = qs.filter(transfer_date__date__gte=d_from)
    if d_to:
        qs = qs.filter(transfer_date__date__lte=d_to)

    recv_ids = _sa.allowed_ids(request.user, 'keeper')
    waiting = StoreTransfer.objects.filter(status='in_transit')
    if recv_ids is not None:
        waiting = waiting.filter(to_warehouse_id__in=recv_ids)
    waiting_count = waiting.count()

    page_obj = Paginator(qs.annotate(item_count=Count('items', distinct=True)).order_by('-transfer_date', '-id'),
                         25).get_page(request.GET.get('page', 1))
    for t in page_obj.object_list:
        t.can_receive = t.status == 'in_transit' and _sa.can(request.user, t.to_warehouse_id, 'keeper')

    keep = request.GET.copy()
    keep.pop('page', None)
    return render(request, 'store_issue/transfer_list.html', {
        'company_name': _st_company(), 'page_obj': page_obj, 'qs': keep.urlencode(),
        'f': {'status': status, 'q': q, 'store': store, 'from': request.GET.get('from', ''),
              'to': request.GET.get('to', '')},
        'stores': _st_stores_qs(view_ids), 'waiting_count': waiting_count,
        'can_send': bool(_st_send_stores(request.user)),
        'filters_active': bool(status or q or store or d_from or d_to),
    })


# ---------------------------------------------------------------------------
# Create (dispatch)
# ---------------------------------------------------------------------------
def _st_parse_dt(value):
    value = (value or '').strip()
    if not value:
        return timezone.now()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(value, fmt)
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except ValueError:
            continue
    raise _sts.StoreTransferError('Invalid date.')


def _st_form_context(request, form=None, rows=None):
    return {
        'company_name': _st_company(),
        'from_stores': _st_send_stores(request.user),
        'to_stores': _st_dest_stores(),
        'purposes': StoreTransfer.PURPOSES,
        'production_orders': ProductionOrder.objects.filter(status__in=['approved', 'in_progress']).select_related('product'),
        'form': form or {'purpose': request.GET.get('purpose', 'production'),
                         'from_store': request.GET.get('from', ''), 'to_store': request.GET.get('to', ''),
                         'transfer_date': timezone.localtime().strftime('%Y-%m-%dT%H:%M')},
        'rows': rows or [],
    }


@login_required
def store_transfer_create(request):
    if not _st_send_stores(request.user):
        return _st_deny(request, 'send stock (you are not a keeper/manager of any store)')

    if request.method != 'POST':
        return render(request, 'store_issue/transfer_form.html', _st_form_context(request))

    p = request.POST
    form = {k: p.get(k, '') for k in ('from_store', 'to_store', 'purpose', 'production_order', 'notes',
                                      'transfer_date')}
    ids, qtys, remarks = p.getlist('product_id'), p.getlist('qty'), p.getlist('remarks')
    raw = [(i.strip(), (qtys[n] if n < len(qtys) else '').strip(), (remarks[n] if n < len(remarks) else '').strip())
           for n, i in enumerate(ids)]
    raw = [r for r in raw if r[0] or r[1]]
    products = {str(x.pk): x for x in Product.objects.filter(pk__in=[r[0] for r in raw if r[0].isdigit()])}
    rows = [{'product_id': r[0], 'name': products[r[0]].name if r[0] in products else '', 'qty': r[1],
             'remarks': r[2]} for r in raw]

    def fail(msg):
        messages.error(request, f'❌ {msg}')
        return render(request, 'store_issue/transfer_form.html', _st_form_context(request, form, rows))

    try:
        src = Warehouse.objects.filter(pk=form['from_store']).first() if form['from_store'].isdigit() else None
        dst = Warehouse.objects.filter(pk=form['to_store']).first() if form['to_store'].isdigit() else None
        if src is not None and not _sa.can(request.user, src.pk, 'keeper'):
            return fail('You do not have the right to send goods from this store.')
        if dst is not None and dst.pk in _sa.unavailable_warehouse_ids():
            return fail('This store is not available right now.')
        order = (ProductionOrder.objects.filter(pk=form['production_order']).first()
                 if form['production_order'].isdigit() else None)
        when = _st_parse_dt(form['transfer_date'])
        if when > timezone.now() + timedelta(days=1):
            return fail('A future date is not allowed.')
        items = []
        for pid, qty, rem in raw:
            if pid not in products:
                return fail('Select an item in every line.')
            items.append((products[pid], qty, rem))
        transfer = _sts.dispatch_transfer(user=request.user, from_warehouse=src, to_warehouse=dst,
                                          purpose=form['purpose'], items=items, transfer_date=when,
                                          production_order=order, notes=form['notes'])
    except _sts.StoreTransferError as e:
        return fail(str(e))

    messages.success(request, f'✅ {transfer.transfer_no} sent. The team of {dst.name} will receive it.')
    return redirect('store_transfer_detail', pk=transfer.pk)


# ---------------------------------------------------------------------------
# Detail / receive / cancel / print
# ---------------------------------------------------------------------------
@login_required
def store_transfer_detail(request, pk):
    t = _st_get(request, pk)
    in_transit = t.status == 'in_transit'
    return render(request, 'store_issue/transfer_detail.html', {
        'company_name': _st_company(), 't': t,
        'items': t.items.select_related('product', 'product__unit'),
        'can_receive': in_transit and _sa.can(request.user, t.to_warehouse_id, 'keeper'),
        'can_cancel': in_transit and _sa.can(request.user, t.from_warehouse_id, 'manager'),
    })


@login_required
@require_POST
def store_transfer_receive(request, pk):
    t = _st_get(request, pk)
    if not _sa.can(request.user, t.to_warehouse_id, 'keeper'):
        return _st_deny(request, f'receive stock into {t.to_warehouse.name}')
    received, reasons = {}, {}
    for item in t.items.all():
        raw = (request.POST.get(f'recv_{item.pk}') or '').strip()
        if raw != '':
            try:
                received[item.pk] = float(raw)
            except ValueError:
                messages.error(request, f'❌ {item.product.name}: enter a valid quantity.')
                return redirect('store_transfer_detail', pk=pk)
        reasons[item.pk] = request.POST.get(f'reason_{item.pk}', '')
    try:
        _sts.receive_transfer(t.pk, request.user, received, reasons, request.POST.get('notes', ''))
    except _sts.StoreTransferError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_transfer_detail', pk=pk)
    messages.success(request, f'✅ {t.transfer_no} received, the stock arrived in {t.to_warehouse.name}.')
    return redirect('store_transfer_detail', pk=pk)


@login_required
@require_POST
def store_transfer_cancel(request, pk):
    t = _st_get(request, pk)
    if not _sa.can(request.user, t.from_warehouse_id, 'manager'):
        return _st_deny(request, 'cancel this transfer')
    reason = (request.POST.get('reason') or '').strip()
    if not reason:
        messages.error(request, '❌ A reason for cancelling is required.')
        return redirect('store_transfer_detail', pk=pk)
    try:
        _sts.cancel_transfer(t.pk, request.user, reason)
    except _sts.StoreTransferError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_transfer_detail', pk=pk)
    messages.success(request, f'↩️ {t.transfer_no} cancelled, the goods are back in {t.from_warehouse.name}.')
    return redirect('store_transfer_detail', pk=pk)


@login_required
def store_transfer_print(request, pk):
    t = _st_get(request, pk)
    return render(request, 'store_issue/transfer_print.html', {
        'company_name': _st_company(), 'company': CompanyInfo.objects.first(), 't': t,
        'items': t.items.select_related('product', 'product__unit'),
    })


# ---------------------------------------------------------------------------
# Store Receipts: which store the purchase / GRN goods went to
# ---------------------------------------------------------------------------
@login_required
def store_receipts(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _st_no_store(request)

    d_from = _st_date(request.GET.get('from')) or date.today().replace(day=1)
    d_to = _st_date(request.GET.get('to')) or date.today()
    kind = request.GET.get('kind', '')
    store = request.GET.get('store', '')
    only_pending = request.GET.get('pending') == '1'

    wh_filter = {}
    if store.isdigit() and (view_ids is None or int(store) in view_ids):
        wh_filter = {'warehouse_id': int(store)}
    elif view_ids is not None:
        wh_filter = {'warehouse_id__in': view_ids}
    wh_filter.setdefault('warehouse__isnull', False)
    excl = _sa.unavailable_warehouse_ids()

    rows = []
    if kind in ('', 'grn'):
        grns = (GoodsReceivedNote.objects.select_related('vendor', 'warehouse', 'purchase_order')
                .filter(grn_date__date__gte=d_from, grn_date__date__lte=d_to, **wh_filter)
                .exclude(warehouse_id__in=excl)
                .annotate(total_qty_=Sum('items__qty'), total_value_=Sum('items__total_amt')))
        if only_pending:
            grns = grns.filter(converted_to_purchase=False)
        for g in grns.order_by('-grn_date')[:300]:
            rows.append({
                'kind': 'GRN', 'no': g.grn_no, 'date': g.grn_date, 'vendor': g.vendor.name, 'store': g.warehouse,
                'qty': g.total_qty_ or 0, 'value': g.total_value_ or Decimal('0.00'),
                'posted': g.converted_to_purchase,
                'status': 'Stock has arrived in the store' if g.converted_to_purchase else 'Stock has NOT arrived in the store yet (convert to purchase)',
                'url_name': 'grn_detail', 'pk': g.pk,
            })
    if kind in ('', 'purchase') and not only_pending:
        purchases = (Purchase.objects.select_related('vendor', 'warehouse')
                     .filter(pur_date__date__gte=d_from, pur_date__date__lte=d_to, **wh_filter)
                     .exclude(warehouse_id__in=excl)
                     .annotate(total_qty_=Sum('purchaseitem__qty'), total_value_=Sum('purchaseitem__total_amt')))
        for pu in purchases.order_by('-pur_date')[:300]:
            rows.append({
                'kind': 'Purchase', 'no': pu.bill_no or f'#{pu.pk}', 'date': pu.pur_date, 'vendor': pu.vendor.name,
                'store': pu.warehouse, 'qty': pu.total_qty_ or 0, 'value': pu.total_value_ or Decimal('0.00'),
                'posted': True, 'status': 'Stock has arrived in the store', 'url_name': 'purchase_detail', 'pk': pu.pk,
            })
    rows.sort(key=lambda r: r['date'], reverse=True)

    pending_grns = GoodsReceivedNote.objects.filter(converted_to_purchase=False).exclude(warehouse_id__in=excl)
    if view_ids is not None:
        pending_grns = pending_grns.filter(warehouse_id__in=view_ids)

    keeper_ids = _sa.allowed_ids(request.user, 'keeper')
    incoming = (StoreTransfer.objects.select_related('from_warehouse', 'to_warehouse')
                .filter(status='in_transit').order_by('-transfer_date'))
    if keeper_ids is not None:
        incoming = incoming.filter(to_warehouse_id__in=keeper_ids)

    page_obj = Paginator(rows, 30).get_page(request.GET.get('page', 1))
    keep = request.GET.copy()
    keep.pop('page', None)
    return render(request, 'store_issue/receipts.html', {
        'company_name': _st_company(), 'page_obj': page_obj, 'qs': keep.urlencode(),
        'f': {'from': d_from.isoformat(), 'to': d_to.isoformat(), 'kind': kind, 'store': store,
              'pending': '1' if only_pending else ''},
        'stores': _st_stores_qs(view_ids),
        'total_value': sum((r['value'] for r in rows), Decimal('0.00')),
        'total_rows': len(rows),
        'pending_grn_count': pending_grns.count(),
        'incoming': incoming[:10], 'incoming_count': incoming.count(),
    })
