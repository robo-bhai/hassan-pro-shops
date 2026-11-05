# app/module_config/settings_catalog.py
"""
ONE SINGLE LIST OF ALL PROJECT SETTINGS (single source of truth).

Settings Center (/settings/center/) builds tabs and form fields from this list.
To add a new setting, just write one field here; no need to change the view/template.

Tab keys:
  key, label, icon, desc : tab ka naam aur tafseel
  access   : 'superuser' | 'admin' (superuser ya staff) | 'owner' (superuser, Owner ya CEO)
  store    : where the data is saved ('system' | 'security' | 'delivery' | 'company' | None)
  fields   : generic fields (neeche)
  special  : a special part that is not built by the generic form ('modules' | 'city_charges' | 'logo' | 'voice')
  links    : [(label, url_name)] - tab ke neeche quick buttons

Field keys:
  name, label, type, default, help, group
  type   : bool | int | decimal | text | textarea | email | url | select
  min/max: limits for int/decimal
  choices: for select [(value, label), ...]
  prefix/suffix: input ke aage/peeche ka text (Rs., %, Days ...)
  required: if True it cannot be empty

NOTE ('system' store): SystemSetting.set_value lowercases the value, so in this store
keep only bool / number / select (lowercase values). Use a dedicated model for free text.
"""

TABS = [
    # ------------------------------------------------------------------ Modules
    {
        'key': 'modules', 'label': 'Modules', 'icon': 'bi-toggles',
        'desc': 'Business mode and the Shop / Factory switch for each module',
        'access': 'superuser', 'store': 'system', 'special': 'modules',
        'fields': [
            {'name': 'business_mode', 'label': 'Business Mode', 'type': 'select', 'default': 'both',
             'choices': [('both', 'Both (Shop + Factory)'), ('shop', 'Shop only'), ('factory', 'Factory only')],
             'help': 'In Shop mode the Shop switches apply, in Factory mode the Factory ones, and in Both the module shows if any is ON.',
             'group': 'Business Mode'},
        ],
    },
    # ------------------------------------------------------- Shareholders / Dividends
    {
        'key': 'shareholders', 'label': 'Shareholders', 'icon': 'bi-people',
        'desc': 'Purchase deduction and dividend rules',
        'access': 'superuser', 'store': 'system',
        'links': [('Bulk Process Deductions', 'bulk_process_deductions'),
                  ('Deduction Report', 'shareholder_deduction_report')],
        'fields': [
            {'name': 'enable_shareholder_purchase_deduction', 'label': 'Purchase par shareholder deduction', 'type': 'bool',
             'default': True, 'group': 'Purchase Deduction',
             'help': 'If ON, the purchase amount is deducted from the shareholders cash balance.'},
            {'name': 'shareholder_deduction_type', 'label': 'Deduction Type', 'type': 'select', 'default': 'proportional',
             'choices': [('proportional', 'Proportional (by balance)'), ('equal', 'Equal (same for everyone)')],
             'group': 'Purchase Deduction',
             'help': 'Proportional: the higher the balance, the higher the deduction. Equal: same for everyone.'},

            {'name': 'enable_balance_dividend', 'label': 'Balance-based dividend', 'type': 'bool',
             'default': True, 'group': 'Dividends',
             'help': 'When turned OFF, the balance-based dividend options are disabled.'},
            {'name': 'default_dividend_type', 'label': 'Default Dividend Type', 'type': 'select', 'default': 'both',
             'choices': [('share', 'Share-based'), ('balance', 'Balance-based'), ('both', 'Both (admin chune)')],
             'group': 'Dividends'},
            {'name': 'default_dividend_percentage', 'label': 'Default Dividend Percentage', 'type': 'decimal',
             'default': '50', 'min': 1, 'max': 100, 'suffix': '%', 'group': 'Dividends',
             'help': 'How much of the profit goes into the dividend.'},
            {'name': 'min_balance_for_dividend', 'label': 'Minimum Balance Used', 'type': 'decimal',
             'default': '0', 'min': 0, 'prefix': 'Rs.', 'group': 'Eligibility',
             'help': '0 = sab shareholders eligible.'},
            {'name': 'min_holding_months', 'label': 'Minimum Holding Period', 'type': 'int',
             'default': '0', 'min': 0, 'max': 60, 'suffix': 'Months', 'group': 'Eligibility',
             'help': '0 = no condition.'},
            {'name': 'auto_process_days', 'label': 'Auto-Process After', 'type': 'int',
             'default': '7', 'min': 0, 'max': 30, 'suffix': 'Days', 'group': 'Eligibility',
             'help': 'The dividend is processed automatically this many days after declaring (0 = manual only).'},
        ],
    },
    # ------------------------------------------------------------------ Company
    {
        'key': 'company', 'label': 'Company', 'icon': 'bi-building',
        'desc': 'Naam, contact, logo aur deposit payment details',
        'access': 'owner', 'store': 'company', 'special': 'logo',
        'fields': [
            {'name': 'name', 'label': 'Company Name', 'type': 'text', 'required': True, 'group': 'Basic Information', 'max_len': 255},
            {'name': 'email', 'label': 'Email', 'type': 'email', 'required': True, 'group': 'Basic Information'},
            {'name': 'contact_number', 'label': 'Phone', 'type': 'text', 'required': True, 'group': 'Basic Information', 'max_len': 50},
            {'name': 'website', 'label': 'Website', 'type': 'url', 'group': 'Basic Information'},
            {'name': 'address', 'label': 'Address', 'type': 'textarea', 'required': True, 'group': 'Basic Information', 'wide': True},
            {'name': 'tagline', 'label': 'Tagline', 'type': 'text', 'group': 'Basic Information', 'max_len': 255, 'wide': True},
            {'name': 'footer_note', 'label': 'Footer Note (reports)', 'type': 'text', 'group': 'Basic Information', 'max_len': 255, 'wide': True},

            {'name': 'jazzcash_number', 'label': 'JazzCash Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 20},
            {'name': 'easypaisa_number', 'label': 'EasyPaisa Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 20},
            {'name': 'bank_name', 'label': 'Bank Name', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 100},
            {'name': 'bank_account_title', 'label': 'Account Title', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 200},
            {'name': 'bank_account_number', 'label': 'Account Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 50},
            {'name': 'deposit_instructions', 'label': 'Deposit Instructions', 'type': 'textarea', 'group': 'Deposit Payments', 'wide': True},
        ],
    },
    # ----------------------------------------------------------------- Delivery
    {
        'key': 'delivery', 'label': 'Delivery', 'icon': 'bi-truck',
        'desc': 'Delivery charges, express, pickup aur city-wise rates',
        'access': 'admin', 'store': 'delivery', 'special': 'city_charges',
        'fields': [
            {'name': 'standard_charge', 'label': 'Standard Charge', 'type': 'decimal', 'default': '100.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Standard Delivery'},
            {'name': 'standard_delivery_time', 'label': 'Standard Delivery Time', 'type': 'text', 'default': '2-4 working days',
             'required': True, 'max_len': 100, 'group': 'Standard Delivery'},

            {'name': 'express_delivery_enabled', 'label': 'Express Delivery on', 'type': 'bool', 'default': True, 'group': 'Express Delivery'},
            {'name': 'express_charge', 'label': 'Express Charge', 'type': 'decimal', 'default': '300.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Express Delivery'},
            {'name': 'express_delivery_time', 'label': 'Express Delivery Time', 'type': 'text', 'default': 'Same day (within city)',
             'required': True, 'max_len': 100, 'group': 'Express Delivery'},

            {'name': 'store_pickup_enabled', 'label': 'Store Pickup on', 'type': 'bool', 'default': True, 'group': 'Pickup & Free Delivery'},
            {'name': 'free_delivery_enabled', 'label': 'Free Delivery on', 'type': 'bool', 'default': True, 'group': 'Pickup & Free Delivery'},
            {'name': 'free_delivery_threshold', 'label': 'Free Delivery Threshold', 'type': 'decimal', 'default': '1000.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Pickup & Free Delivery', 'help': 'Delivery is free on orders above this amount.'},
        ],
    },
    # ----------------------------------------------------------------- Security
    {
        'key': 'security', 'label': 'Security', 'icon': 'bi-shield-lock',
        'desc': 'Login, password, IP, API aur alerts',
        'access': 'superuser', 'store': 'security',
        'fields': [
            {'name': 'enable_2fa', 'label': 'Two-Factor Authentication', 'type': 'bool', 'default': False, 'group': 'Login & Session'},
            {'name': 'enable_auto_logout', 'label': 'Auto logout', 'type': 'bool', 'default': True, 'group': 'Login & Session'},
            {'name': 'max_login_attempts', 'label': 'Max Login Attempts', 'type': 'int', 'default': '5', 'min': 1, 'max': 20, 'group': 'Login & Session'},
            {'name': 'lockout_time', 'label': 'Lockout Time', 'type': 'int', 'default': '30', 'min': 1, 'max': 1440, 'suffix': 'Min', 'group': 'Login & Session'},
            {'name': 'session_timeout', 'label': 'Session Timeout', 'type': 'int', 'default': '60', 'min': 1, 'max': 1440, 'suffix': 'Min', 'group': 'Login & Session'},

            {'name': 'min_password_length', 'label': 'Min Password Length', 'type': 'int', 'default': '8', 'min': 4, 'max': 64, 'group': 'Password Policy'},
            {'name': 'password_expiry_days', 'label': 'Password Expiry', 'type': 'int', 'default': '90', 'min': 0, 'max': 730, 'suffix': 'Days', 'group': 'Password Policy', 'help': '0 = never expires.'},
            {'name': 'password_history_count', 'label': 'Password History', 'type': 'int', 'default': '5', 'min': 0, 'max': 24, 'group': 'Password Policy'},
            {'name': 'require_uppercase', 'label': 'Uppercase zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_lowercase', 'label': 'Lowercase zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_numbers', 'label': 'Number zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_special_chars', 'label': 'Special character zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'prevent_password_reuse', 'label': 'Prevent reusing an old password', 'type': 'bool', 'default': True, 'group': 'Password Policy'},

            {'name': 'enable_ip_whitelist', 'label': 'IP Whitelist', 'type': 'bool', 'default': False, 'group': 'Access Control'},
            {'name': 'enable_ip_blacklist', 'label': 'IP Blacklist', 'type': 'bool', 'default': True, 'group': 'Access Control'},
            {'name': 'enable_api_auth', 'label': 'API Authentication', 'type': 'bool', 'default': True, 'group': 'Access Control'},
            {'name': 'api_rate_limit', 'label': 'API Rate Limit', 'type': 'int', 'default': '100', 'min': 1, 'max': 100000, 'suffix': '/min', 'group': 'Access Control'},

            {'name': 'enable_security_alerts', 'label': 'Security Alerts', 'type': 'bool', 'default': True, 'group': 'Alerts'},
            {'name': 'alert_email', 'label': 'Alert Email', 'type': 'email', 'group': 'Alerts'},
            {'name': 'alert_whatsapp', 'label': 'Alert WhatsApp', 'type': 'text', 'max_len': 20, 'group': 'Alerts'},
        ],
    },
    # -------------------------------------------------------------------- Voice
    {
        'key': 'voice', 'label': 'Voice', 'icon': 'bi-megaphone',
        'desc': 'Voice announcements',
        'access': 'any', 'store': None, 'special': 'voice', 'fields': [],
        'links': [('Voice Announcement Settings kholein', 'voice_announcement_settings')],
    },
]

TAB_BY_KEY = {t['key']: t for t in TABS}
