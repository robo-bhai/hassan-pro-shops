"""Agri Edition: pure helpers (no Django import, so they can be tested anywhere).

tests/test_agri_pure.py loads this file directly.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ZERO = Decimal('0.00')
CREDIT_MODES = ('block', 'warn', 'off')


def parse_date(raw):
    """'' -> (True, None) (clear). Bad text -> (False, None)."""
    raw = (raw or '').strip()
    if not raw:
        return True, None
    try:
        return True, datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return False, None


def to_dec(raw, default=ZERO):
    try:
        d = Decimal(str(raw).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return default
    return d if d.is_finite() else default


def expiry_status(exp, today):
    """(status, days). status: none / expired / d30 / d60 / d90 / ok."""
    if exp is None:
        return 'none', None
    days = (exp - today).days
    if days < 0:
        return 'expired', days
    if days <= 30:
        return 'd30', days
    if days <= 60:
        return 'd60', days
    if days <= 90:
        return 'd90', days
    return 'ok', days


def wa_number(raw):
    """Pakistani mobile -> wa.me number (923xxxxxxxxx). '' if there are no digits."""
    d = re.sub(r'\D', '', raw or '')
    if not d:
        return ''
    if d.startswith('00'):
        d = d[2:]
    if d.startswith('0'):
        d = '92' + d[1:]
    elif len(d) == 10 and d.startswith('3'):
        d = '92' + d
    return d


def credit_mode(raw):
    raw = (raw or 'block').strip().lower()
    return raw if raw in CREDIT_MODES else 'block'


def credit_decision(limit, outstanding, new_credit, mode='block'):
    """Should a sale that leaves `new_credit` unpaid be allowed?

    limit 0 / None = no limit for this customer.
    Returns (action, message): action is 'ok', 'warn' or 'block'.
    """
    limit = to_dec(limit)
    outstanding = max(to_dec(outstanding), ZERO)
    new_credit = max(to_dec(new_credit), ZERO)
    mode = credit_mode(mode)
    if mode == 'off' or limit <= 0 or new_credit <= 0:
        return 'ok', ''
    after = outstanding + new_credit
    if after <= limit:
        return 'ok', ''
    msg = ('Credit limit Rs. %s hai. Pehle ka baqaya Rs. %s + is bill ka udhaar Rs. %s = Rs. %s, '
           'yani Rs. %s zyada.' % (_money(limit), _money(outstanding), _money(new_credit),
                                  _money(after), _money(after - limit)))
    return ('warn' if mode == 'warn' else 'block'), msg


def _money(v):
    return format(int(Decimal(v).quantize(Decimal('1'))), ',')
