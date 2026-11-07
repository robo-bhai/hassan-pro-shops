"""Lite Edition: simple Urdu-first mode for small shops (kiryana, general store, mobile shop...).

What Lite does (nothing is deleted - only visibility changes):
  * Only the everyday modules stay ON: POS/sales, customers (udhaar khata), stock, purchase,
    daily expenses/closing, cash, WhatsApp, reports, backup.
  * Everything else (shareholders, dividends, production, HR, AI, BI, budgets, loans ...) is hidden
    and its URLs are blocked by the existing ModuleAccessMiddleware.
  * The sidebar shows a short Urdu/English menu (templates/components/sidebar_lite_menu.html).
  * The dashboard shows 5 numbers (templates/index_lite.html).
  * Default language is Urdu (a user can still switch language).

Switch it on/off from the shell:
    python manage.py lite_edition on            # or: on --also installment hr
    python manage.py lite_edition off
    python manage.py lite_edition status

Shop Edition (online shop order process) lives in the same file: Settings > Modules > Edition card
(Full ERP / Lite / Shop) or `python manage.py shop_edition on|off|status`.

This file keeps Django imports lazy so the planning logic can be tested without Django.
"""

LITE_MARKER = 'lite_edition_on'            # SystemSetting row: 'true' while Lite is ON
LITE_LANG_KEY = 'lite_default_language'    # SystemSetting row: default language while Lite is ON
LITE_DEFAULT_LANG = 'ur'

# Modules that stay ON in Lite (keys of module_catalog.MODULE_CATALOG).
LITE_SHOW = ['inventory', 'purchase', 'sales', 'accounts', 'cash', 'whatsapp', 'reports', 'backup']

# Optional modules a shop may ask for on top of Lite (python manage.py lite_edition on --also installment).
LITE_OPTIONAL = ['installment', 'hr', 'loans', 'services']


def lite_plan(all_keys, also=()):
    """Split the catalog keys into (show, hide) for Lite.

    all_keys : every module key of the catalog (static + auto-detected)
    also     : extra module keys to keep ON
    Unknown keys in `also` are ignored here (the command reports them).
    """
    keep = set(LITE_SHOW) | set(also or ())
    show = [k for k in all_keys if k in keep]
    hide = [k for k in all_keys if k not in keep]
    return show, hide


def setting_keys_for(module_keys):
    """All SystemSetting keys the command touches (used to save/restore the previous state)."""
    return ['business_mode', LITE_LANG_KEY] + ['mode_shop_%s' % k for k in module_keys]


# ----------------------------------------------------------------------------
# Runtime helpers (need Django; imported lazily)
# ----------------------------------------------------------------------------
def is_lite():
    """True while Lite is ON. Cached for 60 seconds; the command clears the cache."""
    try:
        from django.core.cache import cache
        val = cache.get('lite_edition_on')
        if val is None:
            from app.models import SystemSetting
            val = SystemSetting.get_bool(LITE_MARKER, False)
            cache.set('lite_edition_on', val, 60)
        return bool(val)
    except Exception:          # DB not ready (first migrate, tests ...): behave like normal ERP
        return False


def lite_marker_on():
    """Lite state straight from the database (no cache) - used when switching."""
    from app.models import SystemSetting
    return SystemSetting.objects.filter(setting_key=LITE_MARKER).exists()


def default_language():
    """Site default language code while Lite is ON, else None (= keep the normal default)."""
    if not is_lite():
        return None
    try:
        from django.core.cache import cache
        val = cache.get('lite_default_language')
        if val is None:
            from app.models import SystemSetting
            val = SystemSetting.get_value(LITE_LANG_KEY, LITE_DEFAULT_LANG)
            cache.set('lite_default_language', val, 60)
        return val
    except Exception:
        return None


def clear_cache():
    from django.core.cache import cache
    for k in ('lite_edition_on', 'lite_default_language', 'module_visibility', 'shop_scope', 'module_roles_map'):
        cache.delete(k)


def _state_file():
    import os
    from django.conf import settings
    return os.path.join(str(settings.BASE_DIR), 'lite_edition_prev_state.json')


def _set(key, value):
    from app.models import SystemSetting
    SystemSetting.objects.update_or_create(setting_key=key, defaults={'setting_value': value})


def enable_lite(also=(), lang=LITE_DEFAULT_LANG):
    """Turn Lite ON. Returns (show, hide). Raises ValueError for a bad module/language or if already ON.
    The previous values are saved so disable_lite() can restore them."""
    import json
    from app.models import SystemSetting
    from app.module_catalog import get_module_keys

    all_keys = get_module_keys()
    also = [k for k in (also or ())]
    unknown = [k for k in also if k not in all_keys]
    if unknown:
        raise ValueError('Unknown module(s): %s' % ', '.join(unknown))
    if lang not in ('ur', 'en', 'ar'):
        raise ValueError('Unknown language: %s' % lang)
    if SystemSetting.objects.filter(setting_key=LITE_MARKER).exists():
        raise ValueError('Lite is already ON.')

    show, hide = lite_plan(all_keys, also)
    prev = {}
    for k in setting_keys_for(all_keys):
        row = SystemSetting.objects.filter(setting_key=k).first()
        prev[k] = row.setting_value if row else None
    with open(_state_file(), 'w') as fh:
        json.dump(prev, fh)
    _set('business_mode', 'shop')
    _set(LITE_LANG_KEY, lang)
    for k in hide:
        _set('mode_shop_%s' % k, 'false')
    for k in show:
        _set('mode_shop_%s' % k, 'true')
    _set(LITE_MARKER, 'true')
    clear_cache()
    return show, hide


def disable_lite():
    """Turn Lite OFF and restore the previous settings. Returns False if Lite was not ON.
    If the saved state file is gone (e.g. Docker rebuild) the Lite rows are removed, so every module is ON again."""
    import json
    import os
    from app.models import SystemSetting
    from app.module_catalog import get_module_keys

    marker = SystemSetting.objects.filter(setting_key=LITE_MARKER).first()
    if not marker:
        return False
    try:
        with open(_state_file()) as fh:
            prev = json.load(fh)
    except (OSError, ValueError):
        prev = {k: None for k in setting_keys_for(get_module_keys())}
    for k, v in prev.items():
        if v is None:
            SystemSetting.objects.filter(setting_key=k).delete()
        else:
            _set(k, v)
    marker.delete()
    try:
        os.remove(_state_file())
    except OSError:
        pass
    clear_cache()
    return True


# ----------------------------------------------------------------------------
# SHOP EDITION (online shop ka order process: sirf zaroori modules)
# Settings > Modules > Edition card mein Full ERP / Lite ke saath teesra option.
# Lite aur Shop ek waqt mein ON nahi hote: ek se doosre par jate waqt pehli edition khud restore hoti hai.
# ----------------------------------------------------------------------------
SHOP_MARKER = 'shop_edition_on'            # SystemSetting row: 'true' while Shop Edition is ON
AGRI_MARKER = 'agri_edition_on'
# Role-scoped Shop Edition: Shop applies ONLY to users of these roles (Django Groups); everybody else keeps the
# normal module settings. No role chosen = Shop for everybody (old behaviour).
SHOP_ROLES_KEY = 'shop_edition_roles'      # "salesman,warehouse"  (lower-case group names)
SHOP_SHOW_KEY = 'shop_edition_show'        # modules the Shop roles may see

# Zaroori: shop order -> SaleOrder (sales), stock (inventory), vendors (purchase), hisaab (accounts, cash)
SHOP_CORE = ['sales', 'inventory', 'purchase', 'accounts', 'cash']
# Default ON, magar "sirf zaroori" chunne par band
SHOP_OPTIONAL_ON = ['reports', 'whatsapp', 'backup']
# Checkbox ke taur par extra (python manage.py shop_edition on --also installment)
SHOP_OPTIONAL = ['installment', 'hr', 'loans', 'services']


def shop_plan(all_keys, also=(), only_core=False):
    """Catalog keys ko (show, hide) mein baantna. Shop ke liye."""
    keep = set(SHOP_CORE) | set(also or ())
    if not only_core:
        keep |= set(SHOP_OPTIONAL_ON)
    show = [k for k in all_keys if k in keep]
    hide = [k for k in all_keys if k not in keep]
    return show, hide


def shop_setting_keys_for(module_keys):
    return ['business_mode'] + ['mode_shop_%s' % k for k in module_keys]


def shop_marker_on():
    """Shop Edition ki state seedhe database se (cache ke baghair)."""
    from app.models import SystemSetting
    return SystemSetting.objects.filter(setting_key=SHOP_MARKER).exists()


def _shop_state_file():
    import os
    from django.conf import settings
    return os.path.join(str(settings.BASE_DIR), 'shop_edition_prev_state.json')


def validate_shop_also(also):
    """Unknown module par ValueError (kuch badalne se pehle check ke liye)."""
    from app.module_catalog import get_module_keys
    all_keys = get_module_keys()
    unknown = [k for k in (also or ()) if k not in all_keys]
    if unknown:
        raise ValueError('Unknown module(s): %s' % ', '.join(unknown))
    return all_keys


def enable_shop(also=(), only_core=False, roles=()):
    """Shop Edition ON. Returns (show, hide). ValueError: bura module / pehle se ON / Lite ya Agri ON.
    Pehli values save hoti hain taake disable_shop() restore kar sake."""
    import json
    from app.models import SystemSetting

    all_keys = validate_shop_also(also)
    if SystemSetting.objects.filter(setting_key=SHOP_MARKER).exists():
        raise ValueError('Shop Edition is already ON.')
    if SystemSetting.objects.filter(setting_key=LITE_MARKER).exists():
        raise ValueError('Lite Edition ON hai. Pehle usay off karein (ya Settings > Modules se Shop chunen).')
    if SystemSetting.objects.filter(setting_key=AGRI_MARKER).exists():
        raise ValueError('Agri Edition ON hai. Pehle usay off karein.')

    show, hide = shop_plan(all_keys, list(also or ()), only_core)
    roles = sorted({r.strip().lower() for r in (roles or ()) if r and r.strip()})
    if roles:
        # Role-scoped: the global module switches are NOT touched; the plan is stored and applied per user.
        _set(SHOP_ROLES_KEY, ','.join(roles))
        _set(SHOP_SHOW_KEY, ','.join(show))
        _set(SHOP_MARKER, 'true')
        clear_cache()
        return show, hide
    prev = {}
    for k in shop_setting_keys_for(all_keys):
        row = SystemSetting.objects.filter(setting_key=k).first()
        prev[k] = row.setting_value if row else None
    with open(_shop_state_file(), 'w') as fh:
        json.dump(prev, fh)
    _set('business_mode', 'shop')
    for k in hide:
        _set('mode_shop_%s' % k, 'false')
    for k in show:
        _set('mode_shop_%s' % k, 'true')
    _set(SHOP_MARKER, 'true')
    clear_cache()
    return show, hide


def disable_shop():
    """Shop Edition OFF aur pehli settings wapas. False agar ON nahi thi.
    State file na mile (jaise Docker rebuild) to rows hata di jati hain -> har module default (ON)."""
    import json
    import os
    from app.models import SystemSetting
    from app.module_catalog import get_module_keys

    marker = SystemSetting.objects.filter(setting_key=SHOP_MARKER).first()
    if not marker:
        return False
    if SystemSetting.objects.filter(setting_key=SHOP_ROLES_KEY).exclude(setting_value='').exists():
        # role-scoped Shop: nothing global was changed, so just remove the scope
        SystemSetting.objects.filter(setting_key__in=[SHOP_ROLES_KEY, SHOP_SHOW_KEY]).delete()
        marker.delete()
        clear_cache()
        return True
    try:
        with open(_shop_state_file()) as fh:
            prev = json.load(fh)
    except (OSError, ValueError):
        prev = {k: None for k in shop_setting_keys_for(get_module_keys())}
    for k, v in prev.items():
        if v is None:
            SystemSetting.objects.filter(setting_key=k).delete()
        else:
            _set(k, v)
    marker.delete()
    try:
        os.remove(_shop_state_file())
    except OSError:
        pass
    clear_cache()
    return True


def shop_roles_now():
    """Roles the Shop Edition is scoped to (lower-case list); [] = Shop is for everybody."""
    from app.models import SystemSetting
    if not shop_marker_on():
        return []
    val = SystemSetting.get_value(SHOP_ROLES_KEY, '')
    return [r for r in val.split(',') if r]


def edition_context():
    """Template context for the Edition card (Settings > Modules)."""
    from app.models import SystemSetting
    from app.module_catalog import get_module_catalog
    labels = {m['key']: m['label'] for m in get_module_catalog()}
    lite_on, shop_on = lite_marker_on(), shop_marker_on()
    return {
        'lite_on': lite_on,
        'shop_on': shop_on,
        'shop_roles': shop_roles_now(),
        'edition_roles': __import__('app.module_roles', fromlist=['list_roles']).list_roles(),
        'edition_now': 'lite' if lite_on else ('shop' if shop_on else 'full'),
        'lite_lang': SystemSetting.get_value(LITE_LANG_KEY, LITE_DEFAULT_LANG),
        'lite_optional': [{'key': k, 'label': labels.get(k, k)} for k in LITE_OPTIONAL],
        'lite_show_labels': [labels.get(k, k) for k in LITE_SHOW],
        'shop_optional': [{'key': k, 'label': labels.get(k, k)} for k in SHOP_OPTIONAL],
        'shop_core_labels': [labels.get(k, k) for k in SHOP_CORE],
        'shop_extra_labels': [labels.get(k, k) for k in SHOP_OPTIONAL_ON],
    }


def apply_edition_post(post, user=None):
    """Handle the Edition card of the settings form (Full ERP / Lite / Shop).

    Returns None when the form has no `edition` field. Otherwise (switched, level, message):
      switched=True  -> an edition was turned ON/OFF; the caller must redirect and NOT save the rest of the
                        form (it still shows the old module switches and would undo the switch).
      switched=False -> nothing switched (the Lite default language may have been updated); carry on saving.
    Lite <-> Shop: pehli edition pehle restore hoti hai, phir nayi lagti hai (original settings kabhi nahi khoti).
    """
    from app.models import SystemSetting
    edition = post.get('edition')
    if edition not in ('lite', 'full', 'shop'):
        return None
    lite_on, shop_on = lite_marker_on(), shop_marker_on()

    if edition == 'full':
        if not (lite_on or shop_on):
            return False, 'success', ''
        if lite_on:
            disable_lite()
        if shop_on:
            disable_shop()
        return True, 'success', '✅ Full ERP wapas lag gaya — pehle ki module settings restore ho gayin.'

    if edition == 'lite':
        if lite_on:
            if post.get('lang') in ('ur', 'en', 'ar'):
                SystemSetting.set_value(LITE_LANG_KEY, post['lang'], user)
                clear_cache()
            return False, 'success', ''
        if shop_on:
            disable_shop()
        try:
            enable_lite(post.getlist('also'), post.get('lang', LITE_DEFAULT_LANG))
        except ValueError as exc:
            return True, 'error', str(exc)
        return True, 'success', '✅ Lite Edition ON — sirf roz ke modules dikhaye ja rahe hain.'

    # edition == 'shop'
    roles = sorted({r.strip().lower() for r in post.getlist('shop_roles') if r.strip()})
    if shop_on:
        # Shop already ON: the roles tick-boxes may have changed
        if post.get('shop_roles_form') != '1':
            return False, 'success', ''
        current = shop_roles_now()
        if roles == sorted(current):
            return False, 'success', ''
        if current and roles:
            _set(SHOP_ROLES_KEY, ','.join(roles))
            clear_cache()
            return True, 'success', '✅ Shop Edition ab sirf in roles par lagu hai: %s.' % ', '.join(roles)
        if current and not roles:
            return True, 'error', 'Kam az kam ek role chunen. Sab ke liye Shop chahiye to pehle Full ERP lagayen, phir Shop lagayen.'
        return True, 'error', 'Shop pehle se sab par lagu hai. Role chunne ke liye pehle Full ERP lagayen, phir Shop + role chunen.'
    also = post.getlist('shop_also')
    only_core = post.get('shop_only_core') == '1'
    try:
        validate_shop_also(also)
        if SystemSetting.objects.filter(setting_key=AGRI_MARKER).exists():
            raise ValueError('Agri Edition ON hai. Pehle usay off karein.')
        if lite_on:
            disable_lite()
        enable_shop(also, only_core, roles)
    except ValueError as exc:
        return True, 'error', str(exc)
    if roles:
        return True, 'success', '✅ Shop Edition ON — sirf in roles par: %s. Baqi roles ko pehle jaisa poora menu milega.' % ', '.join(roles)
    return True, 'success', '✅ Shop Edition ON — sirf online shop order process ke modules dikhaye ja rahe hain.'


def lite_dashboard_context(today):
    """The 5 numbers of the Lite dashboard. Same formulas as the main dashboard / outstanding report."""
    from decimal import Decimal
    from django.db.models import Sum, Count, F, Value, DecimalField, OuterRef, Subquery
    from django.db.models.functions import Coalesce
    from app.models import Sale, SaleItem, Customer, Inventory, Expense

    zero = Decimal('0.00')
    dec = DecimalField(max_digits=20, decimal_places=2)

    # --- today's sales (VOID bills excluded, discount summed separately - see dashboard_view) ---
    sales = Sale.objects.filter(sale_date__date=today).exclude(returns__notes__startswith='VOID')
    agg = sales.aggregate(total=Coalesce(Sum('saleitem__total_amt', output_field=dec), Value(zero)),
                          count=Count('id', distinct=True))
    discount = sales.aggregate(d=Coalesce(Sum('discount_value'), Value(zero)))['d']
    received = sales.aggregate(p=Coalesce(Sum('paid'), Value(zero)))['p']
    profit_raw = SaleItem.objects.filter(sale__sale_date__date=today).exclude(
        sale__returns__notes__startswith='VOID').aggregate(
        t=Coalesce(Sum('profit'), Value(zero)))['t']

    # --- udhaar: customers who still owe money (same maths as customer_outstanding_report) ---
    total_sub = Sale.objects.filter(customer=OuterRef('pk')).values('customer').annotate(
        t=Sum('saleitem__total_amt', output_field=dec)).values('t')[:1]
    paid_sub = Sale.objects.filter(customer=OuterRef('pk')).values('customer').annotate(
        t=Sum('paid', output_field=dec)).values('t')[:1]
    debtors = Customer.objects.annotate(
        total_sales=Coalesce(Subquery(total_sub), Value(zero), output_field=dec),
        total_paid=Coalesce(Subquery(paid_sub), Value(zero), output_field=dec),
    ).annotate(outstanding=F('total_sales') - F('total_paid')).filter(outstanding__gt=0)
    debtors_total = debtors.aggregate(t=Coalesce(Sum('outstanding'), Value(zero)))['t']
    top_debtors = list(debtors.order_by('-outstanding')[:5])

    # --- low stock ---
    low = Inventory.objects.select_related('product', 'product__unit').filter(
        stock__lt=F('product__low_stock_threshold'))
    low_count = low.count()
    low_items = list(low.order_by('stock')[:5])

    # --- today's expenses (rejected / cancelled ignored) ---
    expense_today = Expense.objects.filter(expense_date=today).exclude(
        status__in=['rejected', 'cancelled']).aggregate(
        t=Coalesce(Sum('total_amount'), Value(zero)))['t']

    return {
        'today': today,
        'today_sales': agg['total'],
        'today_count': agg['count'] or 0,
        'today_received': received,
        'today_profit': profit_raw - discount,
        'today_expense': expense_today,
        'debtors_total': debtors_total,
        'debtors_count': debtors.count(),
        'top_debtors': top_debtors,
        'low_count': low_count,
        'low_items': low_items,
    }
