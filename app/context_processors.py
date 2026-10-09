# context_processors.py — Complete Updated File
from decimal import Decimal
import logging
from django.core.cache import cache
from .models import (
    SystemSetting, Purchase, ShareholderDepositRequest,
    ShareholderWithdrawalRequest, BalanceDividend, Shareholder,
)

logger = logging.getLogger(__name__)


def system_settings(request):
    """
    Context Processor — Client-based Module Visibility
    
    Rules:
    1. Superuser                       → Saare 27 modules enabled
    2. Client (with plan)              → Sirf plan ke modules enabled
    3. Client (without plan)           → Sirf Dashboard
    4. Logged-in but no tenant         → Kuch bhi enabled nahi (blocked)
    5. Anonymous user (login page etc) → Saare modules enabled (fallback)
    """
    
    # ========================================== #
    # 1. USER & TENANT DETECT                   #
    # ========================================== #
    client = getattr(request, 'tenant', None)
    is_superuser = request.user.is_authenticated and request.user.is_superuser
    is_authenticated = request.user.is_authenticated
    
    # ========================================== #
    # 2. ENABLED MODULES DECIDE                 #
    # ========================================== #
    if is_superuser:
        # ✅ Superuser → all enabled
        enabled_modules = None  # None = all True
    
    elif client and client.current_plan:
        # ✅ Client with plan → plan ke modules
        enabled_modules = client.current_plan.enabled_modules or {}
    
    elif client and not client.current_plan:
        # ✅ Client without plan → kuch bhi enabled nahi
        enabled_modules = {}
    
    elif is_authenticated:
        # ✅ Logged-in user but tenant detect nahi hua
        # Middleware ne client nahi dhoonda → block everything
        enabled_modules = {}
        
        # Debug log
        logger.warning(
            f"⚠️ User '{request.user.username}' logged in but no tenant found. "
            f"Host: {request.get_host()}, Path: {request.path}. "
            f"All modules will be HIDDEN."
        )
    
    else:
        # ✅ Anonymous user (login page, register, etc.) → allow all
        enabled_modules = None
    
    # ========================================== #
    # 3. HELPER: Check Module                   #
    # ========================================== #
    def is_module_enabled(key, default=True):
        """
        Check karo module enabled hai ya nahi
        key example: 'show_hr_module'
        """
        # Agar None hai → sab enabled
        if enabled_modules is None:
            return True
        
        # Key ko convert karo: 'show_hr_module' → 'hr'
        module_key = key.replace('show_', '').replace('_module', '')
        
        # Plan mein check karo, default True agar key missing ho
        return enabled_modules.get(module_key, default)
    
    # ========================================== #
    # 4. SYSTEM SETTINGS (Global)               #
    # ========================================== #
    settings = SystemSetting.get_all_settings()
    
    def get_bool(key, default=True):
        value = settings.get(key, str(default).lower())
        return value.lower() in ['true', '1', 'yes', 'on']
    
    def get_val(key, default=''):
        return settings.get(key, default)
    
    # ========================================== #
    # 5. SIDEBAR COUNTS (Global - No Client Filter) #
    # ========================================== #
    cache_key = 'sidebar_counts_global'
    counts = cache.get(cache_key)
    
    if counts is None:
        try:
            shareholders = list(Shareholder.objects.filter(status='active'))
            
            eligible_count = 0
            total_balance = Decimal('0.00')
            
            for shareholder in shareholders:
                balance_used = get_shareholder_balance_used(shareholder)
                if balance_used > 0:
                    eligible_count += 1
                    total_balance += balance_used
            
            counts = {
                'total_deductions': Purchase.objects.filter(
                    shareholder_deduction_done=True
                ).count(),
                'pending_deposit_count': ShareholderDepositRequest.objects.filter(
                    status='pending'
                ).count(),
                'pending_withdrawal_count': ShareholderWithdrawalRequest.objects.filter(
                    status='pending'
                ).count(),
                'eligible_shareholders': eligible_count,
                'total_balance_used': float(total_balance),
                'pending_balance_dividends': BalanceDividend.objects.filter(
                    status='declared'
                ).count(),
                'total_balance_dividends': BalanceDividend.objects.count(),
            }
            cache.set(cache_key, counts, 300)  # 5 min cache
        except Exception as e:
            logger.error(f"Sidebar counts error: {e}")
            counts = {
                'total_deductions': 0,
                'pending_deposit_count': 0,
                'pending_withdrawal_count': 0,
                'eligible_shareholders': 0,
                'total_balance_used': 0.0,
                'pending_balance_dividends': 0,
                'total_balance_dividends': 0,
            }
    
    # ========================================== #
    # 6. RETURN                                  #
    # ========================================== #
    return {
        # ===== MODULE SETTINGS (27 modules) =====
        'SHOW_HR_MODULE': is_module_enabled('show_hr_module'),
        'SHOW_PRODUCTION_MODULE': is_module_enabled('show_production_module'),
        'SHOW_INSTALLMENT_MODULE': is_module_enabled('show_installment_module'),
        'SHOW_REPORTS_MODULE': is_module_enabled('show_reports_module'),
        'SHOW_WHATSAPP_MODULE': is_module_enabled('show_whatsapp_module'),
        'SHOW_INVENTORY_MODULE': is_module_enabled('show_inventory_module'),
        'SHOW_PURCHASE_MODULE': is_module_enabled('show_purchase_module'),
        'SHOW_SALES_MODULE': is_module_enabled('show_sales_module'),
        'SHOW_ACCOUNTS_MODULE': is_module_enabled('show_accounts_module'),
        'SHOW_BACKUP_MODULE': is_module_enabled('show_backup_module'),
        'SHOW_SERVICE_MODULE': is_module_enabled('show_service_module'),
        'SHOW_SUPPLY_CHAIN_MODULE': is_module_enabled('show_supply_chain_module'),
        'SHOW_BUDGET_MODULE': is_module_enabled('show_budget_module'),
        'SHOW_EXPENSES_MODULE': is_module_enabled('show_expenses_module'),
        'SHOW_AUDIT_MODULE': is_module_enabled('show_audit_module'),
        'SHOW_SHAREHOLDER_MODULE': is_module_enabled('show_shareholder_module'),
        'SHOW_LOAN_MODULE': is_module_enabled('show_loan_module'),
        'SHOW_AI_MODULE': is_module_enabled('show_ai_module'),
        'SHOW_BI_MODULE': is_module_enabled('show_bi_module'),
        'SHOW_DOCUMENT_MODULE': is_module_enabled('show_document_module'),
        'SHOW_SECURITY_MODULE': is_module_enabled('show_security_module'),
        'SHOW_TESTING_MODULE': is_module_enabled('show_testing_module'),
        'SHOW_OPERATIONS_MODULE': is_module_enabled('show_operations_module'),
        'SHOW_CASH_MODULE': is_module_enabled('show_cash_module'),
        'SHOW_WAREHOUSE_MODULE': is_module_enabled('show_warehouse_module'),
        'SHOW_RETURNS_MODULE': is_module_enabled('show_returns_module'),
        'SHOW_PEOPLE_MODULE': is_module_enabled('show_people_module'),
        
        # ===== BALANCE DIVIDEND SETTINGS =====
        'ENABLE_BALANCE_DIVIDEND': get_bool('enable_balance_dividend', True),
        'DEFAULT_DIVIDEND_TYPE': get_val('default_dividend_type', 'both'),
        'DEFAULT_DIVIDEND_PERCENTAGE': get_val('default_dividend_percentage', '50'),
        'MIN_BALANCE_FOR_DIVIDEND': get_val('min_balance_for_dividend', '0'),
        'MIN_HOLDING_MONTHS': get_val('min_holding_months', '0'),
        'AUTO_PROCESS_DAYS': get_val('auto_process_days', '7'),
        
        # ===== SHAREHOLDER DEDUCTION =====
        'ENABLE_SHAREHOLDER_DEDUCTION': get_bool('enable_shareholder_purchase_deduction', True),
        'DEDUCTION_TYPE': get_val('shareholder_deduction_type', 'proportional'),
        
        # ===== SIDEBAR COUNTS =====
        'total_deductions': counts['total_deductions'],
        'pending_deposit_count': counts['pending_deposit_count'],
        'pending_withdrawal_count': counts['pending_withdrawal_count'],
        'eligible_shareholders': counts['eligible_shareholders'],
        'total_balance_used': counts['total_balance_used'],
        'pending_balance_dividends': counts['pending_balance_dividends'],
        'total_balance_dividends': counts['total_balance_dividends'],
        
        # ===== CLIENT INFO =====
        'tenant': client,
        'is_tenant': client is not None,
    }


# ========================================== #
# HELPER FUNCTION                            #
# ========================================== #
def get_shareholder_balance_used(shareholder):
    """Calculate total balance used by a specific shareholder"""
    total = Decimal('0.00')
    
    try:
        purchases = Purchase.objects.filter(shareholder_deduction_done=True)
        for purchase in purchases:
            data = purchase.shareholder_deduction_data
            if data and data.get('deducted_from'):
                for item in data['deducted_from']:
                    if item.get('name') == shareholder.name:
                        total += Decimal(str(item.get('deducted', 0)))
    except Exception as e:
        logger.error(f"Balance calculation error for {shareholder.name}: {e}")
    
    return total