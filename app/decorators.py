"""
Custom Decorators for Customer Portal
======================================
- customer_login_required: Customer portal ke pages ke liye
- staff_required: Sirf staff/admin ke liye
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def customer_login_required(view_func):
    """
    ✅ Custom decorator for customer portal pages
    
    Behavior:
    - Agar user authenticated nahi → customer_login par redirect (next ke saath)
    - Agar customer hai → view chalayein
    - Agar admin/staff hai → allowed (bypass)
    - Agar aur koi user hai → shop_home par redirect
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # ==========================================
        # CHECK 1: User authenticated hai?
        # ==========================================
        if not request.user.is_authenticated:
            messages.warning(request, '🛒 Pehle login karein')
            next_url = request.get_full_path()
            return redirect(f"{reverse('customer_login')}?next={next_url}")
        
        # ==========================================
        # CHECK 2: Customer hai ya admin/staff?
        # ==========================================
        is_customer = hasattr(request.user, 'customer_profile')
        is_admin = request.user.is_staff or request.user.is_superuser
        
        if is_customer:
            # ✅ Customer hai — allowed
            return view_func(request, *args, **kwargs)
        
        if is_admin:
            # ✅ Admin/staff hai — allowed (bypass)
            return view_func(request, *args, **kwargs)
        
        # ❌ Koi aur user hai — access denied
        messages.error(request, '❌ Yeh page sirf customers ke liye hai')
        return redirect('shop_home')
    
    return wrapper


def staff_required(view_func):
    """
    ✅ Only staff/admin users ke liye
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Pehle login karein')
            return redirect('login')
        
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, '❌ Access denied')
            return redirect('shop_home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper