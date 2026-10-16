# app/module_catalog.py
"""
Saare switchable modules ki EK hi list (single source of truth).

Isi list se 3 cheezein chalti hain:
  1. Module Settings page (settings/modules/) me har module ke Shop/Factory switch
  2. Template flags: SHOW_<KEY>_MODULE aur MODULE_VISIBLE.<key>   (context_processors.py)
  3. URL block jab module off ho                                  (module_access.py)

Naya module add karna ho to sirf yahan ek entry add karein.

  key       : chhota naam (settings key: show_<key>_module, mode_shop_<key>, mode_factory_<key>)
  shop/factory : pehli baar (save se pehle) default. Sab True hain: jab tak aap khud switch off
                 na karein koi module hidden nahi hota.
  prefixes  : us module ke URL ke shuru ke hisse (urls.py se)
"""

MODULE_GROUPS = ['Operations', 'Finance', 'Shareholders', 'People & Communication',
                 'Insights & Control', 'System']

MODULE_CATALOG = [
    # ---------------- Operations ----------------
    {'key': 'production', 'group': 'Operations', 'label': 'Production', 'icon': 'bi-gear',
     'description': 'Production Orders, BOM, Operations', 'shop': True, 'factory': True,
     'prefixes': ['/production/']},
    {'key': 'inventory', 'group': 'Operations', 'label': 'Inventory', 'icon': 'bi-box',
     'description': 'Stock, Products, Batches, Warehouses, Transfers', 'shop': True, 'factory': True,
     'prefixes': ['/inventory/', '/products/', '/warehouses/', '/batches/', '/transfers/']},
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

# Ye hamesha chalte hain (switch nahi): login, dashboard, profile, users, settings (Module Settings),
# security, notifications, admin chat, OTP, permission matrix, online shop (/shop/), /ajax/, /api/.
ALWAYS_ON_NOTE = 'Login, Dashboard, Users, Settings, Security, Notifications, Online Shop'
