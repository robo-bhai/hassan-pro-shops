"""
Cashier shift + day close.

URLs (add to urls.py):
    path('sales/shift/status/', shift_views.shift_status, name='shift_status'),
    path('sales/shift/open/', shift_views.shift_open, name='shift_open'),
    path('sales/shift/movement/', shift_views.shift_movement, name='shift_movement'),
    path('sales/shift/close/', shift_views.shift_close, name='shift_close'),
    path('sales/shift/<int:pk>/close/', shift_views.shift_close, name='shift_close_pk'),
    path('sales/shift/<int:pk>/report/', shift_views.shift_report, name='shift_report'),
    path('sales/shifts/', shift_views.shift_list, name='shift_list'),

Cash formula:  expected = opening + cash payments + cash in - cash out
Cash payments = the cashier's cash SalePayments made in that store during the shift.
Bills and payments are never changed; this only adds them up.
"""
import csv
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from .shop_tools import audit
from ..models import CashierShift, CompanyInfo, Sale, SaleItem, SalePayment, ShiftCashMovement, Warehouse

ZERO = Decimal('0.00')


def _d(v):
    try:
        d = Decimal(str(v if v not in (None, '') else '0'))
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a valid number.')
    if not d.is_finite():
        raise ValueError('Enter a valid number.')
    return d.quantize(Decimal('0.01'))


def _payload(request):
    if request.content_type and 'json' in request.content_type:
        try:
            return json.loads(request.body or '{}')
        except ValueError:
            return {}
    return request.POST


def open_shift_for(user):
    return CashierShift.objects.filter(user=user, status='open').select_related('warehouse').first()


def _q(v):
    return (v or ZERO).quantize(Decimal('0.01'))


def compute_totals(shift, until=None):
    """Totals for a shift (live while open; frozen when the shift is closed)."""
    until = until or shift.closed_at or now()
    pays = SalePayment.objects.filter(created_by=shift.user, sale__warehouse=shift.warehouse,
                                      payment_date__gte=shift.opened_at, payment_date__lte=until)
    pays = pays.exclude(sale__returns__notes__startswith='VOID')      # voided bills do not count
    by = {r['method__name']: r['t'] or ZERO for r in pays.values('method__name').annotate(t=Sum('amount'))}
    sales = Sale.objects.filter(created_by=shift.user, warehouse=shift.warehouse,
                                sale_date__gte=shift.opened_at, sale_date__lte=until)
    sales = sales.exclude(returns__notes__startswith='VOID')          # voided bills do not count
    items_total = SaleItem.objects.filter(sale__in=sales).aggregate(t=Sum('total_amt'))['t'] or ZERO
    agg = sales.aggregate(n=Count('id'), disc=Sum('discount_value'), paid=Sum('paid'))
    discount = agg['disc'] or ZERO
    total_sales = items_total - discount
    mv = shift.movements.values('kind').annotate(t=Sum('amount'))
    mvd = {r['kind']: r['t'] or ZERO for r in mv}
    t = {
        'sales_count': agg['n'] or 0,
        'total_sales': _q(total_sales), 'discount_total': _q(discount),
        'credit_given': _q(max(total_sales - (agg['paid'] or ZERO), ZERO)),
        'cash_sales': _q(by.get('cash')), 'card_sales': _q(by.get('card')),
        'wallet_sales': _q((by.get('jazzcash') or ZERO) + (by.get('easypaisa') or ZERO)),
        'bank_sales': _q(by.get('bank_transfer')),
        'cash_in': _q(mvd.get('in')), 'cash_out': _q(mvd.get('out')),
    }
    t['expected_cash'] = _q(shift.opening_cash + t['cash_sales'] + t['cash_in'] - t['cash_out'])
    return t


def _view_of(shift):
    """For templates: live numbers for an open shift, frozen numbers for a closed one."""
    if shift.status == 'open':
        v = {**compute_totals(shift), 'counted_cash': None, 'difference': None}
    else:
        v = {k: getattr(shift, k) for k in ('sales_count', 'total_sales', 'discount_total', 'credit_given',
                                            'cash_sales', 'card_sales', 'wallet_sales', 'bank_sales', 'cash_in',
                                            'cash_out', 'expected_cash', 'counted_cash', 'difference')}
    # Card / wallet are no longer used; show them together as "Other" only for older shifts.
    v['other_sales'] = _q(v['card_sales'] + v['wallet_sales'])
    return v


def _can_manage(user, shift):
    return user.is_superuser or shift.user_id == user.pk


# ----------------------------------------------------------------------------- JSON for POS
@login_required
def shift_status(request):
    s = open_shift_for(request.user)
    if not s:
        return JsonResponse({'open': False})
    t = compute_totals(s)
    return JsonResponse({'open': True, 'id': s.pk, 'warehouse': s.warehouse_id, 'warehouse_name': s.warehouse.name,
                         'opened_at': s.opened_at.strftime('%d-%m %I:%M %p'), 'opening_cash': float(s.opening_cash),
                         'sales_count': t['sales_count'], 'cash_in_drawer': float(t['expected_cash'])})


@login_required
@require_POST
def shift_open(request):
    p = _payload(request)
    try:
        if open_shift_for(request.user):
            raise ValueError('You already have an open shift.')
        wh = Warehouse.objects.filter(pk=p.get('warehouse')).first()
        if not wh:
            raise ValueError('Select a store.')
        opening = _d(p.get('opening_cash'))
        if opening < 0:
            raise ValueError('Opening cash cannot be negative.')
        with transaction.atomic():
            s = CashierShift.objects.create(user=request.user, warehouse=wh, opening_cash=opening)
        audit(request, 'CashierShift', s.pk, 'created', {'store': wh.name, 'opening_cash': str(opening)})
    except ValueError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': True, 'id': s.pk})


@login_required
@require_POST
def shift_movement(request):
    p = _payload(request)
    try:
        s = open_shift_for(request.user)
        if not s:
            raise ValueError('Open a shift first.')
        kind = p.get('kind')
        if kind not in ('in', 'out'):
            raise ValueError('Choose cash in or cash out.')
        amount = _d(p.get('amount'))
        reason = (p.get('reason') or '').strip()[:200]
        if amount <= 0:
            raise ValueError('Amount must be greater than zero.')
        if not reason:
            raise ValueError('A reason is required.')
        if kind == 'out' and amount > compute_totals(s)['expected_cash']:
            raise ValueError('There is not enough cash in the drawer.')
        ShiftCashMovement.objects.create(shift=s, kind=kind, amount=amount, reason=reason, created_by=request.user)
        audit(request, 'CashierShift', s.pk, 'updated', {'cash_' + kind: str(amount), 'reason': reason})
    except ValueError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': True, 'cash_in_drawer': float(compute_totals(s)['expected_cash'])})


# ----------------------------------------------------------------------------- close
@login_required
def shift_close(request, pk=None):
    if pk is None:
        shift = open_shift_for(request.user)
        if not shift:
            messages.info(request, 'You have no open shift.')
            return redirect('shift_list')
    else:
        shift = get_object_or_404(CashierShift.objects.select_related('warehouse', 'user'), pk=pk)
    if not _can_manage(request.user, shift):
        raise Http404('Shift not found')
    if shift.status == 'closed':
        return redirect('shift_report', pk=shift.pk)

    if request.method == 'POST':
        try:
            counted = _d(request.POST.get('counted_cash'))
            if counted < 0:
                raise ValueError('Counted cash cannot be negative.')
            notes = (request.POST.get('notes') or '').strip()[:255]
            with transaction.atomic():
                shift = CashierShift.objects.select_for_update().get(pk=shift.pk)
                if shift.status != 'open':
                    raise ValueError('This shift is already closed.')
                closed = now()
                t = compute_totals(shift, until=closed)
                for k, v in t.items():
                    setattr(shift, k, v)
                shift.counted_cash = counted
                shift.difference = (counted - t['expected_cash']).quantize(Decimal('0.01'))
                shift.notes = notes
                shift.closed_at, shift.closed_by, shift.status = closed, request.user, 'closed'
                shift.save()
            audit(request, 'CashierShift', shift.pk, 'completed', {'expected': str(shift.expected_cash), 'counted': str(counted), 'difference': str(shift.difference)})
            messages.success(request, f'Shift #{shift.pk} is closed.')
            return redirect('shift_report', pk=shift.pk)
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, 'sales/shift_close.html', {
        'shift': shift, 't': _view_of(shift), 'movements': shift.movements.all(),
        'company_name': (CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System'),
    })


@login_required
def shift_report(request, pk):
    shift = get_object_or_404(CashierShift.objects.select_related('warehouse', 'user', 'closed_by'), pk=pk)
    if not _can_manage(request.user, shift):
        raise Http404('Shift not found')
    info = CompanyInfo.objects.first()
    return render(request, 'sales/shift_report.html', {
        'shift': shift, 't': _view_of(shift), 'movements': shift.movements.select_related('created_by'),
        'company': info, 'company_name': info.name if info else 'ERP System',
        'print': request.GET.get('print') == '1',
    })


# ----------------------------------------------------------------------------- list / day close
def _pdate(v, default):
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


@login_required
def shift_list(request):
    today = now().date()
    d_from = _pdate(request.GET.get('from'), today - timedelta(days=29))
    d_to = _pdate(request.GET.get('to'), today)
    qs = CashierShift.objects.select_related('user', 'warehouse').filter(opened_at__date__gte=d_from,
                                                                          opened_at__date__lte=d_to)
    if not request.user.is_superuser:
        qs = qs.filter(user=request.user)
    cashier = request.GET.get('cashier', '')
    if request.user.is_superuser and cashier.isdigit():
        qs = qs.filter(user_id=int(cashier))
    store = request.GET.get('store', '')
    if store.isdigit():
        qs = qs.filter(warehouse_id=int(store))
    shifts = list(qs[:500])

    rows, days = [], {}
    for s in shifts:
        t = _view_of(s)
        rows.append({'s': s, 't': t})
        key = timezone_date(s.opened_at)
        d = days.setdefault(key, {'date': key, 'shifts': 0, 'sales': 0, 'total': ZERO, 'cash': ZERO, 'other': ZERO,
                                  'expected': ZERO, 'counted': ZERO, 'diff': ZERO, 'open': 0})
        d['shifts'] += 1
        d['sales'] += t['sales_count']
        d['total'] += t['total_sales']
        d['cash'] += t['cash_sales']
        d['other'] += t['other_sales'] + t['bank_sales']
        d['expected'] += t['expected_cash']
        if s.status == 'closed':
            d['counted'] += t['counted_cash'] or ZERO
            d['diff'] += t['difference'] or ZERO
        else:
            d['open'] += 1

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="shifts_{d_from}_{d_to}.csv"'
        resp.write('\ufeff')
        w = csv.writer(resp)
        w.writerow(['Shift', 'Cashier', 'Store', 'Opened', 'Closed', 'Status', 'Sales', 'Total sales', 'Cash sales',
                    'Card', 'Wallet', 'Bank', 'Credit', 'Opening', 'Cash in', 'Cash out', 'Expected', 'Counted',
                    'Difference'])
        for r in rows:
            s, t = r['s'], r['t']
            w.writerow([s.pk, s.user.get_username(), s.warehouse.name, s.opened_at.strftime('%Y-%m-%d %I:%M %p'),
                        s.closed_at.strftime('%Y-%m-%d %I:%M %p') if s.closed_at else '', s.status, t['sales_count'],
                        t['total_sales'], t['cash_sales'], t['card_sales'], t['wallet_sales'], t['bank_sales'],
                        t['credit_given'], s.opening_cash, t['cash_in'], t['cash_out'], t['expected_cash'],
                        t['counted_cash'] if t['counted_cash'] is not None else '',
                        t['difference'] if t['difference'] is not None else ''])
        return resp

    return render(request, 'sales/shift_list.html', {
        'company_name': (CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System'),
        'rows': rows, 'days': sorted(days.values(), key=lambda d: d['date'], reverse=True),
        'from': d_from.isoformat(), 'to': d_to.isoformat(), 'cashier': cashier, 'store': store,
        'cashiers': User.objects.filter(cashier_shifts__isnull=False).distinct().order_by('username')
        if request.user.is_superuser else [],
        'stores': Warehouse.objects.order_by('name'), 'my_open': open_shift_for(request.user),
    })


def timezone_date(dt):
    from django.utils.timezone import localtime
    return localtime(dt).date()
