"""Frontend views: price history (audit log) and undo (preview + apply)."""
import csv
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

from ...models import CompanyInfo, PriceChangeLog, StockBatch
from ...security.permissions import has_matrix_perm, perm_required
from ...utils import price_audit
from ...utils import price_undo as undo_rules
from ...utils.margin_policy import MarginPolicy
from ...utils import pricing as pricing_rules


def _filtered(request):
    qs = PriceChangeLog.objects.select_related('product', 'batch', 'changed_by')
    g = request.GET
    q = (g.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(product_name__icontains=q) | Q(batch_ref__icontains=q.lstrip('#')) | Q(reason__icontains=q))
    if g.get('user'):
        qs = qs.filter(changed_by_name__icontains=g['user'].strip())
    if g.get('field') in dict(PriceChangeLog.FIELD_CHOICES):
        qs = qs.filter(price_field=g['field'])
    if g.get('source') in dict(PriceChangeLog.SOURCE_CHOICES):
        qs = qs.filter(source=g['source'])
    if g.get('run'):
        try:
            qs = qs.filter(run_id=g['run'].strip())
        except Exception:
            qs = qs.none()
    d_from, d_to = parse_date(g.get('from') or ''), parse_date(g.get('to') or '')
    if d_from:
        qs = qs.filter(changed_at__date__gte=d_from)
    if d_to:
        qs = qs.filter(changed_at__date__lte=d_to)
    return qs


def _export_csv(qs):
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="price_history.csv"'
    resp.write('\ufeff')  # Excel opens UTF-8 correctly
    w = csv.writer(resp)
    w.writerow(['Date/Time', 'Product', 'Batch', 'What', 'Source', 'Old', 'New', 'Cost', 'By', 'IP', 'Reason', 'Run ID'])
    for r in qs.iterator(chunk_size=500):
        w.writerow([r.changed_at.strftime('%Y-%m-%d %H:%M:%S'), r.product_name, r.batch_ref,
                    r.get_price_field_display(), r.get_source_display(), r.old_value, r.new_value,
                    r.cost_price, r.changed_by_name, r.ip_address or '', r.reason, r.run_id or ''])
    return resp


@login_required
@perm_required('view_price_history')
def price_history_list(request):
    qs = _filtered(request)
    if request.GET.get('export') == 'csv':
        return _export_csv(qs[:20000])
    page_obj = Paginator(qs, 50).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    try:
        run_uuid = uuid.UUID((request.GET.get('run') or '').strip())
    except ValueError:
        run_uuid = None
    return render(request, 'inventory/price_history.html', {
        'run_uuid': run_uuid,
        'can_undo': has_matrix_perm(request.user, 'manage_products'),
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'total': page_obj.paginator.count,
        'querystring': params.urlencode(),
        'f': request.GET,
        'field_choices': PriceChangeLog.FIELD_CHOICES,
        'source_choices': PriceChangeLog.SOURCE_CHOICES,
    })


# ----------------------------------------------------------------------------------------------
# Undo: roll back a whole bulk run (by run_id) or revert one single change.
# GET shows a preview of what would happen, POST applies it. The undo is itself logged
# (source = "undo"), so it can be seen - and even undone again - in the same history page.
# ----------------------------------------------------------------------------------------------
def _undo_rows(run_id, log_id):
    """History rows to roll back, as plain dicts for undo_rules.plan_undo()."""
    if run_id is not None:
        logs = list(PriceChangeLog.objects.filter(run_id=run_id).order_by('id'))
        if not logs:
            raise Http404('No price changes found for this run.')
    else:
        logs = [get_object_or_404(PriceChangeLog, pk=log_id)]
    return [{'id': r.pk, 'price_field': r.price_field, 'batch_id': r.batch_id,
             'old': r.old_value, 'new': r.new_value,
             'product_name': r.product_name, 'batch_ref': r.batch_ref} for r in logs]


def _batch_state(batch_ids, lock=False):
    qs = StockBatch.objects.filter(pk__in=batch_ids)
    if lock:
        qs = qs.select_for_update()
    return {b.pk: b for b in qs.select_related('product')}


def _plan(rows, batches):
    policy = MarginPolicy.load()
    state = {bid: {'price': b.selling_price, 'cost': b.price, 'min_margin': policy.for_product(b.product)}
             for bid, b in batches.items()}
    return undo_rules.plan_undo(rows, state, validate=pricing_rules.check_selling_price)


@login_required
@perm_required('view_price_history', post='manage_products')
def price_undo(request, run_id=None, log_id=None):
    rows = _undo_rows(run_id, log_id)
    batch_ids = [r['batch_id'] for r in rows if r['batch_id'] is not None]
    title = (f'Undo bulk run {str(run_id)[:8]}' if run_id is not None else f'Revert change #{log_id}')

    if request.method == 'POST':
        new_run = price_audit.new_run_id()
        ip = price_audit.client_ip(request)
        reason = undo_rules.undo_reason(run_id, log_id, request.POST.get('reason'))
        rule = undo_rules.undo_rule(run_id, log_id)
        entries = []
        with transaction.atomic():
            # Re-check under a row lock: prices may have moved since the preview was shown.
            batches = _batch_state(batch_ids, lock=True)
            items = _plan(rows, batches)
            for it in items:
                if it['status'] != undo_rules.ST_REVERT:
                    continue
                batch = batches[it['batch_id']]
                old_price = batch.selling_price
                batch.selling_price = it['target']
                batch.save(update_fields=['selling_price'])
                entries.append(price_audit.build_entry(
                    price_field='batch_selling_price', source='undo',
                    old=old_price, new=it['target'], product=batch.product, batch=batch, cost=batch.price,
                    user=request.user, ip=ip, run_id=new_run, rule=rule, reason=reason))
            # Same transaction: prices and their history rows are saved together, or not at all.
            price_audit.record(entries)
        summary = undo_rules.summarize(items)
        if not entries:
            messages.warning(request, 'Nothing was reverted: no price could be safely rolled back.')
            return redirect(request.path)
        msg = f'↩ {len(entries)} price(s) reverted.'
        if summary['skipped']:
            msg += f' {summary["skipped"]} skipped (changed again, already reverted or no longer valid).'
        messages.success(request, msg)
        return redirect(reverse('price_history') + f'?run={new_run}')

    batches = _batch_state(batch_ids)
    items = _plan(rows, batches)
    return render(request, 'inventory/price_undo.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'title': title,
        'is_run': run_id is not None,
        'run_id': run_id,
        'items': items,
        'summary': undo_rules.summarize(items),
        'labels': undo_rules.LABELS,
    })

