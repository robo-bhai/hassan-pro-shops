# app/middleware.py

from django.shortcuts import redirect
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)


class ShareholderRestrictionMiddleware:
    """
    Shareholder users ko admin pages par jaane se rokta hai
    Shareholder sirf /shareholder/ se start hone wali URLs par ja sakta hai
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.shareholder_allowed_prefix = '/shareholder/'

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            is_shareholder = hasattr(request.user, 'shareholder_profile')
            
            if is_shareholder:
                path = request.path
                
                # Allow media and static files
                if path.startswith('/media/') or path.startswith('/static/'):
                    response = self.get_response(request)
                    return response
                
                # Check if path starts with /shareholder/
                is_shareholder_path = path.startswith(self.shareholder_allowed_prefix)
                
                if not is_shareholder_path:
                    messages.error(request, '⚠️ Access denied! Shareholders can only access the shareholder portal.')
                    return redirect('shareholder_portal_dashboard')
        
        response = self.get_response(request)
        return response


# ============================================
# ✅ LIVE VISITOR TRACKING MIDDLEWARE
# ============================================

class LiveVisitorMiddleware:
    """
    Track live visitors on customer portal (shop) pages
    
    Features:
    - Har visitor ko 1 minute ke liye "active" mark karta hai
    - Sirf /shop/ se start hone wali pages track karta hai
    - 5 minute purane visitors auto-delete
    - Error-safe: agar koi masla ho to request block nahi hoti
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # ✅ Sirf shop pages par track karo
        if request.path.startswith('/shop/'):
            try:
                from .models import LiveVisitor
                LiveVisitor.track_visitor(request)
            except Exception as e:
                logger.error(f"Live visitor tracking error: {e}")
        
        response = self.get_response(request)
        return response


# ============================================
# ✅ NEW: ADMIN ACTIVITY TRACKING MIDDLEWARE
# ============================================

class AdminActivityMiddleware:
    """
    Har request pe admin ki REAL-TIME activity track karo
    
    Yeh LAST_LOGIN se alag hai:
    - last_login = jab login kiya (stale ho jata hai)
    - last_activity = abhi kaam kar raha hai (fresh)
    
    Isse pata chalta hai ke konsa admin ABHI LIVE hai.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # ✅ Response PEHLE process karo
        response = self.get_response(request)
        
        # ✅ Sirf authenticated staff users ke liye track karo
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
            try:
                # Static files skip karo
                path = request.path
                if not path.startswith('/static/') and \
                   not path.startswith('/media/') and \
                   not path.startswith('/favicon'):
                    
                    from .models import AdminPresence
                    AdminPresence.mark_activity(
                        user=request.user,
                        page=path
                    )
            except Exception as e:
                logger.error(f"Admin presence tracking error: {e}")
        
        return response


# ============================================
# SECURITY MIDDLEWARE
# ============================================

from django.http import JsonResponse
from django.utils.timezone import now
from django.shortcuts import redirect
from django.contrib.auth import logout
from datetime import timedelta
from app.utils.security import is_ip_allowed
from app.models import SecuritySettings, SessionLog


class SecurityMiddleware:
    """Security middleware for request filtering"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip for admin and static
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return self.get_response(request)
        
        # Skip for login page
        if request.path == '/login/' or request.path == '/logout/':
            return self.get_response(request)
        
        # IP Security
        if request.user.is_authenticated:
            ip_allowed, message = is_ip_allowed(request.META.get('REMOTE_ADDR'))
            if not ip_allowed:
                logout(request)
                return JsonResponse({'error': 'Access denied', 'message': message}, status=403)
        
        # Session timeout
        if request.user.is_authenticated:
            settings = SecuritySettings.get_settings()
            if settings.enable_auto_logout:
                session_key = request.session.session_key
                try:
                    session = SessionLog.objects.get(session_key=session_key, is_active=True)
                    if session.last_activity < now() - timedelta(minutes=settings.session_timeout):
                        logout(request)
                        return redirect('/login/?timeout=1')
                    session.last_activity = now()
                    session.save()
                except SessionLog.DoesNotExist:
                    pass
        
        response = self.get_response(request)
        return response