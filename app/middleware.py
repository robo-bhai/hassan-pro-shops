"""
Project middleware.

    ShareholderRestrictionMiddleware  Keeps shareholder users inside /shareholder/.
    LiveVisitorMiddleware             Tracks shop visitors (throttled).
    AdminActivityMiddleware           Tracks staff activity (throttled).
    SecurityMiddleware                IP access control and session timeout.

Place SecurityMiddleware after AuthenticationMiddleware in settings.MIDDLEWARE.
"""

import logging
import time

from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.db import OperationalError
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.utils.html import escape
from django.utils.timezone import now

from app.models import SecuritySettings, SessionLog
from app.utils.security import get_client_ip, is_ip_allowed

logger = logging.getLogger(__name__)

# How often (seconds) a user's activity may be written to the database.
TRACK_INTERVAL = 30

# Session key that stores the time of the user's last real activity.
SESSION_ACTIVITY_KEY = "security_last_activity"

# Paths that are not user activity: static files and background polling.
POLLING_PREFIXES = (
    "/static/",
    "/media/",
    "/favicon",
    "/testing/run-auto/status/",
    "/api/notifications/",
    "/api/announce-alerts/",
)


def _should_write(key, seconds=TRACK_INTERVAL):
    """Return True once per `seconds` for each key (cache-based throttle)."""
    try:
        return cache.add(key, 1, seconds)
    except Exception:
        return False  # If the cache is down, skip the write instead of loading the DB.


# ---------------------------------------------------------------------------
# Shareholder access
# ---------------------------------------------------------------------------

class ShareholderRestrictionMiddleware:
    """Restrict shareholder users to the /shareholder/ portal."""

    allowed_prefix = "/shareholder/"
    open_prefixes = ("/media/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and hasattr(user, "shareholder_profile"):
            path = request.path
            if not path.startswith(self.open_prefixes + (self.allowed_prefix,)):
                messages.error(
                    request, "Access denied. Shareholders can only access the shareholder portal."
                )
                return redirect("shareholder_portal_dashboard")
        return self.get_response(request)


# ---------------------------------------------------------------------------
# Activity tracking
# ---------------------------------------------------------------------------

class LiveVisitorMiddleware:
    """Track shop visitors, at most once per TRACK_INTERVAL per visitor."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/shop/") and request.method == "GET":
            who = request.session.session_key or request.META.get("REMOTE_ADDR", "anon")
            if _should_write(f"live_visitor:{who}"):
                try:
                    from .models import LiveVisitor

                    LiveVisitor.track_visitor(request)
                except OperationalError:
                    logger.warning("Live visitor tracking skipped (database busy).")
                except Exception:
                    logger.exception("Live visitor tracking failed.")
        return self.get_response(request)


class AdminActivityMiddleware:
    """Record staff activity, at most once per TRACK_INTERVAL per user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and user.is_staff
            and not request.path.startswith(POLLING_PREFIXES)
            and _should_write(f"admin_presence:{user.pk}")
        ):
            try:
                from .models import AdminPresence

                AdminPresence.mark_activity(user=user, page=request.path)
            except OperationalError:
                logger.warning("Admin presence tracking skipped (database busy).")
            except Exception:
                logger.exception("Admin presence tracking failed.")

        return response


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class SecurityMiddleware:
    """Request filtering based on the security settings.

    1. IP access control (blacklist / whitelist) for every request, including
       the login page and anonymous visitors, so a blocked IP cannot keep
       guessing passwords.
    2. Inactivity timeout for signed-in users, when auto logout is enabled.
    """

    login_url = "/login/"
    # Never filtered: static assets.
    bypass_prefixes = ("/static/", "/media/", "/favicon")
    # Excluded from the inactivity timeout only (the IP check still applies).
    session_exempt_paths = ("/login/", "/logout/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.bypass_prefixes):
            return self.get_response(request)

        allowed, reason = is_ip_allowed(get_client_ip(request))
        if not allowed:
            logger.warning(
                "Request from %s denied: %s (%s)", get_client_ip(request), reason, request.path
            )
            return self._deny(request, reason)

        expired_response = self._enforce_session_timeout(request)
        if expired_response is not None:
            return expired_response

        return self.get_response(request)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _wants_json(request):
        return (
            request.path.startswith("/api/")
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
        )

    def _deny(self, request, message):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            logout(request)

        if self._wants_json(request):
            return JsonResponse({"error": "Access denied", "message": message}, status=403)
        return HttpResponseForbidden(
            "<!doctype html><title>Access denied</title>"
            "<h1>Access denied</h1>"
            f"<p>{escape(message)}</p>"
            "<p>If you believe this is a mistake, contact your administrator.</p>"
        )

    def _enforce_session_timeout(self, request):
        """Log out users who have been idle longer than the session timeout.

        The last-activity time lives in the Django session itself, so this
        works even if no SessionLog row exists. SessionLog, when present, is
        kept in sync for the "active sessions" count.
        """
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        if request.path in self.session_exempt_paths:
            return None

        policy = SecuritySettings.get_settings()
        if not policy.enable_auto_logout:
            return None

        session_key = request.session.session_key
        current_time = time.time()
        last_activity = request.session.get(SESSION_ACTIVITY_KEY)

        if last_activity is None:
            # First request since this feature was enabled: start tracking.
            request.session[SESSION_ACTIVITY_KEY] = current_time
            return None

        idle_seconds = current_time - last_activity

        if idle_seconds > policy.session_timeout * 60:
            if session_key:
                SessionLog.objects.filter(session_key=session_key, is_active=True).update(
                    is_active=False
                )
            logout(request)
            if self._wants_json(request):
                return JsonResponse({"error": "Session expired"}, status=401)
            return redirect(f"{self.login_url}?timeout=1")

        # Background polling must not keep an idle session alive, and the
        # write is throttled so the session is not saved on every request.
        is_activity = not request.path.startswith(POLLING_PREFIXES)
        if is_activity and idle_seconds >= TRACK_INTERVAL:
            request.session[SESSION_ACTIVITY_KEY] = current_time
            if session_key:
                SessionLog.objects.filter(session_key=session_key, is_active=True).update(
                    last_activity=now()
                )

        return None
