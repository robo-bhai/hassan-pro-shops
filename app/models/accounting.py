"""Accounting models."""
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import datetime
from datetime import date
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from .budgeting import Expense

class Saving(models.Model):
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateTimeField(default=now)
    category = models.CharField(max_length=100, choices=[
        ('utilities', 'Utilities'),
        ('other', 'Other'),
    ], default='other')

    def __str__(self):
        return f"{self.description} - {self.amount}"

    class Meta:
        verbose_name_plural = "10.2 Savings"


# New model for debts
class Debt(models.Model):
    lender = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    start_date = models.DateField(default=now)
    due_date = models.DateField()

    def __str__(self):
        return f"{self.lender} - {self.amount}"

    class Meta:
        verbose_name_plural = "10.1. Debts"


# ============================================
# DAILY CLOSING MODEL
# ============================================
class DailyClosing(models.Model):
    closing_date = models.DateField(unique=True)
    opening_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Sales by payment method
    cash_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    jazzcash_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    easypaisa_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bank_transfer_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_difference = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Daily Closing Reports'
        ordering = ['-closing_date']
    
    def __str__(self):
        return f"Closing - {self.closing_date}"
    
    def total_sales_today(self):
        return self.cash_sales + self.card_sales + self.jazzcash_sales + self.easypaisa_sales + self.bank_transfer_sales
    
    def expected_cash(self):
        return self.opening_cash + self.cash_sales - self.total_expenses
    
    def calculate_difference(self):
        return self.closing_cash - self.expected_cash()
    
    def save(self, *args, **kwargs):
        self.cash_difference = self.calculate_difference()
        super().save(*args, **kwargs)


class DailyClosingExpense(models.Model):
    closing = models.ForeignKey(DailyClosing, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    category = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.description} - Rs.{self.amount}"


class CashTransaction(models.Model):
    """Cash generate aur use track karne ke liye"""
    
    TRANSACTION_TYPES = [
        ('deposit', '💰 Cash Deposit (Add)'),
        ('withdraw', '💸 Cash Withdrawal (Remove)'),
        ('sale', '🛒 Sale Income'),
        ('purchase', '📥 Purchase Expense'),
        ('expense', '📝 Other Expense'),
        ('transfer', '🔄 Transfer'),
        ('opening', '🏁 Opening Balance'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', '💵 Cash'),
        ('bank', '🏦 Bank Transfer'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('card', '💳 Card'),
    ]
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    description = models.TextField()
    date = models.DateTimeField(default=now)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    
    # ✅ NEW: Debit/Credit fields
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Related models
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_transactions')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_transactions')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cash_transactions')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name_plural = "💰 Cash Transactions"
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - Rs. {self.amount:,.2f} on {self.date.strftime('%d-%m-%Y')}"
    
    @property
    def formatted_amount(self):
        return f"Rs. {self.amount:,.2f}"
    
    @property
    def is_inflow(self):
        """Cash inflow hai ya outflow?"""
        return self.transaction_type in ['deposit', 'sale', 'opening']
    
    @property
    def is_outflow(self):
        """Cash outflow hai ya?"""
        return self.transaction_type in ['withdraw', 'purchase', 'expense']
    
    @property
    def formatted_debit(self):
        return f"Rs. {self.debit:,.2f}" if self.debit > 0 else "-"
    
    @property
    def formatted_credit(self):
        return f"Rs. {self.credit:,.2f}" if self.credit > 0 else "-"
    
    @property
    def formatted_balance(self):
        return f"Rs. {self.balance:,.2f}"
    
    @classmethod
    def create_with_balance(cls, amount, transaction_type, user=None, description="", 
                           reference_no="", payment_method='cash', related_obj=None):
        """Create transaction with debit/credit/balance - ✅ FIXED"""
        from django.db import transaction
        
        with transaction.atomic():
            # Get current balance
            balance_obj = CashBalance.objects.first()
            if not balance_obj:
                balance_obj = CashBalance.objects.create(balance=0)
            
            current_balance = balance_obj.balance
            
            # Determine debit or credit
            if transaction_type in ['deposit', 'sale', 'opening']:
                debit = amount
                credit = 0
                new_balance = current_balance + amount
                balance_obj.balance = new_balance
            else:  # withdraw, purchase, expense
                debit = 0
                credit = amount
                if current_balance < amount:
                    raise ValidationError(f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}")
                new_balance = current_balance - amount
                balance_obj.balance = new_balance
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # Create transaction with debit/credit/balance
            cash_trans = cls.objects.create(
                amount=amount,
                transaction_type=transaction_type,
                payment_method=payment_method,
                description=description,
                reference_no=reference_no,
                debit=debit,
                credit=credit,
                balance=new_balance,
                created_by=user
            )
            
            # Link related objects
            if related_obj:
                if transaction_type == 'sale' and isinstance(related_obj, Sale):
                    cash_trans.sale = related_obj
                elif transaction_type == 'purchase' and isinstance(related_obj, Purchase):
                    cash_trans.purchase = related_obj
                cash_trans.save()
            
            return cash_trans


class CashBalance(models.Model):
    """Current cash balance track karne ke liye"""
    
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "💰 Cash Balance"
    
    def __str__(self):
        return f"Current Cash Balance: Rs. {self.balance:,.2f}"
    
    @classmethod
    def get_balance(cls):
        """Get current cash balance"""
        balance_obj = cls.objects.first()
        if not balance_obj:
            balance_obj = cls.objects.create(balance=0)
        return balance_obj.balance
    
    @classmethod
    def update_balance(cls, amount, transaction_type, user=None, description="", 
                      reference_no="", payment_method='cash', related_obj=None):
        """Update cash balance with debit/credit transaction record"""
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            balance_obj, _ = cls.objects.get_or_create(id=1)
            
            old_balance = balance_obj.balance
            
            if transaction_type in ['deposit', 'sale', 'opening']:
                balance_obj.balance += amount
                debit = amount
                credit = 0
            elif transaction_type in ['withdraw', 'purchase', 'expense']:
                if balance_obj.balance < amount:
                    raise ValidationError(f"Insufficient cash balance! Available: Rs. {balance_obj.balance:,.2f}")
                balance_obj.balance -= amount
                debit = 0
                credit = amount
            else:
                raise ValidationError(f"Invalid transaction type: {transaction_type}")
            
            balance_obj.updated_by = user
            balance_obj.save()
            
            # ✅ Create transaction with debit/credit/balance
            cash_trans = CashTransaction.objects.create(
                amount=amount,
                transaction_type=transaction_type,
                payment_method=payment_method,
                description=description,
                reference_no=reference_no,
                debit=debit,
                credit=credit,
                balance=balance_obj.balance,
                created_by=user
            )
            
            # Link related objects
            if related_obj:
                if transaction_type == 'sale' and isinstance(related_obj, Sale):
                    cash_trans.sale = related_obj
                elif transaction_type == 'purchase' and isinstance(related_obj, Purchase):
                    cash_trans.purchase = related_obj
                cash_trans.save(update_fields=['sale', 'purchase'])
            
            return balance_obj.balance


class AccountType(models.Model):
    """Account Types like Assets, Liabilities, Equity, Income, Expenses"""
    
    ACCOUNT_CLASSES = [
        ('asset', 'Assets'),
        ('liability', 'Liabilities'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expenses'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    account_class = models.CharField(max_length=20, choices=ACCOUNT_CLASSES)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Account Types"
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Account(models.Model):
    """Chart of Accounts - Each account entry"""
    
    # Basic Information
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.ForeignKey(AccountType, on_delete=models.CASCADE, related_name='accounts')
    
    # Parent-Child (Hierarchy)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    
    # Opening Balance
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    opening_balance_date = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_contra = models.BooleanField(default=False, help_text="Contra account (e.g., Accumulated Depreciation)")
    is_bank = models.BooleanField(default=False, help_text="Bank account")
    is_cash = models.BooleanField(default=False, help_text="Cash account")
    is_payable = models.BooleanField(default=False, help_text="Accounts Payable")
    is_receivable = models.BooleanField(default=False, help_text="Accounts Receivable")
    
    # Bank Details
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_account_no = models.CharField(max_length=50, blank=True, null=True)
    
    # Description
    description = models.TextField(blank=True, null=True)
    
    # System
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "Chart of Accounts"
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['account_type']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_full_code(self):
        """Get full hierarchical code"""
        if self.parent:
            return f"{self.parent.get_full_code()}-{self.code}"
        return self.code
    
    def get_level(self):
        """Get hierarchy level"""
        if self.parent:
            return self.parent.get_level() + 1
        return 1
    
    def current_balance(self):
        """Calculate current balance of this account"""
        from django.db.models import Sum
        
        # Debits increase Assets & Expenses, decrease Liabilities & Equity & Income
        # Credits decrease Assets & Expenses, increase Liabilities & Equity & Income
        is_debit_balance = self.account_type.account_class in ['asset', 'expense']
        
        debit_total = JournalEntryItem.objects.filter(
            account=self,
            is_debit=True
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        credit_total = JournalEntryItem.objects.filter(
            account=self,
            is_debit=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        if is_debit_balance:
            balance = debit_total - credit_total + self.opening_balance
        else:
            balance = credit_total - debit_total + self.opening_balance
        
        return balance
    
    def debit_balance(self):
        """Get debit balance"""
        if self.account_type.account_class in ['asset', 'expense']:
            return self.current_balance()
        return 0
    
    def credit_balance(self):
        """Get credit balance"""
        if self.account_type.account_class in ['liability', 'equity', 'income']:
            return self.current_balance()
        return 0
    
    def save(self, *args, **kwargs):
        # Auto-generate code if not provided
        if not self.code:
            last_account = Account.objects.order_by('-id').first()
            if last_account and last_account.code:
                try:
                    last_num = int(last_account.code.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'ACC-{new_num}'
        super().save(*args, **kwargs)


class JournalEntry(models.Model):
    """Journal Entry - Main transaction record"""
    
    ENTRY_TYPES = [
        ('manual', 'Manual Entry'),
        ('sale', 'Sale Entry'),
        ('purchase', 'Purchase Entry'),
        ('expense', 'Expense Entry'),
        ('payment', 'Payment Entry'),
        ('receipt', 'Receipt Entry'),
        ('adjustment', 'Adjustment'),
        ('closing', 'Closing Entry'),
    ]
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('posted', '✅ Posted'),
        ('reversed', '🔄 Reversed'),
        ('void', '❌ Void'),
    ]
    
    # Basic Information
    entry_no = models.CharField(max_length=20, unique=True)
    entry_date = models.DateField()
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='manual')
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    
    # Related Documents
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    expense = models.ForeignKey('Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    payment = models.ForeignKey('SalePayment', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_entries')
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='posted_entries')
    posted_at = models.DateTimeField(null=True, blank=True)
    
    # Reversal
    reversed_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reversal_entries')
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    
    # System
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_journal_entries')
    
    class Meta:
        verbose_name_plural = "Journal Entries"
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['entry_no']),
            models.Index(fields=['entry_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.entry_no} - {self.entry_date.strftime('%d-%m-%Y')} - {self.description[:30]}"
    
    def total_debit(self):
        """Total debit amount"""
        return self.items.filter(is_debit=True).aggregate(total=Sum('amount'))['total'] or 0
    
    def total_credit(self):
        """Total credit amount"""
        return self.items.filter(is_debit=False).aggregate(total=Sum('amount'))['total'] or 0
    
    def is_balanced(self):
        """Check if entry is balanced (Debit = Credit)"""
        return self.total_debit() == self.total_credit()
    
    def post(self, user):
        """Post the journal entry"""
        if self.status != 'draft':
            raise ValidationError("Only draft entries can be posted!")
        
        if not self.is_balanced():
            raise ValidationError("Journal entry is not balanced! Debit must equal Credit.")
        
        self.status = 'posted'
        self.posted_by = user
        self.posted_at = now()
        self.save()
        
        # Update account balances
        for item in self.items.all():
            account = item.account
            if item.is_debit:
                account.debit_total = (account.debit_total or 0) + item.amount
            else:
                account.credit_total = (account.credit_total or 0) + item.amount
            account.save()
        
        return True
    
    def reverse(self, user, reason=""):
        """Reverse a posted journal entry"""
        if self.status != 'posted':
            raise ValidationError("Only posted entries can be reversed!")
        
        # Create reversal entry
        reversal = JournalEntry.objects.create(
            entry_no=f"REV-{self.entry_no}",
            entry_date=now().date(),
            entry_type='adjustment',
            reference=f"Reversal of {self.entry_no}",
            description=f"Reversal: {self.description} - Reason: {reason}",
            status='draft',
            created_by=user,
            reversed_from=self
        )
        
        # Create reversal items (opposite)
        for item in self.items.all():
            JournalEntryItem.objects.create(
                journal_entry=reversal,
                account=item.account,
                is_debit=not item.is_debit,  # Reverse the direction
                amount=item.amount,
                description=f"Reversal: {item.description}"
            )
        
        # Post the reversal
        reversal.post(user)
        
        # Mark original as reversed
        self.status = 'reversed'
        self.save()
        
        return reversal
    
    def save(self, *args, **kwargs):
        if not self.entry_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last_entry = JournalEntry.objects.filter(entry_no__startswith=f'JRNL-{year}').order_by('-entry_no').first()
            if last_entry and last_entry.entry_no:
                try:
                    last_num = int(last_entry.entry_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.entry_no = f'JRNL-{year}-{new_num}'
        super().save(*args, **kwargs)


class JournalEntryItem(models.Model):
    """Journal Entry Items - Debit/Credit lines"""
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='items')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='journal_items')
    is_debit = models.BooleanField(help_text="True for Debit, False for Credit")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Journal Entry Items"
        ordering = ['id']
    
    def __str__(self):
        direction = "Dr" if self.is_debit else "Cr"
        return f"{self.account.name} - {direction} - Rs. {self.amount:,.2f}"


class LedgerEntry(models.Model):
    """General Ledger - All transactions with running balance"""
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='ledger_entries')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='ledger_entries')
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Ledger Entries"
        ordering = ['date', 'id']
        indexes = [
            models.Index(fields=['account', 'date']),
            models.Index(fields=['journal_entry']),
        ]
    
    def __str__(self):
        return f"{self.account.name} - {self.date.strftime('%d-%m-%Y')} - Dr: {self.debit} Cr: {self.credit}"


class TrialBalance(models.Model):
    """Trial Balance Report - Summary of all accounts"""
    
    as_at_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    opening_debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    opening_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Trial Balance"
        unique_together = ['as_at_date', 'account']
    
    def __str__(self):
        return f"{self.account.name} - {self.as_at_date}"


class FinancialStatement(models.Model):
    """Store generated financial statements"""
    
    STATEMENT_TYPES = [
        ('balance_sheet', 'Balance Sheet'),
        ('profit_loss', 'Profit & Loss Statement'),
        ('cash_flow', 'Cash Flow Statement'),
        ('trial_balance', 'Trial Balance'),
    ]
    
    statement_type = models.CharField(max_length=20, choices=STATEMENT_TYPES)
    as_at_date = models.DateField()
    data = models.JSONField()  # Store full statement data
    pdf_file = models.FileField(upload_to='financial_statements/%Y/%m/', null=True, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Financial Statements"
        ordering = ['-as_at_date', '-generated_at']
    
    def __str__(self):
        return f"{self.get_statement_type_display()} - {self.as_at_date}"


class FinancialPeriod(models.Model):
    """Accounting periods (Monthly, Quarterly, Yearly)"""
    
    PERIOD_TYPES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='closed_periods')
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Financial Periods"
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_closed']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date.strftime('%d-%m-%Y')} to {self.end_date.strftime('%d-%m-%Y')})"
    
    def is_active(self):
        from django.utils.timezone import now
        return self.start_date <= now().date() <= self.end_date and not self.is_closed


class LoanReturn(models.Model):
    """Loan repayment/return record"""
    
    RETURN_TYPES = [
        ('installment', '📅 Installment Payment'),
        ('full', '💰 Full Settlement'),
        ('partial', '📊 Partial Payment'),
        ('early', '⚡ Early Repayment'),
    ]
    
    # Basic Info
    return_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_agreement_no = models.CharField(max_length=50, verbose_name="Loan Agreement No")
    lender_name = models.CharField(max_length=200, verbose_name="Lender/Bank Name")
    return_type = models.CharField(max_length=20, choices=RETURN_TYPES, default='installment')
    
    # Amounts
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Return Amount")
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    
    # Dates
    return_date = models.DateField(default=now)
    due_date = models.DateField(null=True, blank=True)
    
    # Payment
    payment_method = models.CharField(max_length=50, choices=Expense.PAYMENT_METHODS, default='bank_transfer')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    receipt = models.FileField(upload_to='loan_returns/', null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', '⏳ Pending'),
        ('paid', '✅ Paid'),
        ('cancelled', '❌ Cancelled'),
    ], default='pending')
    
    # Notes
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loan Returns"
        ordering = ['-return_date']
    
    def __str__(self):
        return f"{self.return_no} - {self.lender_name} - Rs. {self.amount:,.2f}"
    
    def save(self, *args, **kwargs):
        if not self.return_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = LoanReturn.objects.filter(return_no__startswith=f'LR-{year}').order_by('-return_no').first()
            if last and last.return_no:
                try:
                    last_num = int(last.return_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.return_no = f'LR-{year}-{new_num}'
        
        self.total_amount = self.amount + self.interest_amount + self.late_fee
        super().save(*args, **kwargs)
    
    def process_payment(self, user):
        """Process loan return payment - Deduct from main cash"""
        from decimal import Decimal
        
        if self.status == 'paid':
            raise ValidationError("This loan return is already paid!")
        
        try:
            with transaction.atomic():
                # Check main cash balance
                current_balance = CashBalance.get_balance()
                if current_balance < self.total_amount:
                    raise ValidationError(
                        f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                        f"Required: Rs. {self.total_amount:,.2f}"
                    )
                
                # Deduct from main cash
                CashBalance.update_balance(
                    amount=self.total_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Loan Return #{self.return_no} - {self.lender_name} - {self.description or 'Loan repayment'}"
                )
                
                # Update status
                self.status = 'paid'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process payment: {str(e)}")


class Loan(models.Model):
    """Loan received from bank/lender"""
    
    LOAN_TYPES = [
        ('business', '🏢 Business Loan'),
        ('personal', '👤 Personal Loan'),
        ('vehicle', '🚗 Vehicle Loan'),
        ('property', '🏠 Property Loan'),
        ('education', '📚 Education Loan'),
        ('other', '📋 Other'),
    ]
    
    LOAN_STATUS = [
        ('active', '✅ Active'),
        ('paid', '💰 Paid'),
        ('defaulted', '❌ Defaulted'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Basic Info
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='business')
    lender_name = models.CharField(max_length=200, verbose_name="Lender/Bank Name")
    lender_contact = models.CharField(max_length=20, blank=True, null=True)
    agreement_no = models.CharField(max_length=50, blank=True, null=True)
    
    # Amounts
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Principal Amount")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Annual interest rate %")
    total_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    loan_date = models.DateField(default=now, verbose_name="Loan Received Date")
    due_date = models.DateField(verbose_name="Due Date")
    paid_date = models.DateField(null=True, blank=True)
    
    # Installments
    total_installments = models.IntegerField(default=0)
    paid_installments = models.IntegerField(default=0)
    installment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='active')
    
    # Purpose
    purpose = models.TextField(blank=True, null=True, verbose_name="Purpose of Loan")
    notes = models.TextField(blank=True, null=True)
    
    # Documents
    agreement_file = models.FileField(upload_to='loan_agreements/', null=True, blank=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loans"
        ordering = ['-loan_date']
        indexes = [
            models.Index(fields=['loan_no']),
            models.Index(fields=['lender_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.loan_no} - {self.lender_name} (Rs. {self.principal_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = Loan.objects.filter(loan_no__startswith=f'LN-{year}').order_by('-loan_no').first()
            if last and last.loan_no:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LN-{year}-{new_num}'
        
        # Calculate totals
        self.total_payable = self.principal_amount + (self.principal_amount * self.interest_rate / 100)
        self.remaining_amount = self.total_payable - self.paid_amount
        
        if self.total_installments > 0:
            self.installment_amount = self.total_payable / self.total_installments
        
        super().save(*args, **kwargs)
    
    def process_loan_received(self, user):
        """Add loan amount to main cash"""
        from decimal import Decimal
        
        try:
            with transaction.atomic():
                # Add to main cash
                CashBalance.update_balance(
                    amount=self.principal_amount,
                    transaction_type='deposit',
                    user=user,
                    description=f"Loan Received: {self.loan_no} - {self.lender_name} - {self.purpose or 'Loan'}"
                )
                
                # Update status
                self.status = 'active'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process loan: {str(e)}")


class LoanGiven(models.Model):
    """Loan Given to someone (Aap ne kisi ko paisa diya)"""
    
    LOAN_TYPES = [
        ('personal', '👤 Personal Loan'),
        ('business', '🏢 Business Loan'),
        ('employee', '👔 Employee Loan'),
        ('customer', '🛒 Customer Loan'),
        ('friend', '🤝 Friend/Family Loan'),
        ('other', '📋 Other'),
    ]
    
    LOAN_STATUS = [
        ('active', '✅ Active'),
        ('paid', '💰 Paid'),
        ('defaulted', '❌ Defaulted'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Basic Info
    loan_no = models.CharField(max_length=20, unique=True, editable=False)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES, default='personal')
    borrower_name = models.CharField(max_length=200, verbose_name="Borrower Name")
    borrower_contact = models.CharField(max_length=20, blank=True, null=True)
    borrower_cnic = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNIC")
    borrower_address = models.TextField(blank=True, null=True)
    
    # Amounts
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Principal Amount")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Annual interest rate %")
    total_receivable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    received_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates
    loan_date = models.DateField(default=now, verbose_name="Loan Given Date")
    due_date = models.DateField(verbose_name="Expected Return Date")
    paid_date = models.DateField(null=True, blank=True)
    
    # Installments
    total_installments = models.IntegerField(default=0)
    received_installments = models.IntegerField(default=0)
    installment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=LOAN_STATUS, default='active')
    
    # Documents
    agreement_file = models.FileField(upload_to='loan_given_agreements/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    # Guarantor
    guarantor_name = models.CharField(max_length=200, blank=True, null=True)
    guarantor_contact = models.CharField(max_length=20, blank=True, null=True)
    
    # System
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Loans Given"
        ordering = ['-loan_date']
        indexes = [
            models.Index(fields=['loan_no']),
            models.Index(fields=['borrower_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.loan_no} - {self.borrower_name} (Rs. {self.principal_amount:,.2f})"
    
    def save(self, *args, **kwargs):
        if not self.loan_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y%m')
            last = LoanGiven.objects.filter(loan_no__startswith=f'LG-{year}').order_by('-loan_no').first()
            if last and last.loan_no:
                try:
                    last_num = int(last.loan_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.loan_no = f'LG-{year}-{new_num}'
        
        # Calculate totals
        self.total_receivable = self.principal_amount + (self.principal_amount * self.interest_rate / 100)
        self.remaining_amount = self.total_receivable - self.received_amount
        
        if self.total_installments > 0:
            self.installment_amount = self.total_receivable / self.total_installments
        
        super().save(*args, **kwargs)
    
    def process_loan_given(self, user):
        """✅ Cash OUTFLOW - Aap ne paisa diya"""
        from decimal import Decimal
        
        try:
            with transaction.atomic():
                # Check if sufficient cash balance
                current_balance = CashBalance.get_balance()
                if current_balance < self.principal_amount:
                    raise ValidationError(
                        f"Insufficient cash balance! Available: Rs. {current_balance:,.2f}, "
                        f"Required: Rs. {self.principal_amount:,.2f}"
                    )
                
                # Cash OUTFLOW
                CashBalance.update_balance(
                    amount=self.principal_amount,
                    transaction_type='withdraw',
                    user=user,
                    description=f"Loan Given to {self.borrower_name} - {self.loan_no}"
                )
                
                self.status = 'active'
                self.save()
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to process loan: {str(e)}")
    
    def receive_payment(self, amount, user, payment_method='cash', reference_no=''):
        """✅ Receive payment from borrower (Cash INFLOW)"""
        from decimal import Decimal
        
        if self.status == 'paid':
            raise ValidationError("This loan is already fully paid!")
        
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero!")
        
        if amount > self.remaining_amount:
            raise ValidationError(f"Amount exceeds remaining balance: Rs. {self.remaining_amount:,.2f}")
        
        try:
            with transaction.atomic():
                # Cash INFLOW - Payment received
                CashBalance.update_balance(
                    amount=amount,
                    transaction_type='deposit',
                    user=user,
                    description=f"Loan repayment from {self.borrower_name} - {self.loan_no}"
                )
                
                # Update loan
                self.received_amount += amount
                self.remaining_amount = self.total_receivable - self.received_amount
                
                # Update installments
                if self.total_installments > 0:
                    self.received_installments += 1
                
                if self.remaining_amount <= 0:
                    self.status = 'paid'
                    self.paid_date = now().date()
                
                self.save()
                
                # Create payment record
                LoanGivenPayment.objects.create(
                    loan_given=self,
                    amount=amount,
                    payment_date=now().date(),
                    payment_method=payment_method,
                    reference_no=reference_no,
                    created_by=user
                )
                
                return True
                
        except Exception as e:
            raise ValidationError(f"Failed to record payment: {str(e)}")


class LoanGivenPayment(models.Model):
    """Payments received from borrower"""
    
    loan_given = models.ForeignKey(LoanGiven, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, default='cash')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.loan_given.loan_no} - Rs. {self.amount:,.2f} on {self.payment_date}"
