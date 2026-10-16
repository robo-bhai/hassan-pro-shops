# app/middleware.py

from django.shortcuts import redirect
from django.contrib import messages
import logging
from django.core.cache import cache
from django.db import OperationalError

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
# ✅ THROTTLED TRACKING (database lock se bachao)
# ============================================

TRACK_INTERVAL = 30  # seconds

# Ye URLs sirf polling hain, inko activity na samjho
SKIP_PREFIXES = (
    '/static/', '/media/', '/favicon',
    '/testing/run-auto/status/',
    '/api/notifications/',
    '/api/announce-alerts/',
)


def _should_write(key, seconds=TRACK_INTERVAL):
    """Har key ke liye `seconds` mein sirf EK baar True deta hai."""
    try:
        return cache.add(key, 1, seconds)
    except Exception:
        return False  # cache kharab ho to DB par bojh mat daalo


class LiveVisitorMiddleware:
    """Shop visitors track karta hai, har visitor ke liye 30s mein ek baar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/shop/') and request.method == 'GET':
            who = request.session.session_key or request.META.get('REMOTE_ADDR', 'anon')
            if _should_write(f'live_visitor:{who}'):
                try:
                    from .models import LiveVisitor
                    LiveVisitor.track_visitor(request)
                except OperationalError:
                    logger.warning("Live visitor tracking skipped (DB busy)")
                except Exception as e:
                    logger.error(f"Live visitor tracking error: {e}")
        return self.get_response(request)


class AdminActivityMiddleware:
    """Admin ki live activity, har admin ke liye 30s mein ek baar likhta hai."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, 'user', None)
        if (user and user.is_authenticated and user.is_staff
                and not request.path.startswith(SKIP_PREFIXES)
                and _should_write(f'admin_presence:{user.pk}')):
            try:
                from .models import AdminPresence
                AdminPresence.mark_activity(user=user, page=request.path)
            except OperationalError:
                logger.warning("Admin presence skipped (DB busy)")
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