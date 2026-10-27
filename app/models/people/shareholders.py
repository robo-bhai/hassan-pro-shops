"""Models: people/shareholders (split from the former shareholders.py)."""
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

        from ...security.security_utils import generate_password
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
        Equal deduction from everyone, whether the balance is high or low
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
        The higher the balance, the higher the deduction
        The lower the balance, the lower the deduction
        Nothing is deducted from those with zero balance
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
                    from .. import Notification
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
            from .. import Notification
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
        return self.requested_at.strftime('%d-%m-%Y %I:%M %p')
    
    @property
    def formatted_reviewed_date(self):
        if self.reviewed_at:
            return self.reviewed_at.strftime('%d-%m-%Y %I:%M %p')
        return '-'
