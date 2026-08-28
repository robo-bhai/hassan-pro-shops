# context_processors.py
from django.core.cache import cache
from .models import SystemSetting, Purchase, ShareholderDepositRequest, ShareholderWithdrawalRequest, BalanceDividend, Shareholder

def system_settings(request):
    """Context processor to make system settings available in all templates"""
    
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
        # ========================================== #
        # MODULE SETTINGS                            #
        # ========================================== #
        'SHOW_HR_MODULE': SystemSetting.get_bool('show_hr_module', True),
        'SHOW_PRODUCTION_MODULE': SystemSetting.get_bool('show_production_module', True),
        'SHOW_INSTALLMENT_MODULE': SystemSetting.get_bool('show_installment_module', True),
        'SHOW_REPORTS_MODULE': SystemSetting.get_bool('show_reports_module', True),
        'SHOW_WHATSAPP_MODULE': SystemSetting.get_bool('show_whatsapp_module', True),
        'SHOW_INVENTORY_MODULE': SystemSetting.get_bool('show_inventory_module', True),
        'SHOW_PURCHASE_MODULE': SystemSetting.get_bool('show_purchase_module', True),
        'SHOW_SALES_MODULE': SystemSetting.get_bool('show_sales_module', True),
        'SHOW_ACCOUNTS_MODULE': SystemSetting.get_bool('show_accounts_module', True),
        'SHOW_BACKUP_MODULE': SystemSetting.get_bool('show_backup_module', True),
        
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