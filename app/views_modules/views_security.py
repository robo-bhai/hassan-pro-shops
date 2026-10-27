from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import logout
from django.core.paginator import Paginator
from django.utils.timezone import now
from app.models import (
    CompanyInfo, SecuritySettings, User2FASettings, OTPVerification,
    LoginAttempt, IPWhitelist, IPBlacklist, AccessLog, SecurityAlert,
    APIKey, PasswordHistory, SessionLog
)
from app.utils.security import (
    validate_password_strength, check_password_history, save_password_history,
    generate_otp, verify_otp, send_otp_email, create_security_alert,
    generate_api_key, track_login_attempt
)
from django.contrib.auth.models import User
from django.db.models import Q


@login_required
def security_dashboard(request):
    """Security dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    settings = SecuritySettings.get_settings()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'settings': settings,
        'total_alerts': SecurityAlert.objects.count(),
        'unresolved_alerts': SecurityAlert.objects.filter(is_resolved=False).count(),
        'critical_alerts': SecurityAlert.objects.filter(severity='critical', is_resolved=False).count(),
        'total_logins': LoginAttempt.objects.count(),
        'failed_logins': LoginAttempt.objects.filter(is_success=False).count(),
        'active_sessions': SessionLog.objects.filter(is_active=True).count(),
        'blocked_ips': IPBlacklist.objects.filter(is_active=True).count(),
        'recent_alerts': SecurityAlert.objects.order_by('-created_at')[:10],
        'recent_logins': LoginAttempt.objects.order_by('-attempted_at')[:10],
    }
    return render(request, 'security/dashboard.html', context)


@login_required
def security_settings_view(request):
    """View and update security settings"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    settings = SecuritySettings.get_settings()
    
    if request.method == 'POST':
        settings.enable_2fa = request.POST.get('enable_2fa') == 'on'
        settings.max_login_attempts = int(request.POST.get('max_login_attempts', 5))
        settings.lockout_time = int(request.POST.get('lockout_time', 30))
        settings.session_timeout = int(request.POST.get('session_timeout', 60))
        settings.enable_auto_logout = request.POST.get('enable_auto_logout') == 'on'
        
        settings.min_password_length = int(request.POST.get('min_password_length', 8))
        settings.require_uppercase = request.POST.get('require_uppercase') == 'on'
        settings.require_lowercase = request.POST.get('require_lowercase') == 'on'
        settings.require_numbers = request.POST.get('require_numbers') == 'on'
        settings.require_special_chars = request.POST.get('require_special_chars') == 'on'
        settings.password_expiry_days = int(request.POST.get('password_expiry_days', 90))
        settings.prevent_password_reuse = request.POST.get('prevent_password_reuse') == 'on'
        settings.password_history_count = int(request.POST.get('password_history_count', 5))
        
        settings.enable_ip_whitelist = request.POST.get('enable_ip_whitelist') == 'on'
        settings.enable_ip_blacklist = request.POST.get('enable_ip_blacklist') == 'on'
        settings.enable_api_auth = request.POST.get('enable_api_auth') == 'on'
        settings.api_rate_limit = int(request.POST.get('api_rate_limit', 100))
        settings.enable_security_alerts = request.POST.get('enable_security_alerts') == 'on'
        settings.alert_email = request.POST.get('alert_email', '')
        settings.alert_whatsapp = request.POST.get('alert_whatsapp', '')
        
        settings.updated_by = request.user
        settings.save()
        
        messages.success(request, '✅ Security settings updated!')
        return redirect('security_settings')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'settings': settings,
    }
    return render(request, 'security/settings.html', context)


@login_required
def two_factor_setup(request):
    """Setup two-factor authentication"""
    user_settings, created = User2FASettings.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        user_settings.phone_number = request.POST.get('phone_number')
        user_settings.email = request.POST.get('email')
        user_settings.is_2fa_enabled = True
        user_settings.save()
        
        otp = generate_otp(request.user, 'email_verification')
        send_otp_email(request.user, otp.otp_code)
        
        messages.success(request, '✅ 2FA enabled! Please verify.')
        return redirect('two_factor_verify')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'user_settings': user_settings,
    }
    return render(request, 'security/two_factor_setup.html', context)


@login_required
def two_factor_verify(request):
    """Verify two-factor authentication"""
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')
        success, message = verify_otp(request.user, otp_code, 'email_verification')
        
        if success:
            user_settings = User2FASettings.objects.get(user=request.user)
            user_settings.verified_at = now()
            user_settings.save()
            messages.success(request, '✅ 2FA verified!')
            return redirect('security_dashboard')
        else:
            messages.error(request, f'❌ {message}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'security/two_factor_verify.html', context)


@login_required
def ip_whitelist_view(request):
    """View and manage IP whitelist"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    whitelist = IPWhitelist.objects.all()
    
    if request.method == 'POST':
        ip = request.POST.get('ip_address')
        description = request.POST.get('description')
        IPWhitelist.objects.create(ip_address=ip, description=description, created_by=request.user)
        messages.success(request, f'✅ IP {ip} whitelisted!')
        return redirect('ip_whitelist')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'whitelist': whitelist,
    }
    return render(request, 'security/ip_whitelist.html', context)


@login_required
def ip_blacklist_view(request):
    """View and manage IP blacklist"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    blacklist = IPBlacklist.objects.all()
    
    if request.method == 'POST':
        ip = request.POST.get('ip_address')
        reason = request.POST.get('reason')
        IPBlacklist.objects.create(ip_address=ip, reason=reason, blocked_by=request.user)
        
        create_security_alert(
            title="IP Blacklisted",
            description=f"IP {ip} was blacklisted",
            alert_type='ip_blocked',
            severity='medium',
            user=request.user,
            ip_address=ip
        )
        
        messages.success(request, f'✅ IP {ip} blacklisted!')
        return redirect('ip_blacklist')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'blacklist': blacklist,
    }
    return render(request, 'security/ip_blacklist.html', context)


@login_required
def security_logs(request):
    """View security logs"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    logs = AccessLog.objects.select_related('user').order_by('-created_at')
    
    user_filter = request.GET.get('user', '')
    if user_filter:
        logs = logs.filter(user__username=user_filter)
    
    module_filter = request.GET.get('module', '')
    if module_filter:
        logs = logs.filter(module=module_filter)
    
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'user_filter': user_filter,
        'module_filter': module_filter,
        'users': User.objects.all(),
        'modules': AccessLog.objects.values_list('module', flat=True).distinct(),
    }
    return render(request, 'security/logs.html', context)


@login_required
def security_alerts_view(request):
    """View security alerts"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    alerts = SecurityAlert.objects.all()
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    paginator = Paginator(alerts, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    if request.method == 'POST':
        alert_id = request.POST.get('alert_id')
        try:
            alert = SecurityAlert.objects.get(id=alert_id)
            alert.is_resolved = True
            alert.resolved_at = now()
            alert.resolved_by = request.user
            alert.save()
            messages.success(request, f'✅ Alert resolved!')
        except SecurityAlert.DoesNotExist:
            messages.error(request, 'Alert not found!')
        return redirect('security_alerts')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'severity': severity,
        'severity_choices': SecurityAlert.SEVERITY_CHOICES,
    }
    return render(request, 'security/alerts.html', context)


@login_required
def api_key_management(request):
    """Manage API keys"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    api_keys = APIKey.objects.select_related('user').all()
    
    if request.method == 'POST':
        user_id = request.POST.get('user')
        name = request.POST.get('name')
        user = User.objects.get(id=user_id)
        api_key = generate_api_key(user, name)
        messages.success(request, f'✅ API Key created! Key: {api_key.key}')
        return redirect('api_key_management')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'api_keys': api_keys,
        'users': User.objects.filter(is_active=True),
    }
    return render(request, 'security/api_keys.html', context)


@login_required
def change_password_security(request):
    """Change password with security validation"""
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not request.user.check_password(current_password):
            messages.error(request, '❌ Current password is incorrect!')
            return redirect('change_password_security')
        
        if new_password != confirm_password:
            messages.error(request, '❌ Passwords do not match!')
            return redirect('change_password_security')
        
        errors = validate_password_strength(new_password)
        if errors:
            for error in errors:
                messages.error(request, f'❌ {error}')
            return redirect('change_password_security')
        
        if not check_password_history(request.user, new_password):
            messages.error(request, '❌ Password was used before!')
            return redirect('change_password_security')
        
        request.user.set_password(new_password)
        request.user.save()
        save_password_history(request.user, new_password)
        
        create_security_alert(
            title="Password Changed",
            description=f"User {request.user.username} changed password",
            alert_type='password_change',
            severity='low',
            user=request.user
        )
        
        messages.success(request, '✅ Password changed successfully!')
        return redirect('security_dashboard')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'security/change_password.html', context)