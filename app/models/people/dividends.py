"""Models: people/dividends (split from the former shareholders.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
import logging
from django.db.models import Q
from .shareholders import Shareholder
logger = logging.getLogger(__name__)

class Dividend(models.Model):
    """Dividend declaration and distribution with custom percentage allocations"""
    
    STATUS_CHOICES = [
        ('declared', 'Declared'),
        ('approved', 'Approved'),
        ('distributed', 'Distributed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # ============================================
    # BASIC INFORMATION
    # ============================================
    dividend_no = models.CharField(max_length=20, unique=True, editable=False)
    amount_per_share = models.DecimalField(max_digits=15, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ============================================
    # DATES
    # ============================================
    declaration_date = models.DateField()
    record_date = models.DateField(help_text="Date to determine eligible shareholders")
    payment_date = models.DateField(null=True, blank=True)
    
    # ============================================
    # STATUS
    # ============================================
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='declared')
    is_interim = models.BooleanField(default=False, help_text="Interim dividend")
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # ALLOCATION PERCENTAGES
    # ============================================
    admin_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Admin's percentage of dividend (default: 5%)"
    )
    manager_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=28.00,
        help_text="Store Manager's percentage of dividend (default: 28%)"
    )
    shareholders_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=67.00,
        help_text="Shareholders' percentage of dividend (default: 67%)"
    )
    
    # ============================================
    # ALLOCATED AMOUNTS
    # ============================================
    admin_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Admin"
    )
    manager_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Store Manager"
    )
    shareholders_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Amount allocated to Shareholders"
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_dividends'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Dividends"
        ordering = ['-declaration_date']
        indexes = [
            models.Index(fields=['dividend_no']),
            models.Index(fields=['status']),
            models.Index(fields=['declaration_date']),
        ]
    
    def __str__(self):
        return f"Dividend #{self.dividend_no} - Rs. {self.amount_per_share:,.2f}/share"
    
    # ============================================
    # TOTAL ELIGIBLE SHARES
    # ============================================
    def total_eligible_shares(self):
        """Total shares eligible for this dividend"""
        return Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    # ============================================
    # CALCULATE TOTAL AMOUNT
    # ============================================
    def calculate_total_amount(self):
        """Calculate total dividend amount"""
        total_shares = self.total_eligible_shares()
        return total_shares * self.amount_per_share
    
    # ============================================
    # ✅ FIXED: CALCULATE ALLOCATIONS (NO SAVE CALL)
    # ============================================
    def calculate_allocation(self):
        """
        Calculate dividend allocation based on percentages
        ✅ FIXED: Removed self.save() call to prevent recursion
        """
        total = self.total_amount
        
        self.admin_amount = (self.admin_percentage / 100) * total
        self.manager_amount = (self.manager_percentage / 100) * total
        self.shareholders_amount = (self.shareholders_percentage / 100) * total
        
        return {
            'admin': self.admin_amount,
            'manager': self.manager_amount,
            'shareholders': self.shareholders_amount
        }
    
    # ============================================
    # ✅ CHECK: Can create new dividend?
    # ============================================
    @classmethod
    def can_create_new_dividend(cls):
        """
        Check if a new dividend can be created
        Returns: (bool, message)
        """
        # Check if any active dividend exists
        active_dividends = cls.objects.filter(
            status__in=['declared', 'approved']
        ).exists()
        
        if active_dividends:
            return False, "❌ An active dividend already exists! Please complete or cancel it first."
        
        # Check if any dividend is pending payment
        pending_payments = DividendPayment.objects.filter(status='pending').exists()
        if pending_payments:
            return False, "❌ There are pending dividend payments! Please complete them first."
        
        return True, "✅ You can create a new dividend."
    
    # ============================================
    # ✅ CHECK: Can modify this dividend?
    # ============================================
    def can_modify(self):
        """
        Check if this dividend can be modified
        Returns: (bool, message)
        """
        if self.status == 'distributed':
            return False, "❌ This dividend is already distributed and cannot be modified!"
        
        if self.status == 'cancelled':
            return False, "❌ This dividend is cancelled and cannot be modified!"
        
        # Check if payments exist
        if self.payments.exists():
            paid_count = self.payments.filter(status='paid').count()
            if paid_count > 0:
                return False, f"❌ {paid_count} payment(s) already made! Cannot modify this dividend."
        
        return True, "✅ You can modify this dividend."
    
    # ============================================
    # ✅ CHECK: Can delete this dividend?
    # ============================================
    def can_delete(self):
        """
        Check if this dividend can be deleted
        Returns: (bool, message)
        """
        if self.status == 'distributed':
            return False, "❌ Cannot delete a distributed dividend!"
        
        if self.status == 'approved':
            return False, "❌ Cannot delete an approved dividend! Cancel it first."
        
        if self.payments.filter(status='paid').exists():
            return False, "❌ Cannot delete dividend with paid payments!"
        
        return True, "✅ You can delete this dividend."
    
    # ============================================
    # ✅ CANCEL DIVIDEND
    # ============================================
    def cancel_dividend(self, user, reason=""):
        """
        Cancel a dividend
        ✅ Only if not distributed
        """
        if self.status == 'distributed':
            raise ValidationError("❌ Cannot cancel a distributed dividend!")
        
        if self.status == 'cancelled':
            raise ValidationError("❌ This dividend is already cancelled!")
        
        # Check if any paid payments exist
        if self.payments.filter(status='paid').exists():
            raise ValidationError(
                "❌ Cannot cancel dividend! Some payments have already been made. "
                "Please refund them first."
            )
        
        # Cancel all pending payments
        pending_payments = self.payments.filter(status='pending')
        for payment in pending_payments:
            payment.status = 'failed'
            payment.notes = f"Cancelled due to dividend cancellation: {reason}"
            payment.save()
        
        self.status = 'cancelled'
        self.notes = f"{self.notes}\nCancelled by {user.username}: {reason}".strip()
        self.save()
        
        # Create notification
        try:
            from .. import Notification
            Notification.send(
                user=user,
                title="❌ Dividend Cancelled",
                message=f"Dividend #{self.dividend_no} has been cancelled. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments'
            )
        except Exception:
            pass
        
        return True
    
    # ============================================
    # ✅ SAVE METHOD (NO RECURSION)
    # ============================================
    def save(self, *args, **kwargs):
        """
        Save dividend with allocations
        ✅ FIXED: No recursive calls
        ✅ ADDED: Prevent duplicate/approved dividend modification
        """
        
        # ============================================
        # 🔒 CHECK: If updating existing dividend
        # ============================================
        if self.pk:
            old_dividend = Dividend.objects.filter(pk=self.pk).first()
            
            if old_dividend:
                # 🔒 Cannot modify distributed dividend
                if old_dividend.status == 'distributed':
                    raise ValidationError(
                        "❌ This dividend is already distributed and cannot be modified!"
                    )
                
                # 🔒 Cannot modify cancelled dividend
                if old_dividend.status == 'cancelled':
                    raise ValidationError(
                        "❌ This dividend is cancelled and cannot be modified!"
                    )
                
                # 🔒 Cannot modify if payments exist
                if old_dividend.payments.filter(status='paid').exists():
                    raise ValidationError(
                        "❌ Cannot modify dividend! Payments have already been made."
                    )
                
                # 🔒 Cannot change status from approved back to declared
                if old_dividend.status == 'approved' and self.status == 'declared':
                    raise ValidationError(
                        "❌ Cannot change status from 'Approved' back to 'Declared'!"
                    )
        
        # ============================================
        # 🔒 CHECK: If creating new dividend
        # ============================================
        else:
            # Check if a dividend already exists
            active_dividends = Dividend.objects.filter(
                status__in=['declared', 'approved', 'distributed']
            ).exists()
            
            if active_dividends:
                raise ValidationError(
                    "❌ A dividend already exists! Only one dividend can be active at a time. "
                    "Please complete or cancel the existing dividend first."
                )
            
            # Check if any pending payments from previous dividend
            pending_payments = DividendPayment.objects.filter(status='pending').exists()
            if pending_payments:
                raise ValidationError(
                    "❌ There are pending dividend payments! Please complete them before creating a new dividend."
                )
        
        # ============================================
        # Auto-generate dividend number
        # ============================================
        if not self.dividend_no:
            last_dividend = Dividend.objects.order_by('-id').first()
            if last_dividend and last_dividend.dividend_no:
                try:
                    last_num = int(last_dividend.dividend_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.dividend_no = f'DIV-{new_num}'
        
        # Calculate total amount
        self.total_amount = self.calculate_total_amount()
        
        # ✅ Calculate allocations (NO SAVE CALL INSIDE)
        self.calculate_allocation()
        
        # ✅ Single save call
        super().save(*args, **kwargs)
    
    # ============================================
    # GENERATE ALLOCATIONS
    # ============================================
    def generate_allocations(self, user):
        """Generate allocation records for all parties"""
        
        # Admin Allocation
        admin_allocation, admin_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='admin',
            defaults={
                'recipient_name': 'Admin',
                'percentage': self.admin_percentage,
                'amount': self.admin_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not admin_created and admin_allocation.amount != self.admin_amount:
            admin_allocation.amount = self.admin_amount
            admin_allocation.percentage = self.admin_percentage
            admin_allocation.save(update_fields=['amount', 'percentage'])
        
        # Manager Allocation
        manager_users = User.objects.filter(groups__name='Store Manager').first()
        manager_name = manager_users.get_full_name() if manager_users else 'Store Manager'
        
        manager_allocation, manager_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='manager',
            defaults={
                'recipient_name': manager_name,
                'recipient_id': manager_users.id if manager_users else None,
                'percentage': self.manager_percentage,
                'amount': self.manager_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not manager_created and manager_allocation.amount != self.manager_amount:
            manager_allocation.amount = self.manager_amount
            manager_allocation.percentage = self.manager_percentage
            manager_allocation.save(update_fields=['amount', 'percentage'])
        
        # Shareholders Allocation
        shareholders_allocation, shareholders_created = DividendAllocation.objects.get_or_create(
            dividend=self,
            allocation_type='shareholders',
            defaults={
                'recipient_name': 'All Shareholders',
                'percentage': self.shareholders_percentage,
                'amount': self.shareholders_amount,
                'is_paid': False,
                'created_by': user
            }
        )
        if not shareholders_created and shareholders_allocation.amount != self.shareholders_amount:
            shareholders_allocation.amount = self.shareholders_amount
            shareholders_allocation.percentage = self.shareholders_percentage
            shareholders_allocation.save(update_fields=['amount', 'percentage'])
        
        return {
            'admin': admin_allocation,
            'manager': manager_allocation,
            'shareholders': shareholders_allocation
        }
    
    # ============================================
    # GENERATE SHAREHOLDER PAYMENTS
    # ============================================
    def generate_shareholder_payments(self, user):
        """Generate dividend payments for all shareholders"""
        
        if self.status not in ['declared', 'approved']:
            raise ValidationError("Dividend must be declared or approved to generate payments!")
        
        # 🔒 Check if payments already exist
        if self.payments.exists():
            raise ValidationError(
                f"❌ Payments already exist for this dividend! "
                f"Total: {self.payments.count()} payments."
            )
        
        shareholders = Shareholder.objects.filter(status='active')
        count = 0
        
        for shareholder in shareholders:
            shares = shareholder.total_shares()
            if shares > 0:
                amount = shares * self.amount_per_share
                DividendPayment.objects.get_or_create(
                    dividend=self,
                    shareholder=shareholder,
                    defaults={
                        'shares_held': shares,
                        'amount': amount,
                        'status': 'pending'
                    }
                )
                count += 1
        
        self.status = 'approved'
        # ✅ Single save, no recursion
        self.save(update_fields=['status'])
        
        return count
    
    # ============================================
    # MARK AS DISTRIBUTED
    # ============================================
    def mark_distributed(self, user):
        """
        Mark entire dividend as distributed
        ✅ Only if all payments are paid
        """
        if self.status == 'distributed':
            raise ValidationError("❌ This dividend is already distributed!")
        
        # Check if all payments are paid
        pending_payments = self.payments.filter(status='pending')
        if pending_payments.exists():
            raise ValidationError(
                f"❌ Cannot mark as distributed! {pending_payments.count()} payments are still pending."
            )
        
        self.status = 'distributed'
        self.payment_date = now()
        self.save(update_fields=['status', 'payment_date'])
        
        # Create notification
        try:
            from .. import Notification
            Notification.send(
                user=user,
                title="✅ Dividend Distributed",
                message=f"Dividend #{self.dividend_no} of Rs. {self.total_amount:,.2f} has been fully distributed.",
                notification_type='success',
                category='payments'
            )
        except Exception:
            pass
        
        return True
    
    # ============================================
    # GET ALLOCATION SUMMARY
    # ============================================
    def get_allocation_summary(self):
        """Get allocation summary with percentages and amounts"""
        return {
            'admin': {
                'percentage': self.admin_percentage,
                'amount': self.admin_amount,
                'is_paid': self.allocations.filter(allocation_type='admin', is_paid=True).exists()
            },
            'manager': {
                'percentage': self.manager_percentage,
                'amount': self.manager_amount,
                'is_paid': self.allocations.filter(allocation_type='manager', is_paid=True).exists()
            },
            'shareholders': {
                'percentage': self.shareholders_percentage,
                'amount': self.shareholders_amount,
                'is_paid': self.allocations.filter(allocation_type='shareholders', is_paid=True).exists()
            }
        }
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def admin_allocation_paid(self):
        return self.allocations.filter(allocation_type='admin', is_paid=True).exists()
    
    @property
    def manager_allocation_paid(self):
        return self.allocations.filter(allocation_type='manager', is_paid=True).exists()
    
    @property
    def shareholders_allocation_paid(self):
        return self.allocations.filter(allocation_type='shareholders', is_paid=True).exists()
    
    @property
    def all_allocations_paid(self):
        return (self.admin_allocation_paid and 
                self.manager_allocation_paid and 
                self.shareholders_allocation_paid)
    
    @property
    def total_paid_allocations(self):
        total = 0
        for alloc in self.allocations.filter(is_paid=True):
            total += alloc.amount
        return total
    
    @property
    def total_pending_allocations(self):
        total = 0
        for alloc in self.allocations.filter(is_paid=False):
            total += alloc.amount
        return total
    
    @property
    def status_badge(self):
        colors = {
            'declared': 'primary',
            'approved': 'warning',
            'distributed': 'success',
            'cancelled': 'danger'
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def is_active(self):
        return self.status not in ['cancelled', 'distributed']
    
    @property
    def can_generate_payments(self):
        return self.status in ['declared', 'approved'] and not self.payments.exists()
    
    @property
    def total_payments(self):
        return self.payments.count()
    
    @property
    def total_paid_payments(self):
        return self.payments.filter(status='paid').count()
    
    @property
    def total_pending_payments(self):
        return self.payments.filter(status='pending').count()


class DividendAllocation(models.Model):
    """Track dividend allocations to different parties"""
    
    ALLOCATION_TYPES = [
        ('admin', '👑 Admin'),
        ('manager', '👔 Store Manager'),
        ('shareholders', '👥 Shareholders'),
        ('individual', '👤 Individual Shareholder'),
    ]
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    dividend = models.ForeignKey(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='allocations'
    )
    allocation_type = models.CharField(max_length=20, choices=ALLOCATION_TYPES)
    recipient_name = models.CharField(max_length=200, blank=True, null=True)
    recipient_id = models.PositiveIntegerField(null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Dividend Allocations"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dividend']),
            models.Index(fields=['allocation_type']),
            models.Index(fields=['is_paid']),
        ]
    
    def __str__(self):
        return f"{self.dividend.dividend_no} - {self.get_allocation_type_display()} - Rs. {self.amount:,.2f}"
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def status_badge(self):
        if self.is_paid:
            return '<span class="badge bg-success">✅ Paid</span>'
        return '<span class="badge bg-warning">⏳ Pending</span>'
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def formatted_percentage(self):
        return f"{self.percentage}%"
    
    # ============================================
    # ✅ MARK AS PAID (NO RECURSION)
    # ============================================
    def mark_paid(self, user, payment_method=None, reference_no=None):
        """
        Mark allocation as paid
        ✅ FIXED: No recursion, proper transaction handling
        """
        from django.db import transaction
        
        # 🔒 Check if already paid
        if self.is_paid:
            raise ValidationError("This allocation is already marked as paid!")
        
        try:
            with transaction.atomic():
                # 🔒 Lock the record
                allocation = DividendAllocation.objects.select_for_update().get(pk=self.pk)
                
                if allocation.is_paid:
                    raise ValidationError(
                        "❌ This allocation was just marked as paid by another process!"
                    )
                
                # Update allocation status
                self.is_paid = True
                self.payment_date = now()
                self.payment_method = payment_method
                self.reference_no = reference_no
                
                # ✅ Use update() to avoid recursive save signals
                DividendAllocation.objects.filter(pk=self.pk).update(
                    is_paid=True,
                    payment_date=self.payment_date,
                    payment_method=payment_method,
                    reference_no=reference_no
                )
                
                # For admin/manager, deduct from cash balance
                if self.allocation_type in ['admin', 'manager']:
                    from .. import CashBalance
                    
                    current_balance = CashBalance.get_balance()
                    if current_balance < self.amount:
                        raise ValidationError(
                            f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                            f"Required: Rs. {self.amount:,.2f}"
                        )
                    
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='withdraw',
                        user=user,
                        description=f"Dividend allocation - {self.get_allocation_type_display()} - {self.dividend.dividend_no}"
                    )
                
                # Create notification
                try:
                    from .. import Notification
                    Notification.send(
                        user=user,
                        title="💰 Dividend Allocation Paid",
                        message=f"Dividend allocation of Rs. {self.amount:,.2f} for {self.get_allocation_type_display()} has been paid.",
                        notification_type='success',
                        category='payments',
                        link=f"/admin/app/dividend/{self.dividend.id}/change/"
                    )
                except Exception:
                    pass
                
                return True
                
        except ValidationError as e:
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error marking dividend allocation as paid: {str(e)}")
            raise ValidationError(f"Failed to mark allocation as paid: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Save allocation with proper validation"""
        # 🔒 Prevent changing paid allocation
        if self.pk:
            old = DividendAllocation.objects.filter(pk=self.pk).first()
            if old and old.is_paid and not self.is_paid:
                raise ValidationError(
                    "❌ Cannot change status of a paid allocation!"
                )
        
        super().save(*args, **kwargs)      


class DividendPayment(models.Model):
    """Individual dividend payment to shareholder with cash balance support"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    dividend = models.ForeignKey(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='dividend_payments'
    )
    shares_held = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # PAYMENT SETTINGS
    # ============================================
    paid_to_shareholder_balance = models.BooleanField(
        default=True,
        help_text="If True, dividend is paid to shareholder's cash balance. If False, paid as separate payment."
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='processed_dividend_payments'
    )
    
    class Meta:
        verbose_name_plural = "📤 Dividend Payments"
        ordering = ['-created_at']
        unique_together = ['dividend', 'shareholder']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(status='paid', payment_date__isnull=True),
                name='paid_payment_must_have_date'
            )
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['dividend', 'shareholder']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.amount:,.2f}"
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'pending':
            return '<span class="badge bg-warning">⏳ Pending</span>'
        else:
            return '<span class="badge bg-danger">❌ Failed</span>'
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    # ============================================
    # ✅ MARK AS PAID - COMPLETE PROTECTION
    # ============================================
    def mark_paid(self, payment_method=None, reference_no=None, processed_by=None):
        """
        Mark dividend as paid - the Shareholder RECEIVES the money
        ✅ FIXED: Complete double-payment protection
        """
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        # ============================================
        # 🔒 CHECK 1: Already paid?
        # ============================================
        if self.status == 'paid':
            raise ValidationError(
                "❌ This dividend payment is already marked as paid! "
                "Double payment is not allowed."
            )
        
        # ============================================
        # 🔒 CHECK 2: Amount validation
        # ============================================
        if self.amount <= 0:
            raise ValidationError("Dividend amount must be greater than zero!")
        
        # ============================================
        # 🔒 CHECK 3: Shareholder exists?
        # ============================================
        if self.paid_to_shareholder_balance and not self.shareholder:
            raise ValidationError("Shareholder not found!")
        
        try:
            with transaction.atomic():
                # ============================================
                # 🔒 CHECK 4: Lock the record for update
                # ============================================
                payment = DividendPayment.objects.select_for_update().get(pk=self.pk)
                
                # Double-check (prevent race condition)
                if payment.status == 'paid':
                    raise ValidationError(
                        "❌ This payment was just marked as paid by another process! "
                        "Please refresh and try again."
                    )
                
                # ============================================
                # ✅ PAY TO SHAREHOLDER (DEPOSIT)
                # ============================================
                if self.paid_to_shareholder_balance:
                    # 🔒 Check if shareholder already received this dividend
                    existing_transaction = ShareholderCashTransaction.objects.filter(
                        shareholder=self.shareholder,
                        dividend_payment=self,
                        transaction_type='dividend'
                    ).exists()
                    
                    if existing_transaction:
                        raise ValidationError(
                            f"❌ {self.shareholder.name} has already received this dividend payment!"
                        )
                    
                    # ✅ DEPOSIT to shareholder
                    new_balance = ShareholderCashBalance.deposit(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        user=processed_by or self.processed_by,
                        description=f"Dividend #{self.dividend.dividend_no} - {self.amount:,.2f} for {self.shares_held} shares"
                    )
                    
                    # ✅ Create transaction record
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        transaction_type='dividend',
                        balance_after=new_balance,
                        description=f"Dividend #{self.dividend.dividend_no} payment",
                        reference_no=reference_no,
                        dividend_payment=self,
                        created_by=processed_by or self.processed_by
                    )
                
                # ============================================
                # ✅ COMPANY CASH DEDUCT
                # ============================================
                from .. import CashBalance
                current_balance = CashBalance.get_balance()
                if current_balance < self.amount:
                    raise ValidationError(
                        f"Insufficient company cash balance! "
                        f"Available: Rs. {current_balance:,.2f}, Required: Rs. {self.amount:,.2f}"
                    )
                
                CashBalance.update_balance(
                    amount=self.amount,
                    transaction_type='withdraw',
                    user=processed_by or self.processed_by,
                    description=f"Dividend Payment #{self.dividend.dividend_no} to {self.shareholder.name}"
                )
                
                # ============================================
                # ✅ UPDATE PAYMENT STATUS
                # ============================================
                self.status = 'paid'
                self.payment_date = now()
                if payment_method:
                    self.payment_method = payment_method
                if reference_no:
                    self.reference_no = reference_no
                if processed_by:
                    self.processed_by = processed_by
                
                # ✅ Use update() to avoid recursion
                DividendPayment.objects.filter(pk=self.pk).update(
                    status='paid',
                    payment_date=self.payment_date,
                    payment_method=self.payment_method,
                    reference_no=self.reference_no,
                    processed_by=self.processed_by
                )
                
                # ============================================
                # ✅ UPDATE DIVIDEND STATUS IF ALL PAID
                # ============================================
                self._update_dividend_status()
                
                # ============================================
                # ✅ CREATE NOTIFICATION
                # ============================================
                try:
                    from .. import Notification
                    if self.processed_by:
                        Notification.send(
                            user=self.processed_by,
                            title="💰 Dividend Paid",
                            message=f"Dividend of Rs. {self.amount:,.2f} paid to {self.shareholder.name}",
                            notification_type='success',
                            category='payments'
                        )
                except Exception:
                    pass
                
                return True
                
        except ValidationError as e:
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error marking dividend payment as paid: {str(e)}")
            raise ValidationError(f"Failed to mark dividend as paid: {str(e)}")
    
    # ============================================
    # HELPER: Update Dividend Status
    # ============================================
    def _update_dividend_status(self):
        """
        Update dividend status based on payments
        Called after each payment is marked paid
        """
        total_payments = self.dividend.payments.count()
        paid_payments = self.dividend.payments.filter(status='paid').count()
        
        if total_payments > 0 and paid_payments == total_payments:
            self.dividend.status = 'distributed'
            self.dividend.payment_date = now()
            self.dividend.save(update_fields=['status', 'payment_date'])
    
    # ============================================
    # BULK PAYMENT
    # ============================================
    def mark_paid_bulk(self, processed_by=None):
        """Mark as paid without custom fields (for bulk operations)"""
        return self.mark_paid(
            payment_method='Bank Transfer',
            processed_by=processed_by
        )
    
    # ============================================
    # CANCEL PAYMENT
    # ============================================
    def cancel_payment(self, processed_by=None, reason=""):
        """
        Cancel a paid dividend payment - reverse the transaction
        """
        if self.status != 'paid':
            raise ValidationError("Only paid payments can be cancelled!")
        
        try:
            with transaction.atomic():
                if self.paid_to_shareholder_balance:
                    # 🔒 Check if shareholder has enough balance to refund
                    current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                    if current_balance < self.amount:
                        raise ValidationError(
                            f"Insufficient balance in {self.shareholder.name}'s account for refund! "
                            f"Available: Rs. {current_balance:,.2f}"
                        )
                    
                    # ✅ Deduct from shareholder
                    new_balance = ShareholderCashBalance.withdraw(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund #{self.dividend.dividend_no} - Cancelled: {reason}"
                    )
                    
                    # ✅ Create transaction record
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.shareholder,
                        amount=self.amount,
                        transaction_type='adjustment',
                        balance_after=new_balance,
                        description=f"Dividend refund - Cancelled: {reason}",
                        reference_no=self.reference_no,
                        dividend_payment=self,
                        created_by=processed_by or self.processed_by
                    )
                    
                    # ✅ Add back to company cash
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='deposit',
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund from {self.shareholder.name} - #{self.dividend.dividend_no}"
                    )
                    
                else:
                    # Direct refund to company cash
                    CashBalance.update_balance(
                        amount=self.amount,
                        transaction_type='deposit',
                        user=processed_by or self.processed_by,
                        description=f"Dividend refund - {self.shareholder.name} - #{self.dividend.dividend_no}"
                    )
                
                # ✅ Update payment status
                self.status = 'failed'
                self.notes = f"{self.notes}\nCancelled by {processed_by.username if processed_by else 'System'}: {reason}".strip()
                self.save()
                
                # ✅ Update dividend status
                self._update_dividend_status()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to cancel payment: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Save payment without recursion"""
        # 🔒 Prevent changing status of paid payments
        if self.pk:
            old = DividendPayment.objects.filter(pk=self.pk).first()
            if old and old.status == 'paid' and self.status != 'paid':
                raise ValidationError(
                    "❌ Cannot change status of a paid payment!"
                )
        
        super().save(*args, **kwargs)
    
    # ============================================
    # DELETE PROTECTION
    # ============================================
    def delete(self, *args, **kwargs):
        """🔒 Prevent deleting paid payments"""
        if self.status == 'paid':
            raise ValidationError(
                "❌ Cannot delete a paid dividend payment! "
                "Use cancel_payment() to reverse the transaction first."
            )
        super().delete(*args, **kwargs)


class BalanceDividend(models.Model):
    """
    Balance-Based Dividend Model
    Profit distribution based on balance usage (not shares)
    ✅ NEW: Refund + Profit system with Balance-Only option
    """
    
    # ========================================== #
    # STATUS CHOICES                            #
    # ========================================== #
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('declared', '📢 Declared'),
        ('approved', '✅ Approved'),
        ('distributed', '💰 Distributed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    DISTRIBUTION_TYPES = [
        ('balance_used', 'Based on Balance Used'),
        ('equal', 'Equal Distribution'),
        ('proportional', 'Proportional by Balance'),
    ]
    
    # ========================================== #
    # REFUND TYPES                              #
    # ========================================== #
    REFUND_TYPES = [
        ('full', 'Full Refund + Profit'),
        ('partial', 'Partial Refund + Profit'),
        ('profit_only', 'Profit Only'),
    ]
    
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    dividend_no = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False,
        verbose_name="Dividend Number"
    )
    total_profit = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Total Profit",
        help_text="Total profit from sales"
    )
    dividend_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=Decimal('50.00'),
        verbose_name="Dividend Percentage",
        help_text="% of profit to distribute"
    )
    
    # ========================================== #
    # DATES                                     #
    # ========================================== #
    declaration_date = models.DateField(
        verbose_name="Declaration Date",
        help_text="Date when dividend is declared"
    )
    record_date = models.DateField(
        verbose_name="Record Date",
        help_text="Date to check active shareholders"
    )
    distribution_date = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Distribution Date",
        help_text="Date when dividend was distributed"
    )
    
    # ========================================== #
    # DATE RANGE FOR PROFIT CALCULATION         #
    # ========================================== #
    profit_from_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Profit From Date",
        help_text="Start date for profit calculation"
    )
    profit_to_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Profit To Date",
        help_text="End date for profit calculation"
    )
    
    # ========================================== #
    # REFUND SETTINGS                           #
    # ========================================== #
    refund_type = models.CharField(
        max_length=20,
        choices=REFUND_TYPES,
        default='full',
        verbose_name="Refund Type",
        help_text="How to return deducted balance"
    )
    refund_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        verbose_name="Refund Percentage",
        help_text="% of deducted balance to refund (100 = full refund)"
    )
    total_refund_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Refund Amount"
    )
    total_payment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Payment Amount",
        help_text="Refund + Profit total"
    )
    
    # ========================================== #
    # STATUS & TYPE                             #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft'
    )
    distribution_type = models.CharField(
        max_length=20, 
        choices=DISTRIBUTION_TYPES, 
        default='balance_used'
    )
    notes = models.TextField(
        blank=True, 
        null=True,
        verbose_name="Notes"
    )
    
    # ========================================== #
    # TRACK USED SALES                          #
    # ========================================== #
    used_sales = models.ManyToManyField(
        'Sale',
        blank=True,
        related_name='balance_dividends',
        help_text="Sales used in this dividend"
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_balance_dividends'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Balance-Based Dividends"
        ordering = ['-declaration_date']
        indexes = [
            models.Index(fields=['dividend_no']),
            models.Index(fields=['status']),
            models.Index(fields=['declaration_date']),
        ]
    
    def __str__(self):
        return f"BD-{self.dividend_no} - {self.declaration_date.strftime('%B %Y')}"
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def amount_to_distribute(self):
        """Calculate total profit amount to distribute"""
        return self.total_profit * (self.dividend_percentage / 100)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount_to_distribute:,.2f}"
    
    @property
    def formatted_refund(self):
        return f"Rs. {self.total_refund_amount:,.2f}"
    
    @property
    def formatted_total_payment(self):
        return f"Rs. {self.total_payment_amount:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        colors = {
            'draft': 'secondary',
            'declared': 'primary',
            'approved': 'info',
            'distributed': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def refund_badge(self):
        """HTML badge for refund type"""
        colors = {
            'full': 'success',
            'partial': 'warning',
            'profit_only': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.refund_type, "secondary")}">{self.get_refund_type_display()}</span>'
    
    @property
    def is_active(self):
        """Check if dividend is active"""
        return self.status not in ['cancelled', 'distributed']
    
    @property
    def can_generate_payments(self):
        """Can generate payments?"""
        return self.status in ['draft', 'declared'] and not self.payments.exists()
    
    @property
    def can_edit(self):
        """Can edit?"""
        return self.status in ['draft', 'declared'] and not self.payments.exists()
    
    @property
    def can_delete(self):
        """Can delete?"""
        return self.status == 'draft'
    
    @property
    def can_distribute(self):
        """Can distribute?"""
        return self.status in ['declared', 'approved'] and self.payments.exists()
    
    @property
    def used_sales_count(self):
        """Get count of used sales"""
        return self.used_sales.count()
    
    @property
    def total_sales_profit(self):
        """Get total profit from used sales"""
        from decimal import Decimal
        from django.db.models import Sum
        
        total = self.used_sales.aggregate(
            total=Sum('saleitem__profit')
        )['total'] or Decimal('0.00')
        
        discounts = self.used_sales.aggregate(
            total=Sum('discount_value')
        )['total'] or Decimal('0.00')
        
        return total - discounts
    
    # ========================================== #
    # CORE BUSINESS METHODS                      #
    # ========================================== #
    
    def get_shareholder_balance_used(self, shareholder):
        """
        Calculate total balance used by a specific shareholder
        Returns: Decimal
        """
        from decimal import Decimal
        
        total = Decimal('0.00')
        
        # Get all purchases with shareholder deductions
        purchases = Purchase.objects.filter(
            shareholder_deduction_done=True
        )
        
        for purchase in purchases:
            data = purchase.shareholder_deduction_data
            if data and data.get('deducted_from'):
                for item in data['deducted_from']:
                    # Match by name or ID
                    if item.get('name') == shareholder.name:
                        total += Decimal(str(item.get('deducted', 0)))
                        break
        
        return total
    
    def get_eligible_shareholders(self):
        """
        Get shareholders eligible for dividend
        Returns: List of dicts with shareholder and balance_used
        """
        # Get system settings
        min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
        min_months = int(SystemSetting.get_value('min_holding_months', '0'))
        
        eligible = []
        
        for shareholder in Shareholder.objects.filter(status='active'):
            # Get balance used
            balance_used = self.get_shareholder_balance_used(shareholder)
            
            # Check min balance requirement
            if balance_used < min_balance:
                continue
            
            # Check min holding period (in months)
            if min_months > 0:
                first_share = shareholder.shares.order_by('issue_date').first()
                if not first_share:
                    continue
                months_held = (date.today() - first_share.issue_date).days // 30
                if months_held < min_months:
                    continue
            
            # Add to eligible list
            eligible.append({
                'shareholder': shareholder,
                'balance_used': balance_used,
                'shares': shareholder.total_shares(),
                'investment': shareholder.total_investment(),
                'percentage': 0,
                'dividend_amount': Decimal('0.00'),
                'refund_amount': Decimal('0.00'),
                'total_payment': Decimal('0.00'),
            })
        
        # Calculate percentages
        total_used = sum(item['balance_used'] for item in eligible)
        
        if total_used > 0:
            for item in eligible:
                item['percentage'] = (item['balance_used'] / total_used) * 100
        
        return eligible
    
    def calculate_distribution(self):
        """
        Calculate dividend distribution for all eligible shareholders
        ✅ NEW: Includes refund of deducted balance
        """
        eligible = self.get_eligible_shareholders()
        total_to_distribute = self.amount_to_distribute
        
        # Calculate refund for each shareholder
        total_refund = Decimal('0.00')
        
        for item in eligible:
            # Calculate refund amount based on balance used
            if self.refund_type == 'full':
                refund_amount = item['balance_used']
            elif self.refund_type == 'partial':
                refund_amount = item['balance_used'] * (self.refund_percentage / 100)
            else:  # profit_only
                refund_amount = Decimal('0.00')
            
            item['refund_amount'] = refund_amount
            total_refund += refund_amount
        
        self.total_refund_amount = total_refund
        
        # Calculate profit distribution
        if self.distribution_type == 'equal':
            per_shareholder = total_to_distribute / len(eligible) if eligible else 0
            for item in eligible:
                item['dividend_amount'] = per_shareholder
        elif self.distribution_type == 'proportional':
            total_balance_used = sum(item['balance_used'] for item in eligible) or Decimal('1')
            for item in eligible:
                proportion = item['balance_used'] / total_balance_used
                item['dividend_amount'] = total_to_distribute * proportion
        else:  # balance_used (default)
            total_balance_used = sum(item['balance_used'] for item in eligible) or Decimal('1')
            for item in eligible:
                proportion = item['balance_used'] / total_balance_used
                item['dividend_amount'] = total_to_distribute * proportion
        
        # Calculate total payment (refund + profit)
        total_payment = Decimal('0.00')
        for item in eligible:
            item['total_payment'] = item['dividend_amount'] + item['refund_amount']
            total_payment += item['total_payment']
        
        self.total_payment_amount = total_payment
        
        return eligible
    
    def generate_payments(self):
        """
        Generate dividend payments for all eligible shareholders
        ✅ Returns: (count, total_profit, total_refund)
        """
        from django.db import transaction
        from django.utils.timezone import now
        from decimal import Decimal
        
        if self.payments.exists():
            raise ValidationError("Payments already exist for this dividend!")
        
        # Get unused sales for this period
        used_sale_ids = list(
            BalanceDividend.objects.exclude(pk=self.pk).values_list('used_sales', flat=True).distinct()
        )
        
        from_date = self.profit_from_date or self.declaration_date
        to_date = self.profit_to_date or self.declaration_date
        
        unused_sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).exclude(
            id__in=used_sale_ids
        )
        
        distribution = self.calculate_distribution()
        count = 0
        total_profit = Decimal('0.00')
        total_refund = Decimal('0.00')
        
        with transaction.atomic():
            for item in distribution:
                if item['total_payment'] > 0:
                    # Create payment with refund details
                    payment = BalanceDividendPayment.objects.create(
                        dividend=self,
                        shareholder=item['shareholder'],
                        balance_used=item['balance_used'],
                        percentage=item['percentage'],
                        amount=item['dividend_amount'],  # Profit
                        refund_amount=item['refund_amount'],
                        total_payment=item['total_payment'],
                        status='pending',
                        main_cash_deducted=False  # ✅ Default: No cash deduction
                    )
                    count += 1
                    total_profit += item['dividend_amount']
                    total_refund += item['refund_amount']
            
            # Track which sales were used
            if unused_sales.exists():
                self.used_sales.set(unused_sales)
            
            # Update dividend status and totals
            if count > 0:
                self.total_refund_amount = total_refund
                self.total_payment_amount = total_profit + total_refund
                self.status = 'declared'
                self.save(update_fields=['status', 'total_refund_amount', 'total_payment_amount'])
        
        return count, total_profit, total_refund
    
    def distribute(self, user):
        """
        Distribute dividend (mark all as distributed)
        Requires all payments to be paid
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status not in ['declared', 'approved']:
            raise ValidationError("Dividend must be declared or approved!")
        
        pending_payments = self.payments.filter(status='pending')
        if pending_payments.exists():
            raise ValidationError(
                f"Cannot distribute! {pending_payments.count()} payments are still pending."
            )
        
        with transaction.atomic():
            self.status = 'distributed'
            self.distribution_date = now().date()
            self.save(update_fields=['status', 'distribution_date'])
        
        return True
    
    def cancel(self, user, reason=""):
        """
        Cancel dividend
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status == 'distributed':
            raise ValidationError("Cannot cancel a distributed dividend!")
        
        if self.status == 'cancelled':
            raise ValidationError("Dividend is already cancelled!")
        
        # Check if any paid payments exist
        if self.payments.filter(status='paid').exists():
            raise ValidationError(
                "Cannot cancel! Some payments have already been paid."
            )
        
        with transaction.atomic():
            # Delete all pending payments
            self.payments.filter(status='pending').delete()
            
            # Remove used sales tracking
            self.used_sales.clear()
            
            # Update status
            self.status = 'cancelled'
            self.notes = f"{self.notes}\nCancelled by {user.username}: {reason}".strip()
            self.save(update_fields=['status', 'notes'])
        
        return True
    
    # ========================================== #
    # STATIC METHODS                             #
    # ========================================== #
    
    @classmethod
    def get_auto_profit(cls, from_date=None, to_date=None, exclude_used=True):
        """
        Auto-calculate profit from sales
        ✅ NEW: Exclude sales already used in dividends
        """
        from decimal import Decimal
        from django.db.models import Sum, F, Q
        
        if not from_date:
            from_date = date.today().replace(day=1)
        if not to_date:
            to_date = date.today()
        
        # Get all sale IDs already used in balance dividends
        used_sale_ids = []
        if exclude_used:
            used_sale_ids = list(
                BalanceDividend.objects.values_list('used_sales', flat=True).distinct()
            )
        
        # Build query - exclude used sales
        sales_query = Q(
            sale__sale_date__date__gte=from_date,
            sale__sale_date__date__lte=to_date
        )
        
        if used_sale_ids:
            sales_query &= ~Q(sale_id__in=used_sale_ids)
        
        # Total Sales Profit (only from unused sales)
        total_sales_profit = SaleItem.objects.filter(
            sales_query
        ).aggregate(
            total=Sum('profit')
        )['total'] or Decimal('0.00')
        
        # Total Discounts (only from unused sales)
        total_discounts = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date,
            id__in=SaleItem.objects.filter(sales_query).values_list('sale_id', flat=True).distinct()
        ).aggregate(
            total=Sum('discount_value')
        )['total'] or Decimal('0.00')
        
        # Total Expenses (all expenses, not just sales)
        total_expenses = Expense.objects.filter(
            expense_date__gte=from_date,
            expense_date__lte=to_date,
            status__in=['approved', 'paid']
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Net Profit = Sales Profit - Discounts - Expenses
        net_profit = total_sales_profit - total_discounts
        final_profit = net_profit - total_expenses
        
        # Get list of unused sales for display
        unused_sales = Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).exclude(
            id__in=used_sale_ids
        ).values('id', 'bill_no', 'sale_date')
        
        return {
            'total_sales_profit': total_sales_profit,
            'total_discounts': total_discounts,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'final_profit': final_profit,
            'from_date': from_date,
            'to_date': to_date,
            'used_sale_count': len(used_sale_ids),
            'unused_sale_count': unused_sales.count(),
            'unused_sales': list(unused_sales),
            'total_sales_count': Sale.objects.filter(
                sale_date__date__gte=from_date,
                sale_date__date__lte=to_date
            ).count(),
        }
    
    @classmethod
    def get_total_balance_used(cls):
        """
        Get total balance used by all shareholders
        Returns: Decimal
        """
        total = Decimal('0.00')
        
        for shareholder in Shareholder.objects.filter(status='active'):
            dummy_dividend = cls.objects.first()
            if dummy_dividend:
                total += dummy_dividend.get_shareholder_balance_used(shareholder)
        
        return total
    
    @classmethod
    def get_eligible_shareholders_count(cls):
        """
        Get count of shareholders eligible for dividend
        Returns: int
        """
        min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
        min_months = int(SystemSetting.get_value('min_holding_months', '0'))
        
        count = 0
        dummy_dividend = cls.objects.first()
        
        if not dummy_dividend:
            dummy_dividend = cls(
                total_profit=Decimal('1000'),
                dividend_percentage=50,
                declaration_date=date.today(),
                record_date=date.today()
            )
        
        for shareholder in Shareholder.objects.filter(status='active'):
            balance_used = dummy_dividend.get_shareholder_balance_used(shareholder)
            
            if balance_used < min_balance:
                continue
            
            if min_months > 0:
                first_share = shareholder.shares.order_by('issue_date').first()
                if not first_share:
                    continue
                months_held = (date.today() - first_share.issue_date).days // 30
                if months_held < min_months:
                    continue
            
            count += 1
        
        return count
    
    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate number and validate"""
        
        # Auto-generate dividend number
        if not self.dividend_no:
            last_dividend = BalanceDividend.objects.order_by('-id').first()
            if last_dividend and last_dividend.dividend_no:
                try:
                    last_num = int(last_dividend.dividend_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.dividend_no = f'BD-{new_num}'
        
        # Set default date range if not set
        if not self.profit_from_date:
            self.profit_from_date = self.declaration_date.replace(day=1)
        if not self.profit_to_date:
            self.profit_to_date = self.declaration_date
        
        # Validate refund type and percentage
        if self.refund_type == 'profit_only':
            self.refund_percentage = Decimal('0.00')
        elif self.refund_type == 'full':
            self.refund_percentage = Decimal('100.00')
        elif self.refund_type == 'partial':
            if self.refund_percentage < 0 or self.refund_percentage > 100:
                raise ValidationError("Refund percentage must be between 0 and 100!")
        
        # Validate status transitions
        if self.pk:
            old = BalanceDividend.objects.filter(pk=self.pk).first()
            if old:
                if old.status == 'distributed' and self.status != 'distributed':
                    raise ValidationError("Cannot change status of distributed dividend!")
                if old.status == 'cancelled' and self.status != 'cancelled':
                    raise ValidationError("Cannot change status of cancelled dividend!")
        
        super().save(*args, **kwargs)
    
    # ========================================== #
    # DELETE METHOD                              #
    # ========================================== #
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of distributed dividends"""
        if self.status == 'distributed':
            raise ValidationError("Cannot delete a distributed dividend!")
        if self.payments.filter(status='paid').exists():
            raise ValidationError("Cannot delete dividend with paid payments!")
        super().delete(*args, **kwargs)


class BalanceDividendPayment(models.Model):
    """
    Individual dividend payment based on balance usage
    ✅ NEW: Refund + Profit system with Balance-Only option
    """
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('paid', '✅ Paid'),
        ('failed', '❌ Failed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # ========================================== #
    # BASIC FIELDS                              #
    # ========================================== #
    dividend = models.ForeignKey(
        BalanceDividend, 
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    shareholder = models.ForeignKey(
        Shareholder, 
        on_delete=models.CASCADE,
        related_name='balance_dividend_payments'
    )
    
    # ========================================== #
    # BALANCE USAGE DETAILS                     #
    # ========================================== #
    balance_used = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Balance Used"
    )
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        verbose_name="Percentage"
    )
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        verbose_name="Dividend Amount (Profit)"
    )
    
    # ========================================== #
    # REFUND FIELDS                             #
    # ========================================== #
    refund_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Refund Amount",
        help_text="Deducted balance being returned"
    )
    total_payment = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total Payment",
        help_text="Refund + Profit"
    )
    
    # ========================================== #
    # MAIN CASH DEDUCTION TRACKING              #
    # ========================================== #
    main_cash_deducted = models.BooleanField(
        default=False,
        verbose_name="Main Cash Deducted",
        help_text="Has main cash been deducted for this payment?"
    )
    main_cash_deducted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Main Cash Deducted At"
    )
    
    # ========================================== #
    # PAYMENT STATUS                            #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    payment_date = models.DateTimeField(
        null=True, 
        blank=True
    )
    payment_method = models.CharField(
        max_length=50, 
        blank=True, 
        null=True
    )
    reference_no = models.CharField(
        max_length=100, 
        blank=True, 
        null=True
    )
    notes = models.TextField(
        blank=True, 
        null=True
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='processed_balance_dividend_payments'
    )
    
    class Meta:
        verbose_name_plural = "💰 Balance Dividend Payments"
        ordering = ['-created_at']
        unique_together = ['dividend', 'shareholder']
        indexes = [
            models.Index(fields=['dividend', 'shareholder']),
            models.Index(fields=['status']),
            models.Index(fields=['main_cash_deducted']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Profit: Rs. {self.amount:,.2f}, Refund: Rs. {self.refund_amount:,.2f}, Total: Rs. {self.total_payment:,.2f}"
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def formatted_refund(self):
        return f"Rs. {self.refund_amount:,.2f}"
    
    @property
    def formatted_total(self):
        return f"Rs. {self.total_payment:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        colors = {
            'pending': 'warning',
            'paid': 'success',
            'failed': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def cash_badge(self):
        """HTML badge for cash deduction status"""
        if self.main_cash_deducted:
            return '<span class="badge bg-success">✅ Cash Deducted</span>'
        return '<span class="badge bg-secondary">⏳ Balance Only</span>'
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    @property
    def is_cancelled(self):
        return self.status == 'cancelled'
    
    @property
    def is_cash_deducted(self):
        return self.main_cash_deducted
    
    # ========================================== #
    # PAYMENT METHODS                            #
    # ========================================== #
    
    def mark_paid(self, user, payment_method=None, reference_no=None, deduct_main_cash=False):
        """
        Mark payment as paid
        ✅ NEW: Main cash deduction is optional
        """
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status == 'paid':
            raise ValidationError("Already paid!")
        
        if self.total_payment <= 0:
            raise ValidationError("Total payment must be greater than zero!")
        
        with transaction.atomic():
            # ========================================== #
            # STEP 1: DEPOSIT TO SHAREHOLDER BALANCE    #
            # ========================================== #
            new_balance = ShareholderCashBalance.deposit(
                shareholder=self.shareholder,
                amount=self.total_payment,
                user=user,
                description=f"Balance Dividend #{self.dividend.dividend_no} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f})"
            )
            
            # ========================================== #
            # STEP 2: CREATE TRANSACTION RECORD         #
            # ========================================== #
            ShareholderCashTransaction.objects.create(
                shareholder=self.shareholder,
                amount=self.total_payment,
                transaction_type='balance_dividend',
                balance_after=new_balance,
                description=f"Balance Dividend #{self.dividend.dividend_no} - Refund: Rs. {self.refund_amount:,.2f}, Profit: Rs. {self.amount:,.2f}",
                reference_no=reference_no,
                balance_dividend_payment=self,
                created_by=user
            )
            
            # ========================================== #
            # STEP 3: MAIN CASH DEDUCTION (OPTIONAL)    #
            # ========================================== #
            if deduct_main_cash:
                current_balance = CashBalance.get_balance()
                if current_balance < self.total_payment:
                    raise ValidationError(
                        f"Insufficient main cash balance! Available: Rs. {current_balance:,.2f}, Required: Rs. {self.total_payment:,.2f}"
                    )
                
                CashBalance.update_balance(
                    amount=self.total_payment,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Balance Dividend withdrawal by {self.shareholder.name} - #{self.dividend.dividend_no}"
                )
                
                self.main_cash_deducted = True
                self.main_cash_deducted_at = now()
            
            # ========================================== #
            # STEP 4: UPDATE PAYMENT STATUS            #
            # ========================================== #
            self.status = 'paid'
            self.payment_date = now()
            self.payment_method = payment_method or 'Bank Transfer'
            self.reference_no = reference_no
            self.processed_by = user
            self.save(update_fields=[
                'status', 'payment_date', 'payment_method', 
                'reference_no', 'processed_by',
                'main_cash_deducted', 'main_cash_deducted_at'
            ])
            
            # ========================================== #
            # STEP 5: UPDATE DIVIDEND STATUS           #
            # ========================================== #
            self._update_dividend_status()
            
            # ========================================== #
            # STEP 6: CREATE NOTIFICATION              #
            # ========================================== #
            try:
                from .. import Notification
                if deduct_main_cash:
                    message = f"Rs. {self.total_payment:,.2f} paid to {self.shareholder.name} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f}) - Cash Withdrawn"
                else:
                    message = f"Rs. {self.total_payment:,.2f} credited to {self.shareholder.name} (Refund: Rs. {self.refund_amount:,.2f} + Profit: Rs. {self.amount:,.2f}) - Balance Only"
                
                Notification.send(
                    user=user,
                    title="💰 Balance Dividend Paid" if deduct_main_cash else "💰 Balance Dividend Credited",
                    message=message,
                    notification_type='success',
                    category='payments',
                    link=f"/balance-dividend/{self.dividend.id}/"
                )
            except:
                pass
            
            return True
    
    def mark_paid_no_cash(self, user, payment_method=None, reference_no=None):
        """
        Mark payment as paid WITHOUT main cash deduction
        Only shareholder balance increases
        """
        return self.mark_paid(user, payment_method, reference_no, deduct_main_cash=False)
    
    def mark_paid_with_cash(self, user, payment_method=None, reference_no=None):
        """
        Mark payment as paid WITH main cash deduction
        Shareholder balance increases AND main cash decreases
        """
        return self.mark_paid(user, payment_method, reference_no, deduct_main_cash=True)
    
    # ========================================== #
    # HELPER METHODS                            #
    # ========================================== #
    
    def _update_dividend_status(self):
        """
        Update dividend status based on payments
        """
        total_payments = self.dividend.payments.count()
        paid_payments = self.dividend.payments.filter(status='paid').count()
        
        if total_payments > 0 and paid_payments == total_payments:
            self.dividend.status = 'distributed'
            self.dividend.distribution_date = date.today()
            self.dividend.save(update_fields=['status', 'distribution_date'])
    
    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Prevent changing status of paid payments"""
        if self.pk:
            old = BalanceDividendPayment.objects.filter(pk=self.pk).first()
            if old and old.status == 'paid' and self.status != 'paid':
                raise ValidationError("Cannot change status of a paid payment!")
        super().save(*args, **kwargs)
    
    # ========================================== #
    # DELETE METHOD                              #
    # ========================================== #
    
    def delete(self, *args, **kwargs):
        """Prevent deleting paid payments"""
        if self.status == 'paid':
            raise ValidationError("Cannot delete a paid payment!")
        super().delete(*args, **kwargs)
