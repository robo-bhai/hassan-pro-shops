"""Password reset (customer + vendor): phone likho -> code (WhatsApp/email) -> code + naya password.

- Code CustomerOTP (purpose='forgot_password') se jata hai: 5 minute, 5 ghalat koshishon par 30 min lock.
- Jawab hamesha ek jaisa hota hai (phone registered ho ya na ho) taake koi phone number check na kar sake.
- Naya password portal policy (app/utils/password_policy.py) se guzarta hai.
- Rider ka apna raasta hai: views_rider_password_reset.py. Admin/staff ka: app/security/views_admin_reset.py
Engine: app/utils/password_reset.py
"""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..models import CompanyInfo
from ..utils import password_reset as pr
from ..utils.security import get_client_ip
from .views_customer_auth import is_valid_phone, normalize_phone

logger = logging.getLogger(__name__)

SESSION_KEY = 'fp_phone'
GENERIC_MSG = ('Agar yeh phone registered hai to 6-digit code bhej diya gaya hai (WhatsApp ya email par, '
               '5 minute valid). Spam folder bhi dekh lein.')
TOO_MANY_MSG = '❌ Bohat zyada koshishen. Thori der baad dobara try karein.'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'Shop'


@require_http_methods(['GET', 'POST'])
def forgot_password(request):
    """Step 1: phone number likho, code WhatsApp/email par jata hai."""
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        if not phone_raw or not is_valid_phone(phone_raw):
            messages.error(request, '❌ Sahi phone number likhein (03XXXXXXXXX)')
            return redirect('customer_forgot_password')
        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''

        if pr.too_many('fp_req_ip', ip, pr.REQ_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('customer_forgot_password')
        pr.bump(f'fp_req_ip:{ip}')

        account = pr.find_account(phone, pr.SHOP_KINDS)
        if account:
            # Email/WhatsApp na ho to bhi code banta hai: admin ko OTP Management mein nazar aata hai
            pr.request_code(account, ip, request.META.get('HTTP_USER_AGENT', ''))

        request.session[SESSION_KEY] = phone
        request.session.modified = True
        messages.info(request, GENERIC_MSG)
        return redirect('customer_reset_password')

    return render(request, 'customer_portal/auth/forgot_password.html', {
        'page_title': 'Forgot Password', 'company_name': _company_name(),
    })


@require_http_methods(['GET', 'POST'])
def reset_password(request):
    """Step 2: 6-digit code + naya password."""
    phone = request.session.get(SESSION_KEY)
    if not phone:
        messages.info(request, 'Pehle apna phone number likhein.')
        return redirect('customer_forgot_password')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()[:6]
        ip = get_client_ip(request) or ''
        if pr.too_many('fp_ver_ip', ip, pr.VERIFY_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('customer_reset_password')
        pr.bump(f'fp_ver_ip:{ip}')

        account = pr.find_account(phone, pr.SHOP_KINDS)
        if not account:
            messages.error(request, '❌ Code ghalat ya expire ho chuka hai.')
            return redirect('customer_reset_password')

        ok, msg = pr.complete_reset(account, code, request.POST.get('password', ''),
                                    request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, '✅ ' + msg)
            return redirect(account.login_url_name)
        messages.error(request, '❌ ' + msg)
        return redirect('customer_reset_password')

    masked = phone[:5] + '*****' + phone[-2:]
    return render(request, 'customer_portal/auth/reset_password.html', {
        'page_title': 'Reset Password', 'company_name': _company_name(), 'masked_phone': masked,
    })
