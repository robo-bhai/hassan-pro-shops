"""Models package: split from the former single models.py.

Every model is re-exported here, so `from .models import X` and
`from .models import *` keep working and no migration changes.
"""
from importlib import import_module as _im

_MODULES = [
    "core",
    "budgeting",
    "accounting",
    "catalog",
    "purchasing",
    "sales",
    "hr",
    "production",
    "shareholders",
    "services",
    "audit_qa",
    "supply_chain",
    "security",
    "bi",
    "documents",
    "ai_ops",
    "customer_portal",
    "delivery",
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
