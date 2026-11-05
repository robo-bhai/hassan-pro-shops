# app/module_access.py
"""
Middleware that blocks the URL of a disabled (off) module even if it is opened directly.

Hiding the link in the sidebar is not enough: if someone typed the URL the page used to open.
Ye middleware Module Settings (Shop/Factory switches) ke mutabiq us module ke
On those URLs it shows the "Module is disabled" page (or JSON for AJAX).

In settings.py, add this line to the MIDDLEWARE list, AFTER AuthenticationMiddleware:
    'app.module_access.ModuleAccessMiddleware',
"""
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.html import escape

from .context_processors import module_visibility
from .store.store_access import module_scope

from .module_catalog import STORE_USER_BLOCKED_PREFIXES, get_module_catalog

# (URL prefix, module key, name) - built from the catalog, longest prefix first.
def _url_prefixes():
    return sorted(
        ((prefix, m['key'], m['label']) for m in get_module_catalog() for prefix in m['prefixes']),
        key=lambda item: -len(item[0]),
    )


def module_for_path(path):
    """URL path se (module_key, naam) ya None."""
    for prefix, key, label in _url_prefixes():
        if path.startswith(prefix):
            return key, label
    return None


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Module is disabled</title>
<style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f6f8fb;
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1f2937;padding:16px}}
.c{{background:#fff;border:1px solid #e8ebf0;border-radius:16px;padding:32px 28px;max-width:420px;text-align:center;
box-shadow:0 8px 30px rgba(16,24,40,.08)}}
.i{{width:56px;height:56px;border-radius:50%;background:#fff0d6;color:#b35c00;display:inline-flex;align-items:center;
justify-content:center;font-size:26px;margin-bottom:12px}}
h1{{font-size:1.15rem;margin:0 0 8px}} p{{color:#6b7280;font-size:.9rem;margin:0 0 18px}}
a{{display:inline-block;padding:9px 18px;border-radius:9px;text-decoration:none;font-weight:600;font-size:.85rem;
background:#3b5bdb;color:#fff;margin:4px}} a.s{{background:#f1f3f5;color:#1f2937}}
</style></head><body><div class="c"><div class="i">&#128274;</div>
<h1>{label} module is disabled</h1>
<p>This module is turned off for the current ({mode} mode).{hint}</p>
<a class="s" href="/">Dashboard</a>{settings_link}
</div></body></html>"""


class ModuleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        hit = module_for_path(request.path)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            vis = module_visibility()
            if hit:
                key, label = hit
                if not vis.get(key, True):
                    return self._blocked(request, user, label, vis.get('_mode', 'both'))

            # Member of a store team: only that store's modules (admin pages closed)
            scope = module_scope(user)
            if scope is not None:
                # The store's own dashboard instead of the company-wide Dashboard (Stores)
                if request.method == 'GET' and self._is_company_dashboard(request.path_info):
                    return redirect('store_dashboard')
                if hit and hit[0] not in scope:
                    return self._blocked_store(request, hit[1])
                if request.path.startswith(tuple(STORE_USER_BLOCKED_PREFIXES)):
                    return self._blocked_store(request, 'Ye page')
        return self.get_response(request)

    @staticmethod
    def _is_company_dashboard(path):
        try:
            return resolve(path).url_name == 'dashboard'
        except Resolver404:
            return False

    @staticmethod
    def _blocked_store(request, label):
        wants_json = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                      or 'application/json' in request.headers.get('accept', '')
                      or request.path.startswith(('/ajax/', '/api/')))
        msg = '%s is not allowed for your store.' % label
        if wants_json:
            return JsonResponse({'success': False, 'message': msg}, status=403)
        return HttpResponse(_PAGE.format(label=escape(label), mode='store',
                                         hint=' This is not included in your store modules.', settings_link=''),
                            status=403)

    @staticmethod
    def _blocked(request, user, label, mode):
        wants_json = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                      or 'application/json' in request.headers.get('accept', '')
                      or request.path.startswith(('/ajax/', '/api/')))
        if wants_json:
            return JsonResponse({'success': False, 'message': 'The %s module is disabled.' % label}, status=403)
        link = hint = ''
        if user.is_superuser:
            try:
                link = '<a href="%s">Module Settings</a>' % reverse('module_settings')
            except Exception:
                link = ''
            hint = ' To enable it, turn on the switch in Module Settings.'
        return HttpResponse(_PAGE.format(label=escape(label), mode=escape(mode), hint=hint, settings_link=link),
                            status=403)
