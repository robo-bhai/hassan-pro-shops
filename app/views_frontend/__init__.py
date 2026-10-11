"""Frontend views package (split from the former single views_frontend.py).

Every view is re-exported here, so `views_frontend.some_view` in urls.py keeps working.
"""
import types as _types
from importlib import import_module as _im

_MODULES = [
    "dashboard",
    "purchasing",
    "shareholder_portal",
    "shareholders",
    "dividends",
    "masters_api",
    "cash",
    "reports",
    "sales",
    "closing",
    "hr",
    "warehouses",
    "returns",
    "production",
    "products",
    "users",
    "notifications",
    "installments",
    "backup",
    "shareholder_cash",
    "loans",
    "services",
    "expenses_budget",
    "audit",
    "supply_chain",
    "accounting",
    "ai_ops",
    "chat",
]
_CONSTANTS = ['ROLE_GROUPS', 'ROLE_ICONS']

_mods = [_im(f"{__name__}.{_m}") for _m in _MODULES]
_shared = {}
for _mod in _mods:
    for _k, _v in vars(_mod).items():
        if (isinstance(_v, _types.FunctionType) and _v.__module__ == _mod.__name__) or _k in _CONSTANTS:
            _shared[_k] = _v

# Views call each other (and share constants) at runtime: make every name visible in every file,
# without top-level imports between them, so there are no circular imports.
for _mod in _mods:
    _d = vars(_mod)
    for _k, _v in _shared.items():
        _d.setdefault(_k, _v)

globals().update(_shared)
del _types, _im, _mod, _k, _v, _d
