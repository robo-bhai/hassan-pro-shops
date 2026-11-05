"""Accuracy dashboard + one-click approve / reject of alias suggestions."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ....models import OcrAliasSuggestion, OcrScanLog, ProductAlias
from ....security.permissions import perm_required
from ....utils.pos import ocr_cache
from ....utils.pos import ocr_core as core
from .common import _has_perm, _int_or_none


def _approve_suggestion(user, sug):
    """Turn one suggestion into a ProductAlias. -> 'approved' | 'clash' (the text already means ANOTHER product)."""
    if ProductAlias.objects.filter(alias__iexact=sug.text).exclude(product=sug.product).exists():
        return 'clash'
    ProductAlias.objects.get_or_create(product=sug.product, alias=sug.text, defaults={'created_by': user})
    sug.status = 'approved'
    sug.save(update_fields=['status', 'last_seen'])
    ocr_cache.invalidate_catalog()
    return 'approved'


@login_required
@perm_required('view_reports', 'manage_inventory')
def ocr_dashboard(request):
    """How well does the camera search work?  Last N days (?days=7|30|90)."""
    days = _int_or_none(request.GET.get('days'), 1, 365) or 30
    since = timezone.now() - timedelta(days=days)
    logs = OcrScanLog.objects.filter(created_at__gte=since)

    counts = dict(logs.values_list('outcome').annotate(n=Count('id')).order_by())
    stats = core.outcome_rates(counts)
    stats['avg_conf'] = round(logs.exclude(ocr_conf=None).aggregate(a=Avg('ocr_conf'))['a'] or 0)
    by_source = list(logs.values('source').annotate(n=Count('id')).order_by('-n'))

    # products the machine keeps getting wrong: it said A, the cashier chose B
    confused = list(logs.filter(outcome='corrected').values('top_product__name', 'chosen_product__name')
                    .annotate(n=Count('id')).order_by('-n')[:15])
    # texts nothing was found for (a missing alias / a product that is not in the catalog)
    unmatched = list(logs.filter(outcome='no_match').exclude(text='').values('text')
                     .annotate(n=Count('id')).order_by('-n')[:15])
    # per day: right first answers vs corrections
    daily = list(logs.annotate(d=TruncDate('created_at')).values('d')
                 .annotate(total=Count('id'),
                           right=Count('id', filter=Q(outcome__in=('auto_added', 'tapped_top'))),
                           wrong=Count('id', filter=Q(outcome='corrected')),
                           none=Count('id', filter=Q(outcome='no_match')))
                 .order_by('d'))
    peak = max([d['total'] for d in daily] or [1])
    for d in daily:
        d['right_h'] = round(100.0 * d['right'] / peak)
        d['wrong_h'] = round(100.0 * d['wrong'] / peak)
        d['none_h'] = round(100.0 * d['none'] / peak)

    pending = (OcrAliasSuggestion.objects.filter(status='pending').select_related('product')
               .order_by('-hits', '-last_seen')[:50])
    can_edit = request.user.is_superuser or _has_perm(request.user, 'manage_inventory')
    return render(request, 'sales/ocr_dashboard.html', {
        'days': days, 'stats': stats, 'by_source': by_source, 'confused': confused, 'unmatched': unmatched,
        'daily': daily, 'pending': pending, 'can_edit': can_edit, 'auto_hits': core.ALIAS_AUTO_HITS,
    })


@login_required
@perm_required('manage_inventory')
@require_POST
def ocr_alias_action(request):
    """AJAX POST: id=<suggestion id>, action=approve|reject.  Used by the dashboard buttons."""
    sid = _int_or_none(request.POST.get('id'))
    action = request.POST.get('action')
    sug = OcrAliasSuggestion.objects.select_related('product').filter(pk=sid).first() if sid else None
    if not sug or action not in ('approve', 'reject'):
        return JsonResponse({'success': False, 'message': 'Not found.'}, status=400)
    if action == 'reject':
        sug.status = 'rejected'
        sug.save(update_fields=['status', 'last_seen'])
        return JsonResponse({'success': True, 'status': 'rejected'})
    result = _approve_suggestion(request.user, sug)
    if result == 'clash':
        return JsonResponse({'success': False, 'message': 'This text already means another product.'}, status=409)
    return JsonResponse({'success': True, 'status': 'approved'})
