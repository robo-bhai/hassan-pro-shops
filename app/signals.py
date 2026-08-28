# app/signals.py

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.utils.timezone import now
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, F, DecimalField
import threading
import logging
import time

# ========================================== #
# IMPORT ALL MODELS                          #
# ========================================== #

from .models import (
    # Core Models
    Sale, Purchase, MonthlyClosing, Inventory, 
    Vendor, Customer, GroupSummary, Shareholder,
    PurchaseItem, SaleItem,  # ✅ ADDED
    
    # User Model
    User,
    
    # Other Models
    Expense, Budget, BudgetGoal, Notification,
    SystemSetting,  # ✅ ADDED
)

logger = logging.getLogger(__name__)


# ========================================== #
# GROUP SUMMARY SIGNALS                      #
# ========================================== #

def update_group_summary():
    """Update GroupSummary totals."""
    summary, created = GroupSummary.objects.get_or_create()
    summary.calculate_totals()


@receiver(post_save, sender=Vendor)
def update_vendor_summary(sender, instance, **kwargs):
    update_group_summary()


@receiver(post_delete, sender=Vendor)
def update_vendor_summary_delete(sender, instance, **kwargs):
    update_group_summary()


@receiver(post_save, sender=Customer)
def update_customer_summary(sender, instance, **kwargs):
    update_group_summary()


@receiver(post_delete, sender=Customer)
def update_customer_summary_delete(sender, instance, **kwargs):
    update_group_summary()


# ========================================== #
# SHAREHOLDER SIGNAL - Auto Create User      #
# ========================================== #

@receiver(post_save, sender=Shareholder)
def create_shareholder_user(sender, instance, created, **kwargs):
    """Auto create user when shareholder is created with allow_login=True"""
    if created and instance.allow_login:
        instance.get_user()


@receiver(post_save, sender=Shareholder)
def update_shareholder_user(sender, instance, created, **kwargs):
    """Update user when shareholder allow_login changes"""
    if not created and instance.allow_login and not instance.user:
        instance.get_user()


# ========================================== #
# ✅ AUTO PURCHASE DEDUCTION SIGNALS         #
# ========================================== #

def process_deduction_async(purchase_id, delay=0.5):
    """
    ✅ Process deduction in background thread
    """
    def process():
        try:
            # Small delay for items to be added
            time.sleep(delay)
            
            from django.db import transaction
            purchase = Purchase.objects.get(id=purchase_id)
            
            with transaction.atomic():
                # 🔥 Check if already processed
                if purchase.shareholder_deduction_done:
                    logger.info(f"⏭️ Deduction already done for {purchase.bill_no}")
                    return
                
                # 🔥 Check if purchase has items
                if not purchase.purchaseitem_set.exists():
                    logger.warning(f"⚠️ No items found for {purchase.bill_no}")
                    return
                
                # 🔥 Process deduction
                success, result = purchase.process_shareholder_deduction()
                
                if success:
                    logger.info(f"✅ Auto-deduction successful for {purchase.bill_no}")
                    logger.info(f"   Total: Rs. {purchase.total_amount():,.2f}")
                    
                    for item in result.get('deducted_from', []):
                        logger.info(f"   - {item['name']}: Rs. {item['deducted']:,.2f} ({item['percentage']:.1f}%)")
                else:
                    logger.error(f"❌ Auto-deduction failed for {purchase.bill_no}: {result}")
                    
        except Purchase.DoesNotExist:
            logger.error(f"❌ Purchase {purchase_id} not found")
        except Exception as e:
            logger.error(f"❌ Auto-deduction error for {purchase_id}: {str(e)}")
    
    # Run in background
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()


@receiver(post_save, sender=Purchase)
def auto_process_purchase_deduction(sender, instance, created, **kwargs):
    """
    ✅ Automatically process shareholder deduction when purchase is created
    """
    # 🔥 ONLY run when purchase is created (not updated)
    if not created:
        return
    
    # 🔥 Check if system setting is enabled
    if not SystemSetting.get_bool('enable_shareholder_purchase_deduction', True):
        logger.info(f"⏭️ Deduction skipped for {instance.bill_no} - System setting disabled")
        return
    
    # 🔥 Check if already processed
    if instance.shareholder_deduction_done:
        logger.info(f"⏭️ Deduction already done for {instance.bill_no}")
        return
    
    # 🔥 Check if purchase has items (if not, will be processed after item added)
    if instance.purchaseitem_set.exists():
        # Process immediately with small delay
        process_deduction_async(instance.id, delay=0.3)
    else:
        # Schedule for later when items are added
        logger.info(f"⏳ Waiting for items on {instance.bill_no}")
        process_deduction_async(instance.id, delay=1.5)


@receiver(post_save, sender=PurchaseItem)
def auto_process_on_item_added(sender, instance, created, **kwargs):
    """
    ✅ When a new item is added to purchase, process deduction
    """
    if not created:
        return
    
    purchase = instance.purchase
    
    # 🔥 Only process if purchase is new and not already processed
    if purchase.shareholder_deduction_done:
        return
    
    # 🔥 Check if system setting is enabled
    if not SystemSetting.get_bool('enable_shareholder_purchase_deduction', True):
        return
    
    # 🔥 Process deduction
    logger.info(f"🔄 Item added to {purchase.bill_no}, processing deduction...")
    process_deduction_async(purchase.id, delay=0.5)


@receiver(post_save, sender=PurchaseItem)
def update_purchase_total(sender, instance, created, **kwargs):
    """
    ✅ Update purchase total when item is added/updated
    """
    if created:
        # Purchase total already updated in PurchaseItem.save()
        pass


# ========================================== #
# EXPENSE SIGNAL - Update Budget & Goals     #
# ========================================== #

@receiver(post_save, sender=Expense)
def update_budget_on_expense(sender, instance, created, **kwargs):
    """Update budget used amount when expense is created/updated"""
    if instance.budget and instance.status in ['approved', 'paid']:
        instance.budget.calculate_used()
    
    # Update budget goals
    if instance.budget:
        goals = BudgetGoal.objects.filter(
            budget=instance.budget,
            category=instance.category,
            status='active'
        )
        for goal in goals:
            # Calculate total expenses for this category
            total_spent = Expense.objects.filter(
                budget=instance.budget,
                category=instance.category,
                status__in=['approved', 'paid'],
                expense_date__gte=goal.start_date,
                expense_date__lte=goal.end_date
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            goal.current_amount = total_spent
            goal.update_progress()


@receiver(post_delete, sender=Expense)
def update_budget_on_expense_delete(sender, instance, **kwargs):
    """Update budget when expense is deleted"""
    if instance.budget:
        instance.budget.calculate_used()


# ========================================== #
# BUDGET GOAL SIGNAL - Auto Update           #
# ========================================== #

@receiver(post_save, sender=BudgetGoal)
def budget_goal_created(sender, instance, created, **kwargs):
    """When goal is created, calculate initial progress"""
    if created:
        # Calculate current progress from existing expenses
        total_spent = Expense.objects.filter(
            budget=instance.budget,
            category=instance.category,
            status__in=['approved', 'paid'],
            expense_date__gte=instance.start_date,
            expense_date__lte=instance.end_date
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        instance.current_amount = total_spent
        instance.update_progress()


# ========================================== #
# MONTHLY CLOSING SIGNAL                     #
# ========================================== #

@receiver(post_save, sender=MonthlyClosing)
def monthly_closing_created(sender, instance, created, **kwargs):
    """When monthly closing is created, update previous balance"""
    if created:
        instance.previous_balance = instance.get_previous_month_closing()
        instance.save(update_fields=['previous_balance'])


# ========================================== #
# BUDGET ROLLOVER SIGNAL                     #
# ========================================== #

@receiver(post_save, sender=Budget)
def budget_rollover_check(sender, instance, **kwargs):
    """Check if budget should rollover to next period"""
    if instance.allow_rollover and instance.status == 'expired':
        # Create new budget with rollover amount
        new_budget = Budget.objects.create(
            name=f"{instance.name} (Rollover)",
            budget_type=instance.budget_type,
            frequency=instance.frequency,
            period_start=instance.period_end + timedelta(days=1),
            period_end=instance.period_end + timedelta(days=30),
            allocated_amount=instance.remaining_amount,
            department=instance.department,
            project=instance.project,
            category=instance.category,
            status='draft',
            created_by=instance.created_by,
            allow_rollover=True,
            rollover_from=instance,
            notes=f"Rollover from {instance.budget_no}"
        )


# ========================================== #
# INVENTORY LOW STOCK SIGNAL                 #
# ========================================== #

@receiver(post_save, sender=Inventory)
def check_low_stock(sender, instance, **kwargs):
    """Check and notify if stock is low"""
    if instance.is_low_stock():
        # Notify admin users
        admin_users = User.objects.filter(is_superuser=True)
        for user in admin_users:
            Notification.objects.create(
                user=user,
                title="⚠️ Low Stock Alert",
                message=f"Product '{instance.product.name}' is low on stock! Current: {instance.stock}",
                notification_type='danger',
                category='stock'
            )


# ========================================== #
# PURCHASE SIGNAL - Update Inventory         #
# ========================================== #

@receiver(post_save, sender=Purchase)
def update_inventory_on_purchase(sender, instance, created, **kwargs):
    """Update inventory when purchase is created"""
    if created:
        for item in instance.purchaseitem_set.all():
            Inventory.update_stock(item.product, item.qty, instance.warehouse)


# ========================================== #
# SALE SIGNAL - Update Inventory             #
# ========================================== #

@receiver(post_save, sender=Sale)
def update_inventory_on_sale(sender, instance, created, **kwargs):
    """Update inventory when sale is created"""
    if created:
        for item in instance.saleitem_set.all():
            Inventory.update_stock(item.product, -item.qty, instance.warehouse)


# ========================================== #
# ✅ BULK PROCESS - PENDING PURCHASES        #
# ========================================== #

def bulk_process_pending_deductions(user=None):
    """
    ✅ Process all pending shareholder deductions
    Call this from shell or management command
    """
    from django.db import transaction
    
    pending = Purchase.objects.filter(
        shareholder_deduction_done=False
    )
    
    if not pending.exists():
        return {
            'success': True,
            'message': 'No pending deductions found',
            'total': 0,
            'processed': 0,
            'failed': 0,
            'total_amount': Decimal('0.00'),
            'details': [],
            'errors': []
        }
    
    results = {
        'total': pending.count(),
        'processed': 0,
        'failed': 0,
        'total_amount': Decimal('0.00'),
        'details': [],
        'errors': []
    }
    
    for purchase in pending:
        try:
            with transaction.atomic():
                if not purchase.purchaseitem_set.exists():
                    results['failed'] += 1
                    results['errors'].append({
                        'bill_no': purchase.bill_no,
                        'error': 'No items in purchase'
                    })
                    continue
                
                success, result = purchase.process_shareholder_deduction(
                    user=user or purchase.created_by
                )
                
                if success:
                    results['processed'] += 1
                    results['total_amount'] += purchase.total_amount()
                    results['details'].append({
                        'bill_no': purchase.bill_no,
                        'amount': float(purchase.total_amount()),
                        'shareholders': len(result.get('deducted_from', [])),
                    })
                    logger.info(f"✅ Bulk processed: {purchase.bill_no} - Rs. {purchase.total_amount():,.2f}")
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'bill_no': purchase.bill_no,
                        'error': str(result)
                    })
                    logger.error(f"❌ Bulk failed: {purchase.bill_no} - {result}")
                    
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({
                'bill_no': purchase.bill_no,
                'error': str(e)
            })
            logger.error(f"❌ Bulk error: {purchase.bill_no} - {str(e)}")
    
    return results


# ========================================== #
# SYSTEM SETTINGS SIGNAL                     #
# ========================================== #

@receiver(post_save, sender=SystemSetting)
def system_setting_changed(sender, instance, **kwargs):
    """Log when system settings change"""
    logger.info(f"⚙️ System setting changed: {instance.setting_key} = {instance.setting_value}")