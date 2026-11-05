"""
OCR product matching for the Sale screen (v4).

The camera + text reading (Tesseract.js) runs in the browser. This view receives the text that was read and
returns the best matching products.  The matching itself lives in app/utils/pos/ocr_core.py (no Django, unit-tested).

URLs (add to urls.py):
    path('ajax/ocr-match-product/', views_frontend.ocr_match_product, name='ocr_match_product'),
    path('ajax/ocr-feedback/',      views_frontend.ocr_feedback,      name='ocr_feedback'),

v3 adds
    * every search is written to OcrScanLog (what was read, what was found, what the cashier did)
    * ocr_feedback: the page tells us which product was finally chosen. When the cashier CORRECTED the machine,
      the text is counted as an alias suggestion for that product. After ALIAS_AUTO_HITS confirmations it becomes a
      real ProductAlias, so the next scan of that packaging is found at once.
    * logging / learning can never break scanning: they are wrapped so a database problem only shows in the log.

v4 (speed + stock awareness)
    * the product catalog + trigram index live in server memory (rebuilt every CATALOG_TTL seconds, or at once
      when an alias is added) - no more unpickling 60,000 products from the cache on every scan
    * only names that share trigrams with the text are compared (inverted index), barcode = dict lookup
    * 3 database queries for the whole result (products, batches, stock) instead of ~4 per product
    * products that have stock in the selected warehouse get +STOCK_BOOST points (180ml in stock beats 90ml sold out)
    * rate limit per user (RATE_MATCH / RATE_FEEDBACK requests per minute) -> HTTP 429

v5 (local catalog + dashboard)
    * ocr_catalog  : the compact product list (id, name, barcode, aliases) for the phone. The phone ranks products
                     itself (static/ocr/ocr_match.js, identical to ocr_core.rank - tests/test_ocr_js_parity.py)
    * ocr_details  : the phone sends only the ids of its best products; the server re-scores them (core.rescore),
                     adds stock/price/batch, decides "confident", writes the log. Same JSON as ocr_match_product.
    * ocr_dashboard / ocr_alias_action : accuracy dashboard + one-click approve / reject of alias suggestions

Response of ocr_match_product:
    {"success": true, "confident": bool, "text": "...", "log_id": 12, "products": [ {...}, ... ]}
"""
import hashlib
import logging
import threading
import time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...security.permissions import has_matrix_perm, perm_required
from ...models import (Inventory, OcrAliasSuggestion, OcrScanLog, Product, ProductAlias, StockBatch)
from ...utils.pos import ocr_cache
from ...utils.pos import ocr_core as core

log = logging.getLogger(__name__)

# re-exported so old tuning / imports keep working
AUTO_ADD_MIN_SCORE = core.AUTO_ADD_MIN_SCORE
AUTO_ADD_MIN_GAP = core.AUTO_ADD_MIN_GAP
MIN_LIST_SCORE = core.MIN_LIST_SCORE
CATALOG_TTL = 120            # seconds the in-memory product index is reused
MAX_CATALOG = 60000
RATE_MATCH = 240             # scans per user per minute (the live camera does ~1-2 per second at most)
RATE_FEEDBACK = 120
LOG_DEDUPE_SECONDS = 10      # the live camera repeats the same text; one log row per text per user per 10 s

_normalize = core.normalize   # old names, in case other code imports them
_tokens = core.tokens
_trigrams = core.trigrams
_score = core.score

_PERMS = ('use_pos', 'create_sales', 'create_purchases', 'manage_orders')


_LOCAL = {'index': None, 'ver': None, 'built': 0.0}
_LOCK = threading.Lock()


def _build_index():
    qs = Product.objects.all()
    try:
        Product._meta.get_field('is_active')
        qs = qs.filter(is_active=True)
    except FieldDoesNotExist:
        pass

    entries = {}
    for pid, name, barcode in qs.values_list('id', 'name', 'barcode')[:MAX_CATALOG]:
        e = core.make_entry(pid, name, barcode)
        if e:
            entries[pid] = e
    try:
        for pid, alias in ProductAlias.objects.values_list('product_id', 'alias')[:MAX_CATALOG]:
            e = entries.get(pid)
            an = core.normalize(alias)
            if e and an:
                e['names'].append((alias, an, core.trigrams(an)))
    except Exception:
        log.exception('OCR: could not load product aliases')
    return core.Index(entries.values())


def _catalog():
    """The product index, kept in this server process (no pickling through the cache on every scan)."""
    ver = ocr_cache.catalog_version()
    L = _LOCAL
    if L['index'] is not None and L['ver'] == ver and time.time() - L['built'] < CATALOG_TTL:
        return L['index']
    with _LOCK:
        if L['index'] is not None and L['ver'] == ver and time.time() - L['built'] < CATALOG_TTL:
            return L['index']
        try:
            idx = _build_index()
        except Exception:
            if L['index'] is not None:          # database hiccup: keep serving the old index
                log.exception('OCR: catalog rebuild failed, using the old one')
                return L['index']
            raise
        L['index'], L['ver'], L['built'] = idx, ver, time.time()
        return idx


def _entry_map():
    """{product_id: catalog entry} of the in-memory index (rebuilt only when the index itself is rebuilt)."""
    idx = _catalog()
    if _LOCAL.get('map_for') is not idx:
        _LOCAL['map'] = {e['id']: e for e in idx.entries}
        _LOCAL['map_for'] = idx
    return _LOCAL['map']


def rank_products(raw_text):
    """-> (cleaned_text, [(score, catalog_entry), ...] best first). No database access except a rebuild every 2 min."""
    return core.rank(raw_text, _catalog())


def _load_batches(product_ids, warehouse_id):
    """{product_id: [(batch_id, remaining, cost, selling), ...]} oldest first - ONE query for all products."""
    qs = StockBatch.objects.filter(product_id__in=product_ids, remaining_qty__gt=0)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    out = {}
    for bid, pid, rem, price, sp in qs.order_by('id').values_list('id', 'product_id', 'remaining_qty', 'price',
                                                                    'selling_price'):
        out.setdefault(pid, []).append((bid, rem, price, sp))
    return out


def _load_stock(product_ids, warehouse_id):
    """{product_id: Inventory.stock} in the warehouse - ONE query."""
    out = {}
    if not warehouse_id:
        return out
    for pid, stock in Inventory.objects.filter(product_id__in=product_ids, warehouse_id=warehouse_id) \
            .order_by('id').values_list('product_id', 'stock'):
        out.setdefault(pid, stock)                 # first row wins, like the old .first()
    return out


def _payload_from(product, batches, inv_stock, warehouse_id):
    """Same fields as search_products_ajax / the old _payload, built from rows that are already loaded."""
    b = core.batch_summary(batches, inv_stock, bool(warehouse_id))
    sp = b['selling_price']
    lb = b['latest_batch_price']
    has_sp = sp > 0
    return {
        'id': product.id,
        'name': product.name,
        'barcode': product.barcode or '',
        'serial_no': product.serial_no or '',
        'price': str(sp if has_sp else 0),
        'cost_price': str(lb if lb > 0 else float(product.price or 0)),
        'stock': b['stock'],
        'unit': product.unit.name if getattr(product, 'unit', None) else '',
        'has_selling_price': has_sp,
        'warning': b['warning'],
        'selling_price': str(sp if has_sp else 0),
        'batch_count': b['batch_count'],
        'latest_batch_price': str(lb if lb > 0 else 0),
        'batch_remaining_qty': str(b['batch_remaining']),
        'batch_id': b['batch_id'],
    }


def _payload(product, warehouse_id):
    """Single product (kept for old callers). The scan view uses the batched loaders instead."""
    wid = _int_or_none(warehouse_id)
    return _payload_from(product, _load_batches([product.id], wid).get(product.id, []),
                         _load_stock([product.id], wid).get(product.id), wid)


# ------------------------------------------------------------------ logging
def _int_or_none(v, lo=None, hi=None):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if lo is not None and n < lo:
        return None
    if hi is not None and n > hi:
        return None
    return n


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


def _too_many(request, bucket, limit):
    if ocr_cache.rate_ok(request.user.id, bucket, limit):
        return None
    return JsonResponse({'success': False, 'message': 'Too many scans. Wait a few seconds.'}, status=429)


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
    return raw, warehouse_id, _int_or_none(warehouse_id), source, _int_or_none(request.GET.get('conf'), 0, 100)


@login_required
@perm_required(*_PERMS)
def ocr_match_product(request):
    """AJAX: text read by the camera (OCR) -> best matching products. (The server ranks; used until the phone has
    its local catalog, and as the fallback.)"""
    limited = _too_many(request, 'match', RATE_MATCH)
    if limited:
        return limited
    raw, warehouse_id, wid, source, ocr_conf = _scan_params(request)
    text, ranked = rank_products(raw)
    return _respond(request, raw, text, ranked, source, ocr_conf, warehouse_id, wid)


@login_required
@perm_required(*_PERMS)
def ocr_catalog(request):
    """AJAX: compact product list for the phone's local matcher.  ?ver=<what the phone has>  -> {"unchanged": true}
    when nothing changed.  Items: [id, name, barcode_digits, [aliases]].  Built from the in-memory index (no DB)."""
    idx = _catalog()
    ver = '%s-%d' % (int(ocr_cache.catalog_version() or 0), len(idx.entries))
    if request.GET.get('ver') == ver:
        return JsonResponse({'unchanged': True, 'ver': ver})
    items = [[e['id'], e['names'][0][0], e['barcode'], [n[0] for n in e['names'][1:]]] for e in idx.entries]
    return JsonResponse({'ver': ver, 'count': len(items), 'items': items})


@login_required
@perm_required(*_PERMS)
def ocr_details(request):
    """AJAX: the phone ranked the catalog itself and sends the ids of its best products (?ids=3,9,12) plus the text.
    The server re-scores exactly those (it never trusts a score from the phone), then answers like ocr_match_product.
    ids= (empty) is allowed: the scan is only logged as 'no match' (the dashboard lists such texts)."""
    limited = _too_many(request, 'match', RATE_MATCH)
    if limited:
        return limited
    raw, warehouse_id, wid, source, ocr_conf = _scan_params(request)
    emap = _entry_map()
    ids = []
    for part in (request.GET.get('ids') or '').split(',')[:core.CANDIDATES + 2]:
        pid = _int_or_none(part)
        if pid in emap and pid not in ids:
            ids.append(pid)
    text, ranked = core.rescore(raw, [emap[i] for i in ids])
    return _respond(request, raw, text, ranked, source, ocr_conf, warehouse_id, wid)


# ------------------------------------------------------------------ learning
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


# ------------------------------------------------------------------ dashboard
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


def _has_perm(user, key):
    try:
        return bool(has_matrix_perm(user, key))
    except Exception:
        return bool(user.is_superuser)


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
