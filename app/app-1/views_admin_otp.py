"""
Admin OTP Management — SECURE VERSION
Only superuser can access
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
from urllib.parse import quote

from .models import CustomerOTP, OTPAuditLog, CompanyInfo


def superuser_required(view_func):
    """Decorator: Only superuser can access"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, '❌ Login required')
            return redirect('login')
        if not request.user.is_superuser:
            messages.error(request, '❌ Access denied! Only superuser.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_client_ip(request):
    """Get client IP"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip or None


@superuser_required
def otp_management(request):
    """Admin panel: List all OTPs (superuser only)"""
    
    status_filter = request.GET.get('status', 'active')
    purpose_filter = request.GET.get('purpose', '')
    
    otps = CustomerOTP.objects.all()
    
    if status_filter == 'active':
        otps = otps.filter(is_used=False, expires_at__gt=now())
    elif status_filter == 'used':
        otps = otps.filter(is_used=True)
    elif status_filter == 'expired':
        otps = otps.filter(is_used=False, expires_at__lte=now())
    
    if purpose_filter:
        otps = otps.filter(purpose=purpose_filter)
    
    otps = otps.order_by('-created_at')[:100]
    
    stats = {
        'total': CustomerOTP.objects.count(),
        'active': CustomerOTP.objects.filter(is_used=False, expires_at__gt=now()).count(),
        'used': CustomerOTP.objects.filter(is_used=True).count(),
        'expired': CustomerOTP.objects.filter(is_used=False, expires_at__lte=now()).count(),
    }
    
    audit_logs = OTPAuditLog.objects.all()[:20]
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'ERP System',
        'otps': otps,
        'stats': stats,
        'audit_logs': audit_logs,
        'status_filter': status_filter,
        'purpose_filter': purpose_filter,
    }
    return render(request, 'admin/otp_management.html', context)


@superuser_required
def otp_detail(request, pk):
    """View OTP detail (superuser only)"""
    
    otp = get_object_or_404(CustomerOTP, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'mark_sent':
            otp.is_sent_to_customer = True
            otp.sent_by = request.user
            otp.sent_at = now()
            otp.send_method = request.POST.get('send_method', 'manual')
            otp.save()
            
            OTPAuditLog.objects.create(
                phone=otp.phone,
                action='sent_to_customer',
                success=True,
                notes=f"Method: {otp.send_method}, By: {request.user.username}"
            )
            
            messages.success(request, '✅ Marked as sent to customer!')
            return redirect('otp_detail', pk=pk)
        
        elif action == 'delete':
            phone = otp.phone
            otp.delete()
            
            OTPAuditLog.objects.create(
                phone=phone,
                action='locked',
                success=True,
                notes=f"Deleted by {request.user.username}"
            )
            
            messages.success(request, '🗑️ OTP deleted!')
            return redirect('otp_management')
    
    # WhatsApp link
    clean_phone = otp.phone.replace('+', '').replace(' ', '').replace('-', '')
    
    message = (
        f"🔐 *Verification Code*\n\n"
        f"Aapka OTP code hai:\n\n"
        f"*{otp.otp_code}*\n\n"
        f"⏱️ Yeh 5 minute mein expire ho jayega.\n"
        f"Kisi ke saath share na karein."
    )
    
    whatsapp_link = f"https://wa.me/{clean_phone}?text={quote(message)}"
    sms_link = f"sms:{otp.phone}?body={quote(message)}"
    
    phone_logs = OTPAuditLog.objects.filter(phone=otp.phone)[:10]
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'ERP System',
        'otp': otp,
        'whatsapp_link': whatsapp_link,
        'sms_link': sms_link,
        'phone_logs': phone_logs,
    }
    return render(request, 'admin/otp_detail.html', context)


@superuser_required
def otp_regenerate(request, pk):
    """Regenerate OTP (superuser only)"""
    
    old_otp = get_object_or_404(CustomerOTP, pk=pk)
    
    if request.method == 'POST':
        try:
            new_otp = CustomerOTP.generate_otp(
                phone=old_otp.phone,
                purpose=old_otp.purpose,
                customer_name=old_otp.customer_name or '',
                customer_email=old_otp.customer_email or '',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(
                request, 
                f'✅ New OTP: {new_otp.otp_code} for {new_otp.phone}'
            )
            return redirect('otp_detail', pk=new_otp.pk)
        except Exception as e:
            messages.error(request, f'❌ {str(e)}')
    
    return redirect('otp_detail', pk=pk)


@superuser_required
def otp_quick_generate(request):
    """Quick generate (superuser only)"""
    
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        name = request.POST.get('name', '').strip()
        
        if not phone:
            return JsonResponse({'success': False, 'message': 'Phone required'})
        
        phone = phone.replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            if phone.startswith('0'):
                phone = '+92' + phone[1:]
            elif phone.startswith('92'):
                phone = '+' + phone
            else:
                phone = '+92' + phone
        
        try:
            otp = CustomerOTP.generate_otp(
                phone=phone,
                purpose='register',
                customer_name=name,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return JsonResponse({
                'success': True,
                'otp_code': otp.otp_code,
                'phone': otp.phone,
                'message': 'OTP generated'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'success': False, 'message': 'POST required'})