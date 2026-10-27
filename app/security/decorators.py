"""
Custom Decorators for Customer Portal
======================================
- customer_login_required: for Customer portal pages
- staff_required: for staff/admin only
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def customer_login_required(view_func):
    """
    ✅ Custom decorator for customer portal pages
    
    Behavior:
    - If the user is not authenticated → redirect to customer_login (with next)
    - If a customer → run the view
    - If admin/staff → allowed (bypass)
    - If any other user → redirect to shop_home
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # ==========================================
        # CHECK 1: User authenticated hai?
        # ==========================================
        if not request.user.is_authenticated:
            messages.warning(request, '🛒 Please log in first')
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
        
        # ❌ Any other user — access denied
        messages.error(request, '❌ This page is for customers only')
        return redirect('shop_home')
    
    return wrapper


def staff_required(view_func):
    """
    ✅ For staff/admin users only
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Please log in first')
            return redirect('login')
        
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, '❌ Access denied')
            return redirect('shop_home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper