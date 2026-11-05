# app/middleware/license_gate.py
"""
License gate: read-only mode once the license has expired (after the grace period).

In settings.py:
    LICENSE_PUBLIC_KEY = '<64 hex characters printed by:  python make_license.py keygen>'
    # optional:  LICENSE_GRACE_DAYS = 7   LICENSE_TRIAL_DAYS = 14   LICENSE_FILE = BASE_DIR / 'license.key'
    #            LICENSE_EXEMPT_PREFIXES = ('/some/extra/url/',)
and add this line to MIDDLEWARE (anywhere after SessionMiddleware, e.g. at the end):
    'app.middleware.license_gate.LicenseMiddleware',

With LICENSE_PUBLIC_KEY unset the gate does nothing (so development and tests are not affected).

What happens:
  valid / grace / trial  -> everything works (grace and trial show a coloured bar on every page)
  read-only              -> viewing, printing and reports still work; anything that changes data
                            (POST/PUT/PATCH/DELETE) is refused, except login, the license page and
                            closing a cashier shift (so the day can still be closed properly).
If the gate itself hits an error it lets the request through and logs it: a bug here must never stop a shop selling.
"""
import logging
import re

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape

from app.licensing import core

logger = logging.getLogger(__name__)

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
DEFAULT_EXEMPT_PREFIXES = ('/license/', '/static/', '/media/', '/admin/login', '/admin/logout',
                           '/accounts/', '/login', '/logout', '/i18n/', '/sales/shift/status')
EXEMPT_PATTERNS = (re.compile(r'^/sales/shift/(\d+/)?close/?$'),)

_COLORS = {'valid': '#b45309', 'grace': '#b45309', 'trial': '#1d4ed8', 'readonly': '#b91c1c'}

_BLOCK_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>License</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f6f8fb;
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1f2937;padding:16px}}
.c{{background:#fff;border:1px solid #e8ebf0;border-radius:16px;padding:28px;max-width:440px;text-align:center}}
a{{display:inline-block;margin-top:12px;padding:9px 18px;border-radius:9px;background:#3b5bdb;color:#fff;text-decoration:none;font-weight:600}}
</style></head><body><div class="c"><h2 style="margin-top:0">System is read-only</h2><p>{message}</p>
<p style="color:#6b7280;font-size:.9rem">Nothing was saved. You can still view records and print reports.</p>
<a href="/license/">Enter license key</a> <a href="javascript:history.back()" style="background:#f1f3f5;color:#1f2937">Back</a></div></body></html>"""


class LicenseMiddleware:
    def __init__(self, get_response):
        core.validate_configuration()              # refuse to start with a malformed key
        self.get_response = get_response

    def _exempt(self, path):
        prefixes = DEFAULT_EXEMPT_PREFIXES + tuple(getattr(settings, 'LICENSE_EXEMPT_PREFIXES', ()))
        login_url = str(getattr(settings, 'LOGIN_URL', '') or '')
        if path.startswith(prefixes) or (login_url.startswith('/') and path.startswith(login_url)):
            return True
        return any(p.match(path) for p in EXEMPT_PATTERNS)

    def __call__(self, request):
        try:
            status = core.get_status()
        except Exception:
            logger.exception('License check failed - letting the request through')
            return self.get_response(request)
        request.license_status = status

        if status.read_only and request.method not in SAFE_METHODS and not self._exempt(request.path):
            return self._block(request, status)

        response = self.get_response(request)
        if status.needs_banner and not request.path.startswith('/license/'):
            response = self._banner(response, status)
        return response

    @staticmethod
    def _block(request, status):
        wants_json = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                      or 'application/json' in request.headers.get('accept', '')
                      or 'json' in (request.content_type or ''))
        if wants_json:
            response = JsonResponse({'success': False, 'error': 'license', 'message': status.message}, status=403)
        else:
            response = HttpResponse(_BLOCK_PAGE.format(message=escape(status.message)), status=403)
        response['X-License-Block'] = '1'
        return response

    @staticmethod
    def _banner(response, status):
        try:
            if (response.streaming or response.status_code != 200 or response.has_header('Content-Encoding')
                    or not response.get('Content-Type', '').startswith('text/html')):
                return response
            body = response.content
            at = body.rfind(b'</body>')
            if at < 0:
                return response
            color = _COLORS.get(status.state, '#b45309')
            bar = (f'<div style="position:fixed;left:0;right:0;bottom:0;z-index:99999;background:{color};color:#fff;'
                   f'padding:8px 14px;font:600 13px system-ui,sans-serif;text-align:center">{escape(status.message)} '
                   f'<a href="/license/" style="color:#fff;text-decoration:underline">License</a></div>').encode()
            response.content = body[:at] + bar + body[at:]
        except Exception:
            logger.exception('Could not add the license bar')
        return response
