"""Cashier feedback on a scan + the alias learning loop."""
import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ....models import OcrAliasSuggestion, OcrScanLog, Product, ProductAlias
from ....security.permissions import perm_required
from ....utils.pos import ocr_cache
from ....utils.pos import ocr_core as core
from .common import _int_or_none, _too_many
from .config import RATE_FEEDBACK, _PERMS

log = logging.getLogger(__name__)


def _learn(user, product, text):
    """Count one confirmation of text -> product. Promote to ProductAlias after ALIAS_AUTO_HITS."""
    alias = core.alias_candidate(text, product.name)
    if not alias:
        return None
    sug, created = OcrAliasSuggestion.objects.get_or_create(product=product, text=alias)
    if sug.status == 'rejected':
        return 'rejected'
    if not created:
        OcrAliasSuggestion.objects.filter(pk=sug.pk).update(hits=F('hits') + 1)
        sug.refresh_from_db()
    if sug.status == 'pending' and sug.hits >= core.ALIAS_AUTO_HITS:
        # the same text must not already point to ANOTHER product
        clash = ProductAlias.objects.filter(alias__iexact=alias).exclude(product=product).exists()
        if not clash:
            ProductAlias.objects.get_or_create(product=product, alias=alias, defaults={'created_by': user})
            sug.status = 'approved'
            sug.save(update_fields=['status', 'last_seen'])
            ocr_cache.invalidate_catalog()
            return 'approved'
    return sug.status


@login_required
@perm_required(*_PERMS)
@require_POST
def ocr_feedback(request):
    """AJAX POST: log_id, product_id, how = auto | tap.  Records the cashier's decision and learns from it."""
    limited = _too_many(request, 'feedback', RATE_FEEDBACK)
    if limited:
        return limited
    log_id = _int_or_none(request.POST.get('log_id'))
    product_id = _int_or_none(request.POST.get('product_id'))
    how = request.POST.get('how', 'tap')
    if not log_id or not product_id:
        return JsonResponse({'success': False}, status=400)
    try:
        with transaction.atomic():
            row = (OcrScanLog.objects.select_for_update().filter(pk=log_id).first())
            if not row or (row.user_id != request.user.id and not request.user.is_superuser):
                return JsonResponse({'success': False}, status=404)
            if row.outcome not in ('pending',):
                return JsonResponse({'success': True, 'outcome': row.outcome, 'learned': None})
            product = Product.objects.filter(pk=product_id).first()
            if not product:
                return JsonResponse({'success': False}, status=404)
            if how == 'auto' and row.top_product_id == product_id:
                outcome = 'auto_added'
            elif row.top_product_id == product_id:
                outcome = 'tapped_top'
            else:
                outcome = 'corrected'
            row.chosen_product = product
            row.outcome = outcome
            row.resolved_at = timezone.now()
            row.save(update_fields=['chosen_product', 'outcome', 'resolved_at'])
            learned = _learn(request.user, product, row.text) if core.should_learn(outcome, row.confident) else None
        return JsonResponse({'success': True, 'outcome': outcome, 'learned': learned})
    except Exception:
        log.exception('OCR: feedback failed')
        return JsonResponse({'success': False}, status=500)
