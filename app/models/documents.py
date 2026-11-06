"""Documents models."""
from django.db import models
from datetime import datetime
from django.contrib.auth.models import User

class DocumentCategory(models.Model):
    """Document categories"""
    
    CATEGORY_TYPES = [
        ('financial', '💰 Financial'),
        ('customer', '👤 Customer'),
        ('employee', '👥 Employee'),
        ('company', '🏢 Company'),
        ('legal', '⚖️ Legal'),
        ('reports', '📊 Reports'),
        ('property', '🏠 Property'),
        ('vehicle', '🚗 Vehicle'),
        ('loan', '💳 Loan'),
        ('other', '📋 Other'),
    ]
    
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='📄')
    color = models.CharField(max_length=20, default='#667eea')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.icon} {self.name}"
    
    class Meta:
        verbose_name_plural = "Document Categories"
        ordering = ['name']


class Document(models.Model):
    """Main Document model"""
    
    DOCUMENT_STATUS = [
        ('draft', '📝 Draft'),
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
        ('archived', '📦 Archived'),
        ('expired', '⏰ Expired'),
    ]
    
    DOCUMENT_VISIBILITY = [
        ('public', '🌍 Public'),
        ('internal', '🏢 Internal'),
        ('private', '🔒 Private'),
        ('confidential', '🤫 Confidential'),
    ]
    
    # Basic Info
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    document_no = models.CharField(max_length=50, unique=True, blank=True)
    category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True, related_name='documents')
    document_type = models.CharField(max_length=100, blank=True, null=True)
    
    # File
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    file_size = models.BigIntegerField(default=0)
    file_type = models.CharField(max_length=50, blank=True, null=True)
    thumbnail = models.ImageField(upload_to='document_thumbnails/', null=True, blank=True)
    
    # Metadata
    version = models.IntegerField(default=1)
    page_count = models.IntegerField(default=0)
    keywords = models.CharField(max_length=500, blank=True, null=True)
    
    # Dates
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_date = models.DateField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=DOCUMENT_STATUS, default='draft')
    visibility = models.CharField(max_length=20, choices=DOCUMENT_VISIBILITY, default='private')
    is_template = models.BooleanField(default=False)
    
    # Relationships
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reviewed_documents')
    
    # Related Modules
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    purchase = models.ForeignKey('Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    employee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    shareholder = models.ForeignKey('Shareholder', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.document_no:
            from datetime import datetime
            year = datetime.now().strftime('%Y')
            last = Document.objects.filter(document_no__startswith=f'DOC-{year}').order_by('-document_no').first()
            if last and last.document_no:
                try:
                    last_num = int(last.document_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.document_no = f'DOC-{year}-{new_num}'
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.document_no} - {self.title}"
    
    def get_file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
    
    class Meta:
        verbose_name_plural = "Documents"
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['document_no']),
            models.Index(fields=['title']),
            models.Index(fields=['status']),
            models.Index(fields=['uploaded_at']),
        ]


class DocumentVersion(models.Model):
    """Document version history"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    file = models.FileField(upload_to='document_versions/%Y/%m/%d/')
    file_size = models.BigIntegerField(default=0)
    changes = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.document.document_no} - v{self.version_number}"
    
    class Meta:
        ordering = ['-version_number']


class DocumentShare(models.Model):
    """Document sharing"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='shares')
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_documents')
    shared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='documents_shared')
    permission = models.CharField(max_length=20, choices=[
        ('view', '👁️ View'),
        ('edit', '✏️ Edit'),
        ('delete', '🗑️ Delete'),
        ('share', '🔗 Share'),
    ], default='view')
    is_active = models.BooleanField(default=True)
    shared_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.document.title} → {self.shared_with.username}"
    
    class Meta:
        unique_together = ['document', 'shared_with']


class DocumentApproval(models.Model):
    """Document approval workflow"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_approvals')
    status = models.CharField(max_length=20, choices=[
        ('pending', '⏳ Pending'),
        ('approved', '✅ Approved'),
        ('rejected', '❌ Rejected'),
    ], default='pending')
    comments = models.TextField(blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.document.document_no} - {self.approver.username}"
    
    class Meta:
        unique_together = ['document', 'approver']


class DocumentTemplate(models.Model):
    """Document templates"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='document_templates/')
    category = models.ForeignKey(DocumentCategory, on_delete=models.SET_NULL, null=True)
    variables = models.JSONField(default=list, help_text="Variables to replace")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class DocumentFolder(models.Model):
    """Document folders for organization"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    color = models.CharField(max_length=20, default='#667eea')
    icon = models.CharField(max_length=50, default='📁')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    def get_full_path(self):
        if self.parent:
            return f"{self.parent.get_full_path()} / {self.name}"
        return self.name
    
    class Meta:
        verbose_name_plural = "Document Folders"
        ordering = ['name']
