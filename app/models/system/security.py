"""Security models."""
from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User
from django.conf import settings

class SecuritySettings(models.Model):
    """Global security settings"""
    
    # Authentication
    enable_2fa = models.BooleanField(default=False)
    max_login_attempts = models.IntegerField(default=5)
    lockout_time = models.IntegerField(default=30, help_text="Minutes")
    session_timeout = models.IntegerField(default=60, help_text="Minutes")
    enable_auto_logout = models.BooleanField(default=True)
    
    # Password Policy
    min_password_length = models.IntegerField(default=8)
    require_uppercase = models.BooleanField(default=True)
    require_lowercase = models.BooleanField(default=True)
    require_numbers = models.BooleanField(default=True)
    require_special_chars = models.BooleanField(default=True)
    password_expiry_days = models.IntegerField(default=90)
    prevent_password_reuse = models.BooleanField(default=True)
    password_history_count = models.IntegerField(default=5)
    
    # IP Security
    enable_ip_whitelist = models.BooleanField(default=False)
    enable_ip_blacklist = models.BooleanField(default=True)
    
    # API Security
    enable_api_auth = models.BooleanField(default=True)
    api_rate_limit = models.IntegerField(default=100)
    
    # Alerts
    enable_security_alerts = models.BooleanField(default=True)
    alert_email = models.EmailField(blank=True, null=True)
    alert_whatsapp = models.CharField(max_length=20, blank=True, null=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Security Settings"
    
    def __str__(self):
        return f"Security Settings (Updated: {self.updated_at})"
    
    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings


class User2FASettings(models.Model):
    """User-specific 2FA settings"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security_settings')
    is_2fa_enabled = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    secret_key = models.CharField(max_length=255, blank=True, null=True)
    backup_codes = models.JSONField(default=list, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - 2FA: {self.is_2fa_enabled}"


class OTPVerification(models.Model):
    """OTP verification records"""
    
    OTP_TYPES = [
        ('login', 'Login OTP'),
        ('password_reset', 'Password Reset'),
        ('email_verification', 'Email Verification'),
        ('transaction', 'Transaction OTP'),
        ('api', 'API Authentication'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_verifications')
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPES)
    is_used = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.otp_type} - {self.otp_code}"
    
    def is_valid(self):
        from django.utils.timezone import now
        return not self.is_used and not self.is_expired and self.expires_at > now()


class IPWhitelist(models.Model):
    """IP whitelist for secure access"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    description = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.ip_address} ({self.description})"


class IPBlacklist(models.Model):
    """IP blacklist for blocked access"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    reason = models.TextField()
    blocked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    blocked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.ip_address} - {self.reason[:50]}"


class LoginAttempt(models.Model):
    """Track login attempts for security"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='login_attempts')
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True, null=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-attempted_at']
    
    def __str__(self):
        return f"{self.username} - {self.ip_address} - {'Success' if self.is_success else 'Failed'}"


class AccessLog(models.Model):
    """Detailed access log for all actions"""
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='access_logs')
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    is_sensitive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['module', 'created_at']),
            models.Index(fields=['ip_address']),
        ]
    
    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'} - {self.action} - {self.module}"


class SecurityAlert(models.Model):
    """Security alerts and notifications"""
    
    SEVERITY_CHOICES = [
        ('low', '🟢 Low'),
        ('medium', '🟡 Medium'),
        ('high', '🔴 High'),
        ('critical', '🔥 Critical'),
    ]
    
    ALERT_TYPES = [
        ('brute_force', 'Brute Force Attack'),
        ('suspicious_login', 'Suspicious Login'),
        ('ip_blocked', 'IP Blocked'),
        ('password_change', 'Password Changed'),
        ('2fa_failed', '2FA Failed'),
        ('unauthorized_access', 'Unauthorized Access'),
        ('api_key_compromised', 'API Key Compromised'),
        ('data_breach', 'Data Breach'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='resolved_alerts')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='security_alerts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_severity_display()} - {self.title}"


class APIKey(models.Model):
    """API key management for secure API access"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    permissions = models.JSONField(default=list, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    def save(self, *args, **kwargs):
        if not self.key:
            import secrets
            self.key = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)


class PasswordHistory(models.Model):
    """Track password history for reuse prevention"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.created_at}"


class SessionLog(models.Model):
    """Active session management"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.ip_address} - {'Active' if self.is_active else 'Logged Out'}"
