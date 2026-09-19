# ========================================== #
# APP SIGNALS - COMPLETE                      #
# ========================================== #

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.utils.timezone import now
from django.contrib.auth.models import User
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
    PurchaseItem, SaleItem,
    
    # Other Models
    Expense, Budget, BudgetGoal, Notification,
    SystemSetting,
)

logger = logging.getLogger(__name__)


# ========================================== #
# HELPER FUNCTION — Create Notification      #
# ========================================== #

def create_announcement_notification(
    title, 
    message, 
    notification_type='info',
    category='system',
    link=None,
    user=None
):
    """Universal helper — notification create karo"""
    try:
        if user:
            # Specific user ke liye
            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                link=link,
            )
        else:
            # Sab staff ke liye
            staff_users = User.objects.filter(is_staff=True, is_active=True)
            for u in staff_users:
                Notification.objects.create(
                    user=u,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    category=category,
                    link=link,
                )
        
        logger.info(f"✅ Notification: {title}")
        return True
    except Exception as e:
        logger.error(f"❌ Notification error: {e}")
        return False


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
    """Process deduction in background thread"""
    def process():
        try:
            time.sleep(delay)
            
            purchase = Purchase.objects.get(id=purchase_id)
            
            with transaction.atomic():
                if purchase.shareholder_deduction_done:
                    logger.info(f"⏭️ Deduction already done for {purchase.bill_no}")
                    return
                
                if not purchase.purchaseitem_set.exists():
                    logger.warning(f"⚠️ No items found for {purchase.bill_no}")
                    return
                
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
    
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()


@receiver(post_save, sender=Purchase)
def auto_process_purchase_deduction(sender, instance, created, **kwargs):
    """Automatically process shareholder deduction when purchase is created"""
    if not created:
        return
    
    if not SystemSetting.get_bool('enable_shareholder_purchase_deduction', True):
        logger.info(f"⏭️ Deduction skipped for {instance.bill_no} - System setting disabled")
        return
    
    if instance.shareholder_deduction_done:
        logger.info(f"⏭️ Deduction already done for {instance.bill_no}")
        return
    
    if instance.purchaseitem_set.exists():
        process_deduction_async(instance.id, delay=0.3)
    else:
        logger.info(f"⏳ Waiting for items on {instance.bill_no}")
        process_deduction_async(instance.id, delay=1.5)


@receiver(post_save, sender=PurchaseItem)
def auto_process_on_item_added(sender, instance, created, **kwargs):
    """When a new item is added to purchase, process deduction"""
    if not created:
        return
    
    purchase = instance.purchase
    
    if purchase.shareholder_deduction_done:
        return
    
    if not SystemSetting.get_bool('enable_shareholder_purchase_deduction', True):
        return
    
    logger.info(f"🔄 Item added to {purchase.bill_no}, processing deduction...")
    process_deduction_async(purchase.id, delay=0.5)


# ========================================== #
# ✅ SALE SIGNAL - COMBINED                   #
# Inventory + Notification (VOICE ANNOUNCE)  #
# ========================================== #

@receiver(post_save, sender=Sale)
def sale_combined_signal(sender, instance, created, **kwargs):
    """
    ✅ Combined Sale Signal
    - Update inventory
    - Create notification (voice announce)
    """
    if not created:
        return
    
    try:
        # ==========================================
        # 1. CREATE NOTIFICATION (VOICE ANNOUNCE)
        # ==========================================
        total = instance.total_amount()
        customer = instance.customer.name if instance.customer else 'Walk-in'
        bill_no = instance.bill_no or f'#{instance.id}'
        
        # ✅ Normal sale notification
        create_announcement_notification(
            title=f"🛒 New Sale: {bill_no}",
            message=f"Rs. {total:,.2f} sale from {customer}",
            notification_type='sale',
            category='sales',
            link=f'/sales/{instance.id}/',
        )
        
        # ✅ Big sale alert (Rs. 1 lakh+)
        if total >= 100000:
            create_announcement_notification(
                title=f"🎉 Big Sale Alert!",
                message=f"Rs. {total:,.2f} sale from {customer} - Congratulations!",
                notification_type='success',
                category='sales',
                link=f'/sales/{instance.id}/',
            )
        
        logger.info(f"✅ Sale signal: {bill_no} - Rs. {total}")
        
    except Exception as e:
        logger.error(f"❌ Sale signal error: {e}")


# ========================================== #
# ✅ SALE ITEM SIGNAL - Inventory Update     #
# ========================================== #

@receiver(post_save, sender=SaleItem)
def saleitem_created_signal(sender, instance, created, **kwargs):
    """Sale item created - inventory already updated in model save"""
    if not created:
        return
    
    try:
        logger.info(f"🛒 SaleItem: {instance.product.name} x {instance.qty}")
    except Exception as e:
        logger.error(f"❌ SaleItem signal error: {e}")


# ========================================== #
# PAYMENT SIGNALS 💰                         #
# ========================================== #

@receiver(post_save, sender='app.SalePayment')
def payment_received_signal(sender, instance, created, **kwargs):
    """Jab payment receive ho"""
    if not created:
        return
    
    try:
        amount = instance.amount
        method = instance.method.get_name_display() if instance.method else 'Cash'
        customer = instance.sale.customer.name if instance.sale and instance.sale.customer else 'Customer'
        
        create_announcement_notification(
            title=f"💰 Payment Received",
            message=f"Rs. {amount:,.2f} from {customer} via {method}",
            notification_type='payment',
            category='payments',
            link=f'/sales/{instance.sale.id}/' if instance.sale else None,
        )
        
        logger.info(f"💰 Payment: Rs. {amount} from {customer}")
    except Exception as e:
        logger.error(f"❌ Payment signal error: {e}")


@receiver(post_save, sender='app.CustomerPayment')
def customer_payment_signal(sender, instance, created, **kwargs):
    """Customer payment received"""
    if not created:
        return
    
    try:
        amount = instance.amount
        customer = instance.customer.name if instance.customer else 'Customer'
        method = instance.payment_method.get_name_display() if instance.payment_method else 'Cash'
        
        create_announcement_notification(
            title=f"💰 Customer Payment",
            message=f"Rs. {amount:,.2f} from {customer} via {method}",
            notification_type='payment',
            category='payments',
            link=f'/customers/{instance.customer.id}/ledger/' if instance.customer else None,
        )
        logger.info(f"💰 Customer payment: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Customer payment error: {e}")


# ========================================== #
# PURCHASE SIGNALS 📥                        #
# ========================================== #

@receiver(post_save, sender='app.Purchase')
def purchase_created_signal(sender, instance, created, **kwargs):
    """Jab nayi purchase create ho"""
    if not created:
        return
    
    try:
        total = instance.total_amount()
        vendor = instance.vendor.name if instance.vendor else 'Vendor'
        bill_no = instance.bill_no or f'#{instance.id}'
        
        create_announcement_notification(
            title=f"📥 New Purchase: {bill_no}",
            message=f"Rs. {total:,.2f} purchase from {vendor}",
            notification_type='info',
            category='purchases',
            link=f'/purchases/{instance.id}/',
        )
        logger.info(f"📥 Purchase: {bill_no} - Rs. {total}")
    except Exception as e:
        logger.error(f"❌ Purchase signal error: {e}")


# ========================================== #
# STOCK SIGNALS 📦                           #
# ========================================== #

@receiver(post_save, sender='app.Inventory')
def low_stock_signal(sender, instance, created, **kwargs):
    """Jab stock low ho jaye"""
    try:
        product = instance.product
        threshold = product.low_stock_threshold
        current_stock = instance.stock
        
        # Low stock
        if current_stock < threshold and current_stock > 0:
            six_hours_ago = now() - timedelta(hours=6)
            existing = Notification.objects.filter(
                title__icontains=f"Low Stock: {product.name}",
                created_at__gte=six_hours_ago,
            ).exists()
            
            if not existing:
                create_announcement_notification(
                    title=f"📦 Low Stock: {product.name}",
                    message=f"Only {current_stock:.0f} units left (threshold: {threshold:.0f})",
                    notification_type='stock',
                    category='stock',
                    link=f'/inventory/?search={product.name}',
                )
                logger.warning(f"📦 Low stock: {product.name} - {current_stock} units")
        
        # Out of stock
        elif current_stock <= 0:
            six_hours_ago = now() - timedelta(hours=6)
            existing = Notification.objects.filter(
                title__icontains=f"Out of Stock: {product.name}",
                created_at__gte=six_hours_ago,
            ).exists()
            
            if not existing:
                create_announcement_notification(
                    title=f"❌ Out of Stock: {product.name}",
                    message=f"{product.name} is out of stock! Order immediately.",
                    notification_type='danger',
                    category='stock',
                    link=f'/inventory/?search={product.name}',
                )
                logger.error(f"❌ Out of stock: {product.name}")
                
    except Exception as e:
        logger.error(f"❌ Stock signal error: {e}")


# ========================================== #
# INSTALLMENT / EMI SIGNALS 📅               #
# ========================================== #

@receiver(post_save, sender='app.SaleInstallment')
def installment_created_signal(sender, instance, created, **kwargs):
    """Naya installment plan bana"""
    if not created:
        return
    
    try:
        customer = instance.sale.customer.name if instance.sale else 'Customer'
        total = instance.total_payable
        
        create_announcement_notification(
            title=f"📅 New Installment Plan",
            message=f"{customer} - Total: Rs. {total:,.2f} - EMI: Rs. {instance.emi_amount:,.2f}",
            notification_type='info',
            category='installments',
            link=f'/installments/{instance.id}/',
        )
        logger.info(f"📅 Installment created for {customer}")
    except Exception as e:
        logger.error(f"❌ Installment signal error: {e}")


@receiver(post_save, sender='app.EmiPayment')
def emi_payment_signal(sender, instance, created, **kwargs):
    """EMI payment received"""
    if not created:
        return
    
    try:
        status = instance.status
        
        if status == 'paid':
            customer = instance.installment.sale.customer.name
            amount = instance.amount_paid
            emi_num = instance.installment_number
            
            create_announcement_notification(
                title=f"✅ EMI #{emi_num} Paid",
                message=f"Rs. {amount:,.2f} received from {customer}",
                notification_type='success',
                category='payments',
                link=f'/installments/{instance.installment.id}/',
            )
            logger.info(f"✅ EMI paid: {customer} - Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ EMI payment error: {e}")


# ========================================== #
# CASH SIGNALS 💵                            #
# ========================================== #

@receiver(post_save, sender='app.CashTransaction')
def cash_transaction_signal(sender, instance, created, **kwargs):
    """Cash transaction hui"""
    if not created:
        return
    
    try:
        amount = instance.amount
        trans_type = instance.transaction_type
        description = instance.description or 'Transaction'
        
        if amount >= 50000:
            if trans_type in ['deposit', 'sale', 'opening']:
                create_announcement_notification(
                    title=f"💵 Big Cash In",
                    message=f"Rs. {amount:,.2f} - {description[:50]}",
                    notification_type='success',
                    category='payments',
                )
            else:
                create_announcement_notification(
                    title=f"💸 Big Cash Out",
                    message=f"Rs. {amount:,.2f} - {description[:50]}",
                    notification_type='warning',
                    category='payments',
                )
            logger.info(f"💵 Big cash: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Cash signal error: {e}")


@receiver(post_save, sender='app.CashBalance')
def cash_low_signal(sender, instance, created, **kwargs):
    """Cash balance kam ho jaye"""
    try:
        balance = instance.balance
        
        if balance < 10000 and balance > 0:
            two_hours_ago = now() - timedelta(hours=2)
            existing = Notification.objects.filter(
                title__icontains="Cash Balance Low",
                created_at__gte=two_hours_ago,
            ).exists()
            
            if not existing:
                create_announcement_notification(
                    title=f"⚠️ Cash Balance Low",
                    message=f"Only Rs. {balance:,.2f} available in cash. Refill soon!",
                    notification_type='warning',
                    category='payments',
                    link='/cash/',
                )
                logger.warning(f"⚠️ Cash low: Rs. {balance}")
    except Exception as e:
        logger.error(f"❌ Cash low error: {e}")


# ========================================== #
# CUSTOMER SIGNALS 👥                        #
# ========================================== #

@receiver(post_save, sender='app.Customer')
def new_customer_signal(sender, instance, created, **kwargs):
    """Naya customer add ho"""
    if not created:
        return
    
    try:
        name = instance.name
        code = instance.customer_code or 'N/A'
        group = instance.group.name if instance.group else 'None'
        
        create_announcement_notification(
            title=f"👤 New Customer",
            message=f"{name} ({code}) - Group: {group}",
            notification_type='success',
            category='customers',
            link=f'/customers/{instance.id}/',
        )
        logger.info(f"👤 New customer: {name}")
    except Exception as e:
        logger.error(f"❌ New customer error: {e}")


# ========================================== #
# VENDOR SIGNALS 🏢                          #
# ========================================== #

@receiver(post_save, sender='app.Vendor')
def new_vendor_signal(sender, instance, created, **kwargs):
    """Naya vendor add ho"""
    if not created:
        return
    
    try:
        name = instance.name
        code = instance.vendor_code or 'N/A'
        
        create_announcement_notification(
            title=f"🏢 New Vendor",
            message=f"{name} ({code}) added to system",
            notification_type='info',
            category='vendors',
            link=f'/vendors/{instance.id}/',
        )
        logger.info(f"🏢 New vendor: {name}")
    except Exception as e:
        logger.error(f"❌ New vendor error: {e}")


# ========================================== #
# SHAREHOLDER / DIVIDEND SIGNALS 👥          #
# ========================================== #

@receiver(post_save, sender='app.Shareholder')
def new_shareholder_signal(sender, instance, created, **kwargs):
    """Naya shareholder add ho"""
    if not created:
        return
    
    try:
        name = instance.name
        code = instance.shareholder_code or 'N/A'
        
        create_announcement_notification(
            title=f"👥 New Shareholder",
            message=f"{name} ({code}) registered",
            notification_type='success',
            category='shareholders',
            link=f'/shareholders/{instance.id}/',
        )
        logger.info(f"👥 New shareholder: {name}")
    except Exception as e:
        logger.error(f"❌ New shareholder error: {e}")


@receiver(post_save, sender='app.Dividend')
def dividend_declared_signal(sender, instance, created, **kwargs):
    """Dividend declare ho"""
    if not created:
        return
    
    try:
        amount = instance.amount_per_share
        total = instance.total_amount
        
        create_announcement_notification(
            title=f"💰 Dividend Declared",
            message=f"Rs. {amount:,.2f} per share - Total: Rs. {total:,.2f}",
            notification_type='success',
            category='shareholders',
            link=f'/dividends/{instance.id}/',
        )
        logger.info(f"💰 Dividend declared: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Dividend error: {e}")


@receiver(post_save, sender='app.BalanceDividend')
def balance_dividend_signal(sender, instance, created, **kwargs):
    """Balance dividend declare ho"""
    if not created:
        return
    
    try:
        total = instance.total_profit
        percentage = instance.dividend_percentage
        
        create_announcement_notification(
            title=f"⚖️ Balance Dividend Declared",
            message=f"Profit: Rs. {total:,.2f} - Distribution: {percentage}%",
            notification_type='success',
            category='shareholders',
            link=f'/balance-dividend/{instance.id}/',
        )
        logger.info(f"⚖️ Balance dividend: Rs. {total}")
    except Exception as e:
        logger.error(f"❌ Balance dividend error: {e}")


# ========================================== #
# SHARE TRANSFER SIGNALS 🔄                  #
# ========================================== #

@receiver(post_save, sender='app.ShareTransfer')
def share_transfer_signal(sender, instance, created, **kwargs):
    """Share transfer hui"""
    try:
        status = instance.status
        quantity = instance.quantity
        from_sh = instance.from_shareholder.name if instance.from_shareholder else 'N/A'
        to_sh = instance.to_shareholder.name if instance.to_shareholder else 'N/A'
        
        if created and status == 'pending':
            create_announcement_notification(
                title=f"🔄 Share Transfer Request",
                message=f"{quantity} shares from {from_sh} to {to_sh}",
                notification_type='info',
                category='shareholders',
                link=f'/transfers/{instance.id}/',
            )
            logger.info(f"🔄 Transfer request: {quantity} shares")
        
        elif not created and status == 'completed':
            create_announcement_notification(
                title=f"✅ Share Transfer Complete",
                message=f"{quantity} shares transferred from {from_sh} to {to_sh}",
                notification_type='success',
                category='shareholders',
                link=f'/transfers/{instance.id}/',
            )
            logger.info(f"✅ Transfer complete: {quantity} shares")
    except Exception as e:
        logger.error(f"❌ Transfer error: {e}")


# ========================================== #
# LOAN SIGNALS 🏦                            #
# ========================================== #

@receiver(post_save, sender='app.Loan')
def loan_created_signal(sender, instance, created, **kwargs):
    """Naya loan liya"""
    if not created:
        return
    
    try:
        amount = instance.principal_amount
        lender = instance.lender_name
        
        create_announcement_notification(
            title=f"🏦 New Loan",
            message=f"Rs. {amount:,.2f} from {lender}",
            notification_type='warning',
            category='loans',
            link=f'/loans/{instance.id}/',
        )
        logger.info(f"🏦 New loan: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Loan error: {e}")


@receiver(post_save, sender='app.LoanGiven')
def loan_given_signal(sender, instance, created, **kwargs):
    """Kisi ko loan diya"""
    if not created:
        return
    
    try:
        amount = instance.principal_amount
        borrower = instance.borrower_name
        
        create_announcement_notification(
            title=f"📤 Loan Given",
            message=f"Rs. {amount:,.2f} to {borrower}",
            notification_type='info',
            category='loans',
            link=f'/loans-given/{instance.id}/',
        )
        logger.info(f"📤 Loan given: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Loan given error: {e}")


# ========================================== #
# EXPENSE SIGNALS 💸                         #
# ========================================== #

@receiver(post_save, sender='app.Expense')
def expense_created_signal(sender, instance, created, **kwargs):
    """Naya expense"""
    if not created:
        return
    
    try:
        amount = instance.amount
        category = instance.category.name if instance.category else 'General'
        description = instance.description[:50]
        
        if amount >= 10000:
            create_announcement_notification(
                title=f"💸 Big Expense",
                message=f"Rs. {amount:,.2f} - {category} - {description}",
                notification_type='warning',
                category='expenses',
                link=f'/expenses/{instance.id}/',
            )
            logger.info(f"💸 Big expense: Rs. {amount}")
    except Exception as e:
        logger.error(f"❌ Expense error: {e}")


@receiver(post_save, sender='app.Expense')
def expense_paid_signal(sender, instance, created, **kwargs):
    """Expense paid"""
    try:
        if not created and instance.status == 'paid':
            amount = instance.amount
            category = instance.category.name if instance.category else 'General'
            
            create_announcement_notification(
                title=f"✅ Expense Paid",
                message=f"Rs. {amount:,.2f} - {category}",
                notification_type='info',
                category='expenses',
                link=f'/expenses/{instance.id}/',
            )
    except Exception as e:
        logger.error(f"❌ Expense paid error: {e}")


# ========================================== #
# OPERATIONS SIGNALS 📋                      #
# ========================================== #

@receiver(post_save, sender='app.OperationTask')
def task_completed_signal(sender, instance, created, **kwargs):
    """Task complete hua"""
    try:
        if not created and instance.status == 'completed':
            title = instance.title[:50]
            
            create_announcement_notification(
                title=f"✅ Task Completed",
                message=f"{title}",
                notification_type='success',
                category='operations',
                link=f'/operations/tasks/{instance.id}/',
            )
            logger.info(f"✅ Task completed: {title}")
    except Exception as e:
        logger.error(f"❌ Task signal error: {e}")


@receiver(post_save, sender='app.OperationTask')
def task_overdue_signal(sender, instance, created, **kwargs):
    """Task overdue ho gaya"""
    try:
        if instance.status in ['pending', 'in_progress']:
            if instance.due_date and instance.due_date < now():
                one_day_ago = now() - timedelta(hours=24)
                existing = Notification.objects.filter(
                    title__icontains=f"Overdue: {instance.title[:30]}",
                    created_at__gte=one_day_ago,
                ).exists()
                
                if not existing:
                    create_announcement_notification(
                        title=f"⏰ Overdue: {instance.title[:50]}",
                        message=f"Task is overdue. Please complete it.",
                        notification_type='warning',
                        category='operations',
                        link=f'/operations/tasks/{instance.id}/',
                    )
                    logger.warning(f"⏰ Task overdue: {instance.title}")
    except Exception as e:
        logger.error(f"❌ Overdue task error: {e}")


@receiver(post_save, sender='app.BusinessOperationPlan')
def plan_created_signal(sender, instance, created, **kwargs):
    """Naya plan bana"""
    if not created:
        return
    
    try:
        title = instance.title[:50]
        dept = instance.get_department_display()
        
        create_announcement_notification(
            title=f"📋 New Plan Created",
            message=f"{title} - {dept}",
            notification_type='info',
            category='operations',
            link=f'/operations/plans/{instance.id}/',
        )
        logger.info(f"📋 Plan created: {title}")
    except Exception as e:
        logger.error(f"❌ Plan signal error: {e}")


# ========================================== #
# KPI SIGNALS 📊                             #
# ========================================== #

@receiver(post_save, sender='app.OperationsKPI')
def kpi_status_signal(sender, instance, created, **kwargs):
    """KPI status change"""
    try:
        status = instance.status
        name = instance.name
        progress = instance.progress_percent
        
        if status == 'critical':
            create_announcement_notification(
                title=f"🔴 Critical KPI: {name}",
                message=f"Only {progress:.1f}% achieved - Immediate action needed!",
                notification_type='danger',
                category='operations',
                link=f'/operations/kpi/{instance.id}/',
            )
            logger.warning(f"🔴 Critical KPI: {name} - {progress}%")
        
        elif status == 'achieved':
            create_announcement_notification(
                title=f"🎉 KPI Achieved: {name}",
                message=f"Congratulations! {progress:.1f}% achieved",
                notification_type='success',
                category='operations',
                link=f'/operations/kpi/{instance.id}/',
            )
            logger.info(f"🎉 KPI achieved: {name}")
    except Exception as e:
        logger.error(f"❌ KPI signal error: {e}")


# ========================================== #
# TARGET SIGNALS 🎯                          #
# ========================================== #

@receiver(post_save, sender='app.SalesTarget')
def target_created_signal(sender, instance, created, **kwargs):
    """Naya target set hua"""
    if not created:
        return
    
    try:
        target = instance.target_amount
        period = instance.get_target_type_display()
        
        create_announcement_notification(
            title=f"🎯 New Target Set",
            message=f"{period}: Rs. {target:,.2f}",
            notification_type='info',
            category='operations',
            link=f'/targets/',
        )
        logger.info(f"🎯 Target set: Rs. {target}")
    except Exception as e:
        logger.error(f"❌ Target signal error: {e}")


# ========================================== #
# SERVICE SIGNALS 🛠️                         #
# ========================================== #

@receiver(post_save, sender='app.ServiceRequest')
def service_request_signal(sender, instance, created, **kwargs):
    """Naya service request"""
    if not created:
        return
    
    try:
        customer = instance.customer.name if instance.customer else 'Customer'
        service = instance.service.name if instance.service else 'Service'
        request_no = instance.request_no or 'N/A'
        
        create_announcement_notification(
            title=f"🛠️ New Service Request",
            message=f"{request_no} - {customer} - {service}",
            notification_type='info',
            category='services',
            link=f'/services/requests/{instance.id}/',
        )
        logger.info(f"🛠️ Service request: {request_no}")
    except Exception as e:
        logger.error(f"❌ Service request error: {e}")


# ========================================== #
# PRODUCTION SIGNALS 🏭                      #
# ========================================== #

@receiver(post_save, sender='app.ProductionOrder')
def production_order_signal(sender, instance, created, **kwargs):
    """Naya production order"""
    if not created:
        return
    
    try:
        order_no = instance.order_no or 'N/A'
        product = instance.product.name if instance.product else 'Product'
        qty = instance.quantity
        
        create_announcement_notification(
            title=f"🏭 Production Order Created",
            message=f"{order_no} - {product} x {qty:.0f} units",
            notification_type='info',
            category='production',
            link=f'/production/orders/{instance.id}/',
        )
        logger.info(f"🏭 Production order: {order_no}")
    except Exception as e:
        logger.error(f"❌ Production signal error: {e}")


# ========================================== #
# SESSION SIGNAL 👋                          #
# ========================================== #

@receiver(post_save, sender='app.SessionLog')
def user_session_signal(sender, instance, created, **kwargs):
    """User login/logout"""
    if not created:
        return
    
    try:
        user = instance.user
        if not user:
            return
        
        if instance.is_active:
            create_announcement_notification(
                title=f"👋 User Login",
                message=f"{user.username} logged in from {instance.ip_address or 'Unknown'}",
                notification_type='info',
                category='system',
                user=user,
            )
            logger.info(f"👋 Login: {user.username}")
    except Exception as e:
        logger.error(f"❌ Session signal error: {e}")


# ========================================== #
# EXPENSE - BUDGET UPDATE                    #
# ========================================== #

@receiver(post_save, sender=Expense)
def update_budget_on_expense(sender, instance, created, **kwargs):
    """Update budget used amount when expense is created/updated"""
    if instance.budget and instance.status in ['approved', 'paid']:
        instance.budget.calculate_used()
    
    if instance.budget:
        goals = BudgetGoal.objects.filter(
            budget=instance.budget,
            category=instance.category,
            status='active'
        )
        for goal in goals:
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
# BUDGET GOAL SIGNAL                         #
# ========================================== #

@receiver(post_save, sender=BudgetGoal)
def budget_goal_created(sender, instance, created, **kwargs):
    """When goal is created, calculate initial progress"""
    if created:
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
# SYSTEM SETTINGS SIGNAL                     #
# ========================================== #

@receiver(post_save, sender=SystemSetting)
def system_setting_changed(sender, instance, **kwargs):
    """Log when system settings change"""
    logger.info(f"⚙️ System setting changed: {instance.setting_key} = {instance.setting_value}")


# ========================================== #
# BULK PROCESS HELPER                        #
# ========================================== #

def bulk_process_pending_deductions(user=None):
    """Process all pending shareholder deductions"""
    pending = Purchase.objects.filter(shareholder_deduction_done=False)
    
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
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'bill_no': purchase.bill_no,
                        'error': str(result)
                    })
                    
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({
                'bill_no': purchase.bill_no,
                'error': str(e)
            })
    
    return results


# ========================================== #
# LOG INITIALIZED                            #
# ========================================== #

logger.info("✅ All signals loaded successfully")