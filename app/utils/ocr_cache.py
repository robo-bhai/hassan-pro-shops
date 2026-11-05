"""Small helpers for the OCR catalog version and the rate limit.  Django is imported lazily, so this file can be
loaded (and tested with a fake cache) without Django."""
import time

VER_KEY = 'ocr_catalog_ver'


def _default_cache():
    from django.core.cache import cache
    return cache


def catalog_version(_cache=None):
    """A tiny number that changes whenever the product catalog must be rebuilt (all server processes see it)."""
    try:
        return (_cache or _default_cache()).get(VER_KEY) or 0
    except Exception:
        return 0


def invalidate_catalog(_cache=None):
    """Call after a ProductAlias was added/removed: every process rebuilds its catalog on the next scan."""
    try:
        (_cache or _default_cache()).set(VER_KEY, time.time(), None)
    except Exception:
        pass


def rate_ok(user_id, bucket, limit, window=60, _cache=None, _now=None):
    """Fixed-window limiter. True = allowed. If the cache is down it allows (never blocks the cashier)."""
    c = _cache or _default_cache()
    slot = int((_now if _now is not None else time.time()) // window)
    key = 'ocr_rl:%s:%s:%s' % (bucket, user_id, slot)
    try:
        c.add(key, 0, window + 5)
        return c.incr(key) <= limit
    except Exception:
        return True
