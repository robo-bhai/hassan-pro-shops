"""
Login-time two-factor authentication (email one-time code) for staff users.

When "Two-factor authentication" is enabled in the security settings, every
staff or superuser session must enter a code emailed to the account before it
can use the system. Shareholder and customer accounts are not affected.

Pieces:
    TwoFactorMiddleware  Sends unverified staff sessions to the code page.
    login_otp            The code page (needs a URL named "login_otp").

Safety rules:
    * Accounts without an email address are not challenged (they could never
      receive a code); a warning is logged.
    * If the "login_otp" URL is missing, the gate stays open and logs an error
      instead of locking everyone out.

Emergency switch-off from the project folder:
    python manage.py shell -c "from app.models import SecuritySettings as S; s=S.get_settings(); s.enable_2fa=False; s.save()"
"""

import logging
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from app.models import SecuritySettings
from app.utils.security import generate_otp, send_otp_email, verify_otp

logger = logging.getLogger(__name__)

OTP_TYPE = "login"
SESSION_VERIFIED_KEY = "security_2fa_verified"
SESSION_NEXT_KEY = "security_2fa_next"
SESSION_SENT_AT_KEY = "security_2fa_sent_at"
RESEND_COOLDOWN_SECONDS = 60


class TwoFactorMiddleware:
    """Require the login code for staff sessions when 2FA is enabled.

    Place it after SecurityMiddleware in settings.MIDDLEWARE.
    """

    exempt_prefixes = ("/static/", "/media/", "/favicon", "/login/", "/logout/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is None
            or not user.is_authenticated
            or not (user.is_staff or user.is_superuser)
            or request.session.get(SESSION_VERIFIED_KEY)
            or request.path.startswith(self.exempt_prefixes)
        ):
            return self.get_response(request)

        if not SecuritySettings.get_settings().enable_2fa:
            return self.get_response(request)

        if not user.email:
            logger.warning("2FA skipped for user %s: no email address.", user.pk)
            return self.get_response(request)

        try:
            otp_url = reverse("login_otp")
        except NoReverseMatch:
            logger.error("2FA is enabled but the 'login_otp' URL is not configured.")
            return self.get_response(request)

        if request.path == otp_url:
            return self.get_response(request)

        wants_json = (
            request.path.startswith("/api/")
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
        )
        if wants_json:
            return JsonResponse({"error": "Two-factor verification required"}, status=403)

        if request.method == "GET":
            request.session[SESSION_NEXT_KEY] = request.get_full_path()
        return redirect(otp_url)


def _mask_email(email):
    name, _, domain = email.partition("@")
    return f"{name[:2]}{'*' * max(len(name) - 2, 1)}@{domain}"


def _next_url(request):
    target = request.session.pop(SESSION_NEXT_KEY, "/")
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return "/"
    return target


def _send_code(request):
    """Generate and email a new code. Returns True if the email was sent."""
    otp = generate_otp(request.user, OTP_TYPE)
    request.session[SESSION_SENT_AT_KEY] = time.time()
    if not send_otp_email(request.user, otp.otp_code):
        messages.error(request, "The code could not be sent. Please contact your administrator.")
        return False
    return True


@login_required
def login_otp(request):
    """Ask for the emailed code after sign-in."""
    if request.session.get(SESSION_VERIFIED_KEY) or not SecuritySettings.get_settings().enable_2fa:
        return redirect(_next_url(request))

    if request.method == "POST":
        if request.POST.get("action") == "resend":
            waited = time.time() - request.session.get(SESSION_SENT_AT_KEY, 0)
            if waited < RESEND_COOLDOWN_SECONDS:
                wait = int(RESEND_COOLDOWN_SECONDS - waited)
                messages.error(request, f"Please wait {wait} seconds before requesting a new code.")
            elif _send_code(request):
                messages.success(request, "A new code has been sent.")
            return redirect("login_otp")

        success, message = verify_otp(request.user, request.POST.get("otp_code"), OTP_TYPE)
        if success:
            request.session[SESSION_VERIFIED_KEY] = True
            return redirect(_next_url(request))
        messages.error(request, message)
        return redirect("login_otp")

    if SESSION_SENT_AT_KEY not in request.session:
        _send_code(request)

    return render(
        request,
        "security/login_otp.html",
        {"masked_email": _mask_email(request.user.email or "")},
    )
