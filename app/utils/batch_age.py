"""Batch age / dead-stock helpers (pure Python, no Django import - easy to test).

Age of a batch = days since its purchase date. A batch is "slow-moving" when it is
still in stock (remaining > 0) and at least STALE_DAYS old.
"""
from datetime import date, datetime, timedelta

STALE_DAYS = 90          # "90 din se purana aur abhi bhi stock mein"
STOCK_EPS = 0.0001       # remaining <= this counts as sold out (float rounding)


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def age_days(purchase_date, today):
    """Whole days between the purchase date and today. None if the date is unknown; never negative."""
    p, t = _as_date(purchase_date), _as_date(today)
    if p is None or t is None:
        return None
    return max((t - p).days, 0)


def is_slow_moving(purchase_date, remaining_qty, today, stale_days=STALE_DAYS):
    """True when the batch is in stock and at least `stale_days` old."""
    if remaining_qty is None or remaining_qty <= STOCK_EPS:
        return False
    a = age_days(purchase_date, today)
    return a is not None and a >= stale_days


def stale_cutoff(today, stale_days=STALE_DAYS):
    """Batches bought on/before this date are slow-moving (use in a DB filter)."""
    return _as_date(today) - timedelta(days=stale_days)
