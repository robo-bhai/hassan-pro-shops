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
    for k in ('lite_edition_on', 'lite_default_language', 'module_visibility'):
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


def edition_context():
    """Template context for the Edition card (Settings > Modules)."""
    from app.models import SystemSetting
    from app.module_catalog import get_module_catalog
    labels = {m['key']: m['label'] for m in get_module_catalog()}
    return {
        'lite_on': lite_marker_on(),
        'lite_lang': SystemSetting.get_value(LITE_LANG_KEY, LITE_DEFAULT_LANG),
        'lite_optional': [{'key': k, 'label': labels.get(k, k)} for k in LITE_OPTIONAL],
        'lite_show_labels': [labels.get(k, k) for k in LITE_SHOW],
    }


def apply_edition_post(post, user=None):
    """Handle the Edition card of the settings form.

    Returns None when the form has no `edition` field. Otherwise (switched, level, message):
      switched=True  -> Lite was turned ON/OFF; the caller must redirect and NOT save the rest of the
                        form (it still shows the old module switches and would undo the switch).
      switched=False -> nothing switched (the default language may have been updated); carry on saving.
    """
    from app.models import SystemSetting
    edition = post.get('edition')
    if edition not in ('lite', 'full'):
        return None
    on = lite_marker_on()
    if edition == 'lite' and not on:
        try:
            enable_lite(post.getlist('also'), post.get('lang', LITE_DEFAULT_LANG))
        except ValueError as exc:
            return True, 'error', str(exc)
        return True, 'success', '✅ Lite Edition ON — sirf roz ke modules dikhaye ja rahe hain.'
    if edition == 'full' and on:
        disable_lite()
        return True, 'success', '✅ Full ERP wapas lag gaya — Lite se pehle ki module settings restore ho gayin.'
    if edition == 'lite' and on and post.get('lang') in ('ur', 'en', 'ar'):
        SystemSetting.set_value(LITE_LANG_KEY, post['lang'], user)
        clear_cache()
    return False, 'success', ''


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
