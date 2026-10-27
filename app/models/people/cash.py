"""Models: people/cash (split from the former shareholders.py)."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from django.utils.timezone import now
from django.contrib.auth.models import User

class ShareholderCashBalance(models.Model):
    """The cash balance of each shareholder"""
    
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
        from .. import CashBalance
        
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
                from .. import Notification
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
            from .. import Notification
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
                from .. import Notification
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
            from .. import Notification
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
