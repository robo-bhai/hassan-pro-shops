# context_processors.py
from decimal import Decimal
from django.core.cache import cache
from .models import (
    SystemSetting, Purchase, ShareholderDepositRequest, 
    ShareholderWithdrawalRequest, BalanceDividend, Shareholder
)


def system_settings(request):
    """Context processor — Optimized for speed"""
    
    # ========================================== #
    # ✅ SAARI SETTINGS EK SAATH — SIRF 1 QUERY  #
    # ========================================== #
    settings = SystemSetting.get_all_settings()
    
    def get_bool(key, default=True):
        value = settings.get(key, str(default).lower())
        return value.lower() in ['true', '1', 'yes', 'on']
    
    def get_val(key, default=''):
        return settings.get(key, default)
    
    # ========================================== #
    # ✅ SIDEBAR COUNTS — CACHED (5 min)        #
    # ========================================== #
    cache_key = 'sidebar_counts'
    counts = cache.get(cache_key)
    
    if counts is None:
        # ✅ Shareholders EK BAAR fetch karein — NO DUPLICATE QUERY
        shareholders = list(Shareholder.objects.filter(status='active'))
        
        # ✅ Eligible count + Total balance — EK LOOP MEIN
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
        cache.set(cache_key, counts, 300)  # 5 minutes
    
    # ========================================== #
    # ✅ RETURN — NO EXTRA QUERIES               #
    # ========================================== #
    return {
        # ===== MODULE SETTINGS =====
        'SHOW_HR_MODULE': get_bool('show_hr_module', True),
        'SHOW_PRODUCTION_MODULE': get_bool('show_production_module', True),
        'SHOW_INSTALLMENT_MODULE': get_bool('show_installment_module', True),
        'SHOW_REPORTS_MODULE': get_bool('show_reports_module', True),
        'SHOW_WHATSAPP_MODULE': get_bool('show_whatsapp_module', True),
        'SHOW_INVENTORY_MODULE': get_bool('show_inventory_module', True),
        'SHOW_PURCHASE_MODULE': get_bool('show_purchase_module', True),
        'SHOW_SALES_MODULE': get_bool('show_sales_module', True),
        'SHOW_ACCOUNTS_MODULE': get_bool('show_accounts_module', True),
        'SHOW_BACKUP_MODULE': get_bool('show_backup_module', True),
        
        # ===== BALANCE DIVIDEND =====
        'ENABLE_BALANCE_DIVIDEND': get_bool('enable_balance_dividend', True),
        'DEFAULT_DIVIDEND_TYPE': get_val('default_dividend_type', 'both'),
        'DEFAULT_DIVIDEND_PERCENTAGE': get_val('default_dividend_percentage', '50'),
        'MIN_BALANCE_FOR_DIVIDEND': get_val('min_balance_for_dividend', '0'),
        'MIN_HOLDING_MONTHS': get_val('min_holding_months', '0'),
        'AUTO_PROCESS_DAYS': get_val('auto_process_days', '7'),
        
        # ===== SHAREHOLDER DEDUCTION =====
        'ENABLE_SHAREHOLDER_DEDUCTION': get_bool('enable_shareholder_purchase_deduction', True),
        'DEDUCTION_TYPE': get_val('shareholder_deduction_type', 'proportional'),
        
        # ===== COUNTS =====
        'total_deductions': counts['total_deductions'],
        'pending_deposit_count': counts['pending_deposit_count'],
        'pending_withdrawal_count': counts['pending_withdrawal_count'],
        'eligible_shareholders': counts['eligible_shareholders'],
        'total_balance_used': counts['total_balance_used'],
        'pending_balance_dividends': counts['pending_balance_dividends'],
        'total_balance_dividends': counts['total_balance_dividends'],
    }


# ========================================== #
# HELPER FUNCTIONS                           #
# ========================================== #

def get_shareholder_balance_used(shareholder):
    """Calculate total balance used by a specific shareholder"""
    total = Decimal('0.00')
    
    purchases = Purchase.objects.filter(shareholder_deduction_done=True)
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    total += Decimal(str(item.get('deducted', 0)))
    
    return total