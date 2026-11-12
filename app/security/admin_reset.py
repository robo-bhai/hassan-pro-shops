"""Admin / staff ka forgot password.

Customer/vendor se sakht qaide (admin account sab se nazuk hai):
  1. Username likhein -> account ke email par 6-digit code (10 minute valid).
  2. Naya password security policy (SecuritySettings) + Django validators + password history se guzarta hai.
  3. Reset ke baad account ko email jati hai aur SecurityAlert banta hai.
Code cache mein sirf HMAC hash ke taur par rehta hai (database mein kuch nahi, migration nahi chahiye).
Jawab hamesha ek jaisa hota hai (username maujood ho ya na ho).
URL /login/... ke neeche hain taake login-gate / 2FA middleware inhein rokein nahi.

Note: is project mein authenticator (TOTP) nahi hai (2FA email code se hai), is liye guide ka TOTP block shamil nahi.
"""
import hashlib
import hmac
import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

CODE_TTL = 10 * 60        # 10 minute
MAX_CODE_ATTEMPTS = 5     # ek code par ghalat koshishen
REQ_PER_USER = 3          # 15 minute mein code mangwane ki had (har account)
REQ_PER_IP = 10           # ghante mein (har IP)
VERIFY_PER_IP = 20        # ghante mein (har IP)
HOUR = 3600


def bump(key, seconds=HOUR):
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, seconds)
        return 1


def too_many(key, limit):
    return cache.get(key, 0) >= limit


def account_email(user):
    email = (user.email or '').strip()
    if email:
        return email
    try:
        s = user.security_settings          # User2FASettings (related_name)
        return (s.email or '').strip()
    except Exception:
        return ''


def find_staff(username):
    """Active staff/superuser jis ka email ho, warna None."""
    username = (username or '').strip()[:150]
    if not username:
        return None
    User = get_user_model()
    user = User.objects.filter(**{f'{User.USERNAME_FIELD}__iexact': username}).first()
    if not user or not user.is_active or not (user.is_staff or user.is_superuser):
        return None
    if not account_email(user):
        return None
    return user


def mask_email(email):
    name, _, domain = email.partition('@')
    return (name[:2] + '***@' + domain) if domain else '***'


def _hash(user, code):
    key = f'{settings.SECRET_KEY}:{user.pk}'.encode()
    return hmac.new(key, str(code).encode(), hashlib.sha256).hexdigest()


def send_code(user, ip=''):
    """Code banata aur email karta hai. True = bhej diya."""
    from app.utils.email_helper import send_notification_email

    if bump(f'arp_req_user:{user.pk}', 15 * 60) > REQ_PER_USER:
        return False
    code = str(secrets.randbelow(900000) + 100000)
    cache.set(f'arp_code:{user.pk}', {'h': _hash(user, code), 'n': 0}, CODE_TTL)
    html = (f'<p>Assalam o Alaikum {user.get_username()},</p>'
            f'<p>Aap ke account ka password reset karne ka code:</p>'
            f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{code}</p>'
            f'<p>Yeh code 10 minute tak valid hai. Request IP: {ip or "unknown"}.<br>'
            f'Agar yeh request aap ne nahi ki to isay nazar-andaz karein aur apna password check karein.</p>')
    ok = send_notification_email(account_email(user), 'Password reset code', html,
                                 body_text=f'Your password reset code: {code} (valid 10 minutes).')
    if not ok:
        cache.delete(f'arp_code:{user.pk}')
    return ok


def _code_ok(user, code):
    """Email code check; ghalat koshishen ginta hai. Return (ok, msg)."""
    key = f'arp_code:{user.pk}'
    entry = cache.get(key)
    if not entry:
        return False, 'Code ghalat ya expire ho chuka hai. Naya code mangwayein.'
    entry['n'] += 1
    if entry['n'] > MAX_CODE_ATTEMPTS:
        cache.delete(key)
        return False, 'Bohat ghalat koshishen. Naya code mangwayein.'
    cache.set(key, entry, CODE_TTL)
    if not (code.isdigit() and len(code) == 6) or not hmac.compare_digest(entry['h'], _hash(user, code)):
        return False, 'Code ghalat ya expire ho chuka hai.'
    return True, ''


def password_problems(user, password, confirm):
    from app.utils.security import check_password_history, validate_password_strength

    if password != confirm:
        return ['Dono password aik jaise likhein.']
    errors = list(validate_password_strength(password))
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        errors.extend(exc.messages)
    if not errors and not check_password_history(user, password):
        errors.append('Yeh password pehle istemal ho chuka hai. Naya password chunein.')
    return errors


def complete_reset(user, code, password, confirm, ip=''):
    """Return (ok, message). Sab shartein poori hon tabhi password badalta hai."""
    from app.utils.email_helper import send_notification_email
    from app.utils.security import create_security_alert, save_password_history

    ok, msg = _code_ok(user, code)
    if not ok:
        return False, msg

    errors = password_problems(user, password, confirm)
    if errors:
        return False, errors[0]

    user.set_password(password)      # purane sessions khud khatam ho jate hain
    user.save(update_fields=['password'])
    try:
        save_password_history(user, password)
    except Exception:
        logger.exception('password history save failed')
    cache.delete(f'arp_code:{user.pk}')

    try:
        create_security_alert(
            title=f'Password reset: {user.get_username()}',
            description=f"'{user.get_username()}' ka password forgot-password se reset hua. IP: {ip or 'unknown'}.",
            alert_type='password_change', severity='medium', user=user, ip_address=ip or None)
    except Exception:
        logger.exception('security alert failed')
    try:
        send_notification_email(account_email(user), 'Aap ka password badal gaya',
                                '<p>Aap ke account ka password abhi reset hua hai. '
                                'Agar yeh aap ne nahi kiya to foran admin se rabta karein.</p>')
    except Exception:
        logger.exception('reset notice email failed')
    return True, 'Password badal gaya. Ab naye password se login karein.'
