"""Frontend views package (split from the former single views_frontend.py).

Every view is re-exported here, so `views_frontend.some_view` in urls.py keeps working.
"""
import types as _types
from importlib import import_module as _im

_MODULES = [
    "system.dashboard",
    "purchase.purchases",
    "purchase.vendor_reports",
    "purchase.vendors",
    "purchase.purchase_orders",
    "purchase.grn",
    "purchase.monthly_plans",
    "purchase.po_pro",
    "shareholder.shareholder_portal",
    "shareholder.certificates",
    "shareholder.shareholders",
    "shareholder.share_transfers",
    "shareholder.meetings",
    "shareholder.terms",
    "shareholder.support_tickets",
    "shareholder.registration_requests",
    "shareholder.dividends",
    "system.masters_api",
    "finance.cash",
    "system.reports",
    "pos_sales.sales",
    "finance.closing",
    "people.hr",
    "inventory.warehouses",
    "pos_sales.returns",
    "inventory.production",
    "inventory.products",
    "people.users",
    "system.notifications",
    "pos_sales.installments",
    "system.backup",
    "shareholder.cash_balances",
    "shareholder.cash_requests",
    "shareholder.cash_deductions",
    "shareholder.cash_reports",
    "finance.loans",
    "pos_sales.services",
    "finance.expenses",
    "finance.budgets",
    "finance.expense_masters",
    "finance.budget_goals",
    "finance.self_expenses",
    "system.audit",
    "purchase.supply_chain",
    "finance.accounting",
    "ai.ai_insights",
    "ai.operations",
    "ai.ai_purchasing",
    "ai.cash_ai",
    "ai.shareholder_ai",
    "ai.board_cso",
    "system.chat",
    "inventory.store_issue",
    "inventory.store_transfer",
    "inventory.store_ops",
    "system.language",
    "system.translations",
    "finance.profit_analysis",
    "finance.subledger"
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
