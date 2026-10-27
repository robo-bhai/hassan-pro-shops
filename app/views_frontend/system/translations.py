"""Translation Manager (Settings): edit Urdu/Arabic text, review auto-translations, import/export."""
import csv
import io
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...i18n import i18n_service as svc


def i18n_admin_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.is_staff):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Only admin can manage translations.')
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _clean(v, n=1000):
    return (v or '').strip()[:n]


@i18n_admin_required
def translation_manager(request):
    from ...models import Translation
    svc.ensure_seeded()
    q = request.GET.get('q', '').strip()
    flt = request.GET.get('f', 'all')
    qs = Translation.objects.all()
    if q:
        qs = qs.filter(Q(source__icontains=q) | Q(ur__icontains=q) | Q(ar__icontains=q))
    if flt == 'missing':
        qs = qs.filter(Q(ur='') | Q(ar=''))
    elif flt == 'auto':
        qs = qs.filter(Q(ur_status='auto') | Q(ar_status='auto'))
    elif flt == 'manual':
        qs = qs.filter(Q(ur_status='manual') | Q(ar_status='manual'))
    elif flt == 'reviewed':
        qs = qs.filter(Q(ur_status='reviewed') | Q(ar_status='reviewed'))
    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    base = Translation.objects
    provider = svc.active_provider()
    return render(request, 'settings/translations.html', {
        'page_obj': page, 'q': q, 'flt': flt,
        'stats': {
            'total': base.count(),
            'missing': base.filter(Q(ur='') | Q(ar='')).count(),
            'auto': base.filter(Q(ur_status='auto') | Q(ar_status='auto')).count(),
            'reviewed': base.filter(Q(ur_status='reviewed') | Q(ar_status='reviewed')).count(),
        },
        'provider': provider, 'provider_label': svc.PROVIDER_LABELS.get(provider, provider),
        'auto_on': svc.auto_enabled(),
        'last_error': cache.get('i18n_last_error') or '',
        'last_run': cache.get('i18n_last_run') or '',
    })


def _body(request):
    if request.content_type and 'json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except ValueError:
            return {}
    return request.POST


@require_POST
@i18n_admin_required
def translation_save(request):
    from ...models import Translation
    data = _body(request)
    obj = Translation.objects.filter(pk=data.get('id')).first()
    if not obj:
        return JsonResponse({'ok': False, 'error': 'Not found'}, status=404)
    for lang in ('ur', 'ar'):
        if lang in data:
            new = _clean(data.get(lang))
            if new != getattr(obj, lang):
                setattr(obj, lang, new)
                setattr(obj, lang + '_status', 'manual' if new else '')
    obj.save()
    return JsonResponse({'ok': True, 'ur_status': obj.ur_status, 'ar_status': obj.ar_status})


@require_POST
@i18n_admin_required
def translation_review(request):
    from ...models import Translation
    data = _body(request)
    now = timezone.now()
    if data.get('all'):
        n = 0
        for lang in ('ur', 'ar'):
            n += Translation.objects.filter(**{lang + '_status': 'auto'}).exclude(**{lang: ''}).update(
                **{lang + '_status': 'reviewed', 'updated_at': now})
        messages.success(request, 'Auto translations marked as reviewed: %d' % n)
        return redirect(request.META.get('HTTP_REFERER') or 'translation_manager')
    obj = Translation.objects.filter(pk=data.get('id')).first()
    if not obj:
        return JsonResponse({'ok': False}, status=404)
    for lang in ('ur', 'ar'):
        if getattr(obj, lang) and getattr(obj, lang + '_status') in ('auto', 'default'):
            setattr(obj, lang + '_status', 'reviewed')
    obj.save()
    return JsonResponse({'ok': True, 'ur_status': obj.ur_status, 'ar_status': obj.ar_status})


@require_POST
@i18n_admin_required
def translation_add(request):
    from ...models import Translation
    source = svc.clean_source(request.POST.get('source', ''))[:300]
    if not source:
        messages.error(request, 'English text required.')
        return redirect('translation_manager')
    obj, _ = Translation.objects.get_or_create(key=svc.make_key(source), defaults={'source': source})
    for lang in ('ur', 'ar'):
        val = _clean(request.POST.get(lang))
        if val:
            setattr(obj, lang, val)
            setattr(obj, lang + '_status', 'manual')
    obj.save()
    messages.success(request, 'Saved: %s' % obj.source)
    return redirect('translation_manager')


@require_POST
@i18n_admin_required
def translation_delete(request):
    from ...models import Translation
    Translation.objects.filter(pk=_body(request).get('id')).delete()
    return JsonResponse({'ok': True})


@require_POST
@i18n_admin_required
def translation_auto_run(request):
    svc.ensure_seeded()
    return JsonResponse(svc.translate_pending(40))


@require_POST
@i18n_admin_required
def translation_toggle_auto(request):
    from ...models import SystemSetting
    on = not svc.auto_enabled()
    SystemSetting.set_value('i18n_auto_translate', 'true' if on else 'false', request.user)
    messages.success(request, 'Auto-translate is now %s.' % ('ON' if on else 'OFF'))
    return redirect('translation_manager')


@require_POST
@i18n_admin_required
def translation_seed(request):
    messages.success(request, 'Default words added: %d' % svc.seed_defaults())
    return redirect('translation_manager')


@i18n_admin_required
def translation_export(request):
    from ...models import Translation
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['source', 'ur', 'ar', 'ur_status', 'ar_status'])
    for t in Translation.objects.all():
        w.writerow([t.source, t.ur, t.ar, t.ur_status, t.ar_status])
    resp = HttpResponse('\ufeff' + out.getvalue(), content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="translations.csv"'
    return resp


@require_POST
@i18n_admin_required
def translation_import(request):
    from ...models import Translation
    f = request.FILES.get('file')
    if not f or f.size > 2 * 1024 * 1024:
        messages.error(request, 'Choose a CSV file (max 2 MB).')
        return redirect('translation_manager')
    text = f.read().decode('utf-8-sig', errors='replace')
    changed = 0
    for row in csv.DictReader(io.StringIO(text)):
        source = svc.clean_source(row.get('source', ''))[:300]
        if not source:
            continue
        obj, _ = Translation.objects.get_or_create(key=svc.make_key(source), defaults={'source': source})
        touched = False
        for lang in ('ur', 'ar'):
            val = _clean(row.get(lang))
            if val and val != getattr(obj, lang):
                setattr(obj, lang, val)
                setattr(obj, lang + '_status', 'manual')
                touched = True
        if touched:
            obj.save()
            changed += 1
    messages.success(request, 'Import done. Updated rows: %d' % changed)
    return redirect('translation_manager')


def i18n_dictionary(request, code):
    """window.ERP_I18N = {...}  (public: the login page can use it too)."""
    if code in ('ur', 'ar'):
        try:
            ver = svc.get_version()
            data = cache.get_or_set('i18n_dict:' + ver, svc.build_dictionary_json, 3600)
        except Exception:
            data = '{}'
    else:
        data = '{}'
    resp = HttpResponse('window.ERP_I18N=' + data + ';', content_type='application/javascript; charset=utf-8')
    resp['Cache-Control'] = 'public, max-age=3600'
    return resp


@require_POST
def i18n_collect(request):
    """Admin browsers report untranslated UI text (menu/button/heading words only)."""
    u = request.user
    if not (u.is_authenticated and (u.is_superuser or u.is_staff)):
        return JsonResponse({'ok': False}, status=403)
    try:
        items = json.loads(request.body.decode('utf-8') or '{}').get('items', [])
    except ValueError:
        return JsonResponse({'ok': False}, status=400)
    if not isinstance(items, list):
        return JsonResponse({'ok': False}, status=400)
    added = svc.record_missing(items)
    if added:
        svc.maybe_start_background()
    return JsonResponse({'ok': True, 'added': added})
