# context_processors.py
from django.core.cache import cache
from .models import SystemSetting, Purchase, ShareholderDepositRequest, ShareholderWithdrawalRequest, BalanceDividend, Shareholder, CompanyInfo


def _company_branding():
    """Company name and logo (for the sidebar etc.)."""
    company = CompanyInfo.objects.only("name", "logo", "tagline", "contact_number", "email", "website").first()
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
        # Shop sidebar SUPPORT section (har page par available, sirf kuch views par nahi)
        "company_contact_number": company.contact_number if company and company.contact_number else "",
        "company_email": company.email if company and company.email else "",
        "company_website": company.website if company and company.website else "",
    }


# ----------------------------------------------------------------------------
# MODULE VISIBILITY
# Factory mode was removed: the business mode is always 'shop' and only the Shop switch of each module counts.
# (The old mode_factory_* rows are ignored.) No module is hidden until you turn its switch off.
# ----------------------------------------------------------------------------
from .module_catalog import MODULE_CATALOG, get_module_catalog, get_module_keys
from .i18n.i18n_lang import LANGUAGES, get_language

from .lite_edition import is_lite

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
        mode = 'shop'                      # Factory mode removed: only the Shop switches apply
        data = {'_mode': mode}
        for m in get_module_keys():
            data[m] = unit_enabled(m, 'shop')
        cache.set('module_visibility', data, 60)
    return data


def system_settings(request):
    """Context processor to make system settings available in all templates"""
    user = getattr(request, 'user', None)
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
    vis = module_visibility()
    # Administrator (superuser) always sees every module. The Module Settings switches only limit the
    # customer side (Owner + staff), so the sidebar flags below are all True for the Administrator.
    if getattr(user, 'is_superuser', False):
        vis = {k: (v if k == '_mode' else True) for k, v in vis.items()}
    else:
        # Role-wise access (Settings > Modules > Roles): hide modules the user's role may not use.
        from .module_roles import apply_roles
        vis = apply_roles(user, vis)
    _is_owner = bool(getattr(user, 'is_authenticated', False)
                     and user.groups.filter(name='Owner').exists())

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
        # Lite Edition (simple Urdu-first mode): templates use {% if LITE_MODE %}
        'LITE_MODE': is_lite(),
        # Owner of the customer account (sidebar: Security section is for Administrator / Owner only)
        'IS_OWNER': _is_owner,
        # ===== LANGUAGE (en / ur / ar) =====
        'LANG_CODE': _lang['code'], 'LANG_DIR': _lang['dir'], 'LANG_LABEL': _lang['native'],
        'LANGUAGES': LANGUAGES,
        'I18N_VERSION': _i18n_ver, 'I18N_COLLECT': _i18n_collect,
        # templates me: {% if MODULE_VISIBLE.loans %} ya {% if SHOW_LOANS_MODULE %}
        'MODULE_VISIBLE': {k: v for k, v in vis.items() if k != '_mode'},
        # Sidebar links for newly auto-detected modules (the ones that are ON)
        'AUTO_MODULES': [m for m in get_module_catalog()
                         if m.get('auto') and vis.get(m["key"], True)],
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