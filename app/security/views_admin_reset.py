"""Admin / staff forgot-password pages (logic: app/security/admin_reset.py)."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from app.security import admin_reset as ar
from app.utils.security import get_client_ip

SESSION_KEY = 'arp_username'
TOO_MANY = 'Bohat zyada koshishen. Thori der baad dobara try karein.'
GENERIC = ('Agar yeh account maujood hai aur us par email set hai to 6-digit code bhej diya gaya hai '
           '(10 minute valid). Spam folder bhi dekh lein.')


def _ctx(extra=None):
    from app.models import CompanyInfo
    c = CompanyInfo.objects.first()
    d = {'company_name': c.name if c else 'SmartERP'}
    d.update(extra or {})
    return d


@require_http_methods(['GET', 'POST'])
def admin_forgot_password(request):
    if request.method == 'POST':
        ip = get_client_ip(request) or ''
        if ar.too_many(f'arp_req_ip:{ip}', ar.REQ_PER_IP):
            messages.error(request, TOO_MANY)
            return redirect('admin_forgot_password')
        ar.bump(f'arp_req_ip:{ip}')

        username = (request.POST.get('username') or '').strip()[:150]
        user = ar.find_staff(username)
        if user:
            ar.send_code(user, ip)
        request.session[SESSION_KEY] = username
        request.session.modified = True
        messages.info(request, GENERIC)
        return redirect('admin_reset_password')
    return render(request, 'auth/forgot_password.html', _ctx())


@require_http_methods(['GET', 'POST'])
def admin_reset_password(request):
    username = request.session.get(SESSION_KEY)
    if not username:
        messages.info(request, 'Pehle apna username likhein.')
        return redirect('admin_forgot_password')

    if request.method == 'POST':
        ip = get_client_ip(request) or ''
        if ar.too_many(f'arp_ver_ip:{ip}', ar.VERIFY_PER_IP):
            messages.error(request, TOO_MANY)
            return redirect('admin_reset_password')
        ar.bump(f'arp_ver_ip:{ip}')

        user = ar.find_staff(username)
        if not user:
            messages.error(request, 'Code ghalat ya expire ho chuka hai.')
            return redirect('admin_reset_password')
        ok, msg = ar.complete_reset(
            user, (request.POST.get('code') or '').strip()[:6],
            request.POST.get('password', ''), request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, msg)
            return redirect('login')
        messages.error(request, msg)
        return redirect('admin_reset_password')
    return render(request, 'auth/reset_password.html', _ctx({'username': username}))
