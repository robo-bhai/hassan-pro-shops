"""
Security utilities: password policy, one-time codes, login tracking and
IP access control.

Public function names and signatures are unchanged, so existing views keep
working. Optional Django settings read by this module:

    SITE_NAME                    Name shown in OTP emails (default "ERP System").
    SECURITY_TRUSTED_PROXY_COUNT Number of reverse proxies in front of Django
                                 (default 0). Only then is X-Forwarded-For used.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.timezone import now

from app.models import (
    IPBlacklist,
    LoginAttempt,
    OTPVerification,
    PasswordHistory,
    SecurityAlert,
    SecuritySettings,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
OTP_MAX_FAILED_ATTEMPTS = 5
OTP_ATTEMPT_WINDOW_SECONDS = 600

BRUTE_FORCE_WINDOW_MINUTES = 5

# A "special character" is anything that is not an ASCII letter, digit or
# whitespace. The change-password page uses the same rule in JavaScript.
SPECIAL_CHAR_PATTERN = re.compile(r"[^\w\s]|_", re.ASCII)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def normalize_ip(value):
    """Return the canonical form of an IPv4/IPv6 address, or None if invalid.

    Use this to validate input on the IP whitelist/blacklist forms.
    """
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def get_client_ip(request):
    """Return the client IP address.

    X-Forwarded-For can be forged by the client, so it is only trusted when
    SECURITY_TRUSTED_PROXY_COUNT says how many proxies sit in front of Django.
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    proxy_count = getattr(django_settings, "SECURITY_TRUSTED_PROXY_COUNT", 0)
    if proxy_count <= 0:
        return remote_addr

    hops = [
        hop.strip()
        for hop in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if hop.strip()
    ]
    if len(hops) < proxy_count:
        return remote_addr
    return normalize_ip(hops[-proxy_count]) or remote_addr


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------

def validate_password_strength(password):
    """Validate a password against the security policy.

    Returns a list of error messages; an empty list means the password is valid.
    """
    policy = SecuritySettings.get_settings()
    errors = []

    if len(password) < policy.min_password_length:
        errors.append(f"Password must be at least {policy.min_password_length} characters.")
    if policy.require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if policy.require_lowercase and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if policy.require_numbers and not re.search(r"\d", password, re.ASCII):
        errors.append("Password must contain at least one number.")
    if policy.require_special_chars and not SPECIAL_CHAR_PATTERN.search(password):
        errors.append("Password must contain at least one special character.")

    return errors


def check_password_history(user, password):
    """Return True if the password may be used, False if it was used recently."""
    policy = SecuritySettings.get_settings()
    if not policy.prevent_password_reuse:
        return True

    if user.has_usable_password() and user.check_password(password):
        return False

    recent = PasswordHistory.objects.filter(user=user).order_by("-created_at")[
        : policy.password_history_count
    ]
    return not any(check_password(password, entry.password_hash) for entry in recent)


def save_password_history(user, password):
    """Store a hash of the password and prune entries beyond the history limit."""
    PasswordHistory.objects.create(user=user, password_hash=make_password(password))

    keep = SecuritySettings.get_settings().password_history_count
    if keep and keep > 0:
        stale_ids = list(
            PasswordHistory.objects.filter(user=user)
            .order_by("-created_at")
            .values_list("pk", flat=True)[keep:]
        )
        if stale_ids:
            PasswordHistory.objects.filter(pk__in=stale_ids).delete()


# ---------------------------------------------------------------------------
# One-time codes (OTP)
# ---------------------------------------------------------------------------

def generate_otp(user, otp_type, length=OTP_LENGTH):
    """Create a new OTP for the user and invalidate any unused earlier ones."""
    OTPVerification.objects.filter(user=user, otp_type=otp_type, is_used=False).update(is_used=True)

    code = f"{secrets.randbelow(10 ** length):0{length}d}"
    return OTPVerification.objects.create(
        user=user,
        otp_code=code,
        otp_type=otp_type,
        expires_at=now() + timedelta(minutes=OTP_TTL_MINUTES),
    )


def _otp_failure_key(user, otp_type):
    return f"otp_failures:{user.pk}:{otp_type}"


def _record_otp_failure(key):
    if cache.add(key, 1, OTP_ATTEMPT_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, OTP_ATTEMPT_WINDOW_SECONDS)


def verify_otp(user, otp_code, otp_type):
    """Verify a submitted OTP. Returns (success, message).

    Failed attempts are limited per user, and the code is compared in
    constant time. The failure message is the same for wrong and expired
    codes so it does not reveal which one it was.
    """
    failure_key = _otp_failure_key(user, otp_type)
    if cache.get(failure_key, 0) >= OTP_MAX_FAILED_ATTEMPTS:
        return False, "Too many incorrect attempts. Please try again in a few minutes."

    otp = (
        OTPVerification.objects.filter(
            user=user, otp_type=otp_type, is_used=False, is_expired=False
        )
        .order_by("-pk")
        .first()
    )
    submitted = (otp_code or "").strip()

    if otp is None or not otp.is_valid() or not hmac.compare_digest(str(otp.otp_code), submitted):
        _record_otp_failure(failure_key)
        return False, "The code is invalid or has expired."

    otp.is_used = True
    otp.save(update_fields=["is_used"])
    cache.delete(failure_key)
    return True, "OTP verified."


def send_otp_email(user, otp_code):
    """Email an OTP to the user. Returns True if the email was sent."""
    if not user.email:
        logger.warning("Cannot send OTP: user %s has no email address.", user.pk)
        return False

    site_name = getattr(django_settings, "SITE_NAME", "ERP System")
    message = "\n".join([
        f"Hello {user.get_username()},",
        "",
        f"Your verification code is: {otp_code}",
        "",
        f"This code expires in {OTP_TTL_MINUTES} minutes. Do not share it with anyone.",
        "If you did not request this code, you can ignore this email.",
        "",
        site_name,
    ])

    try:
        send_mail(f"{site_name} verification code", message, None, [user.email])
    except Exception:
        logger.exception("Failed to send OTP email to user %s.", user.pk)
        return False
    return True


# ---------------------------------------------------------------------------
# Login tracking and brute-force protection
# ---------------------------------------------------------------------------

def track_login_attempt(username, ip_address, user_agent, is_success, failure_reason=None):
    """Record a login attempt and run brute-force detection on failures."""
    User = get_user_model()
    username = (username or "")[:150]
    user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()

    LoginAttempt.objects.create(
        user=user,
        username=username,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255],
        is_success=is_success,
        failure_reason=failure_reason,
    )

    if not is_success:
        check_brute_force(username, ip_address)


def _block_is_in_force(entry):
    return entry.is_active and (entry.expires_at is None or entry.expires_at > now())


def check_brute_force(username, ip_address):
    """Temporarily block an IP that exceeds the failed-login limit.

    Failures are counted per IP (across usernames), so an attacker cannot lock
    out a victim's own IP by guessing the victim's username from elsewhere.
    A permanent manual block is never shortened, and the alert is raised only
    when a new block is applied.
    """
    if not ip_address:
        return

    policy = SecuritySettings.get_settings()
    window_start = now() - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)
    failed_attempts = LoginAttempt.objects.filter(
        ip_address=ip_address, is_success=False, attempted_at__gte=window_start
    ).count()

    if failed_attempts < policy.max_login_attempts:
        return

    reason = f"Brute force attack detected - {failed_attempts} failed attempts"
    expires_at = now() + timedelta(minutes=policy.lockout_time)

    entry = IPBlacklist.objects.filter(ip_address=ip_address).first()
    if entry is None:
        IPBlacklist.objects.create(ip_address=ip_address, reason=reason, expires_at=expires_at)
    elif _block_is_in_force(entry):
        return
    else:
        entry.reason = reason
        entry.expires_at = expires_at
        entry.is_active = True
        entry.save()

    create_security_alert(
        title="Brute Force Attack Detected",
        description=(
            f"IP {ip_address} was blocked for {policy.lockout_time} minutes after "
            f"{failed_attempts} failed login attempts (last username: {username})."
        ),
        alert_type="brute_force",
        severity="high",
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Alerts and API keys
# ---------------------------------------------------------------------------

def create_security_alert(title, description, alert_type, severity="medium", user=None, ip_address=None):
    """Create and return a security alert."""
    return SecurityAlert.objects.create(
        title=title,
        description=description,
        alert_type=alert_type,
        severity=severity,
        user=user,
        ip_address=ip_address,
    )


def generate_api_key(user, name, permissions=None):
    """Create and return an API key for the user."""
    from app.models import APIKey

    return APIKey.objects.create(user=user, name=name, permissions=permissions or [])


# ---------------------------------------------------------------------------
# IP access control
# ---------------------------------------------------------------------------

def is_ip_allowed(ip_address):
    """Check an IP against the blacklist and (if enabled) the whitelist.

    Returns (allowed, message). Expired blacklist entries are ignored.
    """
    policy = SecuritySettings.get_settings()

    if getattr(policy, "enable_ip_blacklist", True) and ip_address:
        blocked = IPBlacklist.objects.filter(ip_address=ip_address, is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now())
        )
        if blocked.exists():
            return False, "IP address is blocked."

    if policy.enable_ip_whitelist:
        from app.models import IPWhitelist

        if not ip_address or not IPWhitelist.objects.filter(
            ip_address=ip_address, is_active=True
        ).exists():
            return False, "IP address is not on the allow list."

    return True, "IP address allowed."
