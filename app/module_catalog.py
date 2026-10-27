# app/module_catalog.py
"""
ONE single list of all switchable modules (single source of truth).

3 things run from this list:
  1. The Shop/Factory switch of each module in the Module Settings page (settings/modules/)
  2. Template flags: SHOW_<KEY>_MODULE aur MODULE_VISIBLE.<key>   (context_processors.py)
  3. URL block jab module off ho                                  (module_access.py)

To add a new module, just add one entry here.

  key       : short name (settings key: show_<key>_module, mode_shop_<key>, mode_factory_<key>)
  shop/factory : default for the first time (before saving). All are True: until you turn a switch off yourself,
                 no module is hidden.
  prefixes  : the starting parts of the URL of that module (from urls.py)
"""

MODULE_GROUPS = ['Operations', 'Finance', 'Shareholders', 'People & Communication',
                 'Insights & Control', 'System', 'New Modules']

MODULE_CATALOG = [
    # ---------------- Operations ----------------
    {'key': 'production', 'group': 'Operations', 'label': 'Production', 'icon': 'bi-gear',
     'description': 'Production Orders, BOM, Operations', 'shop': True, 'factory': True,
     'prefixes': ['/production/']},
    {'key': 'inventory', 'group': 'Operations', 'label': 'Inventory', 'icon': 'bi-box',
     'description': 'Stock, Products, Batches, Warehouses, Transfers', 'shop': True, 'factory': True,
     'prefixes': ['/inventory/', '/products/', '/warehouses/', '/batches/', '/transfers/']},
    {'key': 'store_issue', 'group': 'Operations', 'label': 'Stores & Issue', 'icon': 'bi-buildings',
     'description': 'PMS, RMS, FGS, Technical stores and internal stock issue', 'shop': True, 'factory': True,
     'prefixes': ['/stores/', '/store-issue/', '/store-transfer/', '/store-receipts/', '/store-request/', '/store-count/', '/store-return/']},
    {'key': 'purchase', 'group': 'Operations', 'label': 'Purchase', 'icon': 'bi-cart-plus',
     'description': 'Purchases, Purchase Orders, GRN, Vendors, Returns', 'shop': True, 'factory': True,
     'prefixes': ['/purchases/', '/orders/purchase/', '/grn/', '/vendors/', '/returns/purchase/']},
    {'key': 'sales', 'group': 'Operations', 'label': 'Sales', 'icon': 'bi-cart-check',
     'description': 'Sales, Sale Orders, Challans, Customers, Discounts, Order Tracking, Returns', 'shop': True, 'factory': True,
     'prefixes': ['/sales/', '/challans/', '/orders/sale/', '/customers/', '/discounts/', '/order-tracking/', '/returns/sale/']},
    {'key': 'installment', 'group': 'Operations', 'label': 'Installments', 'icon': 'bi-calendar',
     'description': 'Installment Plans, EMI Payments', 'shop': True, 'factory': True,
     'prefixes': ['/installments/', '/installment/', '/plans/']},
    {'key': 'supply_chain', 'group': 'Operations', 'label': 'Supply Chain', 'icon': 'bi-truck',
     'description': 'Suppliers, supply chain tracking', 'shop': True, 'factory': True,
     'prefixes': ['/supply-chain/']},
    {'key': 'services', 'group': 'Operations', 'label': 'Services', 'icon': 'bi-tools',
     'description': 'Services, Service Requests, Appointments', 'shop': True, 'factory': True,
     'prefixes': ['/services/', '/service-requests/', '/appointments/']},
    {'key': 'operations', 'group': 'Operations', 'label': 'Operations Center', 'icon': 'bi-kanban',
     'description': 'Operations management and AI operation insights', 'shop': True, 'factory': True,
     'prefixes': ['/operations/']},

    # ---------------- Finance ----------------
    {'key': 'accounts', 'group': 'Finance', 'label': 'Accounts', 'icon': 'bi-calculator',
     'description': 'Chart of accounts, Journal, Expenses, Daily Closing', 'shop': True, 'factory': True,
     'prefixes': ['/accounts/', '/expenses/', '/daily-closing/']},
    {'key': 'cash', 'group': 'Finance', 'label': 'Cash Management', 'icon': 'bi-cash-coin',
     'description': 'Cash in/out, opening balance, cash report', 'shop': True, 'factory': True,
     'prefixes': ['/cash/']},
    {'key': 'loans', 'group': 'Finance', 'label': 'Loans', 'icon': 'bi-bank',
     'description': 'Loans taken, Loans given, Loan returns', 'shop': True, 'factory': True,
     'prefixes': ['/loans/', '/loans-given/', '/loan-returns/']},
    {'key': 'budgets', 'group': 'Finance', 'label': 'Budgets & Projects', 'icon': 'bi-pie-chart',
     'description': 'Budgets, Monthly Planner, Projects', 'shop': True, 'factory': True,
     'prefixes': ['/budgets/', '/monthly-planner/', '/projects/']},

    # ---------------- Shareholders ----------------
    {'key': 'shareholders', 'group': 'Shareholders', 'label': 'Shareholders', 'icon': 'bi-people',
     'description': 'Shareholders, Shares, Prices, Requests, Buyback, Certificates, Meetings, Cash Strategies',
     'shop': True, 'factory': True,
     'prefixes': ['/shareholders/', '/shareholder/', '/shareholder-requests/', '/shares/', '/prices/',
                  '/buyback/', '/certificate/', '/certificates/', '/meetings/', '/cash-strategies/',
                  '/strategy-allocations/', '/investor/']},
    {'key': 'dividends', 'group': 'Shareholders', 'label': 'Dividends', 'icon': 'bi-coin',
     'description': 'Dividends, Balance-based dividend, Payments, DRIP', 'shop': True, 'factory': True,
     'prefixes': ['/dividends/', '/dividend-payment/', '/dividend-allocation/', '/balance-dividend/', '/drip/']},

    # ---------------- People & Communication ----------------
    {'key': 'hr', 'group': 'People & Communication', 'label': 'HR Management', 'icon': 'bi-person-badge',
     'description': 'Employees, Departments, Attendance, Payroll, Leaves, Salary Slips', 'shop': True, 'factory': True,
     'prefixes': ['/hr/', '/departments/']},
    {'key': 'whatsapp', 'group': 'People & Communication', 'label': 'WhatsApp', 'icon': 'bi-whatsapp',
     'description': 'Messages, Reminders, Bulk Messaging', 'shop': True, 'factory': True,
     'prefixes': ['/whatsapp/']},

    # ---------------- Insights & Control ----------------
    {'key': 'reports', 'group': 'Insights & Control', 'label': 'Reports', 'icon': 'bi-graph-up',
     'description': 'All Reports (50+ Reports)', 'shop': True, 'factory': True,
     'prefixes': ['/reports/']},
    {'key': 'bi', 'group': 'Insights & Control', 'label': 'Business Intelligence', 'icon': 'bi-bar-chart-line',
     'description': 'BI dashboards and analytics', 'shop': True, 'factory': True,
     'prefixes': ['/bi/']},
    {'key': 'ai', 'group': 'Insights & Control', 'label': 'AI Insights', 'icon': 'bi-stars',
     'description': 'AI dashboard, analysis and insights', 'shop': True, 'factory': True,
     'prefixes': ['/ai/']},
    {'key': 'audit', 'group': 'Insights & Control', 'label': 'Audit & Controls', 'icon': 'bi-shield-check',
     'description': 'Audit plans, findings, internal controls', 'shop': True, 'factory': True,
     'prefixes': ['/audit/']},

    # ---------------- System ----------------
    {'key': 'documents', 'group': 'System', 'label': 'Documents & Terms', 'icon': 'bi-file-earmark-text',
     'description': 'Document library, Terms & conditions', 'shop': True, 'factory': True,
     'prefixes': ['/documents/', '/terms/']},
    {'key': 'testing', 'group': 'System', 'label': 'Testing / QA', 'icon': 'bi-bug',
     'description': 'Auto tests, bugs, test cases, plans, reports', 'shop': True, 'factory': True,
     'prefixes': ['/testing/']},
    {'key': 'backup', 'group': 'System', 'label': 'Database Backup', 'icon': 'bi-hdd-stack',
     'description': 'Backup, Restore, Cloud Sync', 'shop': True, 'factory': True,
     'prefixes': ['/backup/', '/database-backup/']},
]

# These always work (no switch): login, dashboard, profile, users, settings (Module Settings),
# security, notifications, admin chat, OTP, permission matrix, online shop (/shop/), /ajax/, /api/.
ALWAYS_ON_NOTE = 'Login, Dashboard, Users, Settings, Security, Notifications, Online Shop'


# ----------------------------------------------------------------------------
# STORE-WISE MODULES
# Members of a Store team (PMS / RMS / FGS / Technical ...) get in the sidebar and in the URL
# ONLY the modules that are allowed for that store.
#   * It comes from the default store type (below) and can be changed per store in admin
#     (Store Profiles -> "Allowed modules").
#   * If a user is in the team of several stores, the modules of all those stores are combined (union).
#   * It makes no difference for superusers and users who are not in the team of any named store.
# Dashboard, Profile, Password and Logout are always available.
# ----------------------------------------------------------------------------
STORE_TYPE_MODULES = {
    'PMS':  ['inventory', 'store_issue', 'purchase', 'supply_chain', 'reports'],
    'RMS':  ['inventory', 'store_issue', 'purchase', 'supply_chain', 'production', 'reports'],
    'FGS':  ['inventory', 'store_issue', 'sales', 'production', 'reports'],
    'TECH': ['inventory', 'store_issue', 'purchase', 'services', 'reports'],
    'GEN':  ['inventory', 'store_issue', 'reports'],
}

# URLs without a module that are closed for store users (admin / configuration pages).
STORE_USER_BLOCKED_PREFIXES = ['/users/', '/settings/', '/permission-matrix/', '/stores/access/', '/stores/profiles/', '/stores/settings/',
                               '/api/permission-matrix/']

STORE_MODULE_CHOICES = [(m['key'], m['label']) for m in MODULE_CATALOG]   # only static (old name)


# ----------------------------------------------------------------------------
# AUTO-DETECT: a new module appears by itself (no need to write a catalog entry by hand)
#   A new top-level URL part in urls.py (like /targets/) that is not in the catalog or ALWAYS_ON,
#   appears by itself in the "New Modules" group (default: both Shop + Factory ON).
#   The Module Settings page, the sidebar link and the "module closed" URL block all work from this.
#   If you want a better name/icon/group, add a manual entry to MODULE_CATALOG later.
# ----------------------------------------------------------------------------
ALWAYS_ON_SEGMENTS = {
    '', 'login', 'logout', 'admin', 'admin-chat', 'api', 'ajax', 'shop', 'settings', 'security', 'users',
    'otp-management', 'notifications', 'change-password', 'profile', 'permission-matrix', 'register',
    'verify-order-token', 'track-order', 'my-order', 'static', 'media', 'i18n', 'favicon.ico',
    'robots.txt', 'dashboard', 'set-language', '__debug__', 'accounts-login',
}
_AUTO_CACHE = None


def _discover_auto_modules():
    import re
    from django.urls import URLPattern, URLResolver, get_resolver

    static_prefixes = [p for m in MODULE_CATALOG for p in m['prefixes']] + list(STORE_USER_BLOCKED_PREFIXES)
    routes = []

    def walk(patterns, base):
        for pat in patterns:
            route = base + str(pat.pattern).lstrip('^')
            if isinstance(pat, URLResolver):
                walk(pat.url_patterns, route)
            elif isinstance(pat, URLPattern):
                routes.append(route.rstrip('$'))

    walk(get_resolver().url_patterns, '')

    segs = {}
    for r in routes:
        seg = r.split('/')[0]
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', seg or ''):
            continue
        segs.setdefault(seg, []).append(r)

    found = []
    for seg, rs in sorted(segs.items()):
        if seg in ALWAYS_ON_SEGMENTS:
            continue
        if any(('/' + r).startswith(p) for r in rs for p in static_prefixes):
            continue                                   # this segment has a route in the catalog
        plain = [r for r in rs if not re.search(r'[<(\[]', r)]
        home = '/' + (min(plain, key=len) if plain else seg + '/')
        slug = seg.replace('-', '_')
        found.append({
            'key': 'auto_' + slug, 'group': 'New Modules',
            'label': seg.replace('-', ' ').replace('_', ' ').title(), 'icon': 'bi-puzzle',
            'description': 'Naya module (khud detect hua): /%s/' % seg,
            'shop': True, 'factory': True, 'prefixes': ['/%s/' % seg], 'auto': True, 'home': home,
        })
    return found


def get_module_catalog():
    """Static MODULE_CATALOG + automatically detected new modules. Built after the URLs are loaded for the first time."""
    global _AUTO_CACHE
    if _AUTO_CACHE is None:
        try:
            _AUTO_CACHE = _discover_auto_modules()
        except Exception:                               # URLs are not loaded yet: return a static list, it will be tried again
            return list(MODULE_CATALOG)
    return list(MODULE_CATALOG) + _AUTO_CACHE


def get_module_keys():
    return [m['key'] for m in get_module_catalog()]


def get_store_module_choices():
    return [(m['key'], m['label']) for m in get_module_catalog()]


# ----------------------------------------------------------------------------
# STORE TYPE -> BUSINESS UNIT (which company type it is for)
#   shop    : visible only in Shop mode
#   factory : visible only in Factory mode
#   both    : visible in both (or all stores when business_mode = both)
# Can be changed for each store from admin (Store Profiles -> Business unit).
# Business mode is set in Module Settings (shop / factory / both).
# ----------------------------------------------------------------------------
BUSINESS_UNITS = [('shop', 'Shop'), ('factory', 'Factory'), ('both', 'Shop + Factory')]
STORE_TYPE_UNITS = {
    'PMS':  'factory',   # Packing Material Store
    'RMS':  'factory',   # Raw Material Store
    'FGS':  'both',      # Finished Goods Store - it makes goods for the factory and also sells for the shop
    'TECH': 'both',      # Technical Store
    'GEN':  'both',      # General Store
}
