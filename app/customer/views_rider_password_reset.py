"""Rider ka forgot password: phone -> code -> naya password.

Code do raston se milta hai:
  1. WhatsApp par automatic (agar WHATSAPP_* settings hon) ya email (agar rider ke account par ho).
  2. Warna admin ko notification jati hai aur Riders page par code nazar aata hai;
     admin rider ko phone par code bata deta hai.
Jawab hamesha ek jaisa hota hai (phone registered ho ya na ho). Engine: app/utils/password_reset.py
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..models import CompanyInfo
from ..utils import password_reset as pr
from ..utils import whatsapp_otp
from ..utils.security import get_client_ip
from .views_customer_auth import is_valid_phone, normalize_phone

SESSION_KEY = 'rfp_phone'
TOO_MANY_MSG = '❌ Bohat zyada koshishen. Thori der baad dobara try karein.'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'Shop'


@require_http_methods(['GET', 'POST'])
def rider_forgot_password(request):
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        if not phone_raw or not is_valid_phone(phone_raw):
            messages.error(request, '❌ Sahi phone number likhein.')
            return redirect('rider_forgot_password')
        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''

        if pr.too_many('rfp_req_ip', ip, pr.REQ_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('rider_forgot_password')
        pr.bump(f'rfp_req_ip:{ip}')

        account = pr.find_account(phone, pr.RIDER_KINDS)
        if account:
            pr.request_code(account, ip, request.META.get('HTTP_USER_AGENT', ''))

        request.session[SESSION_KEY] = phone
        request.session.modified = True
        if whatsapp_otp.is_configured():
            messages.info(request, 'Agar yeh phone registered rider ka hai to 6-digit code WhatsApp par '
                                   'bhej diya gaya hai (5 minute valid).')
        else:
            messages.info(request, 'Agar yeh phone registered rider ka hai to manager ko khabar de di gayi hai. '
                                   'Manager se 6-digit code le kar yahan likhein (5 minute valid).')
        return redirect('rider_reset_password')

    return render(request, 'customer_portal/rider/forgot_password.html', {
        'company_name': _company_name(), 'whatsapp': whatsapp_otp.is_configured(),
    })


@require_http_methods(['GET', 'POST'])
def rider_reset_password(request):
    phone = request.session.get(SESSION_KEY)
    if not phone:
        messages.info(request, 'Pehle apna phone number likhein.')
        return redirect('rider_forgot_password')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()[:6]
        ip = get_client_ip(request) or ''
        if pr.too_many('rfp_ver_ip', ip, pr.VERIFY_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('rider_reset_password')
        pr.bump(f'rfp_ver_ip:{ip}')

        account = pr.find_account(phone, pr.RIDER_KINDS)
        if not account:
            messages.error(request, '❌ Code ghalat ya expire ho chuka hai.')
            return redirect('rider_reset_password')

        ok, msg = pr.complete_reset(account, code, request.POST.get('password', ''),
                                    request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, '✅ ' + msg)
            return redirect(account.login_url_name)
        messages.error(request, '❌ ' + msg)
        return redirect('rider_reset_password')

    masked = phone[:5] + '*****' + phone[-2:]
    return render(request, 'customer_portal/rider/reset_password.html', {
        'company_name': _company_name(), 'masked_phone': masked, 'whatsapp': whatsapp_otp.is_configured(),
    })
