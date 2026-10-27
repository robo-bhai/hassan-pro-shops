"""Models: people/loans (split from the former shareholders.py)."""
from django.db import models
from django.db import transaction
from datetime import datetime
from datetime import date
from django.utils.timezone import now
from django.contrib.auth.models import User

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
