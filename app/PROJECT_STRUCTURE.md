# app/ — folder layout

| Folder | Contents |
|---|---|
| `models/`, `views_frontend/`, `admin/` | unchanged |
| `views_modules/` | views_admin_otp, views_bi, views_customer_auth, views_customer_portal, views_delivery, views_document, views_loan, views_order_tracking, views_security, views_subscription, views_testing |
| `ai/` | ai_board_room, ai_cash_engine, ai_cso_tech, ai_engine, ai_operations_engine, ai_purchase_planner, ai_shareholder_engine, chatbot_engine, business_ratios |
| `ledger/` | posting, posting_core, posting_gaps, posting_step5, posting_stock, subledger, signals_gl, tests_posting_core |
| `store/` | store_access, store_accounting, store_exports, store_issue_service, store_ops_service, store_receive, store_transfer_service |
| `security/` | security_utils, decorators, signals_security |
| `middleware/` | middleware, module_access, security_2fa |
| `config/` | context_processors, custom_storage |
| `i18n/` | i18n_default, i18n_lang, i18n_service |
| `module_config/` | module_catalog, settings_catalog |
| `testing_qa/` | auto_tester |
| `backup/` | backup_service |
| `utils/` | chat_email_helper (was root email_helper), whatsapp_utils, certificate_utils, barcode_utils, bi, email_helper, security |
| `_backups/` | all .bak / .bad files (not imported) |
| `docs/` | logo_setup.md |

Kept at the root (Django needs them there): `apps.py, urls.py, views.py, forms.py, tests.py, signals.py`

## settings.py paths that changed
- `app.middleware.X` -> `app.middleware.middleware.X`
- `app.module_access.ModuleAccessMiddleware` -> `app.middleware.module_access.ModuleAccessMiddleware`
- `app.security_2fa.TwoFactorMiddleware` -> `app.middleware.security_2fa.TwoFactorMiddleware`
- `app.context_processors.X` -> `app.config.context_processors.X`
- `app.custom_storage.X` -> `app.config.custom_storage.X`
