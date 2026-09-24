"""
Customer Authentication Views — Professional OTP System
=========================================================
✅ Same page OTP verify
✅ Auto order placement
✅ Trust system
✅ Pending OTPs backup
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
from decimal import Decimal
import re
import json
import uuid
import logging

from .models import (
    Customer, CustomerProfile, CustomerOTP, CustomerAddress,
    OTPAuditLog, CompanyInfo, Notification,
    SaleOrder, SaleOrderItem, Sale, Warehouse,
    Product, Inventory
)

from .decorators import customer_login_required

logger = logging.getLogger(__name__)


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_client_ip(request):
    """Get client IP safely"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip or None


def is_valid_phone(phone):
    """Validate Pakistani phone"""
    pattern = r'^(\+92|92|0)?3\d{9}$'
    return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))


def normalize_phone(phone):
    """Normalize to +923XXXXXXXXX"""
    phone = phone.replace(' ', '').replace('-', '').replace('+', '')
    if phone.startswith('92'):
        phone = phone[2:]
    elif phone.startswith('0'):
        phone = phone[1:]
    return f'+92{phone}'


def safe_login(request, user):
    """Safe login with backend"""
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')


# ============================================
# AUTO PLACE ORDER — After OTP Verify
# ============================================

def auto_place_order(request, customer):
    """
    ✅ OTP verify hone ke baad AUTO ORDER PLACE karo
    """
    try:
        with transaction.atomic():
            # Step 1: Cart check
            cart = request.session.get('cart', {})
            if not cart:
                logger.warning(f"Cart khali hai for {customer.name}")
                return None, "Cart khali hai"
            
            # Step 2: Warehouse
            warehouse = Warehouse.objects.first()
            if not warehouse:
                return None, "Koi warehouse nahi hai"
            
            # Step 3: Payment method
            payment_method = request.session.get('selected_payment', 'cod')
            valid_methods = ['cod', 'jazzcash', 'easypaisa', 'bank']
            if payment_method not in valid_methods:
                payment_method = 'cod'
            
            # Step 4: Duplicate check (30 sec)
            recent_order = SaleOrder.objects.filter(
                customer=customer,
                created_at__gte=now() - timedelta(seconds=30),
                status='pending'
            ).first()
            
            if recent_order:
                logger.info(f"Duplicate detected: {recent_order.order_no}")
                return recent_order, None
            
            # Step 5: Stock check
            product_ids = [item['product_id'] for item in cart.values()]
            products = Product.objects.in_bulk(product_ids)
            
            for key, item in cart.items():
                product = products.get(item['product_id'])
                if not product:
                    return None, f"Product not found"
                
                stock = Inventory.objects.filter(
                    product=product, warehouse=warehouse
                ).values_list('stock', flat=True).first() or 0
                
                if stock < item['quantity']:
                    return None, f"{product.name} ka stock kam hai"
            
            # Step 6: Create order
            order = SaleOrder.objects.create(
                customer=customer,
                warehouse=warehouse,
                order_date=now(),
                status='pending',
                notes=f"🌐 WEB ORDER (OTP Verified) | Payment: {payment_method}",
                discount_value=Decimal('0.00'),
                advance_payment=Decimal('0.00'),
                created_by=customer.portal_profile.user,
            )
            
            # Step 7: Add items
            total_amount = Decimal('0.00')
            order_summary = []
            
            for key, item in cart.items():
                product = products.get(item['product_id'])
                quantity = item['quantity']
                price = Decimal(str(item['price']))
                
                SaleOrderItem.objects.create(
                    order=order,
                    product=product,
                    qty=quantity,
                    price=price,
                )
                
                item_total = price * quantity
                total_amount += item_total
                
                order_summary.append({
                    'name': product.name,
                    'qty': quantity,
                    'price': float(price),
                    'total': float(item_total),
                })
            
            # Step 8: Trust update
            customer.portal_profile.record_successful_order()
            
            # Step 9: Clear cart + session
            request.session['cart'] = {}
            request.session.pop('order_verified', None)
            request.session.pop('order_verified_at', None)
            request.session.pop('order_otp_phone', None)
            request.session.pop('order_otp_id', None)
            request.session.pop('order_token', None)
            request.session.pop('selected_payment', None)
            request.session.modified = True
            request.session.save()
            
            # Step 10: Notify admin
            try:
                admins = User.objects.filter(is_superuser=True)
                for admin in admins:
                    Notification.send(
                        user=admin,
                        title=f'🛒 New Order - {customer.name}',
                        message=(
                            f'Order #{order.order_no}\n'
                            f'Amount: Rs. {total_amount:,.2f}\n'
                            f'Phone: {customer.contact_number}\n'
                            f'Items: {len(order_summary)}'
                        ),
                        notification_type='sale',
                        category='sales',
                        link=f'/orders/sale/{order.id}/'
                    )
            except Exception as e:
                logger.error(f"Notification error: {e}")
            
            # Step 11: WhatsApp
            try:
                from .whatsapp_utils import WhatsAppSender
                if customer.contact_number:
                    WhatsAppSender.send_order_confirmation(
                        customer.contact_number,
                        order.order_no,
                        float(total_amount),
                        order_summary
                    )
            except Exception as e:
                logger.error(f"WhatsApp error: {e}")
            
            logger.info(f"✅ Order placed: {order.order_no}")
            return order, None
            
    except Exception as e:
        logger.error(f"Auto place order error: {e}")
        import traceback
        traceback.print_exc()
        return None, str(e)


# ============================================
# 1. CUSTOMER REGISTER
# ============================================

def customer_register(request):
    """Customer registration"""
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        return redirect('my_account')
    
    if request.method == 'POST':
        try:
            full_name = request.POST.get('full_name', '').strip()[:100]
            phone = request.POST.get('phone', '').strip()[:20]
            email = request.POST.get('email', '').strip()[:100]
            city = request.POST.get('city', '').strip()[:100]
            address = request.POST.get('address', '').strip()[:500]
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not full_name or len(full_name) < 3:
                messages.error(request, '❌ Poora naam likhein')
                return redirect('customer_register')
            
            if not phone or not is_valid_phone(phone):
                messages.error(request, '❌ Sahi phone number likhein')
                return redirect('customer_register')
            
            if not city:
                messages.error(request, '❌ Sahi shehar likhein')
                return redirect('customer_register')
            
            if not address or len(address) < 10:
                messages.error(request, '❌ Mukammal pata likhein')
                return redirect('customer_register')
            
            if not password or len(password) < 6:
                messages.error(request, '❌ Password kam az kam 6 characters')
                return redirect('customer_register')
            
            if password != confirm_password:
                messages.error(request, '❌ Password match nahi ho rahe')
                return redirect('customer_register')
            
            phone = normalize_phone(phone)
            
            if Customer.objects.filter(contact_number=phone).exists():
                messages.error(request, '⚠️ Yeh phone pehle se registered hai')
                return redirect('customer_login')
            
            if email:
                try:
                    validate_email(email)
                    if User.objects.filter(email=email).exists():
                        messages.error(request, '⚠️ Yeh email pehle se registered hai')
                        return redirect('customer_register')
                except ValidationError:
                    messages.error(request, '❌ Sahi email likhein')
                    return redirect('customer_register')
            
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
                
                full_address = f"{address}, {city}"
                
                customer = Customer.objects.create(
                    name=full_name,
                    contact_number=phone,
                    email=email or None,
                    address=full_address,
                    customer_code=f'CUS-{user.id:05d}',
                )
                
                profile = CustomerProfile.objects.create(
                    customer=customer,
                    user=user,
                    phone_verified=False,
                    email_verified=bool(email),
                    last_login_at=now()
                )
                
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
            
            messages.success(request, f'🎉 Welcome {customer.name}!')
            return redirect('my_account')
            
        except Exception as e:
            logger.error(f"Register error: {e}")
            messages.error(request, '❌ Register mein masla hua')
            return redirect('customer_register')
    
    company = CompanyInfo.objects.first()
    context = {
        'company_name': company.name if company else 'Shop',
        'page_title': 'Create Account',
    }
    return render(request, 'customer_portal/auth/register.html', context)


# ============================================
# 2. CUSTOMER LOGIN
# ============================================

def customer_login(request):
    """Customer login"""
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        next_url = request.GET.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('my_account')
    
    if request.method == 'POST':
        try:
            phone = request.POST.get('phone', '').strip()[:20]
            password = request.POST.get('password', '')
            next_url = request.POST.get('next') or request.GET.get('next', '')
            
            if not phone or not password:
                messages.error(request, '❌ Phone aur password dono likhein')
                return redirect('customer_login')
            
            phone = normalize_phone(phone)
            
            customer = Customer.objects.filter(contact_number=phone).first()
            if not customer or not hasattr(customer, 'portal_profile'):
                messages.error(request, '❌ Ghalat phone number ya password')
                return redirect('customer_login')
            
            user = customer.portal_profile.user
            if not user:
                messages.error(request, '❌ Account setup incomplete')
                return redirect('customer_login')
            
            if user.is_superuser or user.is_staff:
                messages.error(request, '❌ Yeh admin account hai')
                return redirect('login')
            
            authenticated_user = authenticate(
                request, username=user.username, password=password
            )
            
            if authenticated_user:
                safe_login(request, authenticated_user)
                request.session.save()
                
                customer.portal_profile.last_login_at = now()
                customer.portal_profile.save()
                
                messages.success(request, f'🎉 Welcome back, {customer.name}!')
                
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                
                return redirect('my_account')
            else:
                messages.error(request, '❌ Ghalat password')
                return redirect('customer_login')
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            messages.error(request, '❌ Login mein masla hua')
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
    """Logout with session flush"""
    request.session.flush()
    logout(request)
    messages.success(request, '👋 Aap logout ho gaye hain')
    return redirect('shop_home')


# ============================================
# 4. MY ACCOUNT
# ============================================

@customer_login_required
def my_account(request):
    """Customer dashboard"""
    if not hasattr(request.user, 'customer_profile'):
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
# 5. SEND OTP
# ============================================

@customer_login_required
def send_order_otp(request):
    """Send OTP — same page flow"""
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
        attempts = 0
        while CustomerOTP.objects.filter(
            order_token=order_token, is_used=False
        ).exists() and attempts < 5:
            order_token = str(uuid.uuid4()).replace('-', '')[:8].upper()
            attempts += 1
        
        otp = CustomerOTP.generate_otp(
            phone=phone,
            purpose='order',
            customer_name=customer.name,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            order_token=order_token,
        )
        
        request.session['order_otp_phone'] = phone
        request.session['order_otp_id'] = otp.id
        request.session['order_token'] = order_token
        request.session.modified = True
        request.session.save()
        
        masked = phone[-4:].rjust(len(phone), '*')
        
        return JsonResponse({
            'success': True,
            'skip_otp': False,
            'message': f'OTP sent to {masked}',
            'otp_id': otp.id,
            'order_token': order_token,
        })
        
    except Exception as e:
        logger.error(f"Send OTP error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 6. VERIFY OTP — AUTO ORDER PLACE
# ============================================

@customer_login_required
def verify_order_otp(request):
    """Verify OTP — Auto order place"""
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
            return JsonResponse({'success': False, 'message': 'Session expired'})
        
        success, otp_obj, message = CustomerOTP.find_and_verify(
            phone=phone,
            code=otp_code,
            purpose='order'
        )
        
        if not success:
            return JsonResponse({'success': False, 'message': message})
        
        request.session['order_verified'] = True
        request.session['order_verified_at'] = now().isoformat()
        request.session['order_otp_phone'] = phone
        request.session.modified = True
        request.session.save()
        
        profile = request.user.customer_profile
        profile.phone_verified = True
        profile.save(update_fields=['phone_verified'])
        
        # ✅ AUTO ORDER PLACE
        order, error = auto_place_order(request, profile.customer)
        
        if order:
            return JsonResponse({
                'success': True,
                'message': '✅ OTP verified! Order place ho gaya.',
                'redirect_url': f'/shop/order-success/{order.id}/',
            })
        else:
            return JsonResponse({
                'success': True,
                'message': f'✅ OTP verified! Lekin order place nahi hua: {error}',
                'redirect_url': '/shop/cart/',
            })
        
    except Exception as e:
        logger.error(f"Verify OTP error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 7. SAVE PAYMENT METHOD
# ============================================

@customer_login_required
def save_payment_method(request):
    """Save payment method to session"""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    
    try:
        data = json.loads(request.body)
        payment_method = data.get('payment_method', 'cod')
        
        valid_methods = ['cod', 'jazzcash', 'easypaisa', 'bank']
        if payment_method not in valid_methods:
            payment_method = 'cod'
        
        request.session['selected_payment'] = payment_method
        request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 8. PENDING OTPs (Backup)
# ============================================

def pending_otps_view(request):
    """Pending OTPs page"""
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
        masked_phone = '****' + phone[-4:] if len(phone) > 4 else phone
        
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
# 9. VERIFY OTP LATER (Backup — Pending OTPs se)
# ============================================

def verify_otp_later(request):
    """Verify OTP from Pending OTPs page"""
    prefill_phone = request.GET.get('phone', '').strip()[:20]
    prefill_token = request.GET.get('token', '').strip().upper()[:8]
    
    if request.method == 'POST':
        try:
            phone = request.POST.get('phone', '').strip()[:20]
            order_token = request.POST.get('order_token', '').strip().upper()[:8]
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
            
            if not customer or not customer.portal_profile.user:
                messages.error(request, '❌ Customer account not found')
                return redirect(f"/shop/verify-otp-later/?phone={phone}&token={order_token}")
            
            # Session flags
            request.session['order_verified'] = True
            request.session['order_verified_at'] = now().isoformat()
            request.session['order_token'] = order_token
            request.session.modified = True
            
            # Login
            safe_login(request, customer.portal_profile.user)
            
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
            
            # Auto order place
            order, error = auto_place_order(request, customer)
            
            if order:
                messages.success(request, f'🎉 Order #{order.order_no} place ho gaya!')
                return redirect('order_success_page', order_id=order.id)
            else:
                messages.warning(request, f'⚠️ OTP verified, lekin order place nahi hua: {error}')
                return redirect('cart_view')
                
        except Exception as e:
            logger.error(f"Verify OTP later error: {e}")
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('verify_otp_later')
    
    company = CompanyInfo.objects.first()
    context = {
        'company_name': company.name if company else 'Shop',
        'page_title': 'Verify OTP',
        'prefill_phone': prefill_phone,
        'prefill_token': prefill_token,
    }
    return render(request, 'customer_portal/auth/verify_otp_later.html', context)


# ============================================
# 10. QUICK VERIFY FROM PENDING LIST
# ============================================

def quick_verify_otp(request, otp_id):
    """Quick verify from pending list"""
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
    
# ============================================
# ✅ PLACE ORDER DIRECT (Trusted / Verified)
# ============================================

@customer_login_required
def place_order_direct(request):
    """
    ✅ Trusted/Verified customer ke liye — Direct order place
    """
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Login required'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        profile = request.user.customer_profile
        customer = profile.customer
        
        # Trusted ya Verified hona chahiye
        is_trusted = profile.should_skip_order_otp()
        is_verified = request.session.get('order_verified', False)
        
        if not (is_trusted or is_verified):
            return JsonResponse({
                'success': False,
                'message': 'OTP verify zaroori hai'
            })
        
        # Auto order place
        order, error = auto_place_order(request, customer)
        
        if order:
            return JsonResponse({
                'success': True,
                'message': f'Order #{order.order_no} place ho gaya!',
                'redirect_url': f'/shop/order-success/{order.id}/',
            })
        else:
            return JsonResponse({
                'success': False,
                'message': error or 'Order place nahi hua'
            })
    
    except Exception as e:
        logger.error(f"Place order direct error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# ✅ SAVE PAYMENT METHOD
# ============================================

@customer_login_required
def save_payment_method(request):
    """Save payment method to session"""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    
    try:
        data = json.loads(request.body)
        payment_method = data.get('payment_method', 'cod')
        
        valid_methods = ['cod', 'jazzcash', 'easypaisa', 'bank']
        if payment_method not in valid_methods:
            payment_method = 'cod'
        
        request.session['selected_payment'] = payment_method
        request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})