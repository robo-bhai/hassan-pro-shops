"""Language switch: /set-language/<en|ur|ar>/?next=..."""
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

from ..i18n_lang import COOKIE_NAME, DEFAULT_LANG, LANGUAGE_CODES


def set_language(request, code):
    if code not in LANGUAGE_CODES:
        code = DEFAULT_LANG
    target = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/'
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        target = '/'
    response = HttpResponseRedirect(target)
    response.set_cookie(COOKIE_NAME, code, max_age=365 * 24 * 3600, samesite='Lax', path='/')
    session = getattr(request, 'session', None)
    if session is not None:
        session[COOKIE_NAME] = code
    return response
