"""OCR scan log + alias suggestions (the learning loop of the camera product search)."""
from django.conf import settings
from django.db import models


class OcrScanLog(models.Model):
    SOURCES = [('camera', 'Live camera'), ('photo', 'Photo'), ('manual', 'Typed')]
    OUTCOMES = [
        ('pending', 'Shown, no action yet'),
        ('no_match', 'No product found'),
        ('auto_added', 'Added automatically'),
        ('tapped_top', 'Cashier tapped the first match'),
        ('corrected', 'Cashier chose another product'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='+')
    source = models.CharField(max_length=10, choices=SOURCES, default='camera')
    raw_text = models.CharField(max_length=400, blank=True, default='')
    text = models.CharField(max_length=200, blank=True, default='')          # cleaned text used for matching
    ocr_conf = models.SmallIntegerField(null=True, blank=True)               # Tesseract confidence 0-100
    warehouse_id = models.IntegerField(null=True, blank=True)
    candidates = models.SmallIntegerField(default=0)
    top_product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    top_score = models.SmallIntegerField(default=0)
    confident = models.BooleanField(default=False)
    chosen_product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    outcome = models.CharField(max_length=12, choices=OUTCOMES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'OCR scan log'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['created_at'], name='app_ocrscan_created_idx'),
                   models.Index(fields=['outcome'], name='app_ocrscan_outcome_idx')]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.text[:40]} -> {self.outcome}"


class OcrAliasSuggestion(models.Model):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved (alias created)'), ('rejected', 'Rejected')]
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='ocr_alias_suggestions')
    text = models.CharField(max_length=100)
    hits = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'OCR alias suggestions'
        unique_together = ('product', 'text')
        ordering = ['-hits', '-last_seen']

    def __str__(self):
        return f"{self.text} -> {self.product} ({self.hits}x, {self.status})"
