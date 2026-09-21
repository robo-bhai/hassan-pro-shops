"""
Customer Authentication Views — SECURE VERSION
================================================
- Customer Registration
- Customer Login (with next URL support)
- Customer Logout
- My Account Dashboard
- OTP Send / Verify
- Late OTP Verify
- Pending OTPs List
- Quick Verify
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.utils.timezone import now
from django.db import transaction
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import timedelta
import re
import json
import uuid

from .models import (
    Customer, CustomerProfile, CustomerOTP, CustomerAddress,
    CustomerOrder, CustomerOrderItem, OrderStatusHistory,
    OTPAuditLog, CompanyInfo, Notification,
    SaleOrder, SaleOrderItem,
)

# ✅ Custom decorator import
from .decorators import customer_login_required


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_client_ip(request):
    """Get client IP address safely"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip or None


def is_valid_phone(phone):
    """Validate Pakistani phone number"""
    pattern = r'^(\+92|92|0)?3\d{9}$'
    return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))


def normalize_phone(phone):
    """Normalize phone to +923XXXXXXXXX format"""
    phone = phone.replace(' ', '').replace('-', '').replace('+', '')
    
    if phone.startswith('92'):
        phone = phone[2:]
    elif phone.startswith('0'):
        phone = phone[1:]
    
    return f'+92{phone}'


def safe_login(request, user):
    """Safe login with explicit backend"""
    login(
        request, 
        user, 
        backend='django.contrib.auth.backends.ModelBackend'
    )

def customer_register(request):
    """Customer registration — DIRECT (no OTP)"""
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        return redirect('my_account')
    
    if request.method == 'POST':
        try:
            # ==========================================
            # Get form data
            # ==========================================
            full_name = request.POST.get('full_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            email = request.POST.get('email', '').strip()
            city = request.POST.get('city', '').strip()          # ✅ NEW
            address = request.POST.get('address', '').strip()    # ✅ NEW
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            # ==========================================
            # Validation
            # ==========================================
            if not full_name or len(full_name) < 3:
                messages.error(request, '❌ Poora naam likhein (kam az kam 3 characters)')
                return redirect('customer_register')
            
            if not phone or not is_valid_phone(phone):
                messages.error(request, '❌ Sahi phone number likhein (03XXXXXXXXX)')
                return redirect('customer_register')
            
            if not city:
                messages.error(request, '❌ Sahi shehar likhein')
                return redirect('customer_register')
            
            if not address or len(address) < 10:
                messages.error(request, '❌ Mukammal pata likhein (kam az kam 10 characters)')
                return redirect('customer_register')
            
            if not password or len(password) < 6:
                messages.error(request, '❌ Password kam az kam 6 characters ka hona chahiye')
                return redirect('customer_register')
            
            if password != confirm_password:
                messages.error(request, '❌ Password match nahi ho rahe')
                return redirect('customer_register')
            
            phone = normalize_phone(phone)
            
            if Customer.objects.filter(contact_number=phone).exists():
                messages.error(request, '⚠️ Yeh phone number pehle se registered hai. Login karein.')
                return redirect('customer_login')
            
            if email and email.strip():
                try:
                    validate_email(email)
                    if User.objects.filter(email=email).exists():
                        messages.error(request, '⚠️ Yeh email pehle se registered hai')
                        return redirect('customer_register')
                except ValidationError:
                    messages.error(request, '❌ Sahi email address likhein')
                    return redirect('customer_register')
            
            # ==========================================
            # Create user + customer + profile
            # ==========================================
            with transaction.atomic():
                username = phone.replace('+', '').replace(' ', '')
                counter = 1
                base_username = username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                name_parts = full_name.split()
                
                user = User.objects.create_user(
                    username=username,
                    email=email or '',
                    password=password,
                    first_name=name_parts[0] if name_parts else '',
                    last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                )
                
                # ✅ Full address with city
                full_address = f"{address}, {city}"
                
                customer = Customer.objects.create(
                    name=full_name,
                    contact_number=phone,
                    email=email or None,
                    address=full_address,           # ✅ Address save
                    customer_code=f'CUS-{user.id:05d}',
                )
                
                profile = CustomerProfile.objects.create(
                    customer=customer,
                    user=user,
                    phone_verified=False,
                    email_verified=bool(email),
                    last_login_at=now()
                )
                
                # ✅ Customer ki default address bhi bana dein
                CustomerAddress.objects.create(
                    customer=customer,
                    address_type='home',
                    full_name=full_name,
                    phone=phone,
                    address_line_1=address,
                    city=city,
                    is_default=True,
                )
                
                safe_login(request, user)
                request.session.save()
                
                try:
                    Notification.objects.create(
                        user=user,
                        title="🎉 Welcome!",
                        message=f"Assalam-o-Alaikum {full_name}! Aapka account ban gaya hai.",
                        notification_type='success',
                        category='system',
                    )
                except Exception:
                    pass
            
            messages.success(request, f'🎉 Welcome {customer.name}! Aapka account ban gaya hai.')
            return redirect('my_account')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('customer_register')
    
    company = CompanyInfo.objects.first()
    context = {
        'company_name': company.name if company else 'Shop',
        'page_title': 'Create Account',
    }
    return render(request, 'customer_portal/auth/register.html', context)


# ============================================
# 2. CUSTOMER LOGIN — Password Only (with next support)
# ============================================

def customer_login(request):
    """Customer login — Password only (with next URL support)"""
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        # Agar already logged in hai aur next hai to wahan bhejo
        next_url = request.GET.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('my_account')
    
    if request.method == 'POST':
        try:
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '')
            next_url = request.POST.get('next') or request.GET.get('next', '')
            
            if not phone or not password:
                messages.error(request, '❌ Phone aur password dono likhein')
                return redirect(f"{reverse('customer_login')}?next={next_url}" if next_url else 'customer_login')
            
            phone = normalize_phone(phone)
            
            customer = Customer.objects.filter(contact_number=phone).first()
            if not customer or not hasattr(customer, 'portal_profile'):
                messages.error(request, '❌ Ghalat phone number ya password')
                return redirect(f"{reverse('customer_login')}?next={next_url}" if next_url else 'customer_login')
            
            user = customer.portal_profile.user
            if not user:
                messages.error(request, '❌ Account setup incomplete')
                return redirect('customer_login')
            
            # Check admin account
            if user.is_superuser or user.is_staff:
                messages.error(request, '❌ Yeh admin account hai. Admin panel se login karein.')
                return redirect('login')
            
            authenticated_user = authenticate(request, username=user.username, password=password)
            
            if authenticated_user:
                if not hasattr(authenticated_user, 'backend'):
                    authenticated_user.backend = 'django.contrib.auth.backends.ModelBackend'
                
                safe_login(request, authenticated_user)
                request.session.save()
                
                customer.portal_profile.last_login_at = now()
                customer.portal_profile.save()
                
                messages.success(request, f'🎉 Welcome back, {customer.name}!')
                
                # ✅ FIXED: next URL support
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                
                return redirect('my_account')
            else:
                messages.error(request, '❌ Ghalat password')
                return redirect(f"{reverse('customer_login')}?next={next_url}" if next_url else 'customer_login')
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('customer_login')
    
    context = {
        'page_title': 'Login',
        'next': request.GET.get('next', ''),
    }
    return render(request, 'customer_portal/auth/login.html', context)


# ============================================
# 3. CUSTOMER LOGOUT
# ============================================

def customer_logout(request):
    """Customer logout"""
    logout(request)
    messages.success(request, '👋 Aap logout ho gaye hain')
    return redirect('shop_home')


# ============================================
# 4. MY ACCOUNT DASHBOARD — ✅ CUSTOMER LOGIN REQUIRED
# ============================================

@customer_login_required
def my_account(request):
    """Customer dashboard"""
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, '❌ Yeh page sirf customers ke liye hai')
        return redirect('shop_home')
    
    profile = request.user.customer_profile
    customer = profile.customer
    
    from django.db.models import Sum
    
    orders = SaleOrder.objects.filter(customer=customer).order_by('-order_date')
    
    stats = {
        'total_orders': orders.count(),
        'pending_orders': orders.filter(
            status__in=['pending', 'confirmed', 'processing', 'ready', 'partially_delivered']
        ).count(),
        'delivered_orders': orders.filter(status='delivered').count(),
        'cancelled_orders': orders.filter(status='cancelled').count(),
        'total_spent': SaleOrderItem.objects.filter(
            order__customer=customer,
            order__status='delivered'
        ).aggregate(total=Sum('total_amt'))['total'] or 0,
    }
    
    recent_orders = orders[:5]
    
    for order in recent_orders:
        order.calculated_total = sum(item.total_amt for item in order.items.all())
    
    default_address = customer.addresses.filter(is_default=True).first()
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'profile': profile,
        'customer': customer,
        'stats': stats,
        'recent_orders': recent_orders,
        'default_address': default_address,
        'page_title': 'My Account',
    }
    return render(request, 'customer_portal/account/dashboard.html', context)


# ============================================
# 5. SEND ORDER OTP — ✅ CUSTOMER LOGIN REQUIRED
# ============================================

@customer_login_required
def send_order_otp(request):
    """Send OTP for order verification"""
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Login required'})
    
    profile = request.user.customer_profile
    customer = profile.customer
    phone = customer.contact_number
    
    if not phone:
        return JsonResponse({'success': False, 'message': 'Phone number not found'})
    
    if profile.should_skip_order_otp():
        return JsonResponse({
            'success': True,
            'skip_otp': True,
            'message': 'Trusted customer - OTP not required'
        })
    
    try:
        order_token = str(uuid.uuid4()).replace('-', '')[:8].upper()
        
        while CustomerOTP.objects.filter(order_token=order_token, is_used=False).exists():
            order_token = str(uuid.uuid4()).replace('-', '')[:8].upper()
        
        otp = CustomerOTP.generate_otp(
            phone=phone,
            purpose='order',
            customer_name=customer.name,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            order_token=order_token,
        )
        
        request.session['order_otp_phone'] = phone
        request.session['order_otp_id'] = otp.id
        request.session['order_token'] = order_token
        request.session.modified = True
        
        masked = phone[-4:].rjust(len(phone), '*')
        
        return JsonResponse({
            'success': True,
            'skip_otp': False,
            'message': f'OTP sent to {masked}',
            'otp_id': otp.id,
            'order_token': order_token,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 6. VERIFY ORDER OTP — ✅ CUSTOMER LOGIN REQUIRED
# ============================================

@customer_login_required
def verify_order_otp(request):
    """Verify OTP for order (normal flow)"""
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Login required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        data = json.loads(request.body) if request.body else {}
        otp_code = data.get('otp_code', '').strip()
        
        if not otp_code or len(otp_code) != 6:
            return JsonResponse({'success': False, 'message': 'Please enter 6-digit OTP'})
        
        phone = request.session.get('order_otp_phone')
        if not phone:
            return JsonResponse({'success': False, 'message': 'Session expired. Please place order again.'})
        
        success, otp_obj, message = CustomerOTP.find_and_verify(
            phone=phone,
            code=otp_code,
            purpose='order'
        )
        
        if not success:
            return JsonResponse({'success': False, 'message': message})
        
        # ✅ SESSION FLAGS SET KARO
        request.session['order_verified'] = True
        request.session['order_verified_at'] = now().isoformat()
        request.session['order_otp_phone'] = phone
        request.session.modified = True
        request.session.save()
        
        profile = request.user.customer_profile
        profile.phone_verified = True
        profile.save(update_fields=['phone_verified'])
        
        return JsonResponse({
            'success': True,
            'message': '✅ Order verified successfully!',
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 7. VERIFY OTP LATER
# ============================================

def verify_otp_later(request):
    """Late OTP Verification with Pre-fill"""
    prefill_phone = request.GET.get('phone', '').strip()
    prefill_token = request.GET.get('token', '').strip().upper()
    
    if request.method == 'POST':
        try:
            phone = request.POST.get('phone', '').strip()
            order_token = request.POST.get('order_token', '').strip().upper()
            otp_code = request.POST.get('otp_code', '').strip()
            
            if not all([phone, order_token, otp_code]):
                messages.error(request, '❌ Please fill all fields')
                return redirect(f"/shop/verify-otp-later/?phone={prefill_phone}&token={prefill_token}")
            
            if len(otp_code) != 6:
                messages.error(request, '❌ Please enter 6-digit OTP')
                return redirect(f"/shop/verify-otp-later/?phone={prefill_phone}&token={prefill_token}")
            
            phone = normalize_phone(phone)
            
            otp = CustomerOTP.find_by_token(order_token, phone)
            
            if not otp:
                messages.error(request, '❌ Invalid Order Token or Phone Number')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
            
            if otp.is_locked():
                remaining = int((otp.locked_until - now()).total_seconds() / 60)
                messages.error(request, f'❌ Too many attempts. Try again in {remaining} minutes.')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
            
            if otp.is_expired():
                messages.error(request, '❌ OTP expired. Please place a new order.')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
            
            if not otp.verify(otp_code):
                otp.increment_attempts()
                attempts_left = otp.max_attempts - otp.attempts
                if attempts_left > 0:
                    messages.error(request, f'❌ Invalid OTP. {attempts_left} attempts remaining.')
                else:
                    messages.error(request, '❌ Too many failed attempts. Try again after 30 minutes.')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
            
            otp.mark_used()
            
            customer = Customer.objects.filter(contact_number=phone).first()
            
            if customer and customer.portal_profile.user:
                
                # STEP 1: Session flags before login
                request.session['order_verified'] = True
                request.session['order_verified_at'] = now().isoformat()
                request.session['order_token'] = order_token
                request.session.modified = True
                
                # STEP 2: Login
                safe_login(request, customer.portal_profile.user)
                
                # STEP 3: Session flags after login
                request.session['order_verified'] = True
                request.session['order_verified_at'] = now().isoformat()
                request.session['order_token'] = order_token
                request.session.modified = True
                request.session.save()
                
                customer.portal_profile.phone_verified = True
                customer.portal_profile.save(update_fields=['phone_verified'])
                
                try:
                    OTPAuditLog.objects.create(
                        phone=phone,
                        action='verify_success',
                        success=True,
                        notes=f"Late OTP via token: {order_token}"
                    )
                except Exception:
                    pass
                
                messages.success(request, '✅ OTP verified! Ab apna order place karein.')
                return redirect('checkout')
            else:
                messages.error(request, '❌ Customer account not found')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('verify_otp_later')
    
    company = CompanyInfo.objects.first()
    context = {
        'company_name': company.name if company else 'Shop',
        'page_title': 'Verify OTP (Late)',
        'prefill_phone': prefill_phone,
        'prefill_token': prefill_token,
    }
    return render(request, 'customer_portal/auth/verify_otp_later.html', context)


# ============================================
# 8. PENDING OTPs VIEW
# ============================================

def pending_otps_view(request):
    """Public page: Saari pending OTPs dikhayein"""
    from django.utils.timezone import now
    
    pending_otps = CustomerOTP.objects.filter(
        is_used=False,
        expires_at__gt=now(),
    ).exclude(
        locked_until__gt=now()
    ).order_by('-created_at')[:50]
    
    otp_list = []
    for otp in pending_otps:
        phone = otp.phone or ''
        if len(phone) > 4:
            masked_phone = '****' + phone[-4:]
        else:
            masked_phone = phone
        
        otp_list.append({
            'id': otp.id,
            'masked_phone': masked_phone,
            'otp_code': otp.otp_code,
            'order_token': otp.order_token,
            'customer_name': otp.customer_name or 'Guest',
            'purpose': otp.get_purpose_display(),
            'created_at': otp.created_at,
            'expires_in': otp.time_remaining_display,
        })
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'pending_otps': otp_list,
        'total_pending': len(otp_list),
        'has_otps': len(otp_list) > 0,
    }
    return render(request, 'customer_portal/auth/pending_otps.html', context)


# ============================================
# 9. QUICK VERIFY FROM PENDING LIST
# ============================================

def quick_verify_otp(request, otp_id):
    """Quick verify from pending list"""
    from django.utils.timezone import now
    from urllib.parse import quote
    
    try:
        otp = CustomerOTP.objects.get(id=otp_id)
    except CustomerOTP.DoesNotExist:
        messages.error(request, '❌ OTP not found!')
        return redirect('pending_otps')
    
    if otp.is_used:
        messages.error(request, '❌ This OTP is already used!')
        return redirect('pending_otps')
    
    if otp.is_expired():
        messages.error(request, '❌ This OTP has expired!')
        return redirect('pending_otps')
    
    if otp.is_locked():
        messages.error(request, '🔒 This OTP is locked!')
        return redirect('pending_otps')
    
    phone_encoded = quote(otp.phone or '')
    token_encoded = quote(otp.order_token or '')
    
    return redirect(
        f"/shop/verify-otp-later/?phone={phone_encoded}&token={token_encoded}"
    )