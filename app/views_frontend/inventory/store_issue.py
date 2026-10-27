"""Frontend views: stores dashboard + internal store issue (PMS / RMS / FGS / Technical)."""
from ...security.permissions import perm_required
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...models import (CompanyInfo, Department, Inventory, Product, ProductionOrder, StockBatch,
                      StoreIssue, StoreIssueItem, StoreMember, StoreProfile, Warehouse)
from ...store import store_access as _sa
from ...store import store_issue_service as _sis

# ---- access: superuser sees everything; others only by their own store team (StoreMember) (store_access.py)


def _si_company():
    info = CompanyInfo.objects.first()
    return info.name if info else 'ERP System'


def _si_deny(request, what='view this page'):
    messages.error(request, f'Access denied! You are not allowed to {what}.')
    return redirect('dashboard')


def _si_no_store(request):
    messages.error(request, 'You do not have access to any store yet. Ask a superuser to add you to a store team.')
    return redirect('dashboard')


def _si_stores_qs(ids):
    qs = Warehouse.objects.select_related('store_profile').order_by('name')
    qs = qs.exclude(pk__in=_sa.unavailable_warehouse_ids())      # Stores outside the Shop/Factory mode
    return qs if ids is None else qs.filter(pk__in=ids)


def _si_date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _si_stock_value_expr():
    return ExpressionWrapper(F('remaining_qty') * F('price'),
                             output_field=DecimalField(max_digits=18, decimal_places=2))


def _si_store_choices(user):
    """Warehouses from which this user can issue."""
    ids = _sa.allowed_ids(user, 'keeper')
    qs = Warehouse.objects.filter(Q(store_profile__isnull=True) | Q(store_profile__is_active=True,
                                                                      store_profile__can_issue=True))
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    qs = qs.exclude(pk__in=_sa.unavailable_warehouse_ids())
    stores = list(qs.select_related('store_profile').order_by('name'))
    stores.sort(key=lambda w: (not hasattr(w, 'store_profile'), w.name))
    return stores


# ============================================================================
# Stores dashboard
# ============================================================================
@login_required
@perm_required('view_warehouse')
def store_dashboard(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _si_no_store(request)
    issue_ids = _sa.allowed_ids(request.user, 'keeper')

    stock = {r['warehouse']: r for r in
             StockBatch.objects.filter(remaining_qty__gt=0).values('warehouse')
             .annotate(qty=Sum('remaining_qty'), value=Sum(_si_stock_value_expr()),
                       items=Count('product', distinct=True))}
    month_start = date.today().replace(day=1)
    issued = {r['from_warehouse']: r for r in
              StoreIssue.objects.filter(status='issued', issue_date__date__gte=month_start)
              .values('from_warehouse').annotate(n=Count('id'), cost=Sum('total_cost'))}
    low = {r['warehouse']: r['n'] for r in
           Inventory.objects.filter(stock__lt=F('product__low_stock_threshold'))
           .values('warehouse').annotate(n=Count('id'))}

    cards = []
    for wh in _si_stores_qs(view_ids):
        prof = getattr(wh, 'store_profile', None)
        s, i = stock.get(wh.id, {}), issued.get(wh.id, {})
        cards.append({
            'warehouse': wh, 'profile': prof,
            'code': prof.code if prof else '-',
            'type_label': prof.get_store_type_display() if prof else 'Warehouse',
            'items': s.get('items', 0), 'qty': s.get('qty') or 0,
            'value': s.get('value') or Decimal('0.00'),
            'issues_month': i.get('n', 0), 'issue_cost_month': i.get('cost') or Decimal('0.00'),
            'low_count': low.get(wh.id, 0),
            'can_issue': (issue_ids is None or wh.id in issue_ids) and (prof is None or prof.can_issue),
        })
    cards.sort(key=lambda c: (c['profile'] is None, c['code'], c['warehouse'].name))

    recent_qs = StoreIssue.objects.select_related('from_warehouse', 'department', 'created_by')
    if view_ids is not None:
        recent_qs = recent_qs.filter(from_warehouse_id__in=view_ids)
    recent = recent_qs.order_by('-issue_date', '-id')[:8]
    context = {
        'company_name': _si_company(),
        'cards': cards,
        'has_profiles': any(c['profile'] for c in cards),
        'total_value': sum((c['value'] for c in cards), Decimal('0.00')),
        'total_issue_cost_month': sum((c['issue_cost_month'] for c in cards), Decimal('0.00')),
        'recent': recent,
        'can_issue': any(c['can_issue'] for c in cards),
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'store_issue/dashboard.html', context)


# ============================================================================
# Issue list
# ============================================================================
def _si_filtered_issues(request, view_ids):
    qs = StoreIssue.objects.select_related('from_warehouse', 'department', 'created_by', 'production_order')
    if view_ids is not None:
        qs = qs.filter(from_warehouse_id__in=view_ids)
    q = (request.GET.get('q') or '').strip()
    store = request.GET.get('store', '')
    itype = request.GET.get('type', '')
    dept = request.GET.get('department', '')
    status = request.GET.get('status', '')
    d_from, d_to = _si_date(request.GET.get('from')), _si_date(request.GET.get('to'))

    if q:
        qs = qs.filter(Q(issue_no__icontains=q) | Q(received_by__icontains=q) | Q(purpose__icontains=q) |
                       Q(items__product__name__icontains=q)).distinct()
    if store.isdigit():
        qs = qs.filter(from_warehouse_id=int(store))
    if itype in dict(StoreIssue.ISSUE_TYPES):
        qs = qs.filter(issue_type=itype)
    if dept.isdigit():
        qs = qs.filter(department_id=int(dept))
    if status in ('issued', 'cancelled'):
        qs = qs.filter(status=status)
    if d_from:
        qs = qs.filter(issue_date__date__gte=d_from)
    if d_to:
        qs = qs.filter(issue_date__date__lte=d_to)
    return qs, {'q': q, 'store': store, 'type': itype, 'department': dept, 'status': status,
                'from': request.GET.get('from', ''), 'to': request.GET.get('to', '')}


@login_required
@perm_required('view_warehouse', 'manage_store_issue')
def store_issue_list(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _si_no_store(request)

    qs, f = _si_filtered_issues(request, view_ids)
    totals = qs.filter(status='issued').aggregate(n=Count('id', distinct=True), cost=Sum('total_cost'))
    page_obj = Paginator(qs.annotate(item_count=Count('items', distinct=True)).order_by('-issue_date', '-id'),
                         25).get_page(request.GET.get('page', 1))

    keep = request.GET.copy()
    keep.pop('page', None)
    context = {
        'company_name': _si_company(),
        'page_obj': page_obj,
        'f': f,
        'qs': keep.urlencode(),
        'stores': _si_stores_qs(view_ids),
        'departments': Department.objects.filter(is_active=True),
        'issue_types': StoreIssue.ISSUE_TYPES,
        'total_count': totals['n'] or 0,
        'total_cost': totals['cost'] or Decimal('0.00'),
        'can_issue': bool(_sa.allowed_ids(request.user, 'keeper') is None or _sa.allowed_ids(request.user, 'keeper')),
        'filters_active': any(f.values()),
    }
    return render(request, 'store_issue/list.html', context)


# ============================================================================
# Create issue
# ============================================================================
def _si_parse_dt(value):
    value = (value or '').strip()
    if not value:
        return timezone.now()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(value, fmt)
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except ValueError:
            continue
    raise _sis.StoreIssueError('Invalid date.')


def _si_form_context(request, form=None, rows=None):
    open_orders = ProductionOrder.objects.filter(status__in=['approved', 'in_progress']).select_related('product')
    return {
        'company_name': _si_company(),
        'stores': _si_store_choices(request.user),
        'departments': Department.objects.filter(is_active=True),
        'production_orders': open_orders,
        'issue_types': StoreIssue.ISSUE_TYPES,
        'form': form or {'issue_type': request.GET.get('type', 'production'),
                         'store': request.GET.get('store', ''),
                         'issue_date': timezone.localtime().strftime('%Y-%m-%dT%H:%M')},
        'rows': rows or [],
    }


@login_required
@perm_required('manage_store_issue')
def store_issue_create(request):
    ids = _sa.allowed_ids(request.user, 'keeper')
    if ids is not None and not ids:
        return _si_deny(request, 'issue stock (you are not a keeper/manager of any store)')

    if request.method != 'POST':
        return render(request, 'store_issue/form.html', _si_form_context(request))

    p = request.POST
    form = {k: p.get(k, '') for k in ('store', 'issue_type', 'department', 'production_order',
                                      'received_by', 'purpose', 'issue_date')}
    ids, qtys, remarks = p.getlist('product_id'), p.getlist('qty'), p.getlist('remarks')
    raw = [(i.strip(), (qtys[n] if n < len(qtys) else '').strip(), (remarks[n] if n < len(remarks) else '').strip())
           for n, i in enumerate(ids)]
    raw = [r for r in raw if r[0] or r[1]]
    products = {str(x.pk): x for x in Product.objects.filter(pk__in=[r[0] for r in raw if r[0].isdigit()])}
    rows = [{'product_id': r[0], 'name': products[r[0]].name if r[0] in products else '', 'qty': r[1],
             'remarks': r[2]} for r in raw]

    def fail(msg):
        messages.error(request, f'❌ {msg}')
        return render(request, 'store_issue/form.html', _si_form_context(request, form, rows))

    try:
        wh = Warehouse.objects.filter(pk=form['store']).first() if form['store'].isdigit() else None
        if wh is not None and not _sa.can(request.user, wh.pk, 'keeper'):
            return fail('You do not have the right to issue from this store.')
        dept = Department.objects.filter(pk=form['department']).first() if form['department'].isdigit() else None
        order = (ProductionOrder.objects.filter(pk=form['production_order']).first()
                 if form['production_order'].isdigit() else None)
        when = _si_parse_dt(form['issue_date'])
        if when > timezone.now() + timedelta(days=1):
            return fail('A future date is not allowed.')
        items = []
        for pid, qty, rem in raw:
            if pid not in products:
                return fail('Select an item in every line.')
            items.append((products[pid], qty, rem))
        from ...store import store_ops_service as _ops
        est = _ops.estimate_cost(wh, [(p_, float(q_ or 0)) for p_, q_, _r in items]) if wh else 0
        if wh is not None and _ops.needs_approval(request.user, wh, est):
            req = _ops.create_request(user=request.user, from_warehouse=wh, issue_type=form['issue_type'],
                                      items=items, issue_date=when, department=dept, production_order=order,
                                      received_by=form['received_by'], purpose=form['purpose'])
            messages.success(request, f'📝 {req.request_no} was sent for approval (estimated cost Rs. {req.est_cost:,.2f}). It will be issued once a manager approves.')
            return redirect('store_request_detail', pk=req.pk)
        issue = _sis.create_issue(user=request.user, from_warehouse=wh, issue_type=form['issue_type'],
                                  items=items, issue_date=when, department=dept, production_order=order,
                                  received_by=form['received_by'], purpose=form['purpose'])
    except _sis.StoreIssueError as e:
        return fail(str(e))

    messages.success(request, f'✅ {issue.issue_no} issued. Total cost Rs. {issue.total_cost:,.2f}')
    return redirect('store_issue_detail', pk=issue.pk)


# ============================================================================
# Detail / print / cancel
# ============================================================================
def _si_get_issue(request, pk, need='viewer'):
    """The issue is found only if the user is in that store team (otherwise 404, so it is not even revealed)."""
    issue = get_object_or_404(
        StoreIssue.objects.select_related('from_warehouse', 'department', 'created_by', 'cancelled_by',
                                          'production_order'), pk=pk)
    if not _sa.can(request.user, issue.from_warehouse_id, need):
        from django.http import Http404
        raise Http404('Issue not found')
    return issue


@login_required
@perm_required('view_warehouse', 'manage_store_issue')
def store_issue_detail(request, pk):
    issue = _si_get_issue(request, pk)
    context = {
        'company_name': _si_company(), 'issue': issue,
        'items': issue.items.select_related('product', 'product__unit'),
        'can_cancel': issue.status == 'issued' and _sa.can(request.user, issue.from_warehouse_id, 'manager'),
    }
    return render(request, 'store_issue/detail.html', context)


@login_required
@perm_required('view_warehouse', 'manage_store_issue')
def store_issue_print(request, pk):
    issue = _si_get_issue(request, pk)
    info = CompanyInfo.objects.first()
    return render(request, 'store_issue/print.html', {
        'company_name': _si_company(), 'company': info, 'issue': issue,
        'items': issue.items.select_related('product', 'product__unit'),
    })


@login_required
@perm_required('manage_store_issue')
@require_POST
def store_issue_cancel(request, pk):
    _si_get_issue(request, pk, need='manager')   # only the store team's manager can cancel
    reason = (request.POST.get('reason') or '').strip()
    if not reason:
        messages.error(request, '❌ A reason for cancelling is required.')
        return redirect('store_issue_detail', pk=pk)
    try:
        issue = _sis.cancel_issue(pk, request.user, reason)
    except StoreIssue.DoesNotExist:
        messages.error(request, 'Issue not found.')
        return redirect('store_issue_list')
    except _sis.StoreIssueError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_issue_detail', pk=pk)
    messages.success(request, f'↩️ {issue.issue_no} cancelled, the stock went back to the store.')
    return redirect('store_issue_detail', pk=pk)


# ============================================================================
# AJAX: product search inside one store
# ============================================================================
@login_required
@perm_required('view_warehouse', 'manage_store_issue')
def store_issue_products_api(request):
    wh = request.GET.get('store', '')
    q = (request.GET.get('q') or '').strip()
    if not wh.isdigit():
        return JsonResponse({'results': []})
    if not _sa.can(request.user, int(wh), 'keeper'):
        return JsonResponse({'results': []}, status=403)
    inv = (Inventory.objects.filter(warehouse_id=int(wh), stock__gt=0, product__is_active=True)
           .select_related('product', 'product__unit'))
    if q:
        inv = inv.filter(Q(product__name__icontains=q) | Q(product__barcode__icontains=q) |
                         Q(product__serial_no__icontains=q))
    results = [{
        'id': i.product_id, 'name': i.product.name,
        'unit': i.product.unit.name if i.product.unit else '',
        'available': round(i.available_stock, 3),
    } for i in inv.order_by('product__name')[:25]]
    return JsonResponse({'results': results})


# ============================================================================
# Report
# ============================================================================
_SI_GROUPS = {
    'store': ('from_warehouse__name', 'Store'),
    'type': ('issue__issue_type', 'Issue type'),
    'department': ('issue__department__name', 'Department'),
    'product': ('product__name', 'Product'),
}


@login_required
@perm_required('view_warehouse', 'manage_store_issue')
def store_issue_report(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _si_no_store(request)

    group = request.GET.get('group', 'store')
    if group not in _SI_GROUPS:
        group = 'store'
    d_from = _si_date(request.GET.get('from')) or (date.today().replace(day=1))
    d_to = _si_date(request.GET.get('to')) or date.today()

    items = StoreIssueItem.objects.filter(issue__status='issued', issue__issue_date__date__gte=d_from,
                                          issue__issue_date__date__lte=d_to)
    if view_ids is not None:
        items = items.filter(issue__from_warehouse_id__in=view_ids)
    store = request.GET.get('store', '')
    if store.isdigit():
        items = items.filter(issue__from_warehouse_id=int(store))

    field = {'store': 'issue__from_warehouse__name', 'type': 'issue__issue_type',
             'department': 'issue__department__name', 'product': 'product__name'}[group]
    rows = list(items.values(label=F(field)).annotate(qty=Sum('qty'), cost=Sum('total_cost'),
                                                      issues=Count('issue', distinct=True)).order_by('-cost'))
    type_names = dict(StoreIssue.ISSUE_TYPES)
    for r in rows:
        if group == 'type':
            r['label'] = type_names.get(r['label'], r['label'])
        r['label'] = r['label'] or '(none)'
    grand = sum((r['cost'] or Decimal('0')) for r in rows)

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="store_issue_report_{d_from}_{d_to}.csv"'
        resp.write('\ufeff')
        w = csv.writer(resp)
        w.writerow([_SI_GROUPS[group][1], 'Issues', 'Quantity', 'Cost'])
        for r in rows:
            lbl = str(r['label'])
            w.writerow([("'" + lbl) if lbl[:1] in '=+-@' else lbl, r['issues'], r['qty'], r['cost']])
        w.writerow(['TOTAL', '', '', grand])
        return resp

    context = {
        'company_name': _si_company(), 'rows': rows, 'grand': grand, 'group': group,
        'group_label': _SI_GROUPS[group][1], 'groups': [(k, v[1]) for k, v in _SI_GROUPS.items()],
        'from': d_from.isoformat(), 'to': d_to.isoformat(), 'store': store,
        'stores': _si_stores_qs(view_ids),
    }
    return render(request, 'store_issue/report.html', context)


# ============================================================================
# Store team / access management (superuser only)
# ============================================================================
@login_required
@perm_required('manage_warehouse')
def store_access(request):
    if not request.user.is_superuser:
        return _si_deny(request, 'manage store access')

    levels = dict(StoreMember.LEVELS)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        level = request.POST.get('level', '')
        try:
            if action == 'add':
                user = User.objects.filter(pk=request.POST.get('user'), is_active=True).first()
                wh = Warehouse.objects.filter(pk=request.POST.get('warehouse')).first()
                if not user or not wh or level not in levels:
                    raise ValueError('Select a valid user, store and level.')
                StoreMember.objects.update_or_create(
                    user=user, warehouse=wh,
                    defaults={'level': level, 'is_active': True, 'added_by': request.user})
                messages.success(request, f'✅ {user.get_username()} is now in the team of {wh.name}.')
            elif action == 'create_user':
                username = (request.POST.get('username') or '').strip()
                password = request.POST.get('password') or ''
                wh = Warehouse.objects.filter(pk=request.POST.get('warehouse')).first()
                if not username or not wh or level not in levels:
                    raise ValueError('Username, store and level are required.')
                if password != (request.POST.get('confirm_password') or ''):
                    raise ValueError('The two passwords do not match.')
                new_user = User(username=username,
                                first_name=(request.POST.get('first_name') or '').strip()[:150],
                                last_name=(request.POST.get('last_name') or '').strip()[:150],
                                email=(request.POST.get('email') or '').strip())
                try:
                    new_user.full_clean(exclude=['password', 'last_login', 'date_joined'])
                    validate_password(password, new_user)
                except ValidationError as e:
                    raise ValueError(' '.join(e.messages))
                role_name = (request.POST.get('role') or '').strip()
                with transaction.atomic():
                    new_user.set_password(password)
                    new_user.is_active = True
                    new_user.save()
                    if role_name:
                        grp = Group.objects.filter(name=role_name).first()
                        if grp:
                            new_user.groups.add(grp)
                    StoreMember.objects.create(user=new_user, warehouse=wh, level=level, added_by=request.user)
                messages.success(request, f'✅ New user "{username}" was created and added to the team of {wh.name}.')
            elif action == 'level':
                m = get_object_or_404(StoreMember, pk=request.POST.get('member'))
                if level not in levels:
                    raise ValueError('Invalid level.')
                m.level = level
                m.save(update_fields=['level'])
                messages.success(request, f'✅ The level of {m.user.get_username()} was changed.')
            elif action == 'remove':
                m = get_object_or_404(StoreMember, pk=request.POST.get('member'))
                who, store = m.user.get_username(), m.warehouse.name
                m.delete()
                messages.success(request, f'🗑️ {who} was removed from the team of {store}.')
        except ValueError as e:
            messages.error(request, f'❌ {e}')
        return redirect('store_access')

    stores = (Warehouse.objects.select_related('store_profile')
              .prefetch_related('members__user').order_by('name'))
    stores = sorted(stores, key=lambda w: (not hasattr(w, 'store_profile'), w.name))
    context = {
        'company_name': _si_company(),
        'stores': stores,
        'users': User.objects.filter(is_active=True, is_superuser=False).order_by('username'),
        'levels': StoreMember.LEVELS,
        'roles': list(Group.objects.order_by('name').values_list('name', flat=True)),
        'default_role': 'Warehouse Staff',
    }
    return render(request, 'store_issue/access.html', context)


# ============================================================================
# Store Profiles (frontend): store banana / type / company type / modules badalna (superuser only)
# ============================================================================
def _sp_module_choices():
    from ...module_catalog import MODULE_GROUPS, get_module_catalog
    MODULE_CATALOG = get_module_catalog()
    groups = []
    for g in MODULE_GROUPS:
        items = [(m['key'], m['label']) for m in MODULE_CATALOG if m['group'] == g]
        if items:
            groups.append((g, items))
    return groups


@login_required
@perm_required('manage_warehouse')
def store_profile_list(request):
    if not request.user.is_superuser:
        return _si_deny(request, 'manage store profiles')
    from ...module_catalog import STORE_TYPE_UNITS
    unit_names = dict(StoreProfile.BUSINESS_UNIT_CHOICES)
    mode = _sa.business_mode()
    rows = []
    for p in StoreProfile.objects.select_related('warehouse', 'keeper').order_by('code'):
        rows.append({
            'p': p,
            'unit_label': unit_names.get(p.effective_unit(), p.effective_unit()),
            'unit_is_default': not p.business_unit,
            'modules': sorted(p.effective_modules()),
            'modules_is_default': not p.allowed_modules,
            'visible_now': p.available_in(mode),
            'members': StoreMember.objects.filter(warehouse=p.warehouse, is_active=True).count(),
        })
    return render(request, 'store_issue/profiles.html', {
        'company_name': _si_company(), 'rows': rows, 'mode': mode,
        'plain_warehouses': Warehouse.objects.filter(store_profile__isnull=True).count(),
    })


@login_required
@perm_required('manage_warehouse')
def store_profile_form(request, pk=None):
    """pk=None -> new store; otherwise edit that store."""
    if not request.user.is_superuser:
        return _si_deny(request, 'manage store profiles')
    from ...module_catalog import STORE_TYPE_MODULES, STORE_TYPE_UNITS, get_module_catalog
    MODULE_CATALOG = get_module_catalog()
    profile = get_object_or_404(StoreProfile.objects.select_related('warehouse'), pk=pk) if pk else None
    valid_modules = {m['key'] for m in MODULE_CATALOG}
    valid_types = dict(StoreProfile.STORE_TYPES)
    valid_units = {k for k, _ in StoreProfile.BUSINESS_UNIT_CHOICES}
    form = {}

    if request.method == 'POST':
        P = request.POST
        form = P
        try:
            code = (P.get('code') or '').strip().upper()
            store_type = P.get('store_type', '')
            unit = P.get('business_unit', '')
            modules = [m for m in P.getlist('modules') if m in valid_modules]
            if not code or len(code) > 10:
                raise ValueError('Code is required (max 10 letters), e.g. PMS.')
            if store_type not in valid_types:
                raise ValueError('Store type chunein.')
            if unit not in valid_units:
                raise ValueError('Invalid company type.')
            if StoreProfile.objects.filter(code=code).exclude(pk=getattr(profile, 'pk', None)).exists():
                raise ValueError(f'Code "{code}" already belongs to another store.')

            with transaction.atomic():
                if profile is None:
                    wh_id, new_name = P.get('warehouse', ''), (P.get('new_warehouse') or '').strip()
                    if new_name:
                        if Warehouse.objects.filter(name__iexact=new_name).exists():
                            raise ValueError(f'A warehouse named "{new_name}" already exists, choose it from the list.')
                        wh = Warehouse.objects.create(name=new_name)
                    else:
                        wh = Warehouse.objects.filter(pk=wh_id, store_profile__isnull=True).first()
                        if not wh:
                            raise ValueError('Choose a warehouse or enter a new name.')
                    profile = StoreProfile(warehouse=wh)
                keeper = User.objects.filter(pk=P.get('keeper'), is_active=True).first() if P.get('keeper') else None
                profile.code, profile.store_type, profile.business_unit = code, store_type, unit
                profile.allowed_modules = ','.join(modules)
                profile.can_issue = P.get('can_issue') == 'on'
                profile.is_active = P.get('is_active') == 'on'
                profile.keeper = keeper
                profile.save()
            cache.delete('module_visibility')
            messages.success(request, f'✅ Store {profile.code} saved.')
            return redirect('store_profile_list')
        except ValueError as e:
            messages.error(request, f'❌ {e}')

    if not form:
        if profile:
            form = {
                'code': profile.code, 'store_type': profile.store_type, 'business_unit': profile.business_unit,
                'can_issue': 'on' if profile.can_issue else '', 'is_active': 'on' if profile.is_active else '',
                'keeper': str(profile.keeper_id or ''),
            }
            selected = [k for k in (profile.allowed_modules or '').split(',') if k]
        else:
            form = {'can_issue': 'on', 'is_active': 'on', 'store_type': 'GEN'}
            selected = []
    else:
        selected = [m for m in form.getlist('modules')] if hasattr(form, 'getlist') else []
    def _get(k):
        return form.get(k, '') if hasattr(form, 'get') else ''

    return render(request, 'store_issue/profile_form.html', {
        'company_name': _si_company(), 'profile': profile,
        'form': {k: _get(k) for k in ('code', 'store_type', 'business_unit', 'can_issue', 'is_active',
                                      'keeper', 'warehouse', 'new_warehouse')},
        'selected': set(selected),
        'store_types': StoreProfile.STORE_TYPES,
        'units': StoreProfile.BUSINESS_UNIT_CHOICES,
        'module_groups': _sp_module_choices(),
        'free_warehouses': Warehouse.objects.filter(store_profile__isnull=True).order_by('name'),
        'users': User.objects.filter(is_active=True).order_by('username'),
        'type_defaults': {t: {'unit': STORE_TYPE_UNITS.get(t, 'both'), 'modules': STORE_TYPE_MODULES.get(t, [])}
                          for t in valid_types},
    })
