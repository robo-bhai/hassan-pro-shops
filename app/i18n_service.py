"""Translation Manager logic: keys, dictionary, missing-text capture and auto-translation."""
import html
import json
import os
import re
import threading
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, F, Max, Q
from django.utils import timezone

LANG_NAMES = {'ur': 'Urdu', 'ar': 'Arabic'}
PROVIDER_LABELS = {
    'anthropic': 'Claude (Anthropic)',
    'google': 'Google Cloud Translation',
    'mymemory': 'MyMemory (free, basic quality)',
}
_TRAIL = ' :.\u2026!?*'
_VALID = re.compile(r"^[A-Za-z][A-Za-z0-9 &'\u2019()/.,:+\-%?!#]*$")


# ---------------------------------------------------------------- keys
def norm_text(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def clean_source(s):
    """Visible text without leading emoji/symbols and trailing ':' '...' '?' (same rule as the browser)."""
    s = norm_text(s)
    s = re.sub(r'^[^\w(]+', '', s)
    return s.rstrip(_TRAIL).strip()


def make_key(s):
    return clean_source(s).lower()[:300]


def qualifies(s):
    """Only short, plain UI-style English text may be recorded as 'missing' (never names/data/long text)."""
    if not isinstance(s, str):
        return False
    t = clean_source(s)
    if not (2 <= len(t) <= 100) or not _VALID.match(t):
        return False
    if len(t.split()) > 7 or any(c.isdigit() for c in t):      # numbers = data (invoice no, phone...), not a label
        return False
    return True


# ---------------------------------------------------------------- dictionary
def ensure_seeded():
    from .models import Translation
    if not Translation.objects.exists():
        seed_defaults()


def seed_defaults():
    from .i18n_default import DEFAULTS
    from .models import Translation
    existing = set(Translation.objects.values_list('key', flat=True))
    new = []
    for en, ur, ar in DEFAULTS:
        k = make_key(en)
        if not k or k in existing:
            continue
        existing.add(k)
        new.append(Translation(key=k, source=clean_source(en) or en, ur=ur, ar=ar,
                               ur_status='default', ar_status='default'))
    Translation.objects.bulk_create(new, batch_size=200)
    return len(new)


def get_version():
    from .models import Translation
    agg = Translation.objects.aggregate(m=Max('updated_at'), n=Count('id'))
    m = agg['m']
    return '%s-%s' % (int(m.timestamp()) if m else 0, agg['n'])


def build_dictionary_json():
    from .models import Translation
    ensure_seeded()
    out = {}
    for key, ur, ar in Translation.objects.exclude(ur='', ar='').values_list('key', 'ur', 'ar'):
        out[key] = [ur, ar]
    return json.dumps(out, ensure_ascii=False, separators=(',', ':'))


# ---------------------------------------------------------------- missing capture
def record_missing(items):
    from .models import Translation
    now = timezone.now()
    added = 0
    for raw in list(items)[:100]:
        if not qualifies(raw):
            continue
        key = make_key(raw)
        obj, created = Translation.objects.get_or_create(
            key=key, defaults={'source': clean_source(raw), 'seen_count': 1, 'last_seen': now})
        if created:
            added += 1
        else:
            Translation.objects.filter(pk=obj.pk).update(seen_count=F('seen_count') + 1, last_seen=now)
    return added


def pending_count():
    from .models import Translation
    return Translation.objects.filter(Q(ur='') | Q(ar='')).count()


# ---------------------------------------------------------------- providers
def _conf(name):
    return getattr(settings, name, None) or os.environ.get(name, '')


def active_provider():
    p = (_conf('I18N_PROVIDER') or 'auto').lower()
    if p == 'auto':
        if _conf('ANTHROPIC_API_KEY'):
            return 'anthropic'
        if _conf('GOOGLE_TRANSLATE_API_KEY'):
            return 'google'
        return 'mymemory'
    return p


def _http_json(url, payload=None, headers=None, timeout=25):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    hdrs = {'Content-Type': 'application/json'}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _json_array(text):
    a, b = text.find('['), text.rfind(']')
    if a < 0 or b < a:
        raise ValueError('no JSON array in reply')
    arr = json.loads(text[a:b + 1])
    if not isinstance(arr, list):
        raise ValueError('reply is not a list')
    return [str(x) for x in arr]


def _tr_anthropic(texts, lang):
    key = _conf('ANTHROPIC_API_KEY')
    model = _conf('I18N_CLAUDE_MODEL') or 'claude-haiku-5-5'
    prompt = (
        'Translate these short UI labels of a business ERP (shop/factory, accounting, inventory, HR) '
        'from English to %s. Use concise, formal wording suited to menus and buttons. Keep abbreviations '
        '(GRN, PO, POS, KPI, CEO, API, PDF) and numbers/symbols as they are, or use the common local form. '
        'Return ONLY a JSON array of strings, same order and same length as the input.\n\n%s'
        % (LANG_NAMES[lang], json.dumps(texts, ensure_ascii=False)))
    resp = _http_json('https://api.anthropic.com/v1/messages',
                      {'model': model, 'max_tokens': 4000, 'messages': [{'role': 'user', 'content': prompt}]},
                      {'x-api-key': key, 'anthropic-version': '2023-06-01'})
    text = ''.join(b.get('text', '') for b in resp.get('content', []) if isinstance(b, dict))
    out = _json_array(text)
    if len(out) != len(texts):
        raise ValueError('translator returned %d items for %d' % (len(out), len(texts)))
    return out


def _tr_google(texts, lang):
    key = _conf('GOOGLE_TRANSLATE_API_KEY')
    resp = _http_json('https://translation.googleapis.com/language/translate/v2?key=' + urllib.parse.quote(key),
                      {'q': texts, 'source': 'en', 'target': lang, 'format': 'text'})
    items = resp['data']['translations']
    if len(items) != len(texts):
        raise ValueError('translator returned %d items for %d' % (len(items), len(texts)))
    return [html.unescape(i.get('translatedText', '')) for i in items]


def _tr_mymemory(texts, lang):
    out = []
    for t in texts:
        url = 'https://api.mymemory.translated.net/get?q=%s&langpair=en|%s' % (urllib.parse.quote(t), lang)
        resp = _http_json(url)
        txt = (resp.get('responseData') or {}).get('translatedText', '')
        if resp.get('responseStatus') not in (200, '200') or 'MYMEMORY WARNING' in txt.upper():
            raise ValueError('MyMemory limit/error: %s' % (txt or resp.get('responseDetails', ''))[:120])
        out.append(html.unescape(txt))
    return out


def translate_batch(provider, texts, lang):
    fn = {'anthropic': _tr_anthropic, 'google': _tr_google, 'mymemory': _tr_mymemory}.get(provider)
    if not fn:
        raise ValueError('unknown provider %r' % provider)
    return fn(texts, lang)


def translate_pending(limit=40):
    """Fill empty Urdu/Arabic cells with machine translation (status 'auto'). Never touches filled cells."""
    from .models import Translation
    provider = active_provider()
    rows = list(Translation.objects.filter(Q(ur='') | Q(ar='')).order_by('-seen_count', 'id')[:limit])
    done, error = 0, ''
    for lang in ('ur', 'ar'):
        todo = [r for r in rows if not getattr(r, lang)]
        for i in range(0, len(todo), 40):
            chunk = todo[i:i + 40]
            try:
                res = translate_batch(provider, [r.source for r in chunk], lang)
            except Exception as e:                       # network / quota / bad reply: stop, report
                error = ('%s: %s' % (provider, e))[:300]
                break
            for r, t in zip(chunk, res):
                t = (t or '').strip()
                if not t:
                    continue
                done += Translation.objects.filter(pk=r.pk, **{lang: ''}).update(
                    **{lang: t, lang + '_status': 'auto', 'updated_at': timezone.now()})
        if error:
            break
    cache.set('i18n_last_error', error, 86400)
    cache.set('i18n_last_run', timezone.now().isoformat(timespec='seconds'), 86400)
    return {'translated': done, 'error': error, 'provider': provider, 'pending': pending_count()}


# ---------------------------------------------------------------- automatic (background) run
def auto_enabled():
    from .models import SystemSetting
    return SystemSetting.get_bool('i18n_auto_translate', False)


def _background():
    from django.db import connection
    try:
        translate_pending(40)
    except Exception as e:
        cache.set('i18n_last_error', str(e)[:300], 86400)
    finally:
        connection.close()


def maybe_start_background():
    """Called when new missing text was captured: translate it in the background (throttled, 1 run / 5 min)."""
    try:
        if auto_enabled() and cache.add('i18n_bg_lock', 1, 300):
            threading.Thread(target=_background, daemon=True).start()
            return True
    except Exception:
        pass
    return False
