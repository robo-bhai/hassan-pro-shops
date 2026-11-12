"""Password reset ka common engine: customer, vendor, rider.

Views (forgot/reset pages) sirf form dikhate hain; asal kaam yahan hota hai:
    find_account()   -> phone se account dhoondna
    request_code()   -> code banana aur bhejna
    complete_reset() -> code verify karke naya password set karna

Har kind ki apni OTP 'purpose' hai, is liye ek hi phone customer aur rider dono ho to codes alag rehte hain.
Admin/staff ka apna alag raasta hai: app/security/admin_reset.py
"""
import logging
from dataclasses import dataclass

from django.core.cache import cache

from .password_policy import password_errors

logger = logging.getLogger(__name__)

HOUR = 3600
REQ_PER_IP = 10          # ek IP se ghante mein code mangwane ki had
VERIFY_PER_IP = 20       # ek IP se ghante mein code/password ki koshishen
PER_PHONE_VERIFY = 15    # ek phone par ghante mein koshishen (IP badalne se bhi na tootay)

# kind -> (OTP purpose, login url name)
KINDS = {
    'customer': ('forgot_password', 'customer_login'),
    'vendor': ('forgot_password', 'vendor_login'),
    'rider': ('rider_reset', 'rider_login'),
}
SHOP_KINDS = ('customer', 'vendor')   # forgot_password page in dono ko check karta hai
RIDER_KINDS = ('rider',)              # rider ka apna page hai


@dataclass
class Account:
    kind: str
    user: object
    name: str
    email: str
    phone: str

    @property
    def purpose(self):
        return KINDS[self.kind][0]

    @property
    def login_url_name(self):
        return KINDS[self.kind][1]


def bump(key, seconds=HOUR):
    """Counter ko atomically barhata hai (cache.get + set ki tarah do requests mein ginti nahi bhoolta)."""
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key)
    except ValueError:      # key beech mein expire ho gayi
        cache.set(key, 1, seconds)
        return 1


def too_many(prefix, ip, limit):
    return cache.get(f'{prefix}:{ip}', 0) >= limit


def _plain_user(user):
    """Sirf active, non-staff user is raste se reset ho sakta hai."""
    return bool(user and user.is_active and not (user.is_staff or user.is_superuser))


def find_account(phone, kinds=SHOP_KINDS):
    """Phone se Account ya None. Staff/admin accounts is raste se kabhi reset nahi hote."""
    from ..models import Customer, RiderProfile, VendorProfile

    for kind in kinds:
        if kind == 'customer':
            customer = Customer.objects.filter(contact_number=phone).first()
            if customer and hasattr(customer, 'portal_profile'):
                user = customer.portal_profile.user
                if _plain_user(user):
                    email = (customer.email or user.email or '').strip()
                    return Account('customer', user, customer.name, email, phone)
        elif kind == 'vendor':
            vp = (VendorProfile.objects.select_related('user', 'vendor')
                  .filter(vendor__contact_number=phone).first())
            if vp and _plain_user(vp.user):
                email = (vp.user.email or getattr(vp.vendor, 'email', '') or '').strip()
                return Account('vendor', vp.user, vp.business_name, email, phone)
        elif kind == 'rider':
            rp = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=True).first()
            if rp and _plain_user(rp.user):
                return Account('rider', rp.user, rp.name, (rp.user.email or '').strip(), phone)
    return None


def request_code(account, ip='', user_agent=''):
    """Code banata aur bhejta hai. True = code ban gaya; False = nahi (rate limit ya koi masla)."""
    from ..models import CustomerOTP

    try:
        otp = CustomerOTP.generate_otp(
            phone=account.phone, purpose=account.purpose, customer_name=account.name,
            customer_email=account.email, ip_address=ip or None, user_agent=(user_agent or '')[:500],
        )
    except Exception as exc:    # 15 minute mein 3 se zyada requests, ya email ka masla
        logger.warning('reset code not sent (%s %s): %s', account.kind, account.phone, exc)
        return False
    _deliver_extra(account, otp)
    return True


def can_deliver(account):
    """Is account tak code pohanch sakta hai? (email ho, ya WhatsApp configured ho)"""
    from . import whatsapp_otp
    return bool(account.email) or whatsapp_otp.is_configured()


def _deliver_extra(account, otp):
    """Email ke ilawa WhatsApp par bhi code bhejta hai (agar configured ho)."""
    from django.utils.timezone import now
    from . import whatsapp_otp

    if not whatsapp_otp.is_configured():
        return
    ok, err = whatsapp_otp.send_otp(account.phone, otp.otp_code)
    if not ok:
        logger.warning('WhatsApp reset code not sent (%s %s): %s', account.kind, account.phone, err)
        return
    if not otp.is_sent_to_customer:     # email nahi gayi thi to WhatsApp ko hi record karo
        otp.is_sent_to_customer = True
        otp.sent_at = now()
        otp.send_method = 'whatsapp'
        otp.save(update_fields=['is_sent_to_customer', 'sent_at', 'send_method'])


def _audit(account, action, success, ip, note):
    try:
        from ..models import OTPAuditLog
        OTPAuditLog.objects.create(phone=account.phone, action=action, ip_address=ip or None,
                                   success=success, notes=f'password reset ({account.kind}): {note}')
    except Exception:
        logger.exception('reset audit log failed')


def _notify_changed(account, ip):
    """Password badalne ke baad khabar: 'agar aap ne nahi badla to rabta karein'."""
    from . import whatsapp_otp
    text = ('Aap ke account ka password abhi badla gaya hai. Agar yeh aap ne nahi kiya to foran '
            'humse rabta karein.')
    if account.email:
        try:
            from .email_helper import send_notification_email
            send_notification_email(account.email, 'Aap ka password badal gaya', f'<p>{text}</p>', body_text=text)
        except Exception:
            logger.exception('reset notice email failed')
    try:
        whatsapp_otp.send_notice(account.phone)     # sirf agar WHATSAPP_NOTICE_TEMPLATE set ho
    except Exception:
        logger.exception('reset notice whatsapp failed')


def complete_reset(account, code, password, confirm, ip=''):
    """Code verify karke password set. Return (ok, message)."""
    from ..models import CustomerOTP

    if bump(f'pr_ver_phone:{account.kind}:{account.phone}') > PER_PHONE_VERIFY:
        _audit(account, 'locked', False, ip, 'too many attempts on this phone')
        return False, 'Bohat zyada koshishen. Thori der baad dobara try karein.'

    errors = password_errors(password, (account.name, account.phone, account.user.username, account.email))
    if not (code.isdigit() and len(code) == 6):
        return False, '6-digit code likhein.'
    if password != confirm:
        return False, 'Dono password aik jaise likhein.'
    if errors:
        return False, errors[0]

    ok, _otp, msg = CustomerOTP.find_and_verify(account.phone, code, purpose=account.purpose)
    if not ok:
        _audit(account, 'verify_fail', False, ip, msg)
        return False, msg

    account.user.set_password(password)     # purane sessions khud invalid ho jate hain
    account.user.save(update_fields=['password'])
    CustomerOTP.objects.filter(phone=account.phone, purpose=account.purpose, is_used=False).delete()
    cache.delete(f'pr_ver_phone:{account.kind}:{account.phone}')
    _audit(account, 'verify_success', True, ip, 'password changed')
    _notify_changed(account, ip)
    return True, 'Password badal gaya. Ab naye password se login karein.'
