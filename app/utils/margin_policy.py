"""Minimum-margin policy: which % applies to which product.

Rule: the category's own "Minimum margin %" wins when it is filled in (0 means "no minimum for this
category"); otherwise the company rule from Settings > Pricing applies; 0 / empty means no rule.

``MarginPolicy`` itself is plain Python (build it by hand in tests). Only ``load()`` reads the database
(one SystemSetting row + the few categories that have their own %), so a view loads it ONCE per request.
"""
from decimal import Decimal, InvalidOperation

COMPANY_KEY = 'min_margin_percent'     # SystemSetting key, saved by Settings > Pricing


def _norm(value):
    """Non-negative Decimal; None / blank / invalid / negative -> None for "not set"."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        pct = Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return None
    if not pct.is_finite() or pct < 0:
        return None
    return pct


class MarginPolicy:
    def __init__(self, company=None, categories=None):
        self.company = _norm(company) or Decimal('0')
        self.categories = {cid: p for cid, p in ((cid, _norm(v)) for cid, v in (categories or {}).items())
                           if p is not None}

    @classmethod
    def load(cls):
        from ..models import Category, SystemSetting
        company = SystemSetting.get_value(COMPANY_KEY, '0')
        cats = dict(Category.objects.filter(min_margin_percent__isnull=False)
                    .values_list('pk', 'min_margin_percent'))
        return cls(company, cats)

    def for_category_id(self, category_id):
        """The minimum margin % (Decimal, 0 = none) for a category id (None = uncategorised)."""
        if category_id is not None and category_id in self.categories:
            return self.categories[category_id]
        return self.company

    def for_product(self, product):
        return self.for_category_id(getattr(product, 'category_id', None))
