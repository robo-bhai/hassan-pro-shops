"""Models: people/shares (split from the former shareholders.py)."""
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
            from .. import Notification
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
            from .. import Notification
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
                    from .. import Notification
                    
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
