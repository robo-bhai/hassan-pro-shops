"""Shareholders models."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.db.models import F
from django.contrib.auth.models import User
import logging
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class Shareholder(models.Model):
    """
    Shareholder Model - Complete with Balance Management & Deduction Methods
    """
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    SHAREHOLDER_TYPES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
        ('trust', 'Trust'),
        ('partnership', 'Partnership'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    shareholder_code = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False
    )
    name = models.CharField(max_length=200)
    shareholder_type = models.CharField(
        max_length=20, 
        choices=SHAREHOLDER_TYPES, 
        default='individual'
    )
    
    # ========================================== #
    # CONTACT DETAILS                           #
    # ========================================== #
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # ========================================== #
    # IDENTIFICATION                            #
    # ========================================== #
    cnic = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        verbose_name="CNIC/NTN"
    )
    passport_no = models.CharField(max_length=20, blank=True, null=True)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    registration_no = models.CharField(max_length=50, blank=True, null=True)
    
    # ========================================== #
    # BANKING DETAILS                           #
    # ========================================== #
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    account_title = models.CharField(max_length=200, blank=True, null=True)
    iban = models.CharField(max_length=50, blank=True, null=True)
    
    # ========================================== #
    # STATUS & FLAGS                            #
    # ========================================== #
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='active'
    )
    is_founder = models.BooleanField(
        default=False, 
        help_text="Founder shareholder"
    )
    is_board_member = models.BooleanField(
        default=False, 
        help_text="Board member"
    )
    
    # ========================================== #
    # LOGIN FIELDS                              #
    # ========================================== #
    user = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='shareholder_profile'
    )
    allow_login = models.BooleanField(
        default=False, 
        help_text="Allow shareholder to login to portal"
    )
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_shareholders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "👥 Shareholders"
        indexes = [
            models.Index(fields=['shareholder_code']),
            models.Index(fields=['name']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.shareholder_code} - {self.name}"

    # ========================================== #
    # SHARE CALCULATIONS                        #
    # ========================================== #
    
    def total_shares(self):
        """Total shares held by this shareholder"""
        return self.shares.aggregate(total=Sum('quantity'))['total'] or 0

    def total_investment(self):
        """Total investment amount"""
        return self.shares.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')

    def total_dividends(self):
        """Total dividends received"""
        return self.dividend_payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    def current_value(self, current_price=None):
        """Current value of holdings"""
        total_shares = self.total_shares()
        if current_price:
            return total_shares * current_price
        latest_price = SharePrice.objects.filter(is_active=True).first()
        if latest_price:
            return total_shares * latest_price.price
        return Decimal('0.00')

    def ownership_percentage(self, total_shares=None):
        """Ownership percentage"""
        if total_shares is None:
            total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
        if total_shares > 0:
            return (self.total_shares() / total_shares) * 100
        return Decimal('0.00')

    # ========================================== #
    # BALANCE MANAGEMENT METHODS                #
    # ========================================== #
    
    def get_balance(self):
        """Get current cash balance"""
        return ShareholderCashBalance.get_balance(self)

    def deposit(self, amount, user=None, description=""):
        """Deposit money into shareholder's balance"""
        return ShareholderCashBalance.deposit(
            shareholder=self,
            amount=amount,
            user=user,
            description=description
        )

    def withdraw(self, amount, user=None, description=""):
        """Withdraw money from shareholder's balance"""
        return ShareholderCashBalance.withdraw(
            shareholder=self,
            amount=amount,
            user=user,
            description=description
        )

    # ========================================== #
    # LOGIN METHODS                             #
    # ========================================== #
    
    def get_username(self):
        """Generate username from shareholder name"""
        base = self.name.lower().replace(' ', '').replace('-', '').replace('_', '')
        username = base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1
        return username

    
        
    def create_user(self, password=None):
        """Create the login user (username comes from the name).

        If no password is given a strong random one is generated. The plain password is
        only kept in `self.initial_password` (NOT saved) so the caller can show it once.
        """
        if self.user:
            return self.user

        from ..security_utils import generate_password
        if not password:
            password = generate_password()
        self.initial_password = password

        username = self.get_username()
        user = User.objects.create_user(
            username=username,
            email=self.email or '',
            password=password
        )
        self.user = user
        self.save()
        return user

    def get_user(self):
        """Get existing user or create new"""
        if self.user:
            return self.user
        return self.create_user()

    def set_password(self, raw_password):
        """Set password for shareholder"""
        if self.user:
            self.user.set_password(raw_password)
            self.user.save()
        return True

    def check_password(self, raw_password):
        """Check password"""
        if self.user:
            return self.user.check_password(raw_password)
        return False

    # ========================================== #
    # ✅ SHAREHOLDER DEDUCTION METHODS (FIXED)  #
    # ========================================== #
    
    @classmethod
    def get_all_active_shareholders_with_balance(cls):
        """
        Get all active shareholders with their balances
        ✅ FIXED: Decimal to float conversion
        Returns: List of (shareholder, balance) tuples
        """
        shareholders = cls.objects.filter(status='active')
        result = []
        for shareholder in shareholders:
            balance = shareholder.get_balance()
            if balance > 0:  # Only positive balance shareholders
                result.append({
                    'shareholder': shareholder,
                    'balance': float(balance)  # ✅ Convert to float
                })
        return result

    @classmethod
    def deduct_purchase_equally(cls, purchase_amount, purchase_obj=None, user=None):
        """
        ✅ Deduct purchase amount equally from all shareholders
        Jis ka balance zyada ho ya kam, sab se barabar deduction
        ✅ FIXED: NO main cash deduction - only shareholder balances
        """
        from decimal import Decimal
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get all active shareholders
        shareholders = cls.objects.filter(status='active')
        
        if not shareholders.exists():
            return False, "No active shareholders found"
        
        total_shareholders = shareholders.count()
        
        # ✅ Convert to float for calculation
        purchase_amount_float = float(purchase_amount)
        per_shareholder_float = purchase_amount_float / total_shareholders
        
        # ✅ Convert to Decimal for withdrawal
        per_shareholder_decimal = Decimal(str(per_shareholder_float))
        
        # ✅ Results (all floats for JSON)
        results = {
            'total_shareholders': total_shareholders,
            'per_shareholder': per_shareholder_float,
            'total_amount': purchase_amount_float,
            'deduction_type': 'equal',
            'deducted_from': [],
            'failed': [],
            'skipped': [],
        }
        
        try:
            with transaction.atomic():
                # ❌ REMOVED: CashBalance.update_balance() - NO main cash deduction
                
                # Deduct from each shareholder
                for shareholder in shareholders:
                    try:
                        current_balance = shareholder.get_balance()
                        new_balance = shareholder.withdraw(
                            amount=per_shareholder_decimal,  # ✅ Decimal
                            user=user,
                            description=f"Purchase deduction (Equal) - Rs. {per_shareholder_decimal:,.2f}"
                        )
                        
                        # ✅ Convert to float
                        results['deducted_from'].append({
                            'name': shareholder.name,
                            'code': shareholder.shareholder_code,
                            'balance_before': float(current_balance),
                            'balance_after': float(new_balance),
                            'deducted': per_shareholder_float,
                            'percentage': (per_shareholder_float / purchase_amount_float) * 100,
                            'shares': shareholder.total_shares()
                        })
                        
                        logger.info(f"Deducted Rs. {per_shareholder_float:,.2f} from {shareholder.name}")
                        
                    except Exception as e:
                        logger.error(f"Failed to deduct from {shareholder.name}: {e}")
                        results['failed'].append({
                            'name': shareholder.name,
                            'error': str(e)
                        })
                
                # Save in purchase
                if purchase_obj:
                    purchase_obj.shareholder_deduction_done = True
                    purchase_obj.shareholder_deduction_data = results
                    purchase_obj.shareholder_deduction_date = now()
                    purchase_obj.shareholder_deduction_type = 'equal'
                    purchase_obj.save()
                
                return True, results
                
        except Exception as e:
            logger.error(f"Equal deduction failed: {e}")
            return False, str(e)

    @classmethod
    def deduct_purchase_proportionally_by_balance(cls, purchase_amount, purchase_obj=None, user=None):
        """
        ✅ Deduct purchase amount proportionally by shareholder balance
        Jis ka balance zyada, us ki deduction zyada
        Jis ka balance kam, us ki deduction kam
        Zero balance walo se kuch nahi kata
        ✅ FIXED: NO main cash deduction - only shareholder balances
        ✅ FIXED: Proper Decimal handling for withdrawal
        """
        from decimal import Decimal
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        # ✅ Get active shareholders with positive balance
        shareholders_with_balance = cls.get_all_active_shareholders_with_balance()
        
        if not shareholders_with_balance:
            return False, "No shareholders with positive balance found"
        
        # ✅ Calculate total balance
        total_balance = sum(item['balance'] for item in shareholders_with_balance)
        
        if total_balance == 0:
            return False, "Total shareholder balance is zero"
        
        # ✅ Convert purchase_amount to float for calculations
        purchase_amount_float = float(purchase_amount)
        
        # ✅ Results (all floats for JSON)
        results = {
            'total_shareholders': len(shareholders_with_balance),
            'total_balance': total_balance,
            'total_amount': purchase_amount_float,
            'deduction_type': 'proportional',
            'deducted_from': [],
            'failed': [],
            'skipped': [],
        }
        
        # ✅ Track zero balance shareholders to skip
        all_shareholders = cls.objects.filter(status='active')
        for shareholder in all_shareholders:
            balance = shareholder.get_balance()
            if balance == 0:
                results['skipped'].append({
                    'name': shareholder.name,
                    'code': shareholder.shareholder_code,
                    'reason': 'Zero balance'
                })
        
        try:
            with transaction.atomic():
                # ❌ REMOVED: CashBalance.update_balance() - NO main cash deduction
                
                # ✅ Deduct from each shareholder proportionally
                for item in shareholders_with_balance:
                    shareholder = item['shareholder']
                    balance = item['balance']  # float
                    
                    # ✅ Calculate proportion (float / float = float)
                    proportion = balance / total_balance
                    
                    # ✅ Calculate deduction amount (float * float = float)
                    deduction_amount_float = purchase_amount_float * proportion
                    
                    # ✅ Convert back to Decimal for withdrawal (with rounding)
                    deduction_decimal = Decimal(str(round(deduction_amount_float, 2)))
                    
                    try:
                        current_balance = shareholder.get_balance()
                        new_balance = shareholder.withdraw(
                            amount=deduction_decimal,  # ✅ Decimal with rounding
                            user=user,
                            description=f"Purchase deduction (Proportional) - {proportion*100:.1f}% of total"
                        )
                        
                        # ✅ Store as float in results
                        results['deducted_from'].append({
                            'name': shareholder.name,
                            'code': shareholder.shareholder_code,
                            'balance_before': float(current_balance),
                            'balance_after': float(new_balance),
                            'deducted': deduction_amount_float,
                            'percentage': proportion * 100,
                            'shares': shareholder.total_shares()
                        })
                        
                        logger.info(f"Deducted Rs. {deduction_amount_float:,.2f} ({proportion*100:.1f}%) from {shareholder.name}")
                        
                    except Exception as e:
                        logger.error(f"Failed to deduct from {shareholder.name}: {e}")
                        results['failed'].append({
                            'name': shareholder.name,
                            'error': str(e)
                        })
                
                # ✅ Save in purchase
                if purchase_obj:
                    purchase_obj.shareholder_deduction_done = True
                    purchase_obj.shareholder_deduction_data = results
                    purchase_obj.shareholder_deduction_date = now()
                    purchase_obj.shareholder_deduction_type = 'proportional'
                    purchase_obj.save()
                
                return True, results
                
        except Exception as e:
            logger.error(f"Proportional deduction failed: {e}")
            return False, str(e)

    @classmethod
    def process_purchase_deduction(cls, purchase, user=None):
        """
        ✅ Main method to process purchase deduction
        Automatically selects the best deduction type
        """
        from django.utils.timezone import now
        
        if not purchase:
            return False, "Purchase object required"
        
        if purchase.shareholder_deduction_done:
            return False, "Deduction already processed"
        
        # ✅ Get deduction type from system setting
        deduction_type = SystemSetting.get_value('shareholder_deduction_type', 'proportional')
        
        # ✅ Also check purchase override
        if hasattr(purchase, 'shareholder_deduction_type') and purchase.shareholder_deduction_type != 'skip':
            deduction_type = purchase.shareholder_deduction_type
        
        # ✅ Process based on type
        if deduction_type == 'equal':
            return cls.deduct_purchase_equally(
                purchase_amount=purchase.total_amount(),
                purchase_obj=purchase,
                user=user or purchase.created_by
            )
        else:  # proportional (default)
            return cls.deduct_purchase_proportionally_by_balance(
                purchase_amount=purchase.total_amount(),
                purchase_obj=purchase,
                user=user or purchase.created_by
            )

    # ========================================== #
    # SAVE METHOD                               #
    # ========================================== #
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate code"""
        if not self.shareholder_code:
            last_shareholder = Shareholder.objects.order_by('-id').first()
            if last_shareholder and last_shareholder.shareholder_code:
                try:
                    last_num = int(last_shareholder.shareholder_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.shareholder_code = f'SH-{new_num}'
        
        super().save(*args, **kwargs)

    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def formatted_total_shares(self):
        return f"{self.total_shares():,}"

    @property
    def formatted_total_investment(self):
        return f"Rs. {self.total_investment():,.2f}"

    @property
    def formatted_ownership(self):
        return f"{self.ownership_percentage():.2f}%"

    @property
    def status_badge(self):
        if self.status == 'active':
            return '<span class="badge bg-success">✅ Active</span>'
        elif self.status == 'inactive':
            return '<span class="badge bg-secondary">⏸️ Inactive</span>'
        else:
            return '<span class="badge bg-danger">⛔ Suspended</span>'

    @property
    def has_login(self):
        """Check if shareholder has login access"""
        return self.allow_login and self.user is not None

    @property
    def username(self):
        """Get username"""
        if self.user:
            return self.user.username
        return None


class Share(models.Model):
    """Share/Stock holding record with shareholder cash balance support"""
    SHARE_TYPES = [
        ('ordinary', 'Ordinary Share'),
        ('preference', 'Preference Share'),
        ('bonus', 'Bonus Share'),
        ('founder', 'Founder Share'),
    ]
    
    # ============================================
    # BASIC INFORMATION
    # ============================================
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='shares'
    )
    share_type = models.CharField(
        max_length=20, 
        choices=SHARE_TYPES, 
        default='ordinary'
    )
    quantity = models.PositiveIntegerField(
        help_text="Number of shares held"
    )
    purchase_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Price per share at time of purchase"
    )
    
    # ============================================
    # CERTIFICATE INFORMATION
    # ============================================
    certificate_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True,
        help_text="Unique certificate number"
    )
    certificate_issue_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when certificate was issued"
    )
    certificate_printed = models.BooleanField(
        default=False,
        help_text="Has certificate been printed?"
    )
    certificate_printed_at = models.DateTimeField(
        null=True, 
        blank=True
    )
    certificate_printed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='share_certificates_printed'
    )
    certificate_template = models.CharField(
        max_length=50, 
        default='standard', 
        choices=[
            ('standard', 'Standard'),
            ('premium', 'Premium'),
            ('simple', 'Simple'),
        ],
        help_text="Certificate template style"
    )
    certificate_notes = models.TextField(
        blank=True, 
        null=True,
        help_text="Any notes about the certificate"
    )
    
    # ============================================
    # ISSUE DETAILS
    # ============================================
    issue_date = models.DateField(
        default=now,
        help_text="Date when shares were issued"
    )
    is_locked = models.BooleanField(
        default=False, 
        help_text="Locked shares cannot be transferred"
    )
    notes = models.TextField(
        blank=True, 
        null=True,
        help_text="General notes about this share holding"
    )
    
    # ============================================
    # TRANSFER TRACKING
    # ============================================
    transferred_from = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='transferred_to',
        help_text="Original share this was transferred from"
    )
    transfer_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date of transfer"
    )
    transfer_notes = models.TextField(
        blank=True, 
        null=True,
        help_text="Notes about the transfer"
    )
    
    # ============================================
    # SHAREHOLDER CASH BALANCE SETTINGS
    # ============================================
    paid_from_shareholder_balance = models.BooleanField(
        default=True,
        help_text="If True, shares are purchased from shareholder's cash balance. If False, from main cash balance."
    )
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_shares'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ============================================
    # META
    # ============================================
    class Meta:
        verbose_name_plural = "📈 Share Holdings"
        indexes = [
            models.Index(fields=['shareholder']),
            models.Index(fields=['share_type']),
            models.Index(fields=['certificate_number']),
        ]
    
    # ============================================
    # STRING REPRESENTATION
    # ============================================
    def __str__(self):
        return f"{self.shareholder.name} - {self.quantity} x {self.share_type}"
    
    # ============================================
    # VALUE CALCULATIONS
    # ============================================
    def total_value(self, price=None):
        """Total value of this share holding"""
        if price:
            return self.quantity * price
        latest_price = SharePrice.objects.filter(is_active=True).first()
        if latest_price:
            return self.quantity * latest_price.price
        return self.quantity * self.purchase_price
    
    def total_investment(self):
        """Total investment amount for this holding"""
        return self.quantity * self.purchase_price
    
    def profit_loss(self, current_price=None):
        """Profit/Loss on this holding"""
        if current_price is None:
            latest_price = SharePrice.objects.filter(is_active=True).first()
            current_price = latest_price.price if latest_price else self.purchase_price
        return self.quantity * (current_price - self.purchase_price)
    
    def profit_loss_percent(self, current_price=None):
        """Profit/Loss percentage"""
        if current_price is None:
            latest_price = SharePrice.objects.filter(is_active=True).first()
            current_price = latest_price.price if latest_price else self.purchase_price
        if self.purchase_price > 0:
            return ((current_price - self.purchase_price) / self.purchase_price) * 100
        return Decimal('0.00')
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_quantity(self):
        return f"{self.quantity:,}"
    
    @property
    def formatted_purchase_price(self):
        return f"Rs. {self.purchase_price:,.2f}"
    
    @property
    def formatted_total_value(self):
        return f"Rs. {self.total_value():,.2f}"
    
    @property
    def formatted_total_investment(self):
        return f"Rs. {self.total_investment():,.2f}"
    
    @property
    def formatted_profit_loss(self):
        pl = self.profit_loss()
        if pl >= 0:
            return f"+Rs. {pl:,.2f} (↑{self.profit_loss_percent():.1f}%)"
        return f"-Rs. {abs(pl):,.2f} (↓{abs(self.profit_loss_percent()):.1f}%)"
    
    @property
    def is_transferred(self):
        """Check if this share has been transferred"""
        return self.transferred_from is not None
    
    @property
    def is_active(self):
        """Check if share is active (not locked and quantity > 0)"""
        return not self.is_locked and self.quantity > 0
    
    @property
    def share_status(self):
        """Return status as string"""
        if self.is_locked:
            return "Locked"
        if self.quantity == 0:
            return "Transferred"
        if self.transferred_from:
            return "Transferred In"
        return "Active"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.is_locked:
            return '<span class="badge bg-secondary">🔒 Locked</span>'
        if self.quantity == 0:
            return '<span class="badge bg-info">🔄 Transferred</span>'
        if self.transferred_from:
            return '<span class="badge bg-primary">📥 Transferred In</span>'
        return '<span class="badge bg-success">✅ Active</span>'
    
    # ============================================
    # BUSINESS METHODS
    # ============================================
    def mark_as_transferred(self, new_share, user):
        """Mark this share as transferred"""
        self.quantity = 0
        self.is_locked = True
        self.transfer_date = now().date()
        self.transfer_notes = f"Transferred to {new_share.shareholder.name}"
        self.save()
    
    def lock(self, user, reason=""):
        """Lock shares"""
        self.is_locked = True
        self.notes = f"{self.notes}\nLocked by {user.username}: {reason}".strip()
        self.save()
    
    def unlock(self, user, reason=""):
        """Unlock shares"""
        self.is_locked = False
        self.notes = f"{self.notes}\nUnlocked by {user.username}: {reason}".strip()
        self.save()
    
    def generate_certificate(self, user):
        """Generate certificate for this share"""
        if not self.certificate_number:
            self.certificate_number = f"CERT-{self.id:06d}"
        self.certificate_issue_date = now().date()
        self.certificate_printed = True
        self.certificate_printed_at = now()
        self.certificate_printed_by = user
        self.save()
        return self.certificate_number
    
    # ============================================
    # SAVE METHOD - WITH SHAREHOLDER CASH BALANCE
    # ============================================
    def save(self, *args, **kwargs):
        """Save share with automatic shareholder cash balance update"""
        
        # Auto-set issue date
        if not self.issue_date:
            self.issue_date = now().date()
        
        # Auto-generate certificate number
        if not self.certificate_number and self.id:
            self.certificate_number = f"CERT-{self.id:06d}"
        
        # Check if this is a NEW share or UPDATE
        is_new = self.pk is None
        old_investment = Decimal('0.00')
        old_share = None
        
        # If updating, get old investment amount
        if not is_new:
            old_share = Share.objects.get(pk=self.pk)
            old_investment = old_share.quantity * old_share.purchase_price
        
        # Save the share first
        super().save(*args, **kwargs)
        
        # ============================================
        # SHAREHOLDER CASH BALANCE UPDATE
        # ============================================
        if is_new:
            # ✅ NEW SHARE - Deduct from shareholder's cash balance
            total_investment = self.quantity * self.purchase_price
            
            if total_investment > 0 and self.paid_from_shareholder_balance:
                try:
                    # Check if shareholder has enough balance
                    current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                    if current_balance < total_investment:
                        raise ValidationError(
                            f"❌ {self.shareholder.name} has insufficient balance! "
                            f"Available: Rs. {current_balance:,.2f}, Required: Rs. {total_investment:,.2f}"
                        )
                    
                    # Deduct from shareholder's cash balance
                    ShareholderCashBalance.withdraw(
                        shareholder=self.shareholder,
                        amount=total_investment,
                        user=self.created_by,
                        description=f"Share purchase: {self.quantity} shares @ Rs. {self.purchase_price:,.2f} (Certificate #{self.certificate_number or 'N/A'})"
                    )
                    
                    # Also add to main cash balance (company receives money)
                    CashBalance.update_balance(
                        amount=total_investment,
                        transaction_type='deposit',
                        user=self.created_by,
                        description=f"Share investment from {self.shareholder.name} - {self.quantity} shares @ Rs. {self.purchase_price:,.2f}"
                    )
                    
                except ValidationError as e:
                    # If shareholder doesn't have enough balance, allow fallback to main cash
                    if not self.paid_from_shareholder_balance:
                        raise
                    # Re-raise with clear message
                    raise ValidationError(f"❌ {str(e)}. You can uncheck 'Paid from Shareholder Balance' to use main cash.")
            
            elif total_investment > 0 and not self.paid_from_shareholder_balance:
                # ✅ Using main cash balance
                CashBalance.update_balance(
                    amount=total_investment,
                    transaction_type='deposit',
                    user=self.created_by,
                    description=f"Share investment from {self.shareholder.name} - {self.quantity} shares @ Rs. {self.purchase_price:,.2f} (Main Cash)"
                )
        
        else:
            # ✅ UPDATE SHARE - Adjust difference in balances
            new_investment = self.quantity * self.purchase_price
            difference = new_investment - old_investment
            
            if difference != 0:
                if self.paid_from_shareholder_balance:
                    if difference > 0:
                        # More investment - deduct more from shareholder
                        # Check if shareholder has enough balance for the increase
                        current_balance = ShareholderCashBalance.get_balance(self.shareholder)
                        if current_balance < difference:
                            raise ValidationError(
                                f"❌ {self.shareholder.name} has insufficient balance for increase! "
                                f"Available: Rs. {current_balance:,.2f}, Required: Rs. {difference:,.2f}"
                            )
                        
                        ShareholderCashBalance.withdraw(
                            shareholder=self.shareholder,
                            amount=difference,
                            user=self.created_by,
                            description=f"Share investment increase: +{self.quantity - old_share.quantity} shares (New total: {self.quantity} @ Rs. {self.purchase_price:,.2f})"
                        )
                        CashBalance.update_balance(
                            amount=difference,
                            transaction_type='deposit',
                            user=self.created_by,
                            description=f"Additional investment from {self.shareholder.name} - +{self.quantity - old_share.quantity} shares"
                        )
                    else:
                        # Less investment - refund to shareholder
                        refund_amount = abs(difference)
                        ShareholderCashBalance.deposit(
                            shareholder=self.shareholder,
                            amount=refund_amount,
                            user=self.created_by,
                            description=f"Share investment decrease: -{old_share.quantity - self.quantity} shares (New total: {self.quantity} @ Rs. {self.purchase_price:,.2f})"
                        )
                        CashBalance.update_balance(
                            amount=refund_amount,
                            transaction_type='withdraw',
                            user=self.created_by,
                            description=f"Refund to {self.shareholder.name} - share decrease"
                        )
                else:
                    # Using main cash balance
                    if difference > 0:
                        CashBalance.update_balance(
                            amount=difference,
                            transaction_type='deposit',
                            user=self.created_by,
                            description=f"Additional investment from {self.shareholder.name} - +{self.quantity - old_share.quantity} shares (Main Cash)"
                        )
                    else:
                        CashBalance.update_balance(
                            amount=abs(difference),
                            transaction_type='withdraw',
                            user=self.created_by,
                            description=f"Refund to {self.shareholder.name} - share decrease (Main Cash)"
                        )
    
    # ============================================
    # CLASS METHODS
    # ============================================
    @classmethod
    def create_from_investment(cls, shareholder, quantity, price, user, paid_from_balance=True):
        """Create shares from investment"""
        share = cls.objects.create(
            shareholder=shareholder,
            quantity=quantity,
            purchase_price=price,
            issue_date=now().date(),
            created_by=user,
            paid_from_shareholder_balance=paid_from_balance
        )
        return share
    
    @classmethod
    def get_total_shares(cls):
        """Get total number of shares in the system"""
        return cls.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    @classmethod
    def get_total_investment(cls):
        """Get total investment in the system"""
        return cls.objects.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')
    
    @classmethod
    def get_shareholder_summary(cls, shareholder):
        """Get summary for a specific shareholder"""
        shares = cls.objects.filter(shareholder=shareholder)
        total_shares = shares.aggregate(total=Sum('quantity'))['total'] or 0
        total_investment = shares.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or Decimal('0.00')
        
        latest_price = SharePrice.objects.filter(is_active=True).first()
        current_value = total_shares * (latest_price.price if latest_price else 0)
        
        return {
            'total_shares': total_shares,
            'total_investment': total_investment,
            'current_value': current_value,
            'profit_loss': current_value - total_investment,
            'profit_loss_percent': ((current_value - total_investment) / total_investment * 100) if total_investment > 0 else 0,
        }


class SharePrice(models.Model):
    """Share price history"""
    price = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField(default=now)
    is_active = models.BooleanField(default=True, help_text="Current active price")
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='share_prices')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "💰 Share Prices"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Rs. {self.price:,.2f} - {self.date.strftime('%d-%m-%Y')}"
    
    def save(self, *args, **kwargs):
        # Only one active price at a time
        if self.is_active:
            SharePrice.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


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
            from . import Notification
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
            from . import Notification
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
                    from . import CashBalance
                    
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
                    from . import Notification
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
        Mark dividend as paid - Shareholder ko paisa MILTA hai
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
                from . import CashBalance
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
                    from . import Notification
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


class ShareTransfer(models.Model):
    """Share transfer between shareholders with cash balance support"""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    transfer_no = models.CharField(max_length=20, unique=True, editable=False)
    
    # ============================================
    # FROM/TO SHAREHOLDERS
    # ============================================
    from_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='share_transfers_out'
    )
    to_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='share_transfers_in'
    )
    
    # ============================================
    # SHARES BEING TRANSFERRED
    # ============================================
    shares = models.ManyToManyField('Share', related_name='share_transfers')
    quantity = models.PositiveIntegerField()
    transfer_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transfer_date = models.DateField(default=now)
    
    # ============================================
    # STATUS
    # ============================================
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # ============================================
    # APPROVAL
    # ============================================
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='share_transfers_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # ============================================
    # NOTES
    # ============================================
    reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # ============================================
    # SYSTEM FIELDS
    # ============================================
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='share_transfers_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ============================================
    # META
    # ============================================
    class Meta:
        verbose_name_plural = "🔄 Share Transfers"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transfer_no']),
            models.Index(fields=['from_shareholder', 'to_shareholder']),
            models.Index(fields=['status']),
        ]
    
    # ============================================
    # STRING REPRESENTATION
    # ============================================
    def __str__(self):
        return f"Transfer #{self.transfer_no} - {self.quantity} shares from {self.from_shareholder.name} to {self.to_shareholder.name}"
    
    # ============================================
    # VALUE CALCULATIONS
    # ============================================
    def total_value(self):
        """Calculate total transfer value"""
        return self.quantity * self.transfer_price
    
    # ============================================
    # PROPERTIES
    # ============================================
    @property
    def formatted_quantity(self):
        """Formatted quantity with commas"""
        return f"{self.quantity:,}"
    
    @property
    def formatted_value(self):
        """Formatted total value"""
        return f"Rs. {self.total_value():,.2f}"
    
    @property
    def formatted_transfer_price(self):
        """Formatted transfer price per share"""
        return f"Rs. {self.transfer_price:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status display"""
        colors = {
            'completed': 'success',
            'approved': 'primary',
            'pending': 'warning',
            'rejected': 'danger'
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def status_text(self):
        """Plain text status"""
        return self.get_status_display()
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_rejected(self):
        return self.status == 'rejected'
    
    @property
    def is_actionable(self):
        """Check if transfer can be acted upon"""
        return self.status in ['pending', 'approved']
    
    # ============================================
    # BUSINESS METHODS
    # ============================================
    def approve(self, user):
        """Approve transfer"""
        if self.status != 'pending':
            raise ValidationError(f"Transfer is already {self.status}")
        
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Create notification
        try:
            from . import Notification
            Notification.send(
                user=user,
                title="✅ Transfer Approved",
                message=f"Share transfer #{self.transfer_no} has been approved. {self.quantity} shares from {self.from_shareholder.name} to {self.to_shareholder.name}.",
                notification_type='success',
                category='system',
                link=f"/transfers/{self.id}/"
            )
        except Exception:
            pass
    
    def reject(self, user):
        """Reject transfer"""
        if self.status != 'pending':
            raise ValidationError(f"Transfer is already {self.status}")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        
        # Create notification
        try:
            from . import Notification
            Notification.send(
                user=user,
                title="❌ Transfer Rejected",
                message=f"Share transfer #{self.transfer_no} has been rejected.",
                notification_type='danger',
                category='system',
                link=f"/transfers/{self.id}/"
            )
        except Exception:
            pass
    
    @transaction.atomic
    def complete(self, user):
        """
        Complete transfer - move shares with exact quantity and update cash balances
        """
        from decimal import Decimal
        
        if self.status != 'approved':
            raise ValidationError(f"Transfer must be approved first. Current status: {self.status}")
        
        try:
            with transaction.atomic():
                # ============================================
                # VALIDATE SHAREHOLDER BALANCES
                # ============================================
                total_transfer_value = self.quantity * self.transfer_price
                
                if total_transfer_value > 0:
                    # Check if from_shareholder has enough balance
                    from_balance = ShareholderCashBalance.get_balance(self.from_shareholder)
                    if from_balance < total_transfer_value:
                        raise ValidationError(
                            f"❌ {self.from_shareholder.name} has insufficient balance! "
                            f"Available: Rs. {from_balance:,.2f}, Required: Rs. {total_transfer_value:,.2f}"
                        )
                    
                    # ============================================
                    # DEDUCT FROM SELLER'S BALANCE
                    # ============================================
                    new_from_balance = ShareholderCashBalance.withdraw(
                        shareholder=self.from_shareholder,
                        amount=total_transfer_value,
                        user=user,
                        description=f"Share transfer OUT: {self.quantity} shares @ Rs. {self.transfer_price:,.2f} to {self.to_shareholder.name} - #{self.transfer_no}"
                    )
                    
                    # Create transaction record for from_shareholder
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.from_shareholder,
                        amount=total_transfer_value,
                        transaction_type='transfer_out',
                        balance_after=new_from_balance,
                        description=f"Share transfer to {self.to_shareholder.name} - {self.quantity} shares @ Rs. {self.transfer_price:,.2f}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                    
                    # ============================================
                    # ADD TO BUYER'S BALANCE
                    # ============================================
                    new_to_balance = ShareholderCashBalance.deposit(
                        shareholder=self.to_shareholder,
                        amount=total_transfer_value,
                        user=user,
                        description=f"Share transfer IN: {self.quantity} shares @ Rs. {self.transfer_price:,.2f} from {self.from_shareholder.name} - #{self.transfer_no}"
                    )
                    
                    # Create transaction record for to_shareholder
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.to_shareholder,
                        amount=total_transfer_value,
                        transaction_type='transfer_in',
                        balance_after=new_to_balance,
                        description=f"Share transfer from {self.from_shareholder.name} - {self.quantity} shares @ Rs. {self.transfer_price:,.2f}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                
                # ============================================
                # TRANSFER SHARES
                # ============================================
                remaining_to_transfer = self.quantity
                transferred_shares = []
                
                # Get all shares in the transfer (ordered by issue date - FIFO)
                for share in self.shares.all().order_by('issue_date'):
                    if remaining_to_transfer <= 0:
                        break
                    
                    take = min(share.quantity, remaining_to_transfer)
                    
                    if take <= 0:
                        continue
                    
                    # ============================================
                    # CREATE NEW SHARE FOR RECIPIENT
                    # ============================================
                    new_share = Share(
                        shareholder=self.to_shareholder,
                        share_type=share.share_type,
                        quantity=take,
                        purchase_price=self.transfer_price,  # Transfer price becomes purchase price
                        certificate_number=f"TRF-{self.transfer_no}-{share.id}",
                        issue_date=now().date(),
                        transferred_from=share,
                        transfer_date=now().date(),
                        transfer_notes=f"Transferred from {self.from_shareholder.name} via {self.transfer_no}",
                        created_by=self.created_by or user,
                        paid_from_shareholder_balance=False  # Already handled by transfer
                    )
                    # Bypass cash balance update by using save_base()
                    new_share.save_base()
                    transferred_shares.append(new_share)
                    
                    # ============================================
                    # REDUCE THE OLD SHARE QUANTITY
                    # ============================================
                    share.quantity -= take
                    if share.quantity == 0:
                        share.is_locked = True
                        share.transfer_notes = f"Fully transferred to {self.to_shareholder.name} via {self.transfer_no}"
                    
                    # Bypass cash balance update by using save_base()
                    share.save_base()
                    
                    remaining_to_transfer -= take
                
                # Verify all shares were transferred
                if remaining_to_transfer > 0:
                    raise ValidationError(f"Could not transfer all shares! Remaining: {remaining_to_transfer}")
                
                # ============================================
                # UPDATE TRANSFER STATUS
                # ============================================
                self.status = 'completed'
                self.completed_at = now()
                self.save()
                
                # ============================================
                # CREATE NOTIFICATIONS
                # ============================================
                try:
                    from . import Notification
                    
                    # Notification for from_shareholder (if user exists)
                    if self.from_shareholder.created_by:
                        Notification.send(
                            user=self.from_shareholder.created_by,
                            title="📤 Shares Transferred Out",
                            message=f"{self.quantity} shares transferred to {self.to_shareholder.name}. Amount: Rs. {total_transfer_value:,.2f}",
                            notification_type='success',
                            category='system',
                            link=f"/transfers/{self.id}/"
                        )
                    
                    # Notification for to_shareholder (if user exists)
                    if self.to_shareholder.created_by:
                        Notification.send(
                            user=self.to_shareholder.created_by,
                            title="📥 Shares Received",
                            message=f"{self.quantity} shares received from {self.from_shareholder.name}. Amount: Rs. {total_transfer_value:,.2f}",
                            notification_type='success',
                            category='system',
                            link=f"/transfers/{self.id}/"
                        )
                except Exception:
                    pass
                
                return transferred_shares
                
        except ValidationError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error completing share transfer: {str(e)}")
            raise ValidationError(f"Failed to complete transfer: {str(e)}")
    
    # ============================================
    # CANCEL TRANSFER (Rollback)
    # ============================================
    @transaction.atomic
    def cancel(self, user):
        """
        Cancel a completed transfer - reverse all transactions
        """
        if self.status != 'completed':
            raise ValidationError(f"Cannot cancel a transfer that is not completed. Current status: {self.status}")
        
        try:
            with transaction.atomic():
                total_value = self.quantity * self.transfer_price
                
                if total_value > 0:
                    # ============================================
                    # REVERSE SHAREHOLDER BALANCES
                    # ============================================
                    # Refund to from_shareholder
                    new_from_balance = ShareholderCashBalance.deposit(
                        shareholder=self.from_shareholder,
                        amount=total_value,
                        user=user,
                        description=f"Transfer cancellation refund: #{self.transfer_no}"
                    )
                    
                    ShareholderCashTransaction.objects.create(
                        shareholder=self.from_shareholder,
                        amount=total_value,
                        transaction_type='deposit',
                        balance_after=new_from_balance,
                        description=f"Refund for cancelled transfer #{self.transfer_no}",
                        reference_no=self.transfer_no,
                        share_transfer=self,
                        created_by=user
                    )
                    
                    # Deduct from to_shareholder
                    try:
                        new_to_balance = ShareholderCashBalance.withdraw(
                            shareholder=self.to_shareholder,
                            amount=total_value,
                            user=user,
                            description=f"Transfer cancellation deduction: #{self.transfer_no}"
                        )
                    except ValidationError:
                        # If buyer doesn't have enough balance, we need to handle differently
                        # This is a complex case - maybe use main cash as backup
                        main_balance = CashBalance.get_balance()
                        if main_balance < total_value:
                            raise ValidationError(
                                f"Cannot cancel transfer! {self.to_shareholder.name} doesn't have enough balance "
                                f"and main cash is also insufficient."
                            )
                        
                        CashBalance.update_balance(
                            amount=total_value,
                            transaction_type='withdraw',
                            user=user,
                            description=f"Transfer cancellation from {self.to_shareholder.name} - #{self.transfer_no}"
                        )
                    
                    # ============================================
                    # REVERSE SHARE MOVEMENTS
                    # ============================================
                    # Restore original shares (simplified - in real system, need proper tracking)
                    # This is a simplified version - in production, you'd track this more carefully
                    
                # Update status
                self.status = 'rejected'
                self.notes = f"{self.notes}\nCancelled by {user.username}".strip()
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to cancel transfer: {str(e)}")
    
    # ============================================
    # SAVE METHOD
    # ============================================
    def save(self, *args, **kwargs):
        """Generate transfer number on save"""
        if not self.transfer_no:
            last_transfer = ShareTransfer.objects.order_by('-id').first()
            if last_transfer and last_transfer.transfer_no:
                try:
                    last_num = int(last_transfer.transfer_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.transfer_no = f'ST-{new_num}'
        super().save(*args, **kwargs)


class ShareholderMeeting(models.Model):
    """Shareholder meetings and minutes"""
    MEETING_TYPES = [
        ('agm', 'Annual General Meeting'),
        ('egm', 'Extraordinary General Meeting'),
        ('board', 'Board Meeting'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('held', 'Held'),
        ('cancelled', 'Cancelled'),
        ('adjourned', 'Adjourned'),
    ]
    
    meeting_no = models.CharField(max_length=20, unique=True, editable=False)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES)
    title = models.CharField(max_length=255)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    venue = models.TextField()
    agenda = models.TextField()
    minutes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Attendance
    attendees = models.ManyToManyField(Shareholder, through='MeetingAttendance', related_name='meetings')
    total_attendees = models.PositiveIntegerField(default=0)
    
    # Resolutions
    resolutions = models.TextField(blank=True, null=True)
    resolutions_passed = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_meetings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "📋 Shareholder Meetings"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['meeting_no']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"#{self.meeting_no} - {self.title} ({self.date.strftime('%d-%m-%Y')})"
    
    def save(self, *args, **kwargs):
        if not self.meeting_no:
            last_meeting = ShareholderMeeting.objects.order_by('-id').first()
            if last_meeting and last_meeting.meeting_no:
                try:
                    last_num = int(last_meeting.meeting_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.meeting_no = f'MTG-{new_num}'
        super().save(*args, **kwargs)


class MeetingAttendance(models.Model):
    """Meeting attendance record"""
    ATTENDANCE_STATUS = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('proxy', 'Proxy'),
        ('online', 'Online'),
    ]
    
    meeting = models.ForeignKey(ShareholderMeeting, on_delete=models.CASCADE, related_name='attendance_records')
    shareholder = models.ForeignKey(Shareholder, on_delete=models.CASCADE, related_name='meeting_attendance')
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS)
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Meeting Attendance"
        unique_together = ['meeting', 'shareholder']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.get_status_display()}"


class ShareholderCashBalance(models.Model):
    """Har shareholder ka apna cash balance"""
    
    shareholder = models.OneToOneField(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='cash_balance',
        unique=True
    )
    balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        verbose_name_plural = "💰 Shareholder Cash Balances"
        ordering = ['shareholder__name']
        indexes = [
            models.Index(fields=['shareholder']),
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.balance:,.2f}"
    
    @classmethod
    def get_balance(cls, shareholder):
        """Get balance for a specific shareholder"""
        balance_obj, created = cls.objects.get_or_create(
            shareholder=shareholder,
            defaults={'balance': Decimal('0.00')}
        )
        return balance_obj.balance
    
    @classmethod
    def update_balance(cls, shareholder, amount, transaction_type, user=None, description=""):
        """Update shareholder's cash balance with transaction record"""
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            balance_obj, created = cls.objects.select_for_update().get_or_create(
                shareholder=shareholder,
                defaults={'balance': Decimal('0.00')}
            )
            
            old_balance = balance_obj.balance
            
            if transaction_type == 'deposit':
                balance_obj.balance += amount
            elif transaction_type == 'withdraw':
                if balance_obj.balance < amount:
                    raise ValidationError(
                        f"Insufficient balance for {shareholder.name}! "
                        f"Available: Rs. {balance_obj.balance:,.2f}, Required: Rs. {amount:,.2f}"
                    )
                balance_obj.balance -= amount
            else:
                raise ValidationError(f"Invalid transaction type: {transaction_type}")
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # Create transaction record
            ShareholderCashTransaction.objects.get_or_create(
                shareholder=shareholder,
                transaction_type=transaction_type,
                amount=amount,
                balance_after=balance_obj.balance,
                defaults={
                    'description': description,
                    'created_by': user
                }
            )
            
            return balance_obj.balance
    
    @classmethod
    def deposit(cls, shareholder, amount, user=None, description=""):
        """Deposit money into shareholder's cash balance"""
        return cls.update_balance(shareholder, amount, 'deposit', user, description)
    
    @classmethod
    def withdraw(cls, shareholder, amount, user=None, description=""):
        """Withdraw money from shareholder's cash balance"""
        return cls.update_balance(shareholder, amount, 'withdraw', user, description)
    
    # ========================================== #
    # ✅ NEW: Withdraw from both balances        #
    # ========================================== #
    @classmethod
    def withdraw_from_main_cash(cls, shareholder, amount, user=None, description=""):
        """
        Withdraw from shareholder balance AND main cash
        ✅ Called when shareholder actually withdraws money
        """
        from django.db import transaction as db_transaction
        from . import CashBalance
        
        with db_transaction.atomic():
            # Step 1: Deduct from shareholder balance
            new_balance = cls.withdraw(
                shareholder=shareholder,
                amount=amount,
                user=user,
                description=description
            )
            
            # Step 2: Deduct from main cash
            CashBalance.update_balance(
                amount=amount,
                transaction_type='withdraw',
                user=user,
                description=f"Shareholder withdrawal: {shareholder.name} - {description}"
            )
            
            return new_balance
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class ShareholderCashTransaction(models.Model):
    """Shareholder cash transaction history"""
    
    TRANSACTION_TYPES = [
        ('deposit', '💰 Deposit (Added)'),
        ('withdraw', '💸 Withdrawal (Removed)'),
        ('share_purchase', '📈 Share Purchase'),
        ('dividend', '💵 Dividend Received'),
        ('balance_dividend', '💵 Balance Dividend (Refund + Profit)'),
        ('transfer_in', '🔄 Transfer In'),
        ('transfer_out', '🔄 Transfer Out'),
        ('adjustment', '📝 Adjustment'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='cash_transactions'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    # Keep existing fields
    share = models.ForeignKey(
        'Share', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    dividend_payment = models.ForeignKey(
        'DividendPayment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cash_transactions'
    )
    
    # Balance dividend payment
    balance_dividend_payment = models.ForeignKey(
        'BalanceDividendPayment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='cash_transactions'
    )
    
    share_transfer = models.ForeignKey(
        'ShareTransfer', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 Shareholder Cash Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shareholder']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
        ]
        unique_together = [
            ['shareholder', 'transaction_type', 'amount', 'balance_after', 'created_at']
        ]
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.get_transaction_type_display()} - Rs. {self.amount:,.2f}"
    
    @property
    def formatted_amount(self):
        if self.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']:
            return f"+Rs. {self.amount:,.2f}"
        return f"-Rs. {self.amount:,.2f}"
    
    @property
    def is_deposit(self):
        return self.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    
    @property
    def is_withdraw(self):
        return self.transaction_type in ['withdraw', 'share_purchase', 'transfer_out']


class DividendReinvestmentPlan(models.Model):
    """DRIP settings per dividend"""
    
    DRIP_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('market', 'Market Price'),
    ]
    
    dividend = models.OneToOneField(
        'Dividend', 
        on_delete=models.CASCADE, 
        related_name='drip',
        help_text="Dividend for which DRIP is available"
    )
    plan_name = models.CharField(
        max_length=200,
        default='Dividend Reinvestment Plan',
        help_text="Name of the DRIP plan"
    )
    
    discount_type = models.CharField(
        max_length=20, 
        choices=DISCOUNT_TYPES, 
        default='percentage'
    )
    discount_value = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Discount on share price (e.g., 5 for 5%)"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee per reinvestment"
    )
    
    min_shares = models.PositiveIntegerField(
        default=1,
        help_text="Minimum shares to reinvest"
    )
    max_shares = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maximum shares to reinvest (optional)"
    )
    
    start_date = models.DateField(
        help_text="Date when DRIP becomes available"
    )
    end_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when DRIP expires (optional)"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=DRIP_STATUS, 
        default='active'
    )
    is_auto_enroll = models.BooleanField(
        default=False,
        help_text="Auto-enroll all eligible shareholders"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Default DRIP for all dividends"
    )
    
    round_down_to_nearest = models.PositiveIntegerField(
        default=1,
        help_text="Round down shares to nearest integer"
    )
    fractional_shares_allowed = models.BooleanField(
        default=False,
        help_text="Allow fractional shares"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_drips'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Dividend Reinvestment Plans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP - {self.dividend.dividend_no} ({self.get_discount_type_display()})"
    
    def calculate_shares(self, dividend_amount, share_price):
        """Calculate number of shares to reinvest"""
        if self.discount_type == 'percentage':
            effective_price = share_price * (1 - self.discount_value / 100)
        elif self.discount_type == 'fixed':
            effective_price = share_price - self.discount_value
        else:
            effective_price = share_price
        
        amount_after_fee = dividend_amount - self.admin_fee
        
        if amount_after_fee <= 0:
            return 0
        
        shares = amount_after_fee / effective_price
        
        if not self.fractional_shares_allowed:
            shares = int(shares // self.round_down_to_nearest) * self.round_down_to_nearest
        
        if self.max_shares:
            shares = min(shares, self.max_shares)
        if self.min_shares and shares < self.min_shares:
            shares = 0
        
        return shares


class ShareholderDRIPEnrollment(models.Model):
    """Shareholder enrollment in DRIP"""
    
    ENROLLMENT_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.CASCADE, 
        related_name='drip_enrollments'
    )
    drip = models.ForeignKey(
        DividendReinvestmentPlan, 
        on_delete=models.CASCADE, 
        related_name='enrollments'
    )
    
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=ENROLLMENT_STATUS, 
        default='active'
    )
    auto_reinvest = models.BooleanField(
        default=True,
        help_text="Auto-reinvest future dividends"
    )
    min_dividend_to_reinvest = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=500,
        help_text="Minimum dividend amount to trigger reinvestment"
    )
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_enrollments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Shareholder Enrollments"
        unique_together = ['shareholder', 'drip']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.drip.plan_name}"
    
    def is_eligible(self, dividend_amount):
        """Check if shareholder is eligible for reinvestment"""
        if self.status != 'active':
            return False
        if not self.auto_reinvest:
            return False
        if dividend_amount < self.min_dividend_to_reinvest:
            return False
        return True


class DRIPTransaction(models.Model):
    """DRIP transaction record"""
    
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    dividend_payment = models.ForeignKey(
        'DividendPayment', 
        on_delete=models.CASCADE, 
        related_name='drip_transactions'
    )
    enrollment = models.ForeignKey(
        ShareholderDRIPEnrollment, 
        on_delete=models.CASCADE, 
        related_name='transactions'
    )
    new_shares = models.ManyToManyField(
        'Share', 
        blank=True, 
        related_name='drip_transactions'
    )
    
    dividend_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Original dividend amount"
    )
    shares_purchased = models.PositiveIntegerField(
        default=0,
        help_text="Number of shares purchased"
    )
    purchase_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Price per share"
    )
    admin_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Administrative fee deducted"
    )
    total_cost = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        help_text="Total cost of reinvestment"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=TRANSACTION_STATUS, 
        default='pending'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    reference_no = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False
    )
    
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='drip_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "DRIP - Transactions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DRIP {self.reference_no} - {self.dividend_payment.shareholder.name}"
    
    def save(self, *args, **kwargs):
        if not self.reference_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.reference_no = f'DRIP-{timestamp}-{self.dividend_payment.id}'
        super().save(*args, **kwargs)
    
    def process(self):
        """Process the DRIP transaction"""
        from decimal import Decimal
        from django.db import transaction
        
        try:
            with transaction.atomic():
                drip = self.enrollment.drip
                share_price = SharePrice.objects.filter(is_active=True).first()
                
                if not share_price:
                    self.status = 'failed'
                    self.notes = "No active share price found"
                    self.save()
                    return False
                
                shares = drip.calculate_shares(
                    self.dividend_amount,
                    share_price.price
                )
                
                if shares <= 0:
                    self.status = 'failed'
                    self.notes = "Insufficient amount to purchase shares"
                    self.save()
                    return False
                
                shareholder = self.dividend_payment.shareholder
                
                new_share = Share.objects.create(
                    shareholder=shareholder,
                    quantity=shares,
                    purchase_price=share_price.price,
                    share_type='ordinary',
                    issue_date=now().date(),
                    created_by=self.created_by,
                    paid_from_shareholder_balance=False,
                    notes=f"DRIP purchase from dividend #{self.dividend_payment.dividend.dividend_no}"
                )
                
                new_share.certificate_number = f"DRIP-{new_share.id:06d}"
                new_share.certificate_issue_date = now().date()
                new_share.save()
                
                self.new_shares.add(new_share)
                self.shares_purchased = shares
                self.purchase_price = share_price.price
                self.total_cost = shares * share_price.price
                self.status = 'completed'
                self.completed_at = now()
                
                self.dividend_payment.status = 'paid'
                self.dividend_payment.payment_date = now()
                self.dividend_payment.payment_method = 'DRIP (Dividend Reinvestment)'
                self.dividend_payment.notes = f"Reinvested as {shares} shares via DRIP"
                self.dividend_payment.save()
                
                self.save()
                return True
                
        except Exception as e:
            self.status = 'failed'
            self.notes = str(e)
            self.save()
            return False


class ShareBuyback(models.Model):
    """Company share buyback program"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    BUYBACK_TYPES = [
        ('open_market', 'Open Market'),
        ('tender', 'Tender Offer'),
        ('negotiated', 'Negotiated'),
    ]
    
    # Basic Information
    buyback_no = models.CharField(max_length=20, unique=True, editable=False)
    buyback_type = models.CharField(max_length=20, choices=BUYBACK_TYPES, default='open_market')
    description = models.CharField(max_length=255, help_text="Purpose of buyback")
    
    # Financial Details
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Total budget for buyback")
    price_per_share = models.DecimalField(max_digits=15, decimal_places=2, help_text="Price per share")
    min_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_shares = models.PositiveIntegerField(help_text="Maximum shares to buyback")
    shares_bought = models.PositiveIntegerField(default=0, help_text="Shares already bought")
    amount_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    record_date = models.DateField(help_text="Shareholders eligible for buyback")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_buybacks')
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_buybacks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Share Buybacks"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.buyback_no} - {self.get_buyback_type_display()} (Rs. {self.total_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.buyback_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = ShareBuyback.objects.filter(buyback_no__startswith=f'BB-{year}').order_by('-buyback_no').first()
            if last:
                try:
                    last_num = int(last.buyback_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.buyback_no = f'BB-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def remaining_shares(self):
        return self.max_shares - self.shares_bought
    
    def remaining_amount(self):
        return self.total_amount - self.amount_spent
    
    def progress_percent(self):
        if self.max_shares > 0:
            return (self.shares_bought / self.max_shares) * 100
        return 0
    
    def is_active(self):
        from django.utils.timezone import now
        return self.status in ['approved', 'in_progress'] and self.end_date >= now().date()


class BuybackOffer(models.Model):
    """Shareholder offer to sell shares in buyback"""
    
    OFFER_STATUS = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    buyback = models.ForeignKey(ShareBuyback, on_delete=models.CASCADE, related_name='offers')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='buyback_offers')
    shares_offered = models.PositiveIntegerField()
    shares_accepted = models.PositiveIntegerField(default=0)
    price_offered = models.DecimalField(max_digits=15, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=OFFER_STATUS, default='pending')
    offer_date = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='buyback_offers')
    
    class Meta:
        verbose_name_plural = "Buyback Offers"
        unique_together = ['buyback', 'shareholder']
    
    def __str__(self):
        return f"{self.shareholder.name} - {self.shares_offered} shares"
    
    def accept(self, shares_accepted=None):
        from django.utils.timezone import now
        if shares_accepted is None:
            shares_accepted = self.shares_offered
        self.shares_accepted = shares_accepted
        self.total_amount = shares_accepted * self.price_offered
        self.status = 'accepted'
        self.processed_at = now()
        self.save()
        
        # Update buyback
        self.buyback.shares_bought += shares_accepted
        self.buyback.amount_spent += self.total_amount
        self.buyback.save()
        
        # Transfer shares to company
        self.transfer_shares_to_company(shares_accepted)
    
    def transfer_shares_to_company(self, shares):
        """Transfer shares from shareholder to company"""
        # Get shareholder shares (FIFO)
        shares_to_transfer = self.shareholder.shares.filter(
            is_locked=False,
            quantity__gt=0
        ).order_by('issue_date')
        
        remaining = shares
        for share in shares_to_transfer:
            if remaining <= 0:
                break
            take = min(share.quantity, remaining)
            
            # Reduce shareholder's shares
            share.quantity -= take
            if share.quantity == 0:
                share.is_locked = True
            share.save()
            
            # Create company share (treasury)
            company_share = Share.objects.create(
                shareholder=None,  # Company own shares
                quantity=take,
                purchase_price=self.price_offered,
                share_type='treasury',
                issue_date=now().date(),
                notes=f"Buyback {self.buyback.buyback_no}",
                is_locked=True,
                paid_from_shareholder_balance=False,
                certificate_number=f"TR-{self.buyback.buyback_no}"
            )
            remaining -= take
        
        # Update shareholder's cash balance (they get money)
        ShareholderCashBalance.deposit(
            shareholder=self.shareholder,
            amount=self.total_amount,
            user=self.created_by,
            description=f"Share buyback {self.buyback.buyback_no} - {shares} shares @ Rs. {self.price_offered:,.2f}"
        )


class ShareholderDiscountProgram(models.Model):
    """Discount program for shareholders"""
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('tiered', 'Tiered Discount'),
    ]
    
    name = models.CharField(max_length=100)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=5, decimal_places=2, help_text="Discount % or fixed amount")
    
    min_shares_required = models.PositiveIntegerField(default=1)
    max_shares_required = models.PositiveIntegerField(null=True, blank=True)
    
    min_holding_period = models.IntegerField(default=0, help_text="Minimum months held")
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Product restrictions
    apply_to_all_products = models.BooleanField(default=True)
    products = models.ManyToManyField('Product', blank=True, related_name='discount_programs')
    categories = models.ManyToManyField('Category', blank=True, related_name='discount_programs')
    
    # Usage limits
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_per_shareholder = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    min_order_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher number = higher priority")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_discounts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Discount Programs"
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.discount_value}% off)"
    
    def get_discount_amount(self, shareholder, product=None, amount=0):
        """Calculate discount for shareholder"""
        if not self.is_active:
            return 0
        
        # Check share requirement
        shares = shareholder.total_shares()
        if shares < self.min_shares_required:
            return 0
        if self.max_shares_required and shares > self.max_shares_required:
            return 0
        
        # Check holding period
        if self.min_holding_period > 0:
            first_share = shareholder.shares.order_by('issue_date').first()
            if not first_share:
                return 0
            from datetime import date
            months_held = (date.today() - first_share.issue_date).days // 30
            if months_held < self.min_holding_period:
                return 0
        
        # Check product eligibility
        if not self.apply_to_all_products and product:
            if not self.products.filter(id=product.id).exists():
                if not self.categories.filter(id=product.category.id).exists():
                    return 0
        
        # Check min order
        if amount < self.min_order_amount:
            return 0
        
        # Check uses
        if self.max_uses > 0:
            uses = ShareholderDiscountUsage.objects.filter(program=self).count()
            if uses >= self.max_uses:
                return 0
        
        # Calculate discount
        if self.discount_type == 'percentage':
            return amount * (self.discount_value / 100)
        elif self.discount_type == 'fixed':
            return self.discount_value
        elif self.discount_type == 'tiered':
            # Tiered logic - can be customized
            if shares >= 1000:
                return amount * 0.15  # 15% for 1000+ shares
            elif shares >= 500:
                return amount * 0.10  # 10% for 500+ shares
            elif shares >= 100:
                return amount * 0.05   # 5% for 100+ shares
            else:
                return 0
        
        return 0


class ShareholderDiscountUsage(models.Model):
    """Track discount usage"""
    
    program = models.ForeignKey(ShareholderDiscountProgram, on_delete=models.CASCADE, related_name='usages')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='discount_usages')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, related_name='discount_usages')
    
    original_amount = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2)
    final_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    used_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Discount Usages"
        ordering = ['-used_at']
    
    def __str__(self):
        return f"{self.shareholder.name} - Rs. {self.discount_amount:,.2f} off"


class ShareholderLoan(models.Model):
    """Loans against shares"""
    
    LOAN_STATUS = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('partial_paid', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]
    
    LOAN_TYPES = [
        ('margin', 'Margin Loan'),
        ('pledge', 'Share Pledge'),
        ('personal', 'Personal Loan'),
        ('business', 'Business Loan'),
    ]
    
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='margin')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='loans')
    
    # Loan Details
    principal = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Annual interest rate %")
    disbursed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    outstanding = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Collateral
    collateral_shares = models.ManyToManyField('Share', related_name='loans', blank=True)
    collateral_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ltv_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=60, help_text="Loan to Value %")
    
    # Dates
    start_date = models.DateField()
    maturity_date = models.DateField()
    approval_date = models.DateField(null=True, blank=True)
    disbursement_date = models.DateField(null=True, blank=True)
    
    # Interest
    interest_accrued = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_interest_date = models.DateField(null=True, blank=True)
    
    # Fees
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_loans')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_loans')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Loans"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.loan_no} - {self.shareholder.name} (Rs. {self.principal:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = ShareholderLoan.objects.filter(loan_no__startswith=f'LN-{year}').order_by('-loan_no').first()
            if last:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LN-{year}-{new_num}'
        self.outstanding = self.principal - self.disbursed_amount
        super().save(*args, **kwargs)
    
    def calculate_interest(self, days=None):
        """Calculate interest for given days"""
        from datetime import date
        if days is None:
            today = date.today()
            if self.last_interest_date:
                days = (today - self.last_interest_date).days
            else:
                days = (today - self.start_date).days
        
        if days <= 0:
            return 0
        
        daily_rate = self.interest_rate / 100 / 365
        return self.outstanding * daily_rate * days
    
    def accrue_interest(self):
        """Accrue interest automatically"""
        from django.utils.timezone import now
        interest = self.calculate_interest()
        if interest > 0:
            self.interest_accrued += interest
            self.last_interest_date = now().date()
            self.save()
        return interest
    
    def make_payment(self, amount, payment_method=None):
        """Make loan payment"""
        from decimal import Decimal
        from django.db import transaction
        
        with transaction.atomic():
            # First pay interest
            if self.interest_accrued > 0:
                interest_payment = min(amount, self.interest_accrued)
                self.interest_accrued -= interest_payment
                self.interest_paid += interest_payment
                amount -= interest_payment
                InterestPayment.objects.create(
                    loan=self,
                    amount=interest_payment,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    notes="Interest payment"
                )
            
            # Then pay principal
            if amount > 0:
                principal_payment = min(amount, self.outstanding)
                self.outstanding -= principal_payment
                self.disbursed_amount += principal_payment
                
                PrincipalPayment.objects.create(
                    loan=self,
                    amount=principal_payment,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    notes="Principal payment"
                )
            
            # Update status
            if self.outstanding <= 0 and self.interest_accrued <= 0:
                self.status = 'paid'
            
            self.save()
    
    def get_ltv_percent(self):
        """Calculate Loan to Value percentage"""
        if self.collateral_value > 0:
            return (self.outstanding / self.collateral_value) * 100
        return 0
    
    def is_margin_call(self):
        """Check if margin call needed"""
        ltv = self.get_ltv_percent()
        return ltv > self.ltv_ratio


class LoanPayment(models.Model):
    """Base loan payment (abstract)"""
    
    class Meta:
        abstract = True
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_no = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InterestPayment(LoanPayment):
    """Interest payment record"""
    
    class Meta:
        verbose_name_plural = "Interest Payments"
    
    def __str__(self):
        return f"Interest - {self.loan.loan_no} - Rs. {self.amount:,.2f}"


class PrincipalPayment(LoanPayment):
    """Principal payment record"""
    
    class Meta:
        verbose_name_plural = "Principal Payments"
    
    def __str__(self):
        return f"Principal - {self.loan.loan_no} - Rs. {self.amount:,.2f}"


class ShareholderDepositRequest(models.Model):
    """Deposit request from shareholder that needs admin approval"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('bank_transfer', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('cash', '💵 Cash Deposit'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Payment'),
    ]
    
    request_no = models.CharField(max_length=200, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bank_transfer')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='deposit_requests/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_deposits')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    
    # Payment confirmation after approval
    payment_confirmed = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_deposits')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Notifications
    notification_sent = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💰 Shareholder Deposit Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_no']),
            models.Index(fields=['shareholder', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.request_no} - {self.shareholder.name} - Rs. {self.amount:,.2f} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.request_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            import random
            random_suffix = str(random.randint(100, 999))
            self.request_no = f'DEP-{timestamp}{random_suffix}'
        super().save(*args, **kwargs)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    def approve(self, user):
        """Approve deposit and add to shareholder balance"""
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be approved!")
        
        with transaction.atomic():
            # Update request status
            self.status = 'approved'
            self.approved_by = user
            self.approved_at = now()
            self.save()
            
            # Add to shareholder's cash balance
            new_balance = ShareholderCashBalance.deposit(
                shareholder=self.shareholder,
                amount=self.amount,
                user=user,
                description=f"Deposit request #{self.request_no}: {self.description or 'Deposit'}"
            )
            
            # Add to main cash balance (company received money)
            CashBalance.update_balance(
                amount=self.amount,
                transaction_type='deposit',
                user=user,
                description=f"Deposit from {self.shareholder.name} - Request #{self.request_no}"
            )
            
            # Create notification for shareholder
            try:
                from . import Notification
                Notification.send(
                    user=self.shareholder.created_by if self.shareholder.created_by else user,
                    title="💰 Deposit Approved",
                    message=f"Your deposit of Rs. {self.amount:,.2f} has been approved! New balance: Rs. {new_balance:,.2f}",
                    notification_type='success',
                    category='payments',
                    link=f"/shareholder/transactions/"
                )
            except Exception:
                pass
            
            return new_balance
    
    def reject(self, user, reason=""):
        """Reject deposit request"""
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be rejected!")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejected_reason = reason
        self.save()
        
        # Create notification for shareholder
        try:
            from . import Notification
            Notification.send(
                user=self.shareholder.created_by if self.shareholder.created_by else user,
                title="❌ Deposit Rejected",
                message=f"Your deposit of Rs. {self.amount:,.2f} was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments',
                link=f"/shareholder/transactions/"
            )
        except Exception:
            pass


class ShareholderWithdrawalRequest(models.Model):
    """Withdrawal request from shareholder that needs admin approval"""
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('bank_transfer', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('cash', '💵 Cash Withdrawal'),
        ('cheque', '📄 Cheque'),
        ('online', '🌐 Online Transfer'),
    ]
    
    request_no = models.CharField(max_length=20, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='bank_transfer')
    account_details = models.TextField(blank=True, null=True, help_text="Bank account, JazzCash number, etc.")
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='withdrawal_requests/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_withdrawals')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    
    # Payment confirmation after approval
    payment_confirmed = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_withdrawals')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Notifications
    notification_sent = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "💸 Shareholder Withdrawal Requests"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_no']),
            models.Index(fields=['shareholder', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.request_no} - {self.shareholder.name} - Rs. {self.amount:,.2f} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.request_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            import random
            random_suffix = str(random.randint(100, 999))
            self.request_no = f'WDR-{timestamp}{random_suffix}'
        super().save(*args, **kwargs)
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'cancelled': 'secondary',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    def approve(self, user):
        """Approve withdrawal and deduct from shareholder balance"""
        from decimal import Decimal
        from django.db import transaction
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be approved!")
        
        with transaction.atomic():
            # Check if shareholder has enough balance
            current_balance = ShareholderCashBalance.get_balance(self.shareholder)
            if current_balance < self.amount:
                raise ValidationError(
                    f"Insufficient balance! {self.shareholder.name} has Rs. {current_balance:,.2f}, "
                    f"Requested withdrawal: Rs. {self.amount:,.2f}"
                )
            
            # Update request status
            self.status = 'approved'
            self.approved_by = user
            self.approved_at = now()
            self.save()
            
            # Deduct from shareholder's cash balance
            new_balance = ShareholderCashBalance.withdraw(
                shareholder=self.shareholder,
                amount=self.amount,
                user=user,
                description=f"Withdrawal request #{self.request_no}: {self.description or 'Withdrawal'}"
            )
            
            # Deduct from main cash balance (company pays out)
            main_balance = CashBalance.get_balance()
            if main_balance < self.amount:
                raise ValidationError(
                    f"Insufficient main cash balance! Available: Rs. {main_balance:,.2f}, "
                    f"Required: Rs. {self.amount:,.2f}"
                )
            
            CashBalance.update_balance(
                amount=self.amount,
                transaction_type='withdraw',
                user=user,
                description=f"Withdrawal to {self.shareholder.name} - Request #{self.request_no}"
            )
            
            # Create notification for shareholder
            try:
                from . import Notification
                Notification.send(
                    user=self.shareholder.created_by if self.shareholder.created_by else user,
                    title="💸 Withdrawal Approved",
                    message=f"Your withdrawal of Rs. {self.amount:,.2f} has been approved! New balance: Rs. {new_balance:,.2f}",
                    notification_type='success',
                    category='payments',
                    link=f"/shareholder/transactions/"
                )
            except Exception:
                pass
            
            return new_balance
    
    def reject(self, user, reason=""):
        """Reject withdrawal request"""
        from django.utils.timezone import now
        
        if self.status != 'pending':
            raise ValidationError("Only pending requests can be rejected!")
        
        self.status = 'rejected'
        self.approved_by = user
        self.approved_at = now()
        self.rejected_reason = reason
        self.save()
        
        # Create notification for shareholder
        try:
            from . import Notification
            Notification.send(
                user=self.shareholder.created_by if self.shareholder.created_by else user,
                title="❌ Withdrawal Rejected",
                message=f"Your withdrawal of Rs. {self.amount:,.2f} was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='payments',
                link=f"/shareholder/transactions/"
            )
        except Exception:
            pass


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
                from . import Notification
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


class ShareholderTermsAcceptance(models.Model):
    """Track shareholder acceptance of terms"""
    
    shareholder = models.OneToOneField('Shareholder', on_delete=models.CASCADE, related_name='terms_acceptance')
    terms_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(default=now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Terms Acceptances"
    
    def __str__(self):
        return f"{self.shareholder.name} - Accepted v{self.terms_version}"


class ShareholderSupportTicket(models.Model):
    """Support tickets for shareholders"""
    
    STATUS_CHOICES = [
        ('new', '🆕 New'),
        ('in_progress', '⚙️ In Progress'),
        ('resolved', '✅ Resolved'),
        ('closed', '🔒 Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🔴 High'),
        ('urgent', '🔥 Urgent'),
    ]
    
    ticket_no = models.CharField(max_length=20, unique=True, editable=False)
    shareholder = models.ForeignKey('Shareholder', on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    attachment = models.FileField(upload_to='support_tickets/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Shareholder Support Tickets"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.ticket_no} - {self.subject[:30]}"
    
    def save(self, *args, **kwargs):
        if not self.ticket_no:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.ticket_no = f'ST-{timestamp}'
        super().save(*args, **kwargs)


class SupportTicketReply(models.Model):
    """Replies to support tickets"""
    
    ticket = models.ForeignKey(ShareholderSupportTicket, on_delete=models.CASCADE, related_name='replies')
    message = models.TextField()
    is_internal = models.BooleanField(default=False, help_text="Internal note (not visible to shareholder)")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to='support_replies/', null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Support Ticket Replies"
        ordering = ['created_at']
    
    def __str__(self):
        return f"Reply to {self.ticket.ticket_no}"


class ShareholderLoginRequest(models.Model):
    """
    Shareholder login request - pending approval
    Admin approve karega to user + shareholder create ho ga
    """
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
    ]
    
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    full_name = models.CharField(max_length=200, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    phone = models.CharField(max_length=20, verbose_name="Phone Number")
    cnic = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNIC")
    address = models.TextField(blank=True, null=True, verbose_name="Address")
    notes = models.TextField(blank=True, null=True, verbose_name="Additional Notes")
    
    # ========================================== #
    # REQUEST DETAILS                           #
    # ========================================== #
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Requested At")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Status")
    
    # ========================================== #
    # ADMIN RESPONSE                            #
    # ========================================== #
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reviewed_requests',
        verbose_name="Reviewed By"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Reviewed At")
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="Rejection Reason")
    
    # ========================================== #
    # ✅ GENERATED CREDENTIALS - YEH IMPORTANT   #
    # ========================================== #
    generated_username = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        verbose_name="Generated Username"
    )
    generated_password = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        verbose_name="Generated Password"
    )
    
    # ========================================== #
    # CREATED SHAREHOLDER                       #
    # ========================================== #
    created_shareholder = models.ForeignKey(
        'Shareholder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='login_requests',
        verbose_name="Created Shareholder"
    )
    
    # ========================================== #
    # IP AND DEVICE INFO                        #
    # ========================================== #
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="User Agent")
    
    # ========================================== #
    # META                                      #
    # ========================================== #
    class Meta:
        verbose_name_plural = "Shareholder Login Requests"
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['email']),
            models.Index(fields=['requested_at']),
        ]
    
    def __str__(self):
        return f"{self.full_name} - {self.email} ({self.get_status_display()})"
    
    # ========================================== #
    # ✅ APPROVE METHOD - COMPLETE              #
    # ========================================== #
    
    def approve(self, admin_user):
        """
        ✅ Approve request and create:
        1. User account
        2. Shareholder profile
        3. Cash balance
        4. Store credentials
        """
        from django.contrib.auth.models import User
        from django.utils.timezone import now
        from django.db import transaction
        from decimal import Decimal
        import secrets
        import string
        
        # Check if already approved
        if self.status == 'approved':
            raise ValidationError("This request is already approved!")
        
        # Check if already rejected
        if self.status == 'rejected':
            raise ValidationError("This request was rejected and cannot be approved!")
        
        try:
            with transaction.atomic():
                # ========================================== #
                # STEP 1: CREATE USERNAME                   #
                # ========================================== #
                username = self.email.split('@')[0]
                base_username = username
                counter = 1
                
                # Ensure username is unique
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # ========================================== #
                # STEP 2: GENERATE RANDOM PASSWORD          #
                # ========================================== #
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for i in range(10))
                
                # ========================================== #
                # STEP 3: CREATE USER                       #
                # ========================================== #
                user = User.objects.create_user(
                    username=username,
                    email=self.email,
                    password=password
                )
                user.is_active = True
                user.first_name = self.full_name.split()[0] if self.full_name else ''
                user.last_name = ' '.join(self.full_name.split()[1:]) if self.full_name else ''
                user.save()
                
                # ========================================== #
                # STEP 4: CREATE SHAREHOLDER                #
                # ========================================== #
                shareholder = Shareholder.objects.create(
                    user=user,
                    name=self.full_name,
                    email=self.email,
                    phone=self.phone,
                    cnic=self.cnic,
                    address=self.address,
                    allow_login=True,
                    status='active',
                    created_by=user,
                    shareholder_type='individual',
                    notes=f"Created from registration request #{self.id}"
                )
                
                # ========================================== #
                # STEP 5: CREATE CASH BALANCE               #
                # ========================================== #
                ShareholderCashBalance.objects.create(
                    shareholder=shareholder,
                    balance=Decimal('0.00')
                )
                
                # ========================================== #
                # STEP 6: ✅ STORE CREDENTIALS - YEH IMPORTANT #
                # ========================================== #
                # The password is NEVER saved. It is returned below so the view can show it once.
                self.generated_username = username
                
                # ========================================== #
                # STEP 7: UPDATE REQUEST STATUS            #
                # ========================================== #
                self.status = 'approved'
                self.reviewed_by = admin_user
                self.reviewed_at = now()
                self.created_shareholder = shareholder
                
                # ✅ FORCE SAVE WITH UPDATE_FIELDS
                self.save(update_fields=[
                    'generated_username',
                    'status',
                    'reviewed_by',
                    'reviewed_at',
                    'created_shareholder'
                ])
                
                # ========================================== #
                # STEP 8: CREATE NOTIFICATION               #
                # ========================================== #
                try:
                    from . import Notification
                    # Notify admin
                    Notification.send(
                        user=admin_user,
                        title="✅ Shareholder Request Approved",
                        message=f"{self.full_name} has been approved as shareholder! Username: {username}",
                        notification_type='success',
                        category='system',
                        link=f"/shareholder-requests/{self.id}/"
                    )
                except:
                    pass
                
                # ========================================== #
                # STEP 9: RETURN RESULT                     #
                # ========================================== #
                return {
                    'success': True,
                    'user': user,
                    'shareholder': shareholder,
                    'username': username,
                    'password': password,
                    'email': self.email,
                    'message': "✅ Request approved!"
                }
                
        except Exception as e:
            # Rollback will happen automatically due to atomic
            raise ValidationError(f"Approval failed: {str(e)}")
    
    # ========================================== #
    # REJECT METHOD                             #
    # ========================================== #
    
    def reject(self, admin_user, reason=""):
        """
        ❌ Reject request with reason
        """
        from django.utils.timezone import now
        
        if self.status == 'approved':
            raise ValidationError("Cannot reject an already approved request!")
        
        if self.status == 'rejected':
            raise ValidationError("This request is already rejected!")
        
        self.status = 'rejected'
        self.reviewed_by = admin_user
        self.reviewed_at = now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])
        
        # Create notification
        try:
            from . import Notification
            Notification.send(
                user=admin_user,
                title="❌ Shareholder Request Rejected",
                message=f"{self.full_name}'s request was rejected. Reason: {reason or 'Not specified'}",
                notification_type='danger',
                category='system',
                link=f"/shareholder-requests/{self.id}/"
            )
        except:
            pass
        
        return {
            'success': True,
            'message': f"Request rejected! Reason: {reason or 'Not specified'}"
        }
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_rejected(self):
        return self.status == 'rejected'
    
    @property
    def can_act(self):
        """Can admin act on this request?"""
        return self.status == 'pending'
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'pending':
            return '<span class="badge bg-warning text-dark">⏳ Pending</span>'
        elif self.status == 'approved':
            return '<span class="badge bg-success">✅ Approved</span>'
        else:
            return '<span class="badge bg-danger">❌ Rejected</span>'
    
    @property
    def has_credentials(self):
        """Check if credentials are stored"""
        return bool(self.generated_username)
    
    @property
    def formatted_date(self):
        return self.requested_at.strftime('%d-%m-%Y %H:%M')
    
    @property
    def formatted_reviewed_date(self):
        if self.reviewed_at:
            return self.reviewed_at.strftime('%d-%m-%Y %H:%M')
        return '-'


def get_shareholder_balance_used(shareholder):
    """
    Calculate total balance used by a specific shareholder
    Used by BalanceDividend model
    """
    from decimal import Decimal
    
    total = Decimal('0.00')
    
    purchases = Purchase.objects.filter(shareholder_deduction_done=True)
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    total += Decimal(str(item.get('deducted', 0)))
    
    return total
