"""
Records every login attempt (admin, shareholder, customer) for the security
module by listening to Django's authentication signals.

A failed login is recorded through track_login_attempt(), which blocks an IP
after too many failures. Errors here are logged and never break the login.
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from app.utils.security import get_client_ip, track_login_attempt

logger = logging.getLogger(__name__)


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    try:
        username_field = get_user_model().USERNAME_FIELD
        username = credentials.get("username") or credentials.get(username_field) or ""
        track_login_attempt(
            username,
            get_client_ip(request),
            request.META.get("HTTP_USER_AGENT", ""),
            False,
            "Invalid username or password",
        )
    except Exception:
        logger.exception("Could not record failed login attempt.")


@receiver(user_logged_in)
def record_successful_login(sender, request, user, **kwargs):
    if request is None:
        return
    try:
        track_login_attempt(
            user.get_username(),
            get_client_ip(request),
            request.META.get("HTTP_USER_AGENT", ""),
            True,
        )
    except Exception:
        logger.exception("Could not record successful login.")
