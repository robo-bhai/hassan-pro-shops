"""Permission matrix catalogue  (single source of truth).

Pure data, no Django imports, so it can be imported from anywhere (views, decorators,
templatetags, tests, management commands) without circular imports.

* ``MATRIX_MODULES``   - the groups / rows shown in the Permission Matrix screen.
* ``MATRIX_KEYS``      - every valid permission key (whitelist for the matrix save API).
* ``ROLE_DEFAULTS``    - (full, partial) keys per built-in role, used until someone saves the matrix.
* ``BASIC_KEYS``       - keys every logged-in user always has (so nobody is locked out of the dashboard).

Adding a new permission: add a ``_p(...)`` row below, then use ``@perm_required('your_key')`` on the view.
(A new key shows up in the matrix by itself; nothing else to register, no migration needed.)
"""


def _p(key, name, icon, description):
    return {'key': key, 'name': name, 'icon': icon, 'description': description}


MATRIX_MODULES = [
    {'key': 'dashboard', 'name': '📊 Dashboard', 'permissions': [
        _p('view_dashboard', 'View Dashboard', 'bi-speedometer2', 'Access main dashboard'),
        _p('view_reports', 'View Reports', 'bi-graph-up', 'View all reports'),
        _p('view_analytics', 'View Analytics', 'bi-bar-chart', 'View business analytics'),
        _p('export_reports', 'Export Reports', 'bi-download', 'Export / print reports (PDF, Excel)'),
    ]},
    {'key': 'sales', 'name': '🛒 Sales', 'permissions': [
        _p('view_sales', 'View Sales', 'bi-eye', 'View sales list'),
        _p('create_sales', 'Create Sales', 'bi-plus-circle', 'Create new sales'),
        _p('edit_sales', 'Edit Sales', 'bi-pencil', 'Edit existing sales'),
        _p('delete_sales', 'Delete Sales', 'bi-trash', 'Delete sales records'),
        _p('manage_orders', 'Manage Orders', 'bi-cart', 'Manage sale orders & challans'),
        _p('manage_targets', 'Manage Sales Targets', 'bi-bullseye', 'Set and view sales targets'),
    ]},
    {'key': 'pos', 'name': '🧾 POS & Shifts', 'permissions': [
        _p('use_pos', 'Use POS', 'bi-upc-scan', 'Open POS and sell at the counter'),
        _p('manage_shifts', 'Manage Cashier Shifts', 'bi-clock-history', 'Open / close cashier shifts'),
    ]},
    {'key': 'returns', 'name': '↩️ Returns', 'permissions': [
        _p('view_returns', 'View Returns', 'bi-eye', 'View sale / purchase returns'),
        _p('create_returns', 'Create Returns', 'bi-arrow-return-left', 'Create sale / purchase returns'),
        _p('approve_returns', 'Approve Returns', 'bi-check-circle', 'Approve or post returns'),
        _p('delete_returns', 'Delete Returns', 'bi-trash', 'Delete returns'),
    ]},
    {'key': 'installments', 'name': '🗓️ Installments & Services', 'permissions': [
        _p('view_installments', 'View Installments', 'bi-eye', 'View installment plans'),
        _p('manage_installments', 'Manage Installments', 'bi-gear', 'Create plans and collect installments'),
        _p('view_services', 'View Services', 'bi-eye', 'View service jobs'),
        _p('manage_services', 'Manage Services', 'bi-tools', 'Create and manage service jobs'),
    ]},
    {'key': 'purchase', 'name': '📥 Purchase', 'permissions': [
        _p('view_purchases', 'View Purchases', 'bi-eye', 'View purchase list'),
        _p('create_purchases', 'Create Purchases', 'bi-plus-circle', 'Create new purchases'),
        _p('edit_purchases', 'Edit Purchases', 'bi-pencil', 'Edit existing purchases'),
        _p('delete_purchases', 'Delete Purchases', 'bi-trash', 'Delete purchase records'),
        _p('approve_purchases', 'Approve Purchases', 'bi-check-circle', 'Approve purchase orders'),
        _p('manage_purchase_orders', 'Manage Purchase Orders', 'bi-file-earmark-text', 'PO, GRN and monthly plans'),
        _p('manage_supply_chain', 'Manage Supply Chain', 'bi-truck', 'Supply chain and PO Pro tools'),
    ]},
    {'key': 'inventory', 'name': '📦 Inventory', 'permissions': [
        _p('view_inventory', 'View Inventory', 'bi-eye', 'View inventory list'),
        _p('manage_inventory', 'Manage Inventory', 'bi-gear', 'Manage inventory items'),
        _p('manage_stock', 'Manage Stock', 'bi-box-seam', 'Manage stock levels'),
        _p('receive_goods', 'Receive Goods', 'bi-arrow-down-circle', 'Receive incoming goods'),
        _p('dispatch_goods', 'Dispatch Goods', 'bi-arrow-up-circle', 'Dispatch outgoing goods'),
        _p('view_production', 'View Production', 'bi-eye', 'View production / BOM'),
        _p('manage_production', 'Manage Production', 'bi-diagram-3', 'Create and run production orders'),
    ]},
    {'key': 'customers', 'name': '👥 Customers', 'permissions': [
        _p('view_customers', 'View Customers', 'bi-eye', 'View customer list'),
        _p('create_customers', 'Create Customers', 'bi-person-plus', 'Create new customers'),
        _p('edit_customers', 'Edit Customers', 'bi-pencil', 'Edit customer details'),
        _p('delete_customers', 'Delete Customers', 'bi-trash', 'Delete customers'),
    ]},
    {'key': 'vendors', 'name': '🏢 Vendors', 'permissions': [
        _p('view_vendors', 'View Vendors', 'bi-eye', 'View vendor list'),
        _p('create_vendors', 'Create Vendors', 'bi-building-add', 'Create new vendors'),
        _p('edit_vendors', 'Edit Vendors', 'bi-pencil', 'Edit vendor details'),
        _p('delete_vendors', 'Delete Vendors', 'bi-trash', 'Delete vendors'),
    ]},
    {'key': 'finance', 'name': '💰 Finance', 'permissions': [
        _p('view_financials', 'View Financials', 'bi-eye', 'View financial data'),
        _p('edit_financials', 'Edit Financials', 'bi-pencil', 'Edit financial records'),
        _p('manage_payments', 'Manage Payments', 'bi-credit-card', 'Manage payments'),
        _p('manage_budget', 'Manage Budget', 'bi-wallet', 'Manage budgets and goals'),
        _p('view_expenses', 'View Expenses', 'bi-receipt', 'View expenses'),
        _p('manage_expenses', 'Manage Expenses', 'bi-receipt-cutoff', 'Add / edit / delete expenses'),
        _p('view_cash', 'View Cash Book', 'bi-eye', 'View cash book and balances'),
        _p('manage_cash', 'Manage Cash', 'bi-cash-coin', 'Cash in / out entries'),
        _p('view_accounting', 'View Accounting', 'bi-journal-text', 'View ledgers, trial balance, subledger'),
        _p('manage_accounting', 'Manage Accounting', 'bi-journal-check', 'Journal entries, accounts, posting'),
        _p('manage_closing', 'Manage Period Closing', 'bi-lock', 'Day / month / year closing'),
        _p('view_loans', 'View Loans', 'bi-eye', 'View loans given / taken'),
        _p('manage_loans', 'Manage Loans', 'bi-bank', 'Create loans and record payments'),
        _p('view_profit', 'View Profit Analysis', 'bi-graph-up-arrow', 'See profit and margins'),
    ]},
    {'key': 'shareholders', 'name': '🤝 Shareholders', 'permissions': [
        _p('view_shareholders', 'View Shareholders', 'bi-eye', 'View shareholders, certificates, meetings'),
        _p('manage_shareholders', 'Manage Shareholders', 'bi-people', 'Create / edit shareholders, certificates, meetings, terms'),
        _p('manage_share_transfers', 'Manage Share Transfers', 'bi-arrow-left-right', 'Process share transfers'),
        _p('manage_dividends', 'Manage Dividends', 'bi-piggy-bank', 'Declare and pay dividends'),
        _p('manage_shareholder_cash', 'Manage Shareholder Cash', 'bi-cash-stack', 'Cash balances, requests and deductions'),
    ]},
    {'key': 'hr', 'name': '👔 HR', 'permissions': [
        _p('view_employees', 'View Employees', 'bi-eye', 'View employee list'),
        _p('manage_employees', 'Manage Employees', 'bi-gear', 'Manage employees'),
        _p('manage_attendance', 'Manage Attendance', 'bi-calendar-check', 'Manage attendance'),
        _p('manage_payroll', 'Manage Payroll', 'bi-wallet', 'Manage payroll'),
        _p('manage_leaves', 'Manage Leaves', 'bi-file-spreadsheet', 'Manage leave requests'),
    ]},
    {'key': 'warehouse', 'name': '🏭 Warehouse', 'permissions': [
        _p('view_warehouse', 'View Warehouse', 'bi-eye', 'View warehouse details'),
        _p('manage_warehouse', 'Manage Warehouse', 'bi-gear', 'Manage warehouses'),
        _p('manage_transfers', 'Manage Transfers', 'bi-arrow-left-right', 'Manage stock transfers'),
        _p('manage_store_issue', 'Manage Store Issue', 'bi-box-arrow-up', 'Issue stock from stores'),
        _p('manage_store_ops', 'Manage Store Operations', 'bi-clipboard-check', 'Stock counts and store operations'),
        _p('view_products', 'View Products', 'bi-box', 'View products'),
        _p('manage_products', 'Manage Products', 'bi-box-seam', 'Create / edit / delete products and categories'),
    ]},
    {'key': 'ai', 'name': '🤖 AI & Insights', 'permissions': [
        _p('use_ai', 'Use AI Insights', 'bi-stars', 'AI insights, purchase planner, chatbot'),
        _p('manage_ai_ops', 'Manage AI Operations', 'bi-cpu', 'AI operations, cash AI and shareholder AI'),
        _p('view_board_room', 'View Board Room', 'bi-person-workspace', 'Board room / CSO dashboards'),
    ]},
    {'key': 'documents', 'name': '🗂️ Documents & BI', 'permissions': [
        _p('view_documents', 'View Documents', 'bi-eye', 'View and download documents'),
        _p('manage_documents', 'Manage Documents', 'bi-folder-plus', 'Upload and delete documents'),
    ]},
    {'key': 'users', 'name': '👥 Users', 'permissions': [
        _p('view_users', 'View Users', 'bi-eye', 'View user list'),
        _p('manage_users', 'Manage Users', 'bi-gear', 'Manage users'),
        _p('create_users', 'Create Users', 'bi-person-plus', 'Create new users'),
        _p('delete_users', 'Delete Users', 'bi-trash', 'Delete users'),
        _p('manage_roles', 'Manage Roles', 'bi-shield', 'Manage roles and permissions'),
    ]},
    {'key': 'settings', 'name': '⚙️ Settings', 'permissions': [
        _p('view_settings', 'View Settings', 'bi-eye', 'View system settings'),
        _p('edit_settings', 'Edit Settings', 'bi-pencil', 'Edit system settings'),
        _p('manage_company', 'Manage Company', 'bi-building', 'Manage company settings'),
        _p('manage_system', 'Manage System', 'bi-gear', 'System management'),
        _p('view_audit_log', 'View Audit Log', 'bi-shield-check', 'View audit trail and access logs'),
    ]},
]

MATRIX_KEYS = {p['key'] for m in MATRIX_MODULES for p in m['permissions']}
ALL_KEYS = [p['key'] for m in MATRIX_MODULES for p in m['permissions']]

# Every logged-in user always has these (otherwise a role-less user could not even open the home page).
BASIC_KEYS = frozenset({'view_dashboard'})

# Stored in a group's permissions once the matrix was saved for it. Lets an Administrator
# take *everything* away from a role (an empty set is otherwise indistinguishable from
# "never saved" and would silently fall back to the defaults).
SAVED_SENTINEL = '_matrix_saved'


def _view_keys():
    return [k for k in ALL_KEYS if k.startswith(('view_', 'use_'))]


_ALL_NON_ADMIN = [k for k in ALL_KEYS if k not in (
    'manage_system', 'manage_roles', 'delete_users', 'create_users', 'manage_users', 'manage_company',
    'edit_settings', 'manage_closing')]

# Default (full, partial) permissions per role, used until someone saves the matrix.
# "partial" is display-only in the UI (limited access): it is NOT enforced as granted.
ROLE_DEFAULTS = {
    'owner': (list(ALL_KEYS), []),
    'manager': (
        [k for k in _ALL_NON_ADMIN if k not in ('manage_payroll',)] + ['manage_closing'],
        ['manage_users', 'manage_payroll'],
    ),
    'salesman': (
        ['view_dashboard', 'view_sales', 'create_sales', 'edit_sales', 'manage_orders', 'use_pos',
         'manage_shifts', 'view_customers', 'create_customers', 'edit_customers', 'view_products',
         'view_inventory', 'view_returns', 'create_returns', 'view_installments', 'manage_installments',
         'view_services', 'manage_services', 'manage_targets', 'view_documents'],
        ['delete_sales', 'approve_returns'],
    ),
    'accountant': (
        ['view_dashboard', 'view_reports', 'view_analytics', 'export_reports', 'view_financials',
         'edit_financials', 'manage_payments', 'view_expenses', 'manage_expenses', 'manage_budget',
         'view_cash', 'manage_cash', 'view_accounting', 'manage_accounting', 'view_loans', 'manage_loans',
         'view_profit', 'view_documents', 'view_sales', 'view_purchases', 'view_customers', 'view_vendors',
         'view_returns', 'view_installments', 'view_employees', 'manage_payroll', 'view_shareholders',
         'view_audit_log', 'use_ai'],
        ['manage_closing', 'manage_dividends'],
    ),
    'warehouse': (
        ['view_dashboard', 'view_inventory', 'manage_inventory', 'manage_stock', 'receive_goods',
         'dispatch_goods', 'view_products', 'manage_products', 'view_warehouse', 'manage_warehouse',
         'manage_transfers', 'manage_store_issue', 'manage_store_ops', 'view_documents', 'view_purchases',
         'manage_purchase_orders', 'view_production', 'view_vendors'],
        ['manage_orders', 'view_sales', 'manage_production'],
    ),
}
