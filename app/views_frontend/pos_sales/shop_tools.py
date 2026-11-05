"""
Shop tools: audit helper, bill reprint and Stock Register.

URLs (add to urls.py; the patch script does this for you):
    path('sales/pos/void/', shop_tools.pos_void, name='pos_void'),
    path('sales/pos/recent/', shop_tools.recent_bills, name='pos_recent'),
    path('sales/pos/bill/<int:pk>/', shop_tools.bill_detail, name='pos_bill'),
    path('inventory/stock-register/', shop_tools.stock_register, name='stock_register'),

The reprint and the stock register only read data. Bill void (pos_void) is the one action that
changes data: it restores stock, refunds the cash and records a full sale return marked "VOID".
"""
from ...security.permissions import perm_required
import csv
import json
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.timezone import get_current_timezone, make_aware, now

from ...models import (CashBalance, CashierShift, CompanyInfo, Inventory, Product, Purchase, PurchaseItem,
                      PurchaseRetrnItem, Sale, SaleItem, SalePayment, SaleRetrn, SaleRetrnItem, ShiftCashMovement,
                      StockAdjustmentItem, StockBatch, SystemSetting, Warehouse, WarehouseTransfer)

VOID_TAG = 'VOID'                      # SaleRetrn.notes starts with this for a voided bill

try:                                    # the audit table already exists in the project
    from ...models import AuditTrail
except Exception:                       # pragma: no cover
    AuditTrail = None


# ----------------------------------------------------------------------------- helpers
def is_manager(user):
    """Managers (superuser / staff) may sell below cost and give big discounts."""
    return bool(user.is_superuser or user.is_staff)


def setting_number(key, default):
    try:
        return float(SystemSetting.get_value(key, str(default)))
    except (TypeError, ValueError):
        return float(default)


def audit(request, model_name, record_id, action, changes=None):
    """Write one line to the audit trail. Never breaks the sale if it fails."""
    if AuditTrail is None:
        return
    try:
        AuditTrail.objects.create(
            user=request.user if request.user.is_authenticated else None,
            model_name=model_name, record_id=int(record_id or 0), action=action,
            changes=changes or {}, ip_address=request.META.get('REMOTE_ADDR') or None,
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300])
    except Exception:
        pass


def _f(v):
    return float(v or 0)


def bill_payload(sale, walkin_id=None):
    """Same shape as the checkout response, so the POS can print it again."""
    items = [{'name': i.product.name, 'qty': i.qty, 'price': _f(i.price), 'total': _f(i.total_amt)}
             for i in SaleItem.objects.filter(sale=sale).select_related('product')]
    subtotal = sum(i['total'] for i in items)
    discount = _f(sale.discount_value)
    total = round(subtotal - discount, 2)
    paid = _f(sale.paid)
    return {
        'success': True, 'sale_id': sale.pk, 'bill_no': sale.bill_no,
        'date': sale.sale_date.astimezone(get_current_timezone()).strftime('%d-%m-%Y %I:%M %p'),
        'cashier': sale.created_by.get_username() if sale.created_by_id else '',
        'customer': sale.customer.name, 'is_walkin': sale.customer.customer_code == 'WALKIN', 'items': items,
        'subtotal': round(subtotal, 2), 'discount': discount, 'total': total, 'paid': paid,
        'balance': round(max(total - paid, 0), 2), 'change': 0, 'reprint': True,
        'voided': is_voided(sale),
    }


def _own_sales(request):
    qs = Sale.objects.select_related('customer', 'created_by', 'warehouse')
    return qs if is_manager(request.user) else qs.filter(created_by=request.user)


def is_voided(sale):
    return sale.returns.filter(notes__startswith=VOID_TAG).exists()


def void_block_reason(user, sale, shift):
    """Why this user cannot void this bill (empty string = allowed)."""
    if sale.returns.exists():
        return 'This bill already has a return or is already voided.'
    if sale.is_installment:
        return 'Installment bills cannot be voided here.'
    if is_manager(user):
        return ''
    if not SystemSetting.get_bool('pos_cashier_can_void', False):
        return 'Only a manager can void a bill.'
    if not (shift and sale.created_by_id == user.pk and shift.warehouse_id == sale.warehouse_id
            and sale.sale_date >= shift.opened_at):
        return 'You can void only your own bills from the current shift.'
    return ''


# ----------------------------------------------------------------------------- reprint
@login_required
@perm_required('use_pos', 'view_sales')
def recent_bills(request):
    """Last bills of this cashier (all cashiers for a superuser) for the POS 'Recent bills' window."""
    qs = _own_sales(request)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(bill_no__icontains=q) | Q(customer__name__icontains=q))
    sales = list(qs.annotate(sub=Sum('saleitem__total_amt')).order_by('-id')[:25])
    from .shift import open_shift_for
    shift = open_shift_for(request.user)
    voided = set(SaleRetrn.objects.filter(sale__in=sales, notes__startswith=VOID_TAG).values_list('sale_id', flat=True))
    rows = [{'id': s.pk, 'bill_no': s.bill_no, 'customer': s.customer.name,
             'time': s.sale_date.astimezone(get_current_timezone()).strftime('%d-%m %I:%M %p'),
             'total': round(_f(s.sub) - _f(s.discount_value), 2), 'paid': _f(s.paid),
             'voided': s.pk in voided,
             'can_void': s.pk not in voided and not void_block_reason(request.user, s, shift)} for s in sales]
    return JsonResponse({'results': rows})


@login_required
@perm_required('use_pos', 'view_sales')
def bill_detail(request, pk):
    sale = _own_sales(request).filter(pk=pk).first()
    if not sale:
        raise Http404('Bill not found')
    audit(request, 'Sale', sale.pk, 'viewed', {'bill_no': sale.bill_no, 'reason': 'receipt reprint'})
    return JsonResponse(bill_payload(sale))


# ----------------------------------------------------------------------------- stock register
def _day(value, default):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


def _range(d_from, d_to):
    tz = get_current_timezone()
    return make_aware(datetime.combine(d_from, time.min), tz), make_aware(datetime.combine(d_to, time.max), tz)


def collect_movements(d_from, d_to, product_q='', warehouse_id=None):
    """Every stock in/out in the period, from the existing tables. Returns a list of dicts."""
    start, end = _range(d_from, d_to)
    rows = []

    def pf(prefix):
        if not product_q:
            return Q()
        return (Q(**{prefix + 'name__icontains': product_q}) | Q(**{prefix + 'barcode__icontains': product_q}) |
                Q(**{prefix + 'serial_no__icontains': product_q}))

    def add(when, product, wh, kind, ref, qty_in, qty_out, party='', note=''):
        if warehouse_id and (not wh or wh.pk != warehouse_id):
            return
        rows.append({'date': when, 'product': product.name, 'warehouse': wh.name if wh else '-', 'type': kind,
                     'ref': ref or '', 'qty_in': qty_in, 'qty_out': qty_out, 'party': party, 'note': note})

    for i in (PurchaseItem.objects.filter(pf('product__'), purchase__pur_date__range=(start, end))
              .select_related('product', 'purchase', 'purchase__warehouse', 'purchase__vendor')[:3000]):
        add(i.purchase.pur_date, i.product, i.purchase.warehouse, 'Purchase', i.purchase.bill_no, float(i.qty), 0,
            getattr(i.purchase.vendor, 'name', ''))
    for i in (SaleItem.objects.filter(pf('product__'), sale__sale_date__range=(start, end))
              .select_related('product', 'sale', 'sale__warehouse', 'sale__customer')[:3000]):
        add(i.sale.sale_date, i.product, i.sale.warehouse, 'Sale', i.sale.bill_no, 0, float(i.qty),
            i.sale.customer.name)
    for i in (SaleRetrnItem.objects.filter(pf('product__'), sale_return__sale_return_date__range=(start, end))
              .select_related('product', 'sale_return', 'sale_return__warehouse', 'sale_return__sale',
                              'sale_return__sale__warehouse', 'sale_return__customer')[:3000]):
        r = i.sale_return
        wh = r.warehouse or (r.sale.warehouse if r.sale_id else None)
        add(r.sale_return_date, i.product, wh, 'Sale return', r.bill_no, float(i.qty), 0, r.customer.name)
    for i in (PurchaseRetrnItem.objects.filter(pf('product__'), purchase_return__purchase_return_date__range=(start, end))
              .select_related('product', 'purchase_return', 'purchase_return__purchase',
                              'purchase_return__purchase__warehouse', 'purchase_return__vendor')[:3000]):
        r = i.purchase_return
        wh = r.purchase.warehouse if r.purchase_id else None
        add(r.purchase_return_date, i.product, wh, 'Purchase return', r.bill_no, 0, float(i.qty),
            getattr(r.vendor, 'name', ''))
    for t in (WarehouseTransfer.objects.filter(pf('product__'), transfer_date__range=(start, end))
              .select_related('product', 'from_warehouse', 'to_warehouse')[:3000]):
        add(t.transfer_date, t.product, t.from_warehouse, 'Transfer out', '', 0, float(t.qty),
            note='to ' + t.to_warehouse.name)
        add(t.transfer_date, t.product, t.to_warehouse, 'Transfer in', '', float(t.qty), 0,
            note='from ' + t.from_warehouse.name)
    for i in (StockAdjustmentItem.objects.filter(pf('product__'), adjustment__adjustment_date__range=(start, end))
              .select_related('product', 'adjustment')[:3000]):
        inc = i.adjustment.adjustment_type == 'increase'
        # Adjustments do not store a warehouse, so they are hidden when a single store is selected.
        add(i.adjustment.adjustment_date, i.product, None, 'Adjustment ' + ('+' if inc else '-'), '',
            float(i.qty) if inc else 0, 0 if inc else float(i.qty), note=i.adjustment.reason)
    rows.sort(key=lambda r: r['date'], reverse=True)
    return rows


@login_required
@perm_required('view_inventory', 'view_products')
def stock_register(request):
    today = now().date()
    d_from = _day(request.GET.get('from'), today - timedelta(days=6))
    d_to = _day(request.GET.get('to'), today)
    q = (request.GET.get('q') or '').strip()
    wh = request.GET.get('store', '')
    wid = int(wh) if wh.isdigit() else None
    kind = request.GET.get('type', '')

    rows = collect_movements(d_from, d_to, q, wid)
    if kind:
        grouped = kind in ('Transfer', 'Adjustment')      # these have two variants (in/out, +/-)
        rows = [r for r in rows if (r['type'].startswith(kind) if grouped else r['type'] == kind)]
    tot_in, tot_out = sum(r['qty_in'] for r in rows), sum(r['qty_out'] for r in rows)

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="stock_register_{d_from}_{d_to}.csv"'
        resp.write('﻿')
        w = csv.writer(resp)
        w.writerow(['Date', 'Product', 'Store', 'Type', 'Reference', 'In', 'Out', 'Party', 'Note'])
        for r in rows:
            w.writerow([r['date'].astimezone(get_current_timezone()).strftime('%Y-%m-%d %I:%M %p'), r['product'],
                        r['warehouse'], r['type'], r['ref'], r['qty_in'], r['qty_out'], r['party'], r['note']])
        return resp

    info = CompanyInfo.objects.first()
    return render(request, 'sales/stock_register.html', {
        'company_name': info.name if info else 'ERP System',
        'rows': rows[:1000], 'truncated': len(rows) > 1000, 'count': len(rows),
        'tot_in': round(tot_in, 3), 'tot_out': round(tot_out, 3), 'net': round(tot_in - tot_out, 3),
        'from': d_from.isoformat(), 'to': d_to.isoformat(), 'q': q, 'store': wh, 'type': kind,
        'stores': Warehouse.objects.order_by('name'),
        'types': ['Purchase', 'Sale', 'Sale return', 'Purchase return', 'Transfer', 'Adjustment'],
    })


# ----------------------------------------------------------------------------- bill void
def _restore_item(item, warehouse):
    """Put the sold quantity back: first into the batches it came from (keeps the cost), then Inventory."""
    left = float(item.qty)
    for b in item.batches_used.order_by('id'):
        if left <= 1e-9:
            break
        room = float(b.qty) - float(b.remaining_qty)
        add = min(room, left)
        if add > 0:
            b.remaining_qty = float(b.remaining_qty) + add
            b.save()
            left -= add
    if left > 1e-9:                      # the old batch is gone: make a new one at the latest cost
        last = StockBatch.objects.filter(product=item.product, warehouse=warehouse).order_by('-id').first()
        _src = item.batches_used.order_by('id').first()          # [agri-edition:void]
        StockBatch.objects.create(product=item.product, warehouse=warehouse, qty=left, remaining_qty=left,
                                  price=last.price if last else item.price,
                                  batch_no=getattr(_src, 'batch_no', None),
                                  expiry_date=getattr(_src, 'expiry_date', None))
    Inventory.update_stock(item.product, float(item.qty), warehouse)


@login_required
@perm_required('delete_sales', 'use_pos')
@require_POST
def pos_void(request):
    """Void a whole bill: stock back, cash refunded, customer balance cleared, full audit line."""
    from .shift import compute_totals, open_shift_for
    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)
    try:
        reason = (data.get('reason') or '').strip()[:120]
        if len(reason) < 3:
            raise ValueError('Enter a reason for the void.')
        with transaction.atomic():
            sale = _own_sales(request).select_for_update(of=('self',)).filter(pk=data.get('sale_id')).first()
            if not sale:
                raise ValueError('Bill not found.')
            my_shift = open_shift_for(request.user)
            block = void_block_reason(request.user, sale, my_shift)
            if block:
                raise ValueError(block)
            items = list(SaleItem.objects.filter(sale=sale).select_related('product'))
            if not items:
                raise ValueError('This bill has no items.')

            pays = {r['method__name']: r['t'] or Decimal('0') for r in
                    SalePayment.objects.filter(sale=sale).values('method__name').annotate(t=Sum('amount'))}
            cash_paid = pays.get('cash', Decimal('0'))
            other_paid = sum((v for k, v in pays.items() if k != 'cash'), Decimal('0'))

            # If the cashier's shift that made this bill is still open, the shift report simply leaves the
            # bill out. Otherwise the refund is a cash-out in the shift of the person doing the void.
            orig_shift = None
            if sale.created_by_id:
                orig_shift = CashierShift.objects.filter(status='open', user_id=sale.created_by_id,
                                                         warehouse_id=sale.warehouse_id,
                                                         opened_at__lte=sale.sale_date).first()
            need_movement = cash_paid > 0 and orig_shift is None
            if need_movement:
                if not my_shift:
                    raise ValueError('Open your shift first. The cash refund is taken from your drawer.')
                if cash_paid > compute_totals(my_shift)['expected_cash']:
                    raise ValueError('There is not enough cash in your drawer for this refund.')

            ret = SaleRetrn.objects.create(
                sale=sale, customer=sale.customer, bill_no=f'V{sale.pk}'[:10], sale_return_date=now(),
                return_reason='other', warehouse=sale.warehouse, created_by=request.user,
                notes=f'{VOID_TAG} | {reason} | bill {sale.bill_no} | by {request.user.get_username()}')
            rows = []
            for it in items:
                rows.append(SaleRetrnItem(sale_return=ret, product=it.product,
                                          qty=Decimal(str(it.qty)).quantize(Decimal('0.01')),
                                          price=it.price, total_amt=it.total_amt))
                _restore_item(it, sale.warehouse)
            SaleRetrnItem.objects.bulk_create(rows)       # stock was already restored above, exactly once

            before = {'paid': str(sale.paid), 'discount': str(sale.discount_value)}
            Sale.objects.filter(pk=sale.pk).update(paid=Decimal('0.00'), discount_value=Decimal('0.00'))

            if cash_paid > 0:
                CashBalance.update_balance(amount=cash_paid, transaction_type='withdraw', user=request.user,
                                           description=f'Void refund {sale.bill_no} - {sale.customer.name}')
            if need_movement:
                ShiftCashMovement.objects.create(shift=my_shift, kind='out', amount=cash_paid,
                                                 reason=f'Void refund {sale.bill_no}'[:200], created_by=request.user)
        audit(request, 'Sale', sale.pk, 'deleted', {'void': True, 'bill_no': sale.bill_no, 'reason': reason,
                                                    'cash_refund': str(cash_paid), 'other_paid': str(other_paid),
                                                    'was': before, 'lines': len(items)})
    except (ValueError, ValidationError) as e:
        msg = ' '.join(e.messages) if isinstance(e, ValidationError) else str(e)
        return JsonResponse({'success': False, 'message': msg}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'The bill was not voided: {e}'}, status=500)
    return JsonResponse({'success': True, 'bill_no': sale.bill_no, 'cash_refund': float(cash_paid),
                         'other_refund': float(other_paid)})
