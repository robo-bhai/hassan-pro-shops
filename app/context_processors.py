# context_processors.py
from django.core.cache import cache
from .models import SystemSetting, Purchase, ShareholderDepositRequest, ShareholderWithdrawalRequest, BalanceDividend, Shareholder, CompanyInfo


def _company_branding():
    """Company name and logo (for the sidebar etc.)."""
    company = CompanyInfo.objects.only("name", "logo").first()
    logo_url = None
    if company and company.logo:
        try:
            logo_url = company.logo.url
        except ValueError:
            logo_url = None
    return {
        "company_logo": logo_url,
        "company_name": company.name if company else "ERP System",
        "company_tagline": company.tagline if company and company.tagline else "",
    }


# ----------------------------------------------------------------------------
# MODULE VISIBILITY (per business unit)
# Each module has 2 switches: Shop and Factory.
#   mode = shop    -> only the Shop switches are considered
#   mode = factory -> only the Factory switches are considered
#   mode = both    -> the module shows when it is ON in Shop OR Factory
# No module is hidden until you turn its switch off (there is no fixed rule).
# ----------------------------------------------------------------------------
from .module_catalog import MODULE_CATALOG, get_module_catalog, get_module_keys
from .i18n.i18n_lang import LANGUAGES, get_language

MODULES = [m['key'] for m in MODULE_CATALOG]

# Defaults before the first save (written in the catalog): all modules ON. Only those whose switch is off get hidden.
_BUILTIN_DEFAULTS = {m['key']: {'shop': m['shop'], 'factory': m['factory']} for m in MODULE_CATALOG}


def unit_enabled(module, unit):
    """Is the 'module' ON for this unit ('shop' or 'factory')?"""
    master = SystemSetting.get_bool('show_%s_module' % module, True)   # purana global switch
    default = _BUILTIN_DEFAULTS.get(module, {}).get(unit, True) and master
    return SystemSetting.get_bool('mode_%s_%s' % (unit, module), default)


def module_visibility():
    """{module: True/False, '_mode': mode} - 60 second cache, cleared immediately on save."""
    data = cache.get('module_visibility')
    if data is None:
        mode = SystemSetting.get_value('business_mode', 'both')
        if mode not in ('shop', 'factory', 'both'):
            mode = 'both'
        data = {'_mode': mode}
        for m in get_module_keys():
            shop, fac = unit_enabled(m, 'shop'), unit_enabled(m, 'factory')
            data[m] = shop if mode == 'shop' else fac if mode == 'factory' else (shop or fac)
        cache.set('module_visibility', data, 60)
    return data


def system_settings(request):
    """Context processor to make system settings available in all templates"""
    from .store.store_access import module_scope, restrict_visibility
    user = getattr(request, 'user', None)
    store_scope = module_scope(user)                 # None = no restriction
    _lang = get_language(request)
    _i18n_ver = ''
    if _lang['code'] != 'en':
        try:
            from django.core.cache import cache as _cache
            from .i18n import i18n_service as _i18n
            _i18n_ver = _cache.get_or_set('i18n_ver', _i18n.get_version, 30)
        except Exception:
            _i18n_ver = ''
    _i18n_collect = bool(getattr(user, 'is_authenticated', False) and (user.is_superuser or user.is_staff))
    vis = restrict_visibility(user, module_visibility())

    # Cache counts for 5 minutes to improve performance
    cache_key = 'sidebar_counts'
    counts = cache.get(cache_key)
    
    if counts is None:
        # Get eligible shareholders count for balance dividend
        eligible_count = 0
        for shareholder in Shareholder.objects.filter(status='active'):
            # Check if shareholder has balance usage
            balance_used = get_shareholder_balance_used(shareholder)
            if balance_used > 0:
                eligible_count += 1
        
        counts = {
            # ===== SHAREHOLDER DEDUCTION COUNTS =====
            'total_deductions': Purchase.objects.filter(
                shareholder_deduction_done=True
            ).count(),
            'pending_deposit_count': ShareholderDepositRequest.objects.filter(
                status='pending'
            ).count(),
            'pending_withdrawal_count': ShareholderWithdrawalRequest.objects.filter(
                status='pending'
            ).count(),
            
            # ===== BALANCE DIVIDEND COUNTS =====
            'eligible_shareholders': eligible_count,
            'total_balance_used': get_total_balance_used(),
            'pending_balance_dividends': BalanceDividend.objects.filter(
                status='declared'
            ).count(),
            'total_balance_dividends': BalanceDividend.objects.count(),
        }
        cache.set(cache_key, counts, 300)  # 5 minutes
    
    return {
        # ===== COMPANY BRANDING (logo/name) =====
        **_company_branding(),

        # ========================================== #
        # MODULE SETTINGS                            #
        # ========================================== #
        'BUSINESS_MODE': vis['_mode'],
        # ===== LANGUAGE (en / ur / ar) =====
        'LANG_CODE': _lang['code'], 'LANG_DIR': _lang['dir'], 'LANG_LABEL': _lang['native'],
        'LANGUAGES': LANGUAGES,
        'I18N_VERSION': _i18n_ver, 'I18N_COLLECT': _i18n_collect,
        # True = this user is a member of a store's team: the sidebar shows only that store's modules
        'STORE_RESTRICTED': store_scope is not None,
        # templates me: {% if MODULE_VISIBLE.loans %} ya {% if SHOW_LOANS_MODULE %}
        'MODULE_VISIBLE': {k: v for k, v in vis.items() if k != '_mode'},
        # Sidebar links for newly auto-detected modules (the ones that are ON)
        'AUTO_MODULES': [m for m in get_module_catalog()
                         if m.get('auto') and vis.get(m['key'], True) and not store_scope],
        **{'SHOW_%s_MODULE' % k.upper(): v for k, v in vis.items() if k != '_mode'},

        # ========================================== #
        # BALANCE DIVIDEND SETTINGS                  #
        # ========================================== #
        'ENABLE_BALANCE_DIVIDEND': SystemSetting.get_bool('enable_balance_dividend', True),
        'DEFAULT_DIVIDEND_TYPE': SystemSetting.get_value('default_dividend_type', 'both'),
        'DEFAULT_DIVIDEND_PERCENTAGE': SystemSetting.get_value('default_dividend_percentage', '50'),
        'MIN_BALANCE_FOR_DIVIDEND': SystemSetting.get_value('min_balance_for_dividend', '0'),
        'MIN_HOLDING_MONTHS': SystemSetting.get_value('min_holding_months', '0'),
        'AUTO_PROCESS_DAYS': SystemSetting.get_value('auto_process_days', '7'),
        
        # ========================================== #
        # SHAREHOLDER DEDUCTION SETTINGS             #
        # ========================================== #
        'ENABLE_SHAREHOLDER_DEDUCTION': SystemSetting.get_bool('enable_shareholder_purchase_deduction', True),
        'DEDUCTION_TYPE': SystemSetting.get_value('shareholder_deduction_type', 'proportional'),
        
        # ========================================== #
        # SHAREHOLDER DEDUCTION COUNTS               #
        # ========================================== #
        'total_deductions': counts['total_deductions'],
        'pending_deposit_count': counts['pending_deposit_count'],
        'pending_withdrawal_count': counts['pending_withdrawal_count'],
        
        # ========================================== #
        # BALANCE DIVIDEND COUNTS                    #
        # ========================================== #
        'eligible_shareholders': counts['eligible_shareholders'],
        'total_balance_used': counts['total_balance_used'],
        'pending_balance_dividends': counts['pending_balance_dividends'],
        'total_balance_dividends': counts['total_balance_dividends'],
    }


# ========================================== #
# HELPER FUNCTIONS                           #
# ========================================== #

def get_shareholder_balance_used(shareholder):
    """
    Calculate total balance used by a specific shareholder
    """
    from decimal import Decimal
    from .models import Purchase
    
    total = Decimal('0.00')
    
    purchases = Purchase.objects.filter(shareholder_deduction_done=True)
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    total += Decimal(str(item.get('deducted', 0)))
    
    return total


def get_total_balance_used():
    """
    Calculate total balance used by all shareholders
    """
    from decimal import Decimal
    from .models import Shareholder
    
    total = Decimal('0.00')
    
    for shareholder in Shareholder.objects.filter(status='active'):
        total += get_shareholder_balance_used(shareholder)
    
    return float(total)


def get_eligible_shareholders_count():
    """
    Get count of shareholders eligible for balance dividend
    """
    from .models import Shareholder
    
    count = 0
    min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
    min_months = int(SystemSetting.get_value('min_holding_months', '0'))
    
    for shareholder in Shareholder.objects.filter(status='active'):
        balance_used = get_shareholder_balance_used(shareholder)
        
        # Check minimum balance requirement
        if balance_used < min_balance:
            continue
        
        # Check minimum holding period
        if min_months > 0:
            # Get first share issue date
            first_share = shareholder.shares.order_by('issue_date').first()
            if not first_share:
                continue
            from datetime import date
            months_held = (date.today() - first_share.issue_date).days // 30
            if months_held < min_months:
                continue
        
        count += 1
    
    return count