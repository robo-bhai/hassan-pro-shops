# /storage/emulated/0/django/p1/app/utils/security.py

import secrets
import re
from datetime import timedelta
from django.utils.timezone import now
from django.core.mail import send_mail
from django.contrib.auth.hashers import check_password, make_password
from app.models import SecuritySettings, OTPVerification, LoginAttempt, IPBlacklist, SecurityAlert, PasswordHistory


def validate_password_strength(password):
    """Validate password against security policy"""
    settings = SecuritySettings.get_settings()
    errors = []
    
    if len(password) < settings.min_password_length:
        errors.append(f"Password must be at least {settings.min_password_length} characters")
    
    if settings.require_uppercase and not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if settings.require_lowercase and not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if settings.require_numbers and not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    
    if settings.require_special_chars and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    
    return errors


def check_password_history(user, password):
    """Check if password was used before"""
    settings = SecuritySettings.get_settings()
    if not settings.prevent_password_reuse:
        return True
    
    history = PasswordHistory.objects.filter(user=user).order_by('-created_at')[:settings.password_history_count]
    for entry in history:
        if check_password(password, entry.password_hash):
            return False
    return True


def save_password_history(user, password):
    """Save password to history"""
    PasswordHistory.objects.create(
        user=user,
        password_hash=make_password(password)
    )


def generate_otp(user, otp_type, length=6):
    """Generate OTP for user"""
    import random
    otp_code = ''.join([str(random.randint(0, 9)) for _ in range(length)])
    expires_at = now() + timedelta(minutes=5)
    
    return OTPVerification.objects.create(
        user=user,
        otp_code=otp_code,
        otp_type=otp_type,
        expires_at=expires_at
    )


def verify_otp(user, otp_code, otp_type):
    """Verify OTP"""
    try:
        otp = OTPVerification.objects.get(
            user=user,
            otp_code=otp_code,
            otp_type=otp_type,
            is_used=False,
            is_expired=False
        )
        
        if not otp.is_valid():
            return False, "OTP is expired or invalid"
        
        otp.is_used = True
        otp.save()
        return True, "OTP verified"
        
    except OTPVerification.DoesNotExist:
        return False, "Invalid OTP"


def send_otp_email(user, otp_code):
    """Send OTP via email"""
    subject = "Your OTP Code"
    message = f"""
    Hello {user.username},
    
    Your OTP code is: {otp_code}
    
    This code will expire in 5 minutes.
    
    If you didn't request this, please ignore this email.
    
    Regards,
    ERP System
    """
    send_mail(subject, message, None, [user.email])


def track_login_attempt(username, ip_address, user_agent, is_success, failure_reason=None):
    """Track login attempt"""
    from django.contrib.auth.models import User
    
    user = None
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        pass
    
    LoginAttempt.objects.create(
        user=user,
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
        is_success=is_success,
        failure_reason=failure_reason
    )
    
    # Check for brute force attack
    if not is_success:
        check_brute_force(username, ip_address)


def check_brute_force(username, ip_address):
    """Check for brute force attack"""
    settings = SecuritySettings.get_settings()
    time_window = now() - timedelta(minutes=5)
    
    failed_attempts = LoginAttempt.objects.filter(
        username=username,
        is_success=False,
        attempted_at__gte=time_window
    ).count()
    
    if failed_attempts >= settings.max_login_attempts:
        IPBlacklist.objects.get_or_create(
            ip_address=ip_address,
            defaults={
                'reason': f'Brute force attack detected - {failed_attempts} failed attempts',
                'expires_at': now() + timedelta(minutes=settings.lockout_time)
            }
        )
        
        SecurityAlert.objects.create(
            title="Brute Force Attack Detected",
            description=f"IP {ip_address} had {failed_attempts} failed login attempts for user {username}",
            alert_type='brute_force',
            severity='high',
            ip_address=ip_address
        )


def create_security_alert(title, description, alert_type, severity='medium', user=None, ip_address=None):
    """Create security alert"""
    alert = SecurityAlert.objects.create(
        title=title,
        description=description,
        alert_type=alert_type,
        severity=severity,
        user=user,
        ip_address=ip_address
    )
    return alert


def generate_api_key(user, name, permissions=None):
    """Generate API key for user"""
    from app.models import APIKey
    api_key = APIKey.objects.create(
        user=user,
        name=name,
        permissions=permissions or []
    )
    return api_key


def is_ip_allowed(ip_address):
    """Check if IP is allowed"""
    if IPBlacklist.objects.filter(ip_address=ip_address, is_active=True).exists():
        return False, "IP is blacklisted"
    
    settings = SecuritySettings.get_settings()
    if settings.enable_ip_whitelist:
        from app.models import IPWhitelist
        if not IPWhitelist.objects.filter(ip_address=ip_address, is_active=True).exists():
            return False, "IP is not whitelisted"
    
    return True, "IP allowed"