"""Agri Edition: Expiry Manager + Kisan Udhaar (harvest credit).

Design notes
- Nothing here changes accounting. Expiry / batch / due-date fields are plain data on
  StockBatch, PurchaseItem, Customer and Sale. Writes use queryset.update() so Sale.save()
  / StockBatch.save() (journal posting, price validation) are never triggered.
- Outstanding per bill = items total - discount - paid (same rule as Sale.outstanding_balance),
  computed with sub-queries so multi-item bills are not double counted.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import (Count, DecimalField, ExpressionWrapper, F, OuterRef, Q,
                              Subquery, Sum, Value)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from ..models import (CompanyInfo, Customer, PurchaseItem, Sale, SaleItem, SaleRetrnItem,
                      StockBatch)
from ..security.permissions import perm_required
from . import calc, rules
from .writeoff import REASONS as WO_REASONS, WriteOffError, write_off_batch

MONEY = DecimalField(max_digits=18, decimal_places=2)
ZERO = Decimal('0.00')
STOCK_VALUE = ExpressionWrapper(F('remaining_qty') * F('price'), output_field=MONEY)


# ----------------------------------------------------------------- helpers
def _today():
    return timezone.localdate()


_parse_date = calc.parse_date
_dec = calc.to_dec


def _safe_reverse(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ''


def _next_url(request, fallback):
    nxt = request.POST.get('next') or ''
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


def _company_name():
    info = CompanyInfo.objects.first()
    return (info.name if info and getattr(info, 'name', None) else 'Hamari dukaan')


_wa_number = calc.wa_number
_expiry_status = calc.expiry_status


# ----------------------------------------------------------------- expiry
def _expiry_buckets():
    today = _today()
    base = StockBatch.objects.filter(remaining_qty__gt=0)

    def part(qs):
        r = qs.aggregate(n=Count('id'), v=Sum(STOCK_VALUE))
        return {'count': r['n'] or 0, 'value': r['v'] or ZERO}

    return {
        'expired': part(base.filter(expiry_date__lt=today)),
        'd30': part(base.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30))),
        'd60': part(base.filter(expiry_date__gt=today + timedelta(days=30),
                                expiry_date__lte=today + timedelta(days=60))),
        'd90': part(base.filter(expiry_date__gt=today + timedelta(days=60),
                                expiry_date__lte=today + timedelta(days=90))),
        'missing': part(base.filter(expiry_date__isnull=True)),
    }


@perm_required('view_inventory', 'view_products',
               post=('manage_stock', 'manage_inventory', 'manage_products'))
def expiry_manager(request):
    today = _today()
    flt = request.GET.get('f', 'expired')
    q = (request.GET.get('q') or '').strip()

    qs = StockBatch.objects.filter(remaining_qty__gt=0).select_related('product', 'warehouse')
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(batch_no__icontains=q))
    if flt == 'expired':
        qs = qs.filter(expiry_date__lt=today)
    elif flt == '30':
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30))
    elif flt == '60':
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=60))
    elif flt == '90':
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=90))
    elif flt == 'missing':
        qs = qs.filter(expiry_date__isnull=True)
    else:
        flt = 'all'
    qs = qs.order_by(F('expiry_date').asc(nulls_last=True), 'product__name', 'id')

    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    rows = []
    for b in page:
        status, days = _expiry_status(b.expiry_date, today)
        rows.append({
            'b': b, 'status': status, 'days': days,
            'days_abs': abs(days) if days is not None else None,
            'value': Decimal(str(b.remaining_qty)) * b.price,
        })
    qstring = urlencode({'f': flt, 'q': q})
    return render(request, 'agri/expiry.html', {
        'rows': rows, 'page': page, 'flt': flt, 'q': q, 'qstring': qstring,
        'buckets': _expiry_buckets(),
        'next': request.get_full_path(),
    })


@require_POST
@perm_required('view_inventory', 'view_products',
               post=('manage_stock', 'manage_inventory', 'manage_products'))
def expiry_save(request):
    ids = [i for i in request.POST.getlist('ids') if i.isdigit()]
    saved = bad = 0
    for batch in StockBatch.objects.filter(pk__in=ids):
        raw_exp = request.POST.get('expiry_%s' % batch.pk, '')
        ok, exp = _parse_date(raw_exp)
        if not ok:
            bad += 1
            continue
        bn = (request.POST.get('batch_%s' % batch.pk, '') or '').strip()[:50] or None
        if exp == batch.expiry_date and bn == batch.batch_no:
            continue
        StockBatch.objects.filter(pk=batch.pk).update(expiry_date=exp, batch_no=bn)
        if batch.purchase_item_id:
            PurchaseItem.objects.filter(pk=batch.purchase_item_id).update(
                expiry_date=exp, batch_no=bn)
        saved += 1
    if saved:
        messages.success(request, '%d batch ki expiry/batch no save ho gaya.' % saved)
    elif not bad:
        messages.info(request, 'Koi tabdeeli nahi mili.')
    if bad:
        messages.error(request, '%d row ki tareekh ghalat thi, wo save nahi hui.' % bad)
    return redirect(_next_url(request, reverse('agri_expiry')))


# ----------------------------------------------------------------- farmer credit
_unpaid_sales = rules.unpaid_sales
_returns_by_customer = rules.returns_by_customer


def _wa_link(customer, balance, due, company):
    num = _wa_number(customer.contact_number)
    if not num:
        return ''
    msg = ('Assalam o Alaikum %s sahab, %s ki taraf se yaad-dehani: aap ka Rs. %s baqaya hai.'
           % (customer.name, company, format(int(balance), ',')))
    if due:
        msg += ' Wapsi ki tareekh: %s.' % due.strftime('%d-%m-%Y')
    msg += ' Meharbani karke ada kar dein. Shukriya.'
    return 'https://wa.me/%s?text=%s' % (num, quote(msg))


def _farmers(q='', flt='all'):
    today = _today()
    company = _company_name()
    returns = _returns_by_customer()
    sales = _unpaid_sales()
    if q:
        sales = sales.filter(Q(customer__name__icontains=q) | Q(customer__contact_number__icontains=q)
                             | Q(customer__village__icontains=q))
    grouped = {}
    for s in sales.order_by('sale_date'):
        g = grouped.setdefault(s.customer_id, {'customer': s.customer, 'bills': 0, 'sales_balance': ZERO,
                                               'overdue': ZERO, 'dues': []})
        g['bills'] += 1
        g['sales_balance'] += s.balance
        if s.harvest_due_date:
            g['dues'].append(s.harvest_due_date)
            if s.harvest_due_date < today:
                g['overdue'] += s.balance
    rows = []
    for cid, g in grouped.items():
        c = g['customer']
        balance = g['sales_balance'] - returns.get(cid, ZERO)
        if balance <= 0:
            continue
        nxt = min(g['dues']) if g['dues'] else None
        days = (nxt - today).days if nxt else None
        limit = c.credit_limit or ZERO
        digits = re.sub(r'\D', '', c.contact_number or '')
        rows.append({
            'customer': c, 'balance': balance, 'bills': g['bills'], 'next_due': nxt, 'days': days,
            'days_abs': abs(days) if days is not None else None,
            'overdue': g['overdue'], 'is_overdue': days is not None and days < 0,
            'due_week': days is not None and 0 <= days <= 7, 'nodate': nxt is None,
            'limit': limit, 'over_limit': limit > 0 and balance > limit,
            'wa': _wa_link(c, balance, nxt, company), 'tel': ('tel:' + digits) if digits else '',
        })
    if flt == 'overdue':
        rows = [r for r in rows if r['is_overdue']]
    elif flt == 'week':
        rows = [r for r in rows if r['due_week']]
    elif flt == 'nodate':
        rows = [r for r in rows if r['nodate']]
    elif flt == 'overlimit':
        rows = [r for r in rows if r['over_limit']]
    rows.sort(key=lambda r: (0 if r['is_overdue'] else (1 if r['next_due'] else 2),
                             r['next_due'] or date.max, -r['balance']))
    return rows


def _summary(rows):
    return {
        'farmers': len(rows),
        'total': sum((r['balance'] for r in rows), ZERO),
        'overdue_total': sum((r['overdue'] for r in rows), ZERO),
        'overdue_farmers': sum(1 for r in rows if r['is_overdue']),
        'week_farmers': sum(1 for r in rows if r['due_week']),
        'nodate_farmers': sum(1 for r in rows if r['nodate']),
        'over_limit': sum(1 for r in rows if r['over_limit']),
    }


@perm_required('view_dashboard', 'view_inventory', 'view_sales')
def dashboard(request):
    today = _today()
    rows = _farmers()
    soon = (StockBatch.objects.filter(remaining_qty__gt=0, expiry_date__isnull=False,
                                      expiry_date__lte=today + timedelta(days=60))
            .select_related('product', 'warehouse').order_by('expiry_date')[:8])
    soon_rows = []
    for b in soon:
        status, days = _expiry_status(b.expiry_date, today)
        soon_rows.append({'b': b, 'status': status, 'days': days,
                          'days_abs': abs(days) if days is not None else None})
    return render(request, 'agri/dashboard.html', {
        'buckets': _expiry_buckets(), 'soon_rows': soon_rows,
        'summary': _summary(rows), 'late_rows': [r for r in rows if r['is_overdue']][:8],
    })


@perm_required('view_sales', 'view_customers')
def credit_list(request):
    q = (request.GET.get('q') or '').strip()
    flt = request.GET.get('f', 'all')
    if flt not in ('all', 'overdue', 'week', 'nodate', 'overlimit'):
        flt = 'all'
    rows = _farmers(q, flt)
    return render(request, 'agri/credit.html', {
        'rows': rows, 'summary': _summary(_farmers(q, 'all')) if flt != 'all' else _summary(rows),
        'flt': flt, 'q': q,
    })


@perm_required('view_sales', 'view_customers', post=('edit_sales', 'edit_customers'))
def farmer_detail(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    today = _today()
    sales = list(_unpaid_sales().filter(customer=customer).order_by('harvest_due_date', 'sale_date'))
    returned = _returns_by_customer().get(customer.pk, ZERO)
    total = sum((s.balance for s in sales), ZERO) - returned
    for s in sales:
        s.days = (s.harvest_due_date - today).days if s.harvest_due_date else None
        s.days_abs = abs(s.days) if s.days is not None else None
    limit = customer.credit_limit or ZERO
    return render(request, 'agri/farmer.html', {
        'customer': customer, 'sales': sales, 'total': max(total, ZERO), 'returned': returned,
        'limit': limit, 'over_limit': limit > 0 and total > limit,
        'pay_url': _safe_reverse('customer_ledger_pay', customer.pk),
        'ledger_url': _safe_reverse('customer_ledger', customer.pk),
        'next': request.get_full_path(),
    })


@require_POST
@perm_required('view_sales', post=('edit_sales',))
def sale_set_due(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    ok, due = _parse_date(request.POST.get('harvest_due_date'))
    back = _next_url(request, reverse('agri_farmer', args=[sale.customer_id]))
    if not ok:
        messages.error(request, 'Tareekh ghalat hai.')
        return redirect(back)
    note = (request.POST.get('harvest_note') or '').strip()[:200]
    Sale.objects.filter(pk=sale.pk).update(harvest_due_date=due, harvest_note=note)
    messages.success(request, 'Wapsi ki tareekh save ho gayi.' if due else 'Tareekh hata di gayi.')
    return redirect(back)


@require_POST
@perm_required('view_sales', post=('edit_sales',))
def farmer_set_due(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    back = _next_url(request, reverse('agri_farmer', args=[customer.pk]))
    ok, due = _parse_date(request.POST.get('harvest_due_date'))
    if not ok or due is None:
        messages.error(request, 'Pehle sahi tareekh chunein.')
        return redirect(back)
    qs = _unpaid_sales().filter(customer=customer)
    if request.POST.get('only_missing'):
        qs = qs.filter(harvest_due_date__isnull=True)
    ids = list(qs.values_list('pk', flat=True))
    Sale.objects.filter(pk__in=ids).update(harvest_due_date=due)
    messages.success(request, '%d bill par wapsi ki tareekh lag gayi.' % len(ids))
    return redirect(back)


@require_POST
@perm_required('view_customers', post=('edit_customers',))
def farmer_profile_save(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    limit = _dec(request.POST.get('credit_limit'))
    if limit < 0:
        limit = ZERO
    Customer.objects.filter(pk=customer.pk).update(
        village=(request.POST.get('village') or '').strip()[:100] or None,
        main_crop=(request.POST.get('main_crop') or '').strip()[:100] or None,
        credit_limit=limit,
    )
    messages.success(request, 'Kisan ki maloomat save ho gayin.')
    return redirect(_next_url(request, reverse('agri_farmer', args=[customer.pk])))


# ----------------------------------------------------------------- write-off (expired / damaged)
@require_POST
@perm_required('view_inventory', 'view_products',
               post=('manage_stock', 'manage_inventory', 'manage_products'))
def expiry_writeoff(request):
    ids = [i for i in request.POST.getlist('wo') if i.isdigit()]
    reason = request.POST.get('reason') or 'expired'
    note = (request.POST.get('note') or '').strip()[:200]
    back = _next_url(request, reverse('agri_expiry'))
    if not ids:
        messages.error(request, 'Pehle woh batch tick karen jo nikalne hain.')
        return redirect(back)
    if reason not in WO_REASONS:
        messages.error(request, 'Wajah sahi nahi hai.')
        return redirect(back)
    done = 0
    value = ZERO
    try:
        for bid in ids:
            row = write_off_batch(int(bid), request.user, reason, note)
            done += 1
            value += row.value
    except Exception as exc:          # one failed batch stops the rest; earlier ones stay done (each is atomic)
        messages.error(request, '%d batch nikal diye gaye, phir ruk gaya: %s' % (done, exc) if done
                       else 'Write-off nahi hua: %s' % exc)
        return redirect(back)
    messages.success(request, '%d batch stock se nikal diye (nuqsan Rs. %s).' % (done, format(int(value), ',')))
    return redirect(back)


@perm_required('view_inventory', 'view_products')
def writeoff_list(request):
    from ..models import ExpiryWriteOff
    qs = ExpiryWriteOff.objects.select_related('product', 'warehouse', 'created_by')
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(batch_no__icontains=q))
    total = qs.aggregate(t=Sum('value'))['t'] or ZERO
    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    return render(request, 'agri/writeoffs.html', {'page': page, 'q': q, 'total': total})


# ----------------------------------------------------------------- GRN: batch / expiry before convert
@require_POST
@perm_required('view_purchases', 'receive_goods', post=('receive_goods', 'manage_purchase_orders'))
def grn_expiry_save(request, grn_id):
    from ..models import GoodsReceivedItem, GoodsReceivedNote
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id)
    back = _next_url(request, '/grn/%d/' % grn.pk)
    if grn.converted_to_purchase:
        messages.error(request, 'Yeh GRN purchase mein convert ho chuka hai, ab expiry yahan se nahi badal sakti.')
        return redirect(back)
    saved = bad = 0
    ids = [i for i in request.POST.getlist('ids') if i.isdigit()]
    for item in GoodsReceivedItem.objects.filter(grn=grn, pk__in=ids):
        ok, exp = _parse_date(request.POST.get('expiry_%s' % item.pk, ''))
        if not ok:
            bad += 1
            continue
        bn = (request.POST.get('batch_%s' % item.pk, '') or '').strip()[:50] or None
        if exp == item.expiry_date and bn == item.batch_no:
            continue
        GoodsReceivedItem.objects.filter(pk=item.pk).update(batch_no=bn, expiry_date=exp)
        saved += 1
    if saved:
        messages.success(request, '%d item ki expiry/batch save ho gayi.' % saved)
    elif not bad:
        messages.info(request, 'Koi tabdeeli nahi mili.')
    if bad:
        messages.error(request, '%d item ki tareekh ghalat thi, wo save nahi hui.' % bad)
    return redirect(back)
