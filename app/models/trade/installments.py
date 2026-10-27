"""Models: trade/installments (split from the former sales.py)."""
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User

class InstallmentPlan(models.Model):
    """Installment plan template (e.g., 3 months, 6 months)"""
    name = models.CharField(max_length=100, help_text="e.g., 3-Month Plan, 6-Month Plan")
    duration_months = models.PositiveIntegerField(help_text="Number of months")
    down_payment_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, 
                                                 help_text="Down payment % (e.g., 20 for 20%)")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         help_text="Interest rate % per annum")
    late_fee_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                            help_text="Late fee per day (Rs.)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Installment Plans"
        ordering = ['duration_months']
    
    def __str__(self):
        return f"{self.name} ({self.duration_months} months)"
    
    def calculate_emi(self, total_amount):
        """Calculate EMI amount"""
        down_payment = (self.down_payment_percent / 100) * total_amount
        loan_amount = total_amount - down_payment
        
        if self.interest_rate > 0 and self.duration_months > 0:
            monthly_rate = (self.interest_rate / 100) / 12
            emi = loan_amount * monthly_rate * (1 + monthly_rate) ** self.duration_months
            emi = emi / ((1 + monthly_rate) ** self.duration_months - 1) if emi else loan_amount / self.duration_months
        else:
            emi = loan_amount / self.duration_months if self.duration_months > 0 else 0
        
        return {
            'down_payment': round(down_payment, 2),
            'loan_amount': round(loan_amount, 2),
            'emi': round(emi, 2),
            'total_payable': round(down_payment + (emi * self.duration_months), 2),
            'total_interest': round((down_payment + (emi * self.duration_months)) - total_amount, 2)
        }


class SaleInstallment(models.Model):
    """Link sale with installment plan"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]
    
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='installments')
    plan = models.ForeignKey(InstallmentPlan, on_delete=models.SET_NULL, null=True)
    
    # Amounts
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    down_payment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    down_payment_paid = models.BooleanField(default=False)
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    emi_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_interest = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Tracking
    start_date = models.DateField(default=now)
    end_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Late fees
    late_fee_accrued = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Sale Installments"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Installment - {self.sale.bill_no} ({self.plan.name if self.plan else 'Custom'})"
    
    # ============================================
    # PAYMENT CALCULATION METHODS
    # ============================================
    
    def total_paid(self):
        """Total paid amount including down payment and EMI payments"""
        paid_emis = self.emi_payments.aggregate(total=Sum('amount_paid'))['total'] or 0
        down_payment_paid = self.down_payment_amount if self.down_payment_paid else 0
        return down_payment_paid + paid_emis
    
    def remaining_amount(self):
        """Remaining amount to pay"""
        return self.total_payable - self.total_paid()
    
    def next_emi_due(self):
        """Get next pending EMI"""
        return self.emi_payments.filter(status='pending').order_by('due_date').first()
    
    def calculate_late_fee(self):
        """Calculate accrued late fee"""
        today = now().date()
        pending_emis = self.emi_payments.filter(status='pending', due_date__lt=today)
        
        total_late_fee = 0
        for emi in pending_emis:
            days_late = (today - emi.due_date).days
            if days_late > 0 and self.plan:
                total_late_fee += days_late * self.plan.late_fee_per_day
        
        return total_late_fee
    
    # ============================================
    # STATUS UPDATE METHODS
    # ============================================
    
    def update_status(self):
        """Auto-update status based on payments"""
        remaining = self.remaining_amount()
        if remaining <= 0:
            self.status = 'paid'
            self.end_date = now().date()
        elif self.total_paid() > 0:
            self.status = 'partial'
        else:
            self.status = 'pending'
        
        # Check if defaulted
        if self.next_due_date and now().date() > self.next_due_date and remaining > 0:
            days_overdue = (now().date() - self.next_due_date).days
            if days_overdue > 30:  # 30 days overdue = defaulted
                self.status = 'defaulted'
        
        self.save(update_fields=['status', 'end_date'])
    
    # ✅ FIX: ADD THIS MISSING METHOD
    def update_next_due_date(self):
        """Update next due date based on first unpaid EMI"""
        next_emi = self.emi_payments.filter(status='pending').order_by('due_date').first()
        if next_emi:
            self.next_due_date = next_emi.due_date
        else:
            self.next_due_date = None
        self.save(update_fields=['next_due_date'])
    
    # ============================================
    # WHATSAPP METHODS
    # ============================================
    
    def send_overdue_alert(self):
        """Send overdue alert to customer"""
        try:
            from ...utils.whatsapp_utils import WhatsAppSender
            
            customer = self.sale.customer
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            overdue_emis = self.emi_payments.filter(status='pending', due_date__lt=now().date())
            total_overdue = sum(emi.remaining_due() for emi in overdue_emis)
            days_overdue = (now().date() - self.next_due_date).days if self.next_due_date else 0
            
            result = WhatsAppSender.send_overdue_alert(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=self.sale.bill_no,
                overdue_amount=float(total_overdue),
                days_overdue=days_overdue,
                late_fee=float(self.calculate_late_fee()),
                next_due_date=self.next_due_date
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_monthly_statement(self):
        """Send monthly statement to customer"""
        try:
            from ...utils.whatsapp_utils import WhatsAppSender
            
            customer = self.sale.customer
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            paid_emis = self.emi_payments.filter(status='paid').count()
            total_emis = self.emi_payments.count()
            
            result = WhatsAppSender.send_monthly_statement(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=self.sale.bill_no,
                total_paid=float(self.total_paid()),
                remaining=float(self.remaining_amount()),
                paid_emis=paid_emis,
                total_emis=total_emis,
                next_due_date=self.next_due_date,
                plan_name=self.plan.name if self.plan else 'Installment'
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def progress_percentage(self):
        """Calculate payment progress percentage"""
        if self.total_payable > 0:
            return (self.total_paid() / self.total_payable) * 100
        return 0
    
    @property
    def is_completed(self):
        """Check if installment is fully paid"""
        return self.status == 'paid'
    
    @property
    def is_defaulted(self):
        """Check if installment is defaulted"""
        return self.status == 'defaulted'
    
    @property
    def is_active(self):
        """Check if installment is active (not completed or defaulted)"""
        return self.status in ['pending', 'partial']
    
    @property
    def formatted_total_amount(self):
        """Formatted total amount"""
        return f"Rs. {self.total_amount:,.2f}"
    
    @property
    def formatted_total_paid(self):
        """Formatted total paid"""
        return f"Rs. {self.total_paid():,.2f}"
    
    @property
    def formatted_remaining(self):
        """Formatted remaining amount"""
        return f"Rs. {self.remaining_amount():,.2f}"
    
    @property
    def formatted_emi(self):
        """Formatted EMI amount"""
        return f"Rs. {self.emi_amount:,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'defaulted':
            return '<span class="badge bg-danger">⚠️ Defaulted</span>'
        elif self.status == 'partial':
            return '<span class="badge bg-warning">🟡 Partial</span>'
        else:
            return '<span class="badge bg-secondary">⏳ Pending</span>'
    
    # ============================================
    # EMI GENERATION
    # ============================================
    
    def generate_emi_schedule(self):
        """Generate EMI schedule for this installment"""
        if not self.plan:
            raise ValidationError("Cannot generate EMI schedule without a plan")
        
        # Clear existing EMIs
        self.emi_payments.all().delete()
        
        # Generate new EMIs
        for i in range(1, self.plan.duration_months + 1):
            due_date = self.start_date + timedelta(days=30 * i)
            EmiPayment.objects.create(
                installment=self,
                installment_number=i,
                due_date=due_date,
                amount_due=self.emi_amount
            )
        
        # Update next due date
        self.update_next_due_date()
        
        return True
    
    # ============================================
    # SAVE METHOD
    # ============================================
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.next_due_date = self.start_date + timedelta(days=30)  # First EMI after 1 month
            if self.plan:
                self.end_date = self.start_date + timedelta(days=self.plan.duration_months * 30)
        super().save(*args, **kwargs)


class EmiPayment(models.Model):
    """Individual EMI payment record"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('overdue', 'Overdue'),
    ]
    
    installment = models.ForeignKey('SaleInstallment', on_delete=models.CASCADE, related_name='emi_payments')
    installment_number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=15, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee_charged = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "EMI Payments"
        ordering = ['due_date']
        unique_together = ['installment', 'installment_number']
    
    def __str__(self):
        return f"EMI #{self.installment_number} - {self.installment.sale.bill_no} - Rs.{self.amount_due}"
    
    def remaining_due(self):
        """Calculate remaining amount to pay"""
        return self.amount_due - self.amount_paid
    
    def is_overdue(self):
        """Check if EMI is overdue"""
        from django.utils.timezone import now
        return self.due_date < now().date() and self.status != 'paid'
    
    def get_overdue_days(self):
        """Get number of days overdue"""
        from django.utils.timezone import now
        if self.is_overdue():
            return (now().date() - self.due_date).days
        return 0
    
    def calculate_late_fee(self):
        """Calculate late fee for this EMI"""
        if self.is_overdue() and self.installment.plan:
            days = self.get_overdue_days()
            return days * self.installment.plan.late_fee_per_day
        return Decimal('0.00')
    
    # ============================================
    # WHATSAPP METHODS
    # ============================================
    
    def send_payment_confirmation_whatsapp(self, amount_paid):
        """Send WhatsApp confirmation after payment"""
        try:
            from ...utils.whatsapp_utils import WhatsAppSender
            
            installment = self.installment
            sale = installment.sale
            customer = sale.customer
            
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            remaining_balance = installment.remaining_amount()
            next_due = installment.next_emi_due()
            
            result = WhatsAppSender.send_emi_payment_confirmation(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=sale.bill_no,
                emi_number=self.installment_number,
                amount_paid=float(amount_paid),
                due_date=self.due_date,
                remaining_balance=float(remaining_balance),
                next_due_date=next_due.due_date if next_due else None
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_reminder_whatsapp(self):
        """Send reminder for this EMI"""
        try:
            from ...utils.whatsapp_utils import WhatsAppSender
            
            installment = self.installment
            sale = installment.sale
            customer = sale.customer
            
            if not customer.contact_number:
                return {'success': False, 'message': 'No phone number'}
            
            result = WhatsAppSender.send_emi_reminder(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                bill_no=sale.bill_no,
                emi_number=self.installment_number,
                due_date=self.due_date,
                amount_due=float(self.remaining_due()),
                remaining_balance=float(installment.remaining_amount()),
                plan_name=installment.plan.name if installment.plan else 'Installment',
                late_fee_per_day=float(installment.plan.late_fee_per_day) if installment.plan else 0
            )
            
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # MARK AS PAID METHOD
    # ============================================
    
    def mark_paid(self, amount, payment_method=None, reference_no='', notes='', user=None):
        """Mark EMI as paid partially or fully"""
        from decimal import Decimal
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero")
        
        if amount > self.remaining_due():
            raise ValidationError(f"Amount cannot exceed remaining due: Rs. {self.remaining_due():,.2f}")
        
        # Update payment
        self.amount_paid += amount
        self.payment_date = now()
        self.reference_no = reference_no
        self.notes = notes
        
        if payment_method:
            self.payment_method = payment_method
        
        # Update status
        if self.amount_paid >= self.amount_due:
            self.status = 'paid'
            self.amount_paid = self.amount_due
        else:
            self.status = 'partial'
        
        self.save()
        
        # Update main installment status
        self.installment.update_status()
        
        # Create payment record in SalePayment
        from .. import SalePayment
        SalePayment.objects.create(
            sale=self.installment.sale,
            method=payment_method,
            amount=amount,
            reference_no=reference_no,
            created_by=user
        )
        
        # ✅ Send WhatsApp confirmation
        self.send_payment_confirmation_whatsapp(amount)
        
        return True
    
    def mark_full_paid(self, payment_method=None, reference_no='', notes='', user=None):
        """Mark full EMI as paid"""
        return self.mark_paid(self.remaining_due(), payment_method, reference_no, notes, user)
    
    # ============================================
    # UPDATE OVERDUE STATUS
    # ============================================
    
    def update_overdue_status(self):
        """Update status if overdue"""
        from django.utils.timezone import now
        
        if self.status != 'paid' and self.due_date < now().date():
            self.status = 'overdue'
            self.save(update_fields=['status'])
            return True
        return False
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def payment_percentage(self):
        """Calculate payment percentage for this EMI"""
        if self.amount_due > 0:
            return (self.amount_paid / self.amount_due) * 100
        return 0
    
    @property
    def is_fully_paid(self):
        """Check if fully paid"""
        return self.status == 'paid'
    
    @property
    def is_partially_paid(self):
        """Check if partially paid"""
        return self.status == 'partial'
    
    @property
    def formatted_amount_due(self):
        """Formatted amount due"""
        return f"Rs. {self.amount_due:,.2f}"
    
    @property
    def formatted_amount_paid(self):
        """Formatted amount paid"""
        return f"Rs. {self.amount_paid:,.2f}"
    
    @property
    def formatted_remaining(self):
        """Formatted remaining amount"""
        return f"Rs. {self.remaining_due():,.2f}"
    
    @property
    def status_badge(self):
        """HTML badge for status"""
        if self.status == 'paid':
            return '<span class="badge bg-success">✅ Paid</span>'
        elif self.status == 'overdue':
            return '<span class="badge bg-danger">⚠️ Overdue</span>'
        elif self.status == 'partial':
            return '<span class="badge bg-warning">🟡 Partial</span>'
        else:
            return '<span class="badge bg-secondary">⏳ Pending</span>'
    
    # ============================================
    # SAVE METHOD
    # ============================================
    
    def save(self, *args, **kwargs):
        """Override save to update overdue status"""
        # Check if this is a new record
        is_new = self.pk is None
        
        # For existing records, check overdue status
        if not is_new:
            self.update_overdue_status()
        
        super().save(*args, **kwargs)
        
        # Update installment's next due date if needed
        if not is_new and self.status == 'paid':
            self.installment.update_next_due_date()
