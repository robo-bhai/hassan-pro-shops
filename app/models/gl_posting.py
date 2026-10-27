"""General-ledger posting support: account mapping + one-posting-per-document guard."""
from django.db import models
from django.db.models import Q


class PostingRule(models.Model):
    """
    Which Chart-of-Accounts account a business event uses.

    key examples: cash, bank, receivable, payable, inventory, sales_revenue, sales_discount,
                  cogs, expense_default, expense_cat_<category id>, pm_<payment method name>
    """
    key = models.CharField(max_length=40, unique=True)
    account = models.ForeignKey('Account', on_delete=models.PROTECT, related_name='+')
    note = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['key']

    def __str__(self):
        return f'{self.key} -> {self.account}'


class GLPosting(models.Model):
    """
    Links one business document (sale #12, vendor payment #7...) to the journal entry that booked it.
    Only one ACTIVE posting may exist per document, so nothing is ever booked twice.
    """
    source_type = models.CharField(max_length=30)   # sale, sale_payment, purchase, vendor_payment, expense
    source_id = models.PositiveIntegerField()
    journal_entry = models.ForeignKey('JournalEntry', on_delete=models.PROTECT, related_name='gl_postings')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['source_type', 'source_id'])]
        constraints = [
            models.UniqueConstraint(
                fields=['source_type', 'source_id'],
                condition=Q(is_active=True),
                name='one_active_gl_posting_per_document',
            ),
        ]

    def __str__(self):
        return f'{self.source_type}#{self.source_id} -> {self.journal_entry.entry_no}'
