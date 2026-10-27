"""Translation Manager: English UI text -> Urdu / Arabic (hand-written or auto-translated)."""
from django.db import models


class Translation(models.Model):
    STATUS = [
        ('', 'Missing'),
        ('default', 'Default'),
        ('auto', 'Auto'),
        ('manual', 'Manual'),
        ('reviewed', 'Reviewed'),
    ]

    key = models.CharField(max_length=300, unique=True)            # lower-case lookup key
    source = models.CharField(max_length=300)                      # English text as shown to people
    ur = models.TextField(blank=True, default='')
    ar = models.TextField(blank=True, default='')
    ur_status = models.CharField(max_length=10, blank=True, default='', choices=STATUS)
    ar_status = models.CharField(max_length=10, blank=True, default='', choices=STATUS)
    seen_count = models.PositiveIntegerField(default=0)            # how often a page showed it untranslated
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source']

    def __str__(self):
        return self.source
