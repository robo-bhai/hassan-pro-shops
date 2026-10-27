"""Models package: split from the former single models.py.

Every model is re-exported here, so `from .models import X` and
`from .models import *` keep working and no migration changes.
"""
from importlib import import_module as _im

_MODULES = [
    "system.core",
    "finance.budgeting",
    "finance.accounting",
    "inventory.catalog",
    "trade.vendors",
    "trade.purchase_orders",
    "trade.purchases",
    "trade.purchase_returns",
    "trade.monthly_plans",
    "trade.customers",
    "trade.sales",
    "trade.sale_orders",
    "trade.sale_returns",
    "trade.installments",
    "trade.targets",
    "people.hr",
    "inventory.production",
    "people.shareholders",
    "people.shares",
    "people.dividends",
    "people.cash",
    "people.drip",
    "people.discounts",
    "people.loans",
    "trade.services",
    "system.audit_qa",
    "trade.supply_chain",
    "system.security",
    "ai_bi.bi",
    "system.documents",
    "ai_bi.insights",
    "ai_bi.operations",
    "ai_bi.purchase_ai",
    "ai_bi.board",
    "ai_bi.cash_ai",
    "ai_bi.shareholder_ai",
    "ai_bi.cso_tech",
    "trade.customer_portal",
    "trade.delivery",
    "inventory.store_issue",
    "inventory.store_ops",
    "inventory.store_transfer",
    "trade.pos_shift",
    "system.translation",
    "finance.gl_posting",
    "inventory.agri",
]

_ns = {}
for _m in _MODULES:
    _mod = _im(f"{__name__}.{_m}")
    for _k, _v in vars(_mod).items():
        if _k.startswith("_"):
            continue
        if getattr(_v, "__module__", None) == _mod.__name__:
            _ns[_k] = _v
    globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("_")})

# Models that only refer to each other inside methods (runtime) are shared here,
# after everything is loaded, so there are no circular imports between files.
for _m in _MODULES:
    _d = vars(_im(f"{__name__}.{_m}"))
    for _k, _v in _ns.items():
        _d.setdefault(_k, _v)

del _im, _m, _mod, _k, _v, _d
