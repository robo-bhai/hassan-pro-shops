"""Activation page: shows this computer's machine id and the license status, and accepts a new key."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils.html import escape

from . import core

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>License</title>
<style>body{{margin:0;background:#f6f8fb;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1f2937;padding:16px}}
.c{{background:#fff;border:1px solid #e8ebf0;border-radius:16px;padding:22px;max-width:560px;margin:24px auto}}
h2{{margin:0 0 4px}} .s{{padding:10px 12px;border-radius:10px;margin:12px 0;font-weight:600;background:{bg};color:{fg}}}
code{{display:block;padding:10px;background:#f1f3f5;border-radius:8px;font-size:1.05rem;letter-spacing:.06em;word-break:break-all}}
textarea{{width:100%;box-sizing:border-box;height:110px;border:1px solid #cfd4dc;border-radius:8px;padding:8px;font-family:monospace}}
button{{margin-top:8px;padding:10px 18px;border:0;border-radius:9px;background:#3b5bdb;color:#fff;font-weight:600}}
.m{{color:#b91c1c;font-weight:600}} small{{color:#6b7280}}</style></head><body><div class="c">
<h2>Software license</h2><small>{customer}</small>
<div class="s">{message}</div>
<p><b>This computer's ID</b> (send it to the vendor to get a key):</p><code>{machine}</code>
<form method="post" style="margin-top:16px"><input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">
<p><b>Enter license key</b></p><textarea name="key" placeholder="LIC1...."></textarea>
<div class="m">{error}</div><button type="submit">Activate</button></form>
<p><a href="/">&larr; Back</a></p></div></body></html>"""

_TONES = {'valid': ('#dcfce7', '#166534'), 'grace': ('#fef3c7', '#92400e'),
          'trial': ('#dbeafe', '#1e40af'), 'readonly': ('#fee2e2', '#991b1b')}


@login_required
def license_page(request):
    error = ''
    if request.method == 'POST':
        if not request.user.is_superuser:
            return HttpResponse('Only an administrator can change the license.', status=403)
        public = core.public_key_bytes()
        token = request.POST.get('key', '').strip()
        data = core.parse_token(token, public) if public else None
        if not public:
            error = 'License checking is not set up on this server (LICENSE_PUBLIC_KEY is missing).'
        elif data is None:
            error = 'This key is not valid. Check that you copied all of it.'
        elif data['m'] not in ('*', core.machine_id()):
            error = 'This key was issued for a different computer.'
        else:
            core.save_token(token)
            return HttpResponseRedirect('/license/')
    status = core.get_status()
    bg, fg = _TONES.get(status.state, _TONES['valid'])
    return HttpResponse(_PAGE.format(bg=bg, fg=fg, customer=escape(status.customer), message=escape(status.message),
                                     machine=escape(core.machine_id()), csrf=escape(get_token(request)), error=escape(error)))
