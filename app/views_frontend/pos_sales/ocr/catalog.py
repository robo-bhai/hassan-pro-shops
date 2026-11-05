"""The product catalog the OCR search ranks against: an in-memory trigram index + the phone's local copy."""
import logging
import threading
import time

from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist
from django.http import JsonResponse

from ....models import Product, ProductAlias
from ....security.permissions import perm_required
from ....utils.pos import ocr_cache
from ....utils.pos import ocr_core as core
from .config import CATALOG_TTL, MAX_CATALOG, _PERMS

log = logging.getLogger(__name__)

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


def rank_products(raw_text, wconf=None):
    """-> (cleaned_text, [(score, catalog_entry), ...] best first). No database access except a rebuild every 2 min.
    wconf = {word: camera confidence} the page sent (optional)."""
    return core.rank(raw_text, _catalog(), wconf)


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
