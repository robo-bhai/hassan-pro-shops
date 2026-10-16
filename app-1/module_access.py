# app/module_access.py
"""
Band (off) kiye gaye module ke URL seedha kholne par bhi roknay wala middleware.

Sidebar me link chhupna kaafi nahi hota: koi URL likh kar khole to page khul jata tha.
Ye middleware Module Settings (Shop/Factory switches) ke mutabiq us module ke
URLs par "Module band hai" page (ya AJAX ke liye JSON) dikhata hai.

settings.py me MIDDLEWARE list me, AuthenticationMiddleware ke BAAD ye line add karein:
    'app.module_access.ModuleAccessMiddleware',
"""
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils.html import escape

from .context_processors import module_visibility

from .module_catalog import MODULE_CATALOG

# (URL prefix, module key, naam) - catalog se banta hai, lamba prefix pehle.
MODULE_URL_PREFIXES = sorted(
    ((prefix, m['key'], m['label']) for m in MODULE_CATALOG for prefix in m['prefixes']),
    key=lambda item: -len(item[0]),
)


def module_for_path(path):
    """URL path se (module_key, naam) ya None."""
    for prefix, key, label in MODULE_URL_PREFIXES:
        if path.startswith(prefix):
            return key, label
    return None


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Module band hai</title>
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
<h1>{label} module band hai</h1>
<p>Ye module is waqt ({mode} mode) ke liye off hai.{hint}</p>
<a class="s" href="/">Dashboard</a>{settings_link}
</div></body></html>"""


class ModuleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        hit = module_for_path(request.path)
        user = getattr(request, 'user', None)
        if hit and user is not None and user.is_authenticated:
            key, label = hit
            vis = module_visibility()
            if not vis.get(key, True):
                return self._blocked(request, user, label, vis.get('_mode', 'both'))
        return self.get_response(request)

    @staticmethod
    def _blocked(request, user, label, mode):
        wants_json = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                      or 'application/json' in request.headers.get('accept', '')
                      or request.path.startswith(('/ajax/', '/api/')))
        if wants_json:
            return JsonResponse({'success': False, 'message': '%s module band hai.' % label}, status=403)
        link = hint = ''
        if user.is_superuser:
            try:
                link = '<a href="%s">Module Settings</a>' % reverse('module_settings')
            except Exception:
                link = ''
            hint = ' Chalane ke liye Module Settings me switch on karein.'
        return HttpResponse(_PAGE.format(label=escape(label), mode=escape(mode), hint=hint, settings_link=link),
                            status=403)
