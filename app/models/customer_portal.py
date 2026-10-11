"""Customer Portal models."""
from django.db import models
from datetime import timedelta
from django.utils.timezone import now
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
import hashlib
import logging

logger = logging.getLogger(__name__)

class CustomerOTP(models.Model):
    """
    OTP verification with security features:
    - Hashed storage (SHA-256)
    - Rate limiting (3 requests / 15 min)
    - Brute force protection (5 attempts → 30 min lock)
    - Audit trail with IP tracking
    - Order Token for late OTP verification
    - ✅ Email OTP sending
    """
    PURPOSE_CHOICES = [
        ('register', 'Registration'),
        ('login', 'Login'),
        ('forgot_password', 'Forgot Password'),
        ('order', 'Order Verification'),
    ]
    
    # Basic info
    phone = models.CharField(max_length=15, db_index=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='register')
    
    # ✅ SECURE: OTP hashed
    otp_hash = models.CharField(max_length=128, verbose_name="OTP Hash", default='placeholder_hash')
    otp_code = models.CharField(
        max_length=6, 
        blank=True, 
        null=True,
        verbose_name="OTP (for admin display only)"
    )
    
    # ✅ Order Token (for late OTP verification)
    order_token = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Order Token",
        help_text="8-character token for late OTP verification"
    )
    
    # Customer info
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_email = models.CharField(max_length=100, blank=True, null=True)
    
    # Status
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ✅ SECURITY: Brute force protection
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    locked_until = models.DateTimeField(null=True, blank=True)
    
    # ✅ TRACKING: Send to customer
    is_sent_to_customer = models.BooleanField(default=False, verbose_name="Sent to Customer")
    sent_by = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sent_otps'
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    send_method = models.CharField(
        max_length=20,
        choices=[
            ('whatsapp', '📱 WhatsApp'),
            ('sms', '💬 SMS'),
            ('call', '📞 Call'),
            ('email', '📧 Email'),
            ('manual', '👤 Manual'),
        ],
        blank=True,
        null=True
    )
    
    # ✅ SECURITY: IP tracking
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone', 'purpose', 'is_used']),
            models.Index(fields=['order_token']),
            models.Index(fields=['order_token', 'phone', 'purpose']),
            models.Index(fields=['expires_at', 'is_used']),
            models.Index(fields=['-created_at']),
        ]
        verbose_name_plural = "Customer OTPs"
    
    def __str__(self):
        return f"{self.phone} - {self.purpose} - {'Used' if self.is_used else 'Active'}"
    
    # ==========================================
    # VALIDITY CHECKS
    # ==========================================
    
    def is_valid(self):
        from django.utils.timezone import now
        return (
            not self.is_used and 
            self.expires_at > now() and 
            not self.is_locked()
        )
    
    def is_locked(self):
        from django.utils.timezone import now
        if self.locked_until and self.locked_until > now():
            return True
        return False
    
    def is_expired(self):
        from django.utils.timezone import now
        return self.expires_at <= now()
    
    @property
    def time_remaining(self):
        from django.utils.timezone import now
        if self.is_used or self.is_expired():
            return 0
        delta = self.expires_at - now()
        return max(0, int(delta.total_seconds()))
    
    @property
    def time_remaining_display(self):
        seconds = self.time_remaining
        if seconds <= 0:
            return "Expired"
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    
    @property
    def masked_code(self):
        if not self.otp_code:
            return "******"
        return f"{self.otp_code[:2]}****{self.otp_code[-1]}"
    
    @property
    def status_badge(self):
        if self.is_used:
            return '<span class="badge bg-secondary">✅ Used</span>'
        if self.is_locked():
            return '<span class="badge bg-danger">🔒 Locked</span>'
        if self.is_expired():
            return '<span class="badge bg-danger">⏰ Expired</span>'
        return '<span class="badge bg-success">🟢 Active</span>'
    
    # ==========================================
    # VERIFICATION
    # ==========================================
    
    def verify(self, code):
        import hashlib
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return code_hash == self.otp_hash
    
    def increment_attempts(self):
        from django.utils.timezone import now
        from datetime import timedelta
        
        self.attempts += 1
        
        if self.attempts >= self.max_attempts:
            self.locked_until = now() + timedelta(minutes=30)
            try:
                OTPAuditLog.objects.create(
                    phone=self.phone,
                    action='locked',
                    success=False,
                    notes=f"Locked after {self.attempts} failed attempts"
                )
            except Exception:
                pass
        
        self.save()
    
    def mark_used(self):
        self.is_used = True
        self.save()
    
    # ==========================================
    # GENERATION (UPDATED WITH EMAIL)
    # ==========================================
    
    @classmethod
    def generate_otp(cls, phone, purpose='register', 
                     customer_name='', customer_email='',
                     ip_address=None, user_agent='',
                     order_token=None, verify_url=None):
        """
        Generate OTP, save to DB, send email with verification link, and notify admin.
        """
        import random
        import hashlib
        from django.utils.timezone import now
        from datetime import timedelta
        
        # Rate limiting: 3 per 15 min
        recent_count = cls.objects.filter(
            phone=phone,
            purpose=purpose,
            created_at__gte=now() - timedelta(minutes=15)
        ).count()
        
        if recent_count >= 3:
            raise Exception(
                "Too many OTP requests. Please try again after 15 minutes."
            )
        
        # Delete old unused
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).delete()
        
        # Generate 6-digit
        otp_code = str(random.randint(100000, 999999))
        otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        
        otp = cls.objects.create(
            phone=phone,
            otp_hash=otp_hash,
            otp_code=otp_code,
            purpose=purpose,
            customer_name=customer_name,
            customer_email=customer_email,
            order_token=order_token,
            expires_at=now() + timedelta(minutes=5),
            request_ip=ip_address,
            user_agent=user_agent[:500] if user_agent else None
        )
        
        # Audit log
        try:
            OTPAuditLog.objects.create(
                phone=phone,
                action='generate',
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,
                success=True,
                notes=f"Purpose: {purpose}" + (f" | Token: {order_token}" if order_token else "")
            )
        except Exception:
            pass
        
        # ✅ EMAIL OTP TO CUSTOMER (WITH VERIFICATION LINK)
        if customer_email:
            try:
                from .utils.email_helper import send_otp_email
                
                email_sent = send_otp_email(
                    recipient_email=customer_email,
                    otp_code=otp_code,
                    customer_name=customer_name or 'Customer',
                    purpose=purpose,
                    verify_url=verify_url,  # Pass verification link to email helper
                )
                
                if email_sent:
                    otp.is_sent_to_customer = True
                    otp.sent_at = now()
                    otp.send_method = 'email'
                    otp.save()
                    logger.info(f"✅ OTP email sent to {customer_email}")
                else:
                    logger.warning(f"⚠️ OTP email failed for {customer_email}")
                    
            except Exception as e:
                logger.error(f"❌ OTP email exception for {customer_email}: {e}")
        
        # Admin notification
        try:
            admin_users = User.objects.filter(is_superuser=True)
            purpose_display = {
                'register': 'Registration',
                'login': 'Login',
                'forgot_password': 'Password Reset',
                'order': 'Order Verification'
            }
            
            for admin in admin_users:
                Notification.objects.create(
                    user=admin,
                    title=f"🔐 New OTP - {purpose_display.get(purpose, purpose)}",
                    message=(
                        f"Customer: {customer_name or 'Unknown'}\n"
                        f"Phone: {phone}\n"
                        f"OTP: {otp.masked_code} (masked)\n"
                        f"Email: {customer_email or 'Not provided'}\n"
                        + (f"Token: {order_token}\n" if order_token else "")
                        + (f"Verify Link: {verify_url}\n" if verify_url else "")
                        + f"Valid: 5 minutes"
                    ),
                    notification_type='info',
                    category='system',
                    link=f'/otp-management/{otp.id}/'
                )
        except Exception as e:
            logger.error(f"⚠️ Admin notification failed: {e}")
        
        return otp

    
    @classmethod
    def find_and_verify(cls, phone, code, purpose='register'):
        from django.utils.timezone import now
        
        otp = cls.objects.filter(
            phone=phone,
            purpose=purpose,
            is_used=False
        ).order_by('-created_at').first()
        
        if not otp:
            return False, None, "OTP not found. Please request a new one."
        
        if otp.is_locked():
            remaining = int((otp.locked_until - now()).total_seconds() / 60)
            return False, otp, f"Too many attempts. Try again in {remaining} minutes."
        
        if otp.is_expired():
            return False, otp, "OTP expired. Please request a new one."
        
        if not otp.verify(code):
            otp.increment_attempts()
            attempts_left = otp.max_attempts - otp.attempts
            if attempts_left > 0:
                return False, otp, f"Invalid OTP. {attempts_left} attempts remaining."
            return False, otp, "Too many failed attempts. Account locked for 30 minutes."
        
        otp.mark_used()
        
        try:
            OTPAuditLog.objects.create(
                phone=phone,
                action='verify_success',
                ip_address=otp.request_ip,
                success=True
            )
        except Exception:
            pass
        
        return True, otp, "OTP verified successfully!"
    
    @classmethod
    def find_by_token(cls, order_token, phone):
        """Find OTP by order token and phone"""
        return cls.objects.filter(
            order_token=order_token,
            phone=phone,
            purpose='order',
            is_used=False
        ).order_by('-created_at').first()


class OTPAuditLog(models.Model):
    """Security audit log for OTP activities"""
    ACTIONS = [
        ('generate', '🆕 Generate'),
        ('verify_success', '✅ Verify Success'),
        ('verify_fail', '❌ Verify Fail'),
        ('resend', '🔄 Resend'),
        ('locked', '🔒 Locked'),
        ('sent_to_customer', '📤 Sent to Customer'),
    ]
    
    phone = models.CharField(max_length=15, db_index=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "OTP Audit Logs"
        indexes = [
            models.Index(fields=['phone', '-created_at']),
            models.Index(fields=['action']),
        ]
    
    def __str__(self):
        return f"{self.phone} - {self.action} - {self.created_at.strftime('%d-%m-%Y %H:%M')}"


class CustomerProfile(models.Model):
    """Customer portal profile with trust system"""
    customer = models.OneToOneField(
        'Customer',
        on_delete=models.CASCADE,
        related_name='portal_profile'
    )
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='customer_profile',
        null=True,
        blank=True
    )
    
    # Verification
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    
    # Profile
    profile_pic = models.ImageField(upload_to='customer_profiles/', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        blank=True,
        null=True
    )
    preferred_language = models.CharField(max_length=5, default='en')
    newsletter_subscribed = models.BooleanField(default=True)
    
    # ✅ NEW: Trust system
    is_trusted = models.BooleanField(
        default=False,
        verbose_name="Trusted Customer",
        help_text="Trusted customers ko order par OTP nahi chahiye"
    )
    successful_orders = models.PositiveIntegerField(
        default=0,
        verbose_name="Successful Orders",
        help_text="Delivered orders count"
    )
    failed_orders = models.PositiveIntegerField(
        default=0,
        verbose_name="Failed Orders",
        help_text="Cancelled/Returned orders count"
    )
    trust_reset_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name="Trust Reset Reason"
    )
    
    # Timestamps
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.customer.name} - Portal Profile"
    
    # ==========================================
    # TRUST SYSTEM METHODS
    # ==========================================
    
    def should_skip_order_otp(self):
        """Check if customer can skip order OTP"""
        if not self.is_trusted:
            return False
        if self.failed_orders >= 3:
            return False
        return True
    
    def record_successful_order(self):
        """Record a successful order"""
        self.successful_orders += 1
        if self.successful_orders >= 3 and not self.is_trusted:
            self.is_trusted = True
            self.trust_reset_reason = f"Auto-trusted after {self.successful_orders} successful orders"
        self.save()
    
    def record_failed_order(self, reason=""):
        self.failed_orders += 1
        self.is_trusted = False
        self.trust_reset_reason = f"Failed order #{self.failed_orders}: {reason}"
        self.save()


    def reset_trust(self, reason=""):
        self.is_trusted = False
        self.successful_orders = 0
        self.trust_reset_reason = reason or "Manual reset"
        self.save()

    @property
    def trust_progress_percent(self):
        """Progress to trusted status"""
        return min(int((self.successful_orders / 3) * 100), 100)

    @property
    def orders_needed_for_trust(self):
        """How many more orders to become trusted"""
        return max(0, 3 - self.successful_orders)


class CustomerAddress(models.Model):
    """Customer delivery addresses"""
    ADDRESS_TYPES = [
        ('home', '🏠 Home'),
        ('office', '🏢 Office'),
        ('other', '📍 Other'),
    ]
    
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPES, default='home')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    alternate_phone = models.CharField(max_length=15, blank=True, null=True)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True)
    landmark = models.CharField(max_length=200, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name_plural = "Customer Addresses"
    
    def __str__(self):
        return f"{self.customer.name} - {self.city} ({self.address_type})"
    
    def save(self, *args, **kwargs):
        # Ensure only one default address per customer
        if self.is_default:
            CustomerAddress.objects.filter(
                customer=self.customer,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class CustomerOrder(models.Model):
    """Customer portal orders"""
    ORDER_STATUS = [
        ('pending', '⏳ Pending'),
        ('confirmed', '✅ Confirmed'),
        ('processing', '⚙️ Processing'),
        ('packed', '📦 Packed'),
        ('shipped', '🚚 Shipped'),
        ('out_for_delivery', '🛵 Out for Delivery'),
        ('delivered', '🎉 Delivered'),
        ('cancelled', '❌ Cancelled'),
        ('returned', '↩️ Returned'),
    ]
    
    PAYMENT_METHODS = [
        ('cod', '💵 Cash on Delivery'),
        ('jazzcash', '📱 JazzCash'),
        ('easypaisa', '📱 EasyPaisa'),
        ('bank', '🏦 Bank Transfer'),
        ('card', '💳 Card'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', '⏳ Pending'),
        ('paid', '✅ Paid'),
        ('failed', '❌ Failed'),
        ('refunded', '💰 Refunded'),
    ]
    
    # Order Info
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='portal_orders'
    )
    sale = models.ForeignKey(
        'Sale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_orders'
    )
    
    # Shipping
    shipping_name = models.CharField(max_length=100)
    shipping_phone = models.CharField(max_length=15)
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100, blank=True, null=True)
    shipping_postal_code = models.CharField(max_length=10, blank=True, null=True)
    shipping_landmark = models.CharField(max_length=200, blank=True, null=True)
    
    # Billing (optional, defaults to shipping)
    billing_same_as_shipping = models.BooleanField(default=True)
    billing_name = models.CharField(max_length=100, blank=True, null=True)
    billing_address = models.TextField(blank=True, null=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cod')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    tracking_number = models.CharField(max_length=50, blank=True, null=True)
    courier_name = models.CharField(max_length=100, blank=True, null=True)
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Cancellation
    cancellation_reason = models.TextField(blank=True, null=True)
    cancelled_by = models.CharField(
        max_length=20,
        choices=[('customer', 'Customer'), ('admin', 'Admin'), ('system', 'System')],
        blank=True,
        null=True
    )
    
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['-created_at']),
        ]
        verbose_name_plural = "Customer Portal Orders"
    
    def __str__(self):
        return f"#{self.order_number} - {self.customer.name} - Rs. {self.total_amount}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            from django.utils.timezone import now
            import random
            
            year = now().strftime('%Y%m%d')
            last_order = CustomerOrder.objects.filter(
                order_number__startswith=f'ORD-{year}'
            ).order_by('-order_number').first()
            
            if last_order:
                try:
                    last_num = int(last_order.order_number.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            
            self.order_number = f'ORD-{year}-{new_num}'
        
        super().save(*args, **kwargs)
    
    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())
    
    @property
    def can_cancel(self):
        """Check if order can be cancelled"""
        return self.status in ['pending', 'confirmed', 'processing']
    
    @property
    def can_track(self):
        """Check if order can be tracked"""
        return self.status in ['confirmed', 'processing', 'packed', 'shipped', 'out_for_delivery']
    
    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'confirmed': 'info',
            'processing': 'primary',
            'packed': 'primary',
            'shipped': 'info',
            'out_for_delivery': 'info',
            'delivered': 'success',
            'cancelled': 'danger',
            'returned': 'secondary',
        }
        return colors.get(self.status, 'secondary')


class CustomerOrderItem(models.Model):
    """Order line items"""
    order = models.ForeignKey(
        CustomerOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    
    # Snapshot (in case product changes later)
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=50, blank=True, null=True)
    product_image = models.CharField(max_length=255, blank=True, null=True)
    
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2)
    
    class Meta:
        verbose_name_plural = "Customer Order Items"
    
    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        # Auto-fill snapshot data
        if self.product and not self.product_name:
            self.product_name = self.product.name
            self.product_sku = self.product.serial_no or self.product.barcode
            if self.product.image:
                self.product_image = self.product.image.url
        
        # Calculate total
        self.total = (self.price - self.discount) * self.quantity
        
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """Track order status changes"""
    order = models.ForeignKey(
        CustomerOrder,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    status = models.CharField(max_length=20, choices=CustomerOrder.ORDER_STATUS)
    notes = models.TextField(blank=True, null=True)
    updated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Order Status History"
    
    def __str__(self):
        return f"{self.order.order_number} - {self.status}"


class RecentlyViewed(models.Model):
    """Customer ke recently viewed products"""
    customer = models.ForeignKey(
        'Customer', 
        on_delete=models.CASCADE, 
        related_name='recently_viewed',
        null=True,
        blank=True
    )
    session_key = models.CharField(
        max_length=40, 
        blank=True, 
        null=True,
        db_index=True
    )
    product = models.ForeignKey(
        'Product', 
        on_delete=models.CASCADE,
        related_name='viewed_by'
    )
    viewed_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Recently Viewed"
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['customer', '-viewed_at']),
            models.Index(fields=['session_key', '-viewed_at']),
        ]
    
    def __str__(self):
        name = self.customer.name if self.customer else f"Session {self.session_key}"
        return f"{name} viewed {self.product.name}"
    
    @classmethod
    def track_view(cls, request, product):
        """Product view track karo"""
        customer = None
        session_key = None
        
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile.customer
        else:
            if not request.session.session_key:
                request.session.create()
            session_key = request.session.session_key
        
        # Existing entry delete karo (taake dobara top par aaye)
        cls.objects.filter(
            customer=customer,
            session_key=session_key,
            product=product
        ).delete()
        
        # Naya entry banao
        cls.objects.create(
            customer=customer,
            session_key=session_key,
            product=product
        )
        
        # Purane views delete karo (max 20)
        if customer:
            old_views = cls.objects.filter(customer=customer)[20:]
        else:
            old_views = cls.objects.filter(session_key=session_key)[20:]
        
        for view in old_views:
            view.delete()
    
    @classmethod
    def get_recently_viewed(cls, request, limit=8):
        """Recently viewed products nikalo"""
        customer = None
        session_key = None
        
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile.customer
        else:
            session_key = request.session.session_key
        
        if customer:
            views = cls.objects.filter(customer=customer).select_related(
                'product'
            )[:limit]
        elif session_key:
            views = cls.objects.filter(session_key=session_key).select_related(
                'product'
            )[:limit]
        else:
            return []
        
        return [view.product for view in views]


class LiveVisitor(models.Model):
    """
    Track live visitors on the customer shop
    
    Features:
    - Har visitor 60 second tak "active" rehta hai
    - Har 30 second mein count update hota hai
    - 5 minute purane visitors auto-delete
    - Session-based tracking (same user ek hi count hoga)
    """
    
    # ✅ Basic Fields
    session_key = models.CharField(
        max_length=100, 
        db_index=True,
        verbose_name="Session Key",
        help_text="Django session key of the visitor"
    )
    ip_address = models.GenericIPAddressField(
        null=True, 
        blank=True,
        verbose_name="IP Address"
    )
    user_agent = models.TextField(
        blank=True, 
        null=True,
        verbose_name="User Agent",
        help_text="Browser/device information"
    )
    page_url = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name="Page URL",
        help_text="Current page the visitor is on"
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Seen"
    )
    
    # ✅ Meta
    class Meta:
        verbose_name = "🟢 Live Visitor"
        verbose_name_plural = "🟢 Live Visitors"
        ordering = ['-last_seen']
        indexes = [
            models.Index(fields=['session_key']),
            models.Index(fields=['last_seen']),
        ]
    
    # ✅ String Representation
    def __str__(self):
        return f"{self.session_key[:8]}... - {self.last_seen.strftime('%d-%m-%Y %H:%M:%S')}"
    
    # ==========================================
    # ✅ CLASS METHODS
    # ==========================================
    
    @classmethod
    def get_active_count(cls, seconds=60):
        """
        Kitne log abhi active hain (last N seconds)
        
        Args:
            seconds: Kitne seconds ke andar active visitors count karne hain
        
        Returns:
            int: Active visitors count
        """
        from django.utils.timezone import now
        from datetime import timedelta
        
        cutoff = now() - timedelta(seconds=seconds)
        return cls.objects.filter(last_seen__gte=cutoff).count()
    
    @classmethod
    def track_visitor(cls, request):
        """
        Current visitor ko track karo
        
        Args:
            request: Django request object
        
        Returns:
            LiveVisitor instance
        """
        from django.utils.timezone import now
        
        # ✅ Session key nikalo (agar nahi hai to banao)
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        
        # ✅ IP address nikalo
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        
        # ✅ User agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        # ✅ Current page URL
        page_url = request.path[:255]
        
        # ✅ Update ya create (same session = 1 entry)
        visitor, created = cls.objects.update_or_create(
            session_key=session_key,
            defaults={
                'ip_address': ip or None,
                'user_agent': user_agent or None,
                'page_url': page_url,
            }
        )
        
        # ✅ Purane visitors clean karo (5 minute se purane)
        cls.cleanup_old_visitors(minutes=5)
        
        return visitor
    
    @classmethod
    def cleanup_old_visitors(cls, minutes=5):
        """
        Purane visitors delete karo
        
        Args:
            minutes: Kitne minute se purane visitors delete karne hain
        """
        from django.utils.timezone import now
        from datetime import timedelta
        
        cutoff = now() - timedelta(minutes=minutes)
        deleted_count, _ = cls.objects.filter(last_seen__lt=cutoff).delete()
        
        return deleted_count


class ChatConversation(models.Model):
    """Customer aur admin ke beech ek conversation"""
    
    STATUS_CHOICES = [
        ('active', '🟢 Active'),
        ('closed', '⚫ Closed'),
        ('archived', '📁 Archived'),
    ]
    
    customer = models.ForeignKey(
        'Customer', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='chat_conversations'
    )
    session_key = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        db_index=True,
        help_text="Guest user ke liye session key"
    )
    guest_name = models.CharField(max_length=100, blank=True, null=True)
    guest_phone = models.CharField(max_length=20, blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    subject = models.CharField(max_length=200, blank=True, null=True)
    
    assigned_to = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_chats'
    )
    
    customer_unread_count = models.PositiveIntegerField(default=0)
    admin_unread_count = models.PositiveIntegerField(default=0)
    
    last_message_at = models.DateTimeField(auto_now_add=True)
    last_message_preview = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "💬 Chat Conversations"
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['status', '-last_message_at']),
            models.Index(fields=['session_key']),
            models.Index(fields=['customer']),
        ]
    
    def __str__(self):
        name = self.customer.name if self.customer else (self.guest_name or f"Guest_{self.id}")
        return f"Chat #{self.id} - {name} ({self.get_status_display()})"
    
    def get_display_name(self):
        if self.customer:
            return self.customer.name
        if self.guest_name:
            return self.guest_name
        return f"Guest #{self.id}"


class ChatMessage(models.Model):
    """Individual chat message"""
    
    SENDER_TYPES = [
        ('customer', '👤 Customer'),
        ('admin', '👨‍💼 Admin'),
        ('system', '🤖 System'),  # ✅ IMPORTANT — AI ke liye
    ]
    
    conversation = models.ForeignKey(
        ChatConversation, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    sender_type = models.CharField(max_length=10, choices=SENDER_TYPES)
    sender = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sent_chat_messages'
    )
    message = models.TextField()
    
    attachment = models.FileField(
        upload_to='chat_attachments/%Y/%m/', 
        null=True, 
        blank=True
    )
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "💬 Chat Messages"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['is_read']),
        ]
    
    def __str__(self):
        return f"[{self.get_sender_type_display()}] {self.message[:50]}"
    
    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = now()
            self.save(update_fields=['is_read', 'read_at'])


class ChatTypingStatus(models.Model):
    """Real-time typing indicator"""
    
    conversation = models.ForeignKey(
        ChatConversation, 
        on_delete=models.CASCADE, 
        related_name='typing_status'
    )
    is_customer_typing = models.BooleanField(default=False)
    is_admin_typing = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "⌨️ Chat Typing Status"
    
    def __str__(self):
        return f"Chat #{self.conversation.id} - typing"


class AdminPresence(models.Model):
    """
    Admin ki REAL-TIME presence track karo
    
    Yeh last_login se alag hai:
    - last_login = Kab login kiya (kabhi kabhi purana ho jata hai)
    - last_activity = Abhi kya kaam kar raha hai (real-time)
    """
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='admin_presence'
    )
    is_online = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    current_page = models.CharField(max_length=200, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "👨‍💼 Admin Presence"
        indexes = [
            models.Index(fields=['is_online', '-last_activity']),
        ]
    
    def __str__(self):
        status = "🟢 Online" if self.is_online else "⚫ Offline"
        return f"{self.user.username} - {status}"
    
    def is_really_online(self, seconds=60):
        """Agar 60 second mein activity hui hai to online hai"""
        from django.utils.timezone import now
        from datetime import timedelta
        if not self.is_online:
            return False
        threshold = now() - timedelta(seconds=seconds)
        return self.last_activity >= threshold
    
    @classmethod
    def mark_activity(cls, user, page=None):
        """Admin ki activity mark karo (har page load pe)"""
        presence, _ = cls.objects.get_or_create(user=user)
        presence.is_online = True
        if page:
            presence.current_page = page[:200]
        presence.save()
    
    @classmethod
    def mark_offline(cls, user):
        """Admin offline mark karo (logout pe)"""
        cls.objects.filter(user=user).update(is_online=False)
    
    @classmethod
    def is_any_admin_live(cls, seconds=60):
        """
        Koi bhi admin LIVE hai kya?
        
        Args:
            seconds: Kitne second mein activity hui ho (default 60)
        
        Returns:
            True agar koi admin live ho, warna False
        """
        from django.utils.timezone import now
        from datetime import timedelta
        threshold = now() - timedelta(seconds=seconds)
        return cls.objects.filter(
            is_online=True,
            last_activity__gte=threshold,
            user__is_active=True,
            user__is_staff=True
        ).exists()
    
    @classmethod
    def get_live_admins(cls, seconds=60):
        """Saare live admins ki list"""
        from django.utils.timezone import now
        from datetime import timedelta
        threshold = now() - timedelta(seconds=seconds)
        return cls.objects.filter(
            is_online=True,
            last_activity__gte=threshold,
            user__is_active=True,
            user__is_staff=True
        ).select_related('user')
