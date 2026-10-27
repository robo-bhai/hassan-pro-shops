# Permission Matrix (enforced)

Users -> Permission Matrix decides what each role can do. The views enforce it with decorators.

    from ...security.permissions import perm_required      # inside views_frontend/<group>/x.py

    @login_required
    @perm_required('view_sales')                           # any-of, several keys allowed
    def sale_list(request): ...

    @perm_required('view_cash', post='manage_cash')        # GET: view_cash, POST: manage_cash

Template:  `{% load erp_filters %}{% if request.user|can:"create_sales" %}...{% endif %}`
Python:    `has_matrix_perm(user, 'edit_sales')`

## Rules
* Superuser = everything. Others = union of their role groups. Everybody logged in = `view_dashboard`.
* A role uses `ROLE_DEFAULTS` (permission_catalog.py) until the matrix is saved for it; after that the DB wins
  (even if every permission was removed).
* "Partial" in the matrix UI is display-only and is NOT enforced.
* AJAX / `/api/` requests get JSON 403, pages get a message + redirect to the dashboard.
* `settings.PERMISSION_MATRIX_MODE = 'enforce' | 'warn' | 'off'` ('warn' only logs "PERMISSION WOULD DENY").

## Adding a permission / a new view
1. Add `_p('key', ...)` to `MATRIX_MODULES` in `permission_catalog.py` (shows up in the matrix automatically).
2. Put `@perm_required('key')` on the view. A typo in a key raises at import time.
3. `python manage.py audit_permissions --missing` lists routed views that still have no decorator.

`scripts/patches/apply_perm_decorators.py` is the bulk tool that added the decorators (rules at the top).

## Deliberately NOT decorated
Shareholder portal (self-service), notifications, profile, chatbot/alert widgets, my-tasks/checklist, language,
and views that already have their own guard (backup = superuser, translations, `loan_pay`, drip/buyback self-service).
