"""Frontend views: Store Settings (accounting + approval), Approvals, Physical Count, Return to store."""
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import (Account, CompanyInfo, Inventory, StoreAccountRule, StoreCount, StoreIssue,
                      StoreIssueRequest, StoreReturn, StoreSetting, Warehouse)
from .. import store_access as _sa
from .. import store_accounting as _acc
from .. import store_ops_service as _ops


# ---------------------------------------------------------------------------
# helpers (prefix _so_)
# ---------------------------------------------------------------------------
def _so_company():
    info = CompanyInfo.objects.first()
    return info.name if info else 'ERP System'


def _so_deny(request, what='view this page'):
    messages.error(request, f'Access denied! You are not allowed to {what}.')
    return redirect('dashboard')


def _so_no_store(request):
    messages.error(request, 'You do not have access to any store yet. Ask a superuser to add you to a store team.')
    return redirect('dashboard')


def _so_stores(ids):
    qs = Warehouse.objects.select_related('store_profile').order_by('name').exclude(pk__in=_sa.unavailable_warehouse_ids())
    return qs if ids is None else qs.filter(pk__in=ids)


def _so_float(raw):
    raw = (raw or '').strip()
    if raw == '':
        return None
    return float(raw)


# ===========================================================================
# STORE SETTINGS (superuser): accounting + approval
# ===========================================================================
@login_required
def store_settings(request):
    if not request.user.is_superuser:
        return _so_deny(request, 'change store settings')

    setting = StoreSetting.get()
    issue_types = StoreIssue.ISSUE_TYPES
    stores = list(Warehouse.objects.select_related('store_profile').order_by('name'))

    if request.method == 'POST':
        action = request.POST.get('action', '')
        p = request.POST
        try:
            if action == 'save_rules':
                valid = {str(a.pk): a for a in Account.objects.filter(is_active=True)}
                wanted = [('inventory', '', p.get('inv_default'))]
                wanted += [('inventory', str(w.pk), p.get(f'inv_{w.pk}')) for w in stores]
                wanted += [('expense', '', p.get('exp_default'))]
                wanted += [('expense', k, p.get(f'exp_{k}')) for k, _l in issue_types]
                wanted += [('transit', '', p.get('transit')), ('count_loss', '', p.get('count_loss')),
                           ('count_gain', '', p.get('count_gain')), ('opening', '', p.get('opening'))]
                for kind, key, acc_id in wanted:
                    acc_id = (acc_id or '').strip()
                    if not acc_id:
                        StoreAccountRule.objects.filter(kind=kind, key=key).delete()
                    elif acc_id in valid:
                        StoreAccountRule.objects.update_or_create(kind=kind, key=key,
                                                                  defaults={'account': valid[acc_id]})
                    else:
                        raise ValueError('No valid account.')
                messages.success(request, '✅ Account mapping saved.')

            elif action == 'save_policy':
                want_acc = p.get('accounting_enabled') == 'on'
                mode = p.get('approval_mode', 'off')
                if mode not in dict(StoreSetting.APPROVAL_MODES):
                    raise ValueError('Invalid approval mode.')
                try:
                    limit = Decimal((p.get('approval_limit') or '0').strip() or '0')
                except Exception:
                    raise ValueError('Enter a valid number for the approval limit.')
                if limit < 0:
                    raise ValueError('The limit cannot be negative.')
                if want_acc and not setting.accounting_enabled:
                    # the basic mapping is needed before turning it on
                    missing = []
                    if not StoreAccountRule.objects.filter(kind='inventory').exists():
                        missing.append('Inventory account')
                    if not StoreAccountRule.objects.filter(kind='expense').exists():
                        missing.append('Issue kharch account')
                    if missing:
                        raise ValueError('Before turning accounting on, map these: ' + ', '.join(missing))
                setting.accounting_enabled, setting.approval_mode, setting.approval_limit = want_acc, mode, limit
                setting.updated_by = request.user
                setting.save()
                messages.success(request, '✅ Settings save ho gayin.')

            elif action == 'opening_entry':
                entry, total = _acc.post_opening_entry(request.user, Warehouse.objects.all())
                messages.success(request, f'✅ Opening stock entry {entry.entry_no} ban gayi (Rs. {total:,.2f}).')
        except (ValueError, _acc.AccountingMappingError) as e:
            messages.error(request, f'❌ {e}')
        return redirect('store_settings')

    rules = {(r.kind, r.key): r.account_id for r in StoreAccountRule.objects.all()}

    def row(label, name, kind, key=''):
        return {'label': label, 'name': name, 'sel': rules.get((kind, key))}

    inventory_rows = [row('Default (sab stores)', 'inv_default', 'inventory')] + \
                     [row(w.name, f'inv_{w.pk}', 'inventory', str(w.pk)) for w in stores]
    expense_rows = [row('Default (for any issue type)', 'exp_default', 'expense')] + \
                   [row(label, f'exp_{k}', 'expense', k) for k, label in issue_types]
    single_rows = [row('In-transit (goods between stores)', 'transit', 'transit'),
                   row('Stock loss (count shortage)', 'count_loss', 'count_loss'),
                   row('Stock gain (count surplus)', 'count_gain', 'count_gain'),
                   row('Opening balance (equity)', 'opening', 'opening')]
    from ..models import StoreJournalLink
    return render(request, 'store_issue/settings.html', {
        'company_name': _so_company(), 'setting': setting, 'modes': StoreSetting.APPROVAL_MODES,
        'accounts': Account.objects.filter(is_active=True).select_related('account_type').order_by('code'),
        'inventory_rows': inventory_rows, 'expense_rows': expense_rows, 'single_rows': single_rows,
        'opening_done': StoreJournalLink.objects.filter(doc_type='opening').exists(),
    })


# ===========================================================================
# APPROVALS
# ===========================================================================
def _so_req_access(request, pk):
    req = get_object_or_404(StoreIssueRequest.objects.select_related(
        'from_warehouse', 'department', 'production_order', 'requested_by', 'decided_by', 'issue'), pk=pk)
    if req.requested_by_id != request.user.pk and not _sa.can(request.user, req.from_warehouse_id, 'viewer'):
        raise Http404('Request not found')
    return req


@login_required
def store_request_list(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    qs = StoreIssueRequest.objects.select_related('from_warehouse', 'requested_by')
    if view_ids is not None:
        qs = qs.filter(Q(from_warehouse_id__in=view_ids) | Q(requested_by=request.user))
        if not view_ids and not qs.exists():
            return _so_no_store(request)
    status = request.GET.get('status', 'pending')
    if status in ('pending', 'approved', 'rejected', 'cancelled'):
        qs = qs.filter(status=status)
    mgr_ids = _sa.allowed_ids(request.user, 'manager')
    waiting = StoreIssueRequest.objects.filter(status='pending')
    if mgr_ids is not None:
        waiting = waiting.filter(from_warehouse_id__in=mgr_ids)
    page_obj = Paginator(qs.annotate(item_count=Count('items')).order_by('-requested_at'), 25).get_page(request.GET.get('page', 1))
    return render(request, 'store_issue/request_list.html', {
        'company_name': _so_company(), 'page_obj': page_obj, 'status': status, 'waiting_count': waiting.count(),
        'setting': StoreSetting.get()})


@login_required
def store_request_detail(request, pk):
    req = _so_req_access(request, pk)
    pending = req.status == 'pending'
    is_manager = _sa.can(request.user, req.from_warehouse_id, 'manager')
    own = req.requested_by_id == request.user.pk
    return render(request, 'store_issue/request_detail.html', {
        'company_name': _so_company(), 'req': req, 'items': req.items.select_related('product', 'product__unit'),
        'can_decide': pending and is_manager and (not own or request.user.is_superuser),
        'self_block': pending and is_manager and own and not request.user.is_superuser,
        'can_cancel': pending and (own or is_manager),
    })


@login_required
@require_POST
def store_request_approve(request, pk):
    req = _so_req_access(request, pk)
    if not _sa.can(request.user, req.from_warehouse_id, 'manager'):
        return _so_deny(request, 'approve this request')
    try:
        _ops.approve_request(req.pk, request.user, request.POST.get('note', ''), allow_self=request.user.is_superuser)
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_request_detail', pk=pk)
    req.refresh_from_db()
    messages.success(request, f'✅ {req.request_no} approved, {req.issue.issue_no} issued.')
    return redirect('store_issue_detail', pk=req.issue_id)


@login_required
@require_POST
def store_request_reject(request, pk):
    req = _so_req_access(request, pk)
    if not _sa.can(request.user, req.from_warehouse_id, 'manager'):
        return _so_deny(request, 'reject this request')
    try:
        _ops.reject_request(req.pk, request.user, request.POST.get('note', ''))
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_request_detail', pk=pk)
    messages.success(request, f'🚫 {req.request_no} rejected.')
    return redirect('store_request_detail', pk=pk)


@login_required
@require_POST
def store_request_cancel(request, pk):
    req = _so_req_access(request, pk)
    if not (req.requested_by_id == request.user.pk or _sa.can(request.user, req.from_warehouse_id, 'manager')):
        return _so_deny(request, 'cancel this request')
    try:
        _ops.cancel_request(req.pk, request.user)
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
    else:
        messages.success(request, f'↩️ {req.request_no} cancelled.')
    return redirect('store_request_detail', pk=pk)


# ===========================================================================
# PHYSICAL COUNT
# ===========================================================================
def _so_count(request, pk, need='viewer'):
    c = get_object_or_404(StoreCount.objects.select_related('warehouse', 'created_by', 'submitted_by', 'posted_by'), pk=pk)
    if not _sa.can(request.user, c.warehouse_id, need):
        raise Http404('Count not found')
    return c


@login_required
def store_count_list(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _so_no_store(request)
    qs = StoreCount.objects.select_related('warehouse', 'created_by')
    if view_ids is not None:
        qs = qs.filter(warehouse_id__in=view_ids)
    status = request.GET.get('status', '')
    if status in ('counting', 'submitted', 'posted', 'cancelled'):
        qs = qs.filter(status=status)
    page_obj = Paginator(qs.annotate(line_count=Count('lines')).order_by('-count_date', '-id'), 25).get_page(request.GET.get('page', 1))
    keeper_ids = _sa.allowed_ids(request.user, 'keeper')
    return render(request, 'store_issue/count_list.html', {
        'company_name': _so_company(), 'page_obj': page_obj, 'status': status,
        'can_start': keeper_ids is None or bool(keeper_ids)})


@login_required
def store_count_new(request):
    keeper_ids = _sa.allowed_ids(request.user, 'keeper')
    if keeper_ids is not None and not keeper_ids:
        return _so_deny(request, 'start a stock count (you are not a keeper/manager of any store)')
    stores = list(_so_stores(keeper_ids))
    if request.method == 'POST':
        wh = Warehouse.objects.filter(pk=request.POST.get('warehouse')).first()
        if wh is None or not _sa.can(request.user, wh.pk, 'keeper'):
            messages.error(request, '❌ You do not have the right to start a count in this store.')
        else:
            try:
                c = _ops.start_count(request.user, wh, request.POST.get('notes', ''),
                                     include_zero=request.POST.get('include_zero') == 'on')
                messages.success(request, f'✅ {c.count_no} started. Enter the actual count of each item.')
                return redirect('store_count_detail', pk=c.pk)
            except _ops.StoreOpsError as e:
                messages.error(request, f'❌ {e}')
    return render(request, 'store_issue/count_new.html', {'company_name': _so_company(), 'stores': stores,
                                                          'sel': request.GET.get('store', '')})


@login_required
def store_count_detail(request, pk):
    c = _so_count(request, pk)
    lines = list(c.lines.select_related('product', 'product__unit'))
    can_edit = c.status == 'counting' and _sa.can(request.user, c.warehouse_id, 'keeper')
    is_mgr = _sa.can(request.user, c.warehouse_id, 'manager')
    review = c.status == 'submitted'
    if review:
        cur = {i.product_id: i.stock for i in Inventory.objects.filter(warehouse=c.warehouse,
                                                                         product_id__in=[l.product_id for l in lines])}
        for l in lines:
            l.current = cur.get(l.product_id, 0.0)
            l.diff = round((l.counted_qty or 0) - l.current, 6)
            l.changed = abs(l.current - l.system_qty) > 1e-9
            if l.diff > 0:
                l.est_cost = _ops._avg_cost(l.product, c.warehouse)
    changed = sum(1 for l in lines if getattr(l, 'changed', False))
    diffs = sum(1 for l in lines if (getattr(l, 'diff', 0) if review else l.diff_qty))
    self_block = review and c.submitted_by_id == request.user.pk and not request.user.is_superuser
    return render(request, 'store_issue/count_detail.html', {
        'company_name': _so_company(), 'c': c, 'lines': lines, 'can_edit': can_edit, 'review': review,
        'can_post': review and is_mgr and not self_block, 'self_block': review and is_mgr and self_block,
        'can_cancel': c.status in ('counting', 'submitted') and (is_mgr or (c.status == 'counting' and can_edit)),
        'changed_count': changed, 'diff_count': diffs})


def _so_collect_counts(request, c):
    counted, reasons = {}, {}
    for l in c.lines.all():
        raw = request.POST.get(f'cnt_{l.pk}')
        if raw is not None:
            counted[l.pk] = _so_float(raw)
        if f'rsn_{l.pk}' in request.POST:
            reasons[l.pk] = request.POST.get(f'rsn_{l.pk}', '')
    return counted, reasons


@login_required
@require_POST
def store_count_save(request, pk):
    c = _so_count(request, pk, 'keeper')
    try:
        counted, reasons = _so_collect_counts(request, c)
        _ops.save_counts(c.pk, counted, reasons)
        if request.POST.get('submit') == '1':
            _ops.submit_count(c.pk, request.user)
            messages.success(request, f'✅ {c.count_no} sent for review. A manager will check the difference and post it.')
        else:
            messages.success(request, '💾 Count saved.')
    except ValueError:
        messages.error(request, '❌ Enter only numbers in the count.')
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
    return redirect('store_count_detail', pk=pk)


@login_required
@require_POST
def store_count_post(request, pk):
    c = _so_count(request, pk, 'manager')
    reasons, costs = {}, {}
    for l in c.lines.all():
        if f'rsn_{l.pk}' in request.POST:
            reasons[l.pk] = request.POST.get(f'rsn_{l.pk}', '')
        raw = (request.POST.get(f'cost_{l.pk}') or '').strip()
        if raw:
            try:
                costs[l.pk] = Decimal(raw)
            except Exception:
                messages.error(request, f'❌ {l.product.name}: enter a valid number for the unit cost.')
                return redirect('store_count_detail', pk=pk)
    try:
        _ops.post_count(c.pk, request.user, costs, reasons, allow_self=request.user.is_superuser)
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
        return redirect('store_count_detail', pk=pk)
    messages.success(request, f'✅ {c.count_no} posted, the stock was corrected to match the count.')
    return redirect('store_count_detail', pk=pk)


@login_required
@require_POST
def store_count_cancel(request, pk):
    c = _so_count(request, pk, 'keeper')
    if c.status == 'submitted' and not _sa.can(request.user, c.warehouse_id, 'manager'):
        return _so_deny(request, 'cancel a submitted count')
    try:
        _ops.cancel_count(c.pk, request.user)
        messages.success(request, f'↩️ {c.count_no} cancelled (no change in stock).')
    except _ops.StoreOpsError as e:
        messages.error(request, f'❌ {e}')
    return redirect('store_count_detail', pk=pk)


# ===========================================================================
# RETURN TO STORE
# ===========================================================================
def _so_issue(request, issue_pk, need):
    issue = get_object_or_404(StoreIssue.objects.select_related('from_warehouse', 'department'), pk=issue_pk)
    if not _sa.can(request.user, issue.from_warehouse_id, need):
        raise Http404('Issue not found')
    return issue


@login_required
def store_return_create(request, issue_pk):
    issue = _so_issue(request, issue_pk, 'keeper')
    if issue.status != 'issued':
        messages.error(request, '❌ Goods cannot be returned from a cancelled issue.')
        return redirect('store_issue_detail', pk=issue.pk)
    items = list(issue.items.select_related('product', 'product__unit'))
    for it in items:
        it.returned = round(sum(l.qty for l in it.return_lines.all()), 6)
        it.room = round(it.qty - it.returned, 6)
    if request.method == 'POST':
        qtys = {}
        try:
            for it in items:
                raw = _so_float(request.POST.get(f'qty_{it.pk}'))
                if raw:
                    qtys[it.pk] = raw
            ret = _ops.create_return(user=request.user, issue_id=issue.pk, quantities=qtys,
                                     returned_by=request.POST.get('returned_by', ''),
                                     notes=request.POST.get('notes', ''))
            messages.success(request, f'✅ {ret.return_no}: the goods are back in the store (Rs. {ret.total_cost:,.2f}).')
            return redirect('store_return_detail', pk=ret.pk)
        except ValueError:
            messages.error(request, '❌ Enter only numbers in the quantity.')
        except _ops.StoreOpsError as e:
            messages.error(request, f'❌ {e}')
    return render(request, 'store_issue/return_form.html', {'company_name': _so_company(), 'issue': issue,
                                                            'items': items})


@login_required
def store_return_list(request):
    view_ids = _sa.allowed_ids(request.user, 'viewer')
    if view_ids is not None and not view_ids:
        return _so_no_store(request)
    qs = StoreReturn.objects.select_related('issue', 'issue__from_warehouse', 'created_by')
    if view_ids is not None:
        qs = qs.filter(issue__from_warehouse_id__in=view_ids)
    page_obj = Paginator(qs.order_by('-return_date', '-id'), 25).get_page(request.GET.get('page', 1))
    return render(request, 'store_issue/return_list.html', {'company_name': _so_company(), 'page_obj': page_obj})


@login_required
def store_return_detail(request, pk):
    ret = get_object_or_404(StoreReturn.objects.select_related('issue', 'issue__from_warehouse', 'created_by'), pk=pk)
    if not _sa.can(request.user, ret.issue.from_warehouse_id, 'viewer'):
        raise Http404('Return not found')
    return render(request, 'store_issue/return_detail.html', {
        'company_name': _so_company(), 'ret': ret,
        'lines': ret.lines.select_related('issue_item__product', 'issue_item__product__unit')})
