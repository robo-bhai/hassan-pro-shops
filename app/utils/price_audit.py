"""Price history helpers.

The functions that decide *what* to record are pure Python (no Django needed, so they can be
tested with `python -I tests/test_price_audit_pure.py`). Only `record()` touches the database.
"""
import uuid
from decimal import Decimal

CENT = Decimal('0.01')


def new_run_id():
    """One id for every row written by a single bulk apply."""
    return uuid.uuid4()


def client_ip(request):
    """Best-effort client IP (works behind one proxy). None if unknown."""
    if request is None:
        return None
    fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR')
    return ip or None


def user_label(user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return ''
    full = (user.get_full_name() or '').strip() if hasattr(user, 'get_full_name') else ''
    return full or user.get_username()


def _dec(value):
    if value is None:
        return None
    return Decimal(str(value)).quantize(CENT)


def is_real_change(old, new):
    """True only if the stored 2-dp value really differs (so we never log a no-op)."""
    return _dec(old) != _dec(new)


def build_entry(*, price_field, source, old, new, product=None, batch=None, cost=None,
                user=None, ip=None, run_id=None, rule=None, reason=''):
    """Keyword arguments for one PriceChangeLog row (a plain dict)."""
    return {
        'price_field': price_field,
        'source': source,
        'product': product,
        'batch': batch,
        'product_name': (getattr(product, 'name', '') or '')[:100],
        'batch_ref': f'#{batch.pk}' if batch is not None and batch.pk else '',
        'old_value': _dec(old),
        'new_value': _dec(new),
        'cost_price': _dec(cost),
        'run_id': run_id,
        'rule': rule,
        'reason': (reason or '')[:255],
        'changed_by': user if getattr(user, 'is_authenticated', False) else None,
        'changed_by_name': user_label(user),
        'ip_address': ip,
    }


def rule_dict(mode, value, rounding, only_in_stock=True):
    """The bulk rule as stored in the log (JSON-safe)."""
    return {'mode': mode, 'value': str(value), 'rounding': rounding or 'none',
            'only_in_stock': bool(only_in_stock)}


def record(entries):
    """Write entries (list of dicts from build_entry) in ONE query. Call inside the same
    transaction.atomic() block as the price change, so a price can never change without a log row."""
    if not entries:
        return []
    from ..models import PriceChangeLog
    return PriceChangeLog.objects.bulk_create([PriceChangeLog(**e) for e in entries])
