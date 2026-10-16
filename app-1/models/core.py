"""Core models."""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.utils.timezone import localdate
from django.db.models import Sum
from django.contrib.auth.models import User
import hashlib
from app.utils.email_helper import send_notification_email
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CompanyInfo(models.Model):
    name = models.CharField("Company Name", max_length=255)
    tagline = models.CharField("Tagline", max_length=255, blank=True, null=True)
    address = models.TextField("Address")
    contact_number = models.CharField("Phone", max_length=50)
    email = models.EmailField("Email")
    website = models.URLField("Website", blank=True, null=True)
    logo = models.ImageField("Company Logo", upload_to="company_logo/", blank=True, null=True)
    footer_note = models.CharField("Footer Note (for reports)", max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ✅ NEW FIELDS FOR DEPOSIT PAYMENTS
    jazzcash_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        verbose_name="JazzCash Number",
        help_text="JazzCash account number for deposits"
    )
    easypaisa_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        verbose_name="EasyPaisa Number",
        help_text="EasyPaisa account number for deposits"
    )
    bank_account_title = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        verbose_name="Bank Account Title",
        help_text="Bank account title for deposits"
    )
    bank_account_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Bank Account Number",
        help_text="Bank account number for deposits"
    )
    bank_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="Bank Name",
        help_text="Bank name for deposits"
    )
    deposit_instructions = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Deposit Instructions",
        help_text="Additional instructions for deposit payments"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Company Information"
        verbose_name_plural = "Company Information"


class TrainingTopic(models.Model):
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100, choices=[
        ('product', 'Product Management'),
        ('purchase', 'Purchases'),
        ('sale', 'Sales'),
        ('warehouse', 'Warehouse Management'),
        ('report', 'Reporting'),
        ('backup', 'Backup & Restore'),
        ('other', 'Other')
    ])
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']
        verbose_name_plural = "📘 Training Topics"

    def __str__(self):
        return self.title


class TrainingStep(models.Model):
    topic = models.ForeignKey(TrainingTopic, on_delete=models.CASCADE, related_name="steps")
    step_number = models.PositiveIntegerField()
    description = models.TextField(help_text="Explain what the user should do in this step.")
    screenshot = models.ImageField(upload_to="training_screenshots/", null=True, blank=True)

    class Meta:
        ordering = ['step_number']
        verbose_name_plural = "📗 Training Steps"

    def __str__(self):
        return f"{self.topic.title} - Step {self.step_number}"


class License(models.Model):
    key = models.CharField(max_length=255, unique=True)  # License Key
    expiry_date = models.DateField()  # Expiration Date
    created_at = models.DateTimeField(auto_now_add=True)  # When the key was created
    is_active = models.BooleanField(default=True)

    def is_valid(self):
        """Check if the license is still valid."""
        return self.expiry_date >= localdate()

    @staticmethod
    def generate_license_key(secret):
        """Generate a hash-based license key using a secret string."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def save(self, *args, **kwargs):
        """Ensure only programmers can set the license key."""
        if not self.key:
            raise ValidationError("License key cannot be empty.")
        if not self.expiry_date:
            raise ValidationError("Expiry date must be set.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"License (Valid till {self.expiry_date})"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('info', 'ℹ️ Info'),
        ('success', '✅ Success'),
        ('warning', '⚠️ Warning'),
        ('danger', '❌ Danger'),
        ('sale', '🛒 New Sale'),
        ('installment', '📅 Installment Due'),
        ('stock', '📦 Low Stock'),
        ('payment', '💰 Payment Received'),
    ]
    
    NOTIFICATION_CATEGORIES = [
        ('all', 'All Notifications'),
        ('sales', 'Sales'),
        ('payments', 'Payments'),
        ('installments', 'Installments'),
        ('stock', 'Stock Alerts'),
        ('system', 'System'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    category = models.CharField(max_length=20, choices=NOTIFICATION_CATEGORIES, default='all')
    is_read = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    link = models.CharField(max_length=200, blank=True, null=True, help_text="URL to redirect when clicked")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_read']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%d-%m-%Y %H:%M')}"
    
    @classmethod
    def send(cls, user, title, message, notification_type='info', category='all', link=None):
        """Create in-app notification and trigger email dispatch via email_helper."""
        notification = cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            category=category,
            link=link
        )
        
        # Email Dispatch Logic connected to email_helper.py
        if user and user.email:
            try:
                base_url = getattr(settings, 'SITE_URL', 'https://uqn88.store')
                action_link = None
                
                if link:
                    action_link = f"{base_url}{link}" if not link.startswith('http') else link

                # Import helper inside method to avoid circular import issues
                from app.utils.email_helper import send_notification_email
                
                send_notification_email(
                    recipient_email=user.email,
                    subject=title,
                    body_html=f"<p>{message}</p>",
                    body_text=message,
                    action_link=action_link
                )
            except Exception as e:
                logger.error(f"Failed to send email to {user.email}: {e}")

        return notification
    
    @classmethod
    def send_to_all(cls, title, message, notification_type='info', category='all', link=None):
        """Send notification to all active staff users and email their saved addresses."""
        staff_users = User.objects.filter(is_staff=True, is_active=True)

        for user in staff_users:
            cls.send(
                user=user,
                title=f"[Staff Alert] {title}",
                message=message,
                notification_type=notification_type,
                category=category,
                link=link
            )
    
    @classmethod
    def send_sale_notification(cls, user, sale):
        """Send sale notification"""
        return cls.send(
            user=user,
            title="🛒 New Sale Created",
            message=f"Sale #{sale.bill_no} of Rs. {sale.total_amount():,.2f} created successfully!",
            notification_type='sale',
            category='sales',
            link=f"/sales/{sale.id}/"
        )
    
    @classmethod
    def send_payment_notification(cls, user, sale, amount):
        """Send payment notification"""
        return cls.send(
            user=user,
            title="💰 Payment Received",
            message=f"Payment of Rs. {amount:,.2f} received for {sale.bill_no}",
            notification_type='payment',
            category='payments',
            link=f"/sales/{sale.id}/"
        )
    
    @classmethod
    def send_installment_notification(cls, user, installment):
        """Send installment notification"""
        return cls.send(
            user=user,
            title="📅 Installment Due",
            message=f"Installment for Bill #{installment.sale.bill_no} is due on {installment.next_due_date}. Amount: Rs. {installment.remaining_amount():,.2f}",
            notification_type='installment',
            category='installments',
            link=f"/installments/{installment.id}/"
        )
    
    @classmethod
    def send_low_stock_notification(cls, user, product, current_stock):
        """Send low stock notification"""
        return cls.send(
            user=user,
            title="⚠️ Low Stock Alert",
            message=f"Product '{product.name}' has only {current_stock} units left. Threshold is {product.low_stock_threshold}.",
            notification_type='stock',
            category='stock',
            link=f"/admin/app/product/{product.id}/change/"
        )
    
    @classmethod
    def send_system_notification(cls, user, title, message):
        """Send system notification"""
        return cls.send(
            user=user,
            title=title,
            message=message,
            notification_type='info',
            category='system'
        )
    
    @classmethod
    def send_installment_paid_notification(cls, user, installment, amount):
        """Send installment paid notification"""
        remaining = installment.remaining_amount()
        if remaining <= 0:
            message = f"✅ Installment for Bill #{installment.sale.bill_no} has been fully paid! Total paid: Rs. {installment.total_paid():,.2f}"
        else:
            message = f"💰 Payment of Rs. {amount:,.2f} received for Bill #{installment.sale.bill_no}. Remaining: Rs. {remaining:,.2f}"
        
        return cls.send(
            user=user,
            title="✅ Installment Payment",
            message=message,
            notification_type='payment',
            category='payments',
            link=f"/installments/{installment.id}/"
        )


class SystemSetting(models.Model):
    """System settings for modules visibility and other configurations"""
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.CharField(max_length=255, default='true')
    description = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "System Settings"
        ordering = ['setting_key']
    
    def __str__(self):
        return f"{self.setting_key}: {self.setting_value}"

    @classmethod
    def get_value(cls, key, default='true'):
        """Get setting value by key"""
        setting = cls.objects.filter(setting_key=key).first()
        if setting:
            return setting.setting_value
        return default
    
    @classmethod
    def get_bool(cls, key, default=True):
        """Get setting as boolean"""
        value = cls.get_value(key, str(default).lower())
        return value.lower() in ['true', '1', 'yes', 'on']
    
    @classmethod
    def set_value(cls, key, value, user=None):
        """Set setting value"""
        setting, created = cls.objects.get_or_create(setting_key=key)
        setting.setting_value = str(value).lower()
        if user:
            setting.updated_by = user
        setting.save()
        return setting
    
    @classmethod
    def toggle(cls, key, user=None):
        """Toggle boolean setting"""
        current = cls.get_bool(key)
        cls.set_value(key, not current, user)
        return not current


class Department(models.Model):
    """Department model for cost centers"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Departments"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.name[:3].upper()
        super().save(*args, **kwargs)


class Project(models.Model):
    """Project model for project-wise expenses"""
    
    STATUS_CHOICES = [
        ('active', '✅ Active'),
        ('completed', '🎯 Completed'),
        ('on_hold', '⏸️ On Hold'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Projects"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            last_project = Project.objects.order_by('-id').first()
            if last_project and last_project.code:
                try:
                    last_num = int(last_project.code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except:
                    new_num = '0001'
            else:
                new_num = '0001'
            self.code = f'PRJ-{new_num}'
        super().save(*args, **kwargs)
    
    def total_expenses(self):
        return self.expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    def remaining_budget(self):
        return self.budget - self.total_expenses()


class TermsAndConditions(models.Model):
    version = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200, default="Shareholder Terms & Conditions")
    content = models.TextField()  # English content
    urdu_content = models.TextField(blank=True, null=True)  # ✅ Urdu content
    is_active = models.BooleanField(default=True)
    effective_date = models.DateField(default=now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
