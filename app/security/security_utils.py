"""Small security helpers shared by the views and models.

Put this file next to models/ and views_frontend/ (the app folder).
"""
import logging
import re
import secrets
import string

from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger("app.security")

GENERIC_ERROR = "Something went wrong. Please try again."


# ---------------------------------------------------------------- errors ----
def safe_error(exc, default=GENERIC_ERROR):
    """Log the real exception, return a message that is safe to show to a user.

    Django ValidationError messages are written for users, so they are passed through;
    everything else (database errors, file paths, stack details...) is hidden.
    """
    logger.error("Handled error: %r", exc, exc_info=exc)
    if isinstance(exc, ValidationError):
        return "; ".join(exc.messages)
    return default


# ------------------------------------------------------------ rate limits ----
def client_ip(request):
    # REMOTE_ADDR on purpose: X-Forwarded-For can be forged by the client.
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _key(request, scope, extra, per_ip):
    ip = client_ip(request) if per_ip else "*"
    return f"rl:{scope}:{ip}:{(extra or '').lower()[:80]}"


def failures(request, scope, extra="", per_ip=True):
    return cache.get(_key(request, scope, extra, per_ip), 0)


def blocked(request, scope, limit, extra="", per_ip=True):
    """True when `limit` or more failures were already recorded in the current window."""
    return failures(request, scope, extra, per_ip) >= limit


def register_failure(request, scope, extra="", per_ip=True, window=900):
    key = _key(request, scope, extra, per_ip)
    cache.add(key, 0, window)          # creates the counter with its expiry
    try:
        cache.incr(key)
    except ValueError:                 # counter expired between add() and incr()
        cache.set(key, 1, window)


def clear_failures(request, scope, extra="", per_ip=True):
    cache.delete(_key(request, scope, extra, per_ip))


# ----------------------------------------------------------------- phones ----
def phone_digits(value):
    return re.sub(r"\D", "", value or "")


def phones_match(a, b):
    """Compare the last 10 digits; an empty / too short number never matches."""
    da, db = phone_digits(a), phone_digits(b)
    return len(da) >= 7 and len(db) >= 7 and da[-10:] == db[-10:]


# -------------------------------------------------------------- passwords ----
def generate_password(length=12):
    """Random password with at least one lower-case, upper-case letter and digit."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw
