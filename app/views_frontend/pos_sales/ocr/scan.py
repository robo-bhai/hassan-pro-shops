"""Scan endpoints: text read by the camera -> best matching products (+ the scan log row)."""
import hashlib
import logging

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse

from ....models import OcrScanLog, Product
from ....security.permissions import perm_required
from ....utils.pos import ocr_core as core
from .catalog import _catalog, _entry_map, rank_products
from .common import _int_or_none, _too_many
from .config import LOG_DEDUPE_SECONDS, RATE_MATCH, _PERMS
from .payload import _load_batches, _load_stock, _payload_from

log = logging.getLogger(__name__)


def _write_log(request, raw, text, source, ocr_conf, warehouse_id, ranked_top, confident):
    """Create (or reuse, for the same text within a few seconds) one OcrScanLog row. Returns its id or None."""
    try:
        key = 'ocrlog:%s:%s' % (request.user.id, hashlib.md5(text.encode('utf-8')).hexdigest())
        existing = cache.get(key)
        if existing:
            return existing
        top = ranked_top[0] if ranked_top else None
        row = OcrScanLog.objects.create(
            user=request.user, source=source, raw_text=raw[:400], text=text[:200], ocr_conf=ocr_conf,
            warehouse_id=_int_or_none(warehouse_id), candidates=len(ranked_top),
            top_product_id=top[1]['id'] if top else None, top_score=top[0] if top else 0,
            confident=bool(confident), outcome='pending' if top else 'no_match')
        cache.set(key, row.id, LOG_DEDUPE_SECONDS)
        return row.id
    except Exception:
        log.exception('OCR: could not write scan log')
        return None


def _respond(request, raw, text, ranked, source, ocr_conf, warehouse_id, wid):
    """ranked [(score, entry)...] -> the JSON the page shows (details, stock boost, confidence, log row)."""
    if len(text) < 3:
        return JsonResponse({'success': False, 'message': 'No readable text. Hold the product name steady.'})
    if not ranked:
        log_id = _write_log(request, raw, text, source, ocr_conf, warehouse_id, [], False)
        return JsonResponse({'success': False, 'text': text, 'log_id': log_id,
                             'message': 'No product found for "%s".' % text})

    # look at the best CANDIDATES, load everything for them in 3 queries, then show the best 5
    cand = ranked[:core.CANDIDATES]
    ids = [e['id'] for _s, e in cand]
    prods = {p.id: p for p in Product.objects.filter(id__in=ids).select_related('unit')}
    cand = [(s, e) for s, e in cand if e['id'] in prods]
    if not cand:
        return JsonResponse({'success': False, 'text': text, 'message': 'No product found for "%s".' % text})
    batches = _load_batches(ids, wid)
    stocks = _load_stock(ids, wid)
    if wid:                                              # products that can really be sold from this warehouse
        cand = core.apply_stock_boost(cand, {pid for pid, bl in batches.items() if bl})
    top = cand[:5]

    products = []
    for s, e in top:
        d = _payload_from(prods[e['id']], batches.get(e['id'], []), stocks.get(e['id']), wid)
        d['score'] = s
        products.append(d)

    confident = core.is_confident(top)
    log_id = _write_log(request, raw, text, source, ocr_conf, warehouse_id, top, confident)
    return JsonResponse({'success': True, 'confident': confident, 'text': text, 'log_id': log_id,
                         'products': products})


def _scan_params(request):
    raw = (request.GET.get('text') or '').strip()[:400]
    warehouse_id = request.GET.get('warehouse_id', '')
    source = request.GET.get('source', 'camera')
    if source not in ('camera', 'photo', 'manual'):
        source = 'camera'
    # wc = "word:confidence,word:confidence" - how sure the camera was about each word (optional)
    wconf = core.parse_wconf((request.GET.get('wc') or '')[:600])
    return (raw, warehouse_id, _int_or_none(warehouse_id), source, _int_or_none(request.GET.get('conf'), 0, 100),
            wconf)


@login_required
@perm_required(*_PERMS)
def ocr_match_product(request):
    """AJAX: text read by the camera (OCR) -> best matching products. (The server ranks; used until the phone has
    its local catalog, and as the fallback.)"""
    limited = _too_many(request, 'match', RATE_MATCH)
    if limited:
        return limited
    raw, warehouse_id, wid, source, ocr_conf, wconf = _scan_params(request)
    text, ranked = rank_products(raw, wconf)
    return _respond(request, raw, text, ranked, source, ocr_conf, warehouse_id, wid)


@login_required
@perm_required(*_PERMS)
def ocr_details(request):
    """AJAX: the phone ranked the catalog itself and sends the ids of its best products (?ids=3,9,12) plus the text.
    The server re-scores exactly those (it never trusts a score from the phone), then answers like ocr_match_product.
    ids= (empty) is allowed: the scan is only logged as 'no match' (the dashboard lists such texts)."""
    limited = _too_many(request, 'match', RATE_MATCH)
    if limited:
        return limited
    raw, warehouse_id, wid, source, ocr_conf, wconf = _scan_params(request)
    emap = _entry_map()
    ids = []
    for part in (request.GET.get('ids') or '').split(',')[:core.CANDIDATES + 2]:
        pid = _int_or_none(part)
        if pid in emap and pid not in ids:
            ids.append(pid)
    text, ranked = core.rescore(raw, [emap[i] for i in ids], _catalog().idf, wconf)
    return _respond(request, raw, text, ranked, source, ocr_conf, warehouse_id, wid)
