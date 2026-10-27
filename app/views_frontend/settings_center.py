# app/views_frontend/settings_center.py
"""
SETTINGS CENTER - all project settings in one place.

URL:  /settings/center/            (pehla allowed tab)
      /settings/center/<tab>/      (modules, shareholders, company, delivery, security, voice)

The list of tabs and fields is in `app/settings_catalog.py`. This view reads the catalog and builds the form,
validates and saves. Each tab form is saved separately, so saving one tab
never touches the settings of another tab.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from ..models import CompanyInfo, DeliverySettings, SecuritySettings, SystemSetting
from ..module_catalog import MODULE_GROUPS, get_module_catalog, get_module_keys
from ..settings_catalog import TAB_BY_KEY, TABS

logger = logging.getLogger(__name__)


_DEFAULT_CITY_CHARGES = {
    'karachi': 100, 'lahore': 120, 'islamabad': 150, 'rawalpindi': 150,
    'faisalabad': 130, 'multan': 140, 'peshawar': 180, 'quetta': 250, 'other': 200,
}


# ============================================================ access
def _allowed(user, access):
    if access == 'any':
        return True
    if user.is_superuser:
        return True
    if access == 'admin':
        return user.is_staff
    if access == 'owner':
        return user.groups.filter(name__in=['Owner', 'CEO']).exists()
    return False


# ============================================================ value conversion
def _fmt_decimal(d):
    """Decimal ko saaf string me (50.0 -> '50', 0.50 -> '0.5')."""
    d = d.normalize()
    return format(d, 'f')


def _coerce(field, post):
    """The value of one field from POST. Returns (value, error)."""
    name, ftype, label = field['name'], field['type'], field['label']

    if ftype == 'bool':
        return post.get(name) == 'on', None

    raw = (post.get(name) or '').strip()

    if ftype == 'select':
        allowed = [c[0] for c in field['choices']]
        if raw not in allowed:
            return None, '%s: sahi option chunein.' % label
        return raw, None

    if ftype in ('int', 'decimal'):
        if raw == '':
            return None, '%s: number likhein.' % label
        try:
            num = int(raw) if ftype == 'int' else Decimal(raw)
        except (ValueError, InvalidOperation):
            return None, '%s: enter a valid number.' % label
        if ftype == 'decimal' and not num.is_finite():
            return None, '%s: enter a valid number.' % label
        if 'min' in field and num < field['min']:
            return None, '%s: must be at least %s.' % (label, field['min'])
        if 'max' in field and num > field['max']:
            return None, '%s: must be at most %s.' % (label, field['max'])
        return num, None

    # text / textarea / email / url
    if field.get('required') and not raw:
        return None, '%s is required.' % label
    if field.get('max_len') and len(raw) > field['max_len']:
        return None, '%s: cannot be more than %s characters.' % (label, field['max_len'])
    if raw and ftype == 'email':
        try:
            validate_email(raw)
        except ValidationError:
            return None, '%s: enter a valid email.' % label
    if raw and ftype == 'url':
        try:
            URLValidator()(raw)
        except ValidationError:
            return None, '%s: enter a valid URL (with https://).' % label
    return raw, None


# ============================================================ stores
class _SystemStore(object):
    """SystemSetting table (key/value). Only for bool, number and select."""

    def load(self):
        return None

    def get(self, inst, f):
        default = f.get('default')
        if f['type'] == 'bool':
            return SystemSetting.get_bool(f['name'], bool(default))
        if f['type'] == 'select':
            return SystemSetting.get_value(f['name'], str(default))
        return SystemSetting.get_value(f['name'], str(default if default is not None else ''))

    def save(self, inst, values, user):
        for f in values['fields']:
            v = values['data'][f['name']]
            if isinstance(v, Decimal):
                v = _fmt_decimal(v)
            SystemSetting.set_value(f['name'], v, user)
        cache.delete('module_visibility')


class _ModelStore(object):
    """Ek singleton model (SecuritySettings / CompanyInfo / DeliverySettings)."""

    def __init__(self, loader, after_save=None, set_user=False):
        self._loader = loader
        self._after_save = after_save
        self._set_user = set_user

    def load(self):
        return self._loader()

    def get(self, inst, f):
        return getattr(inst, f['name'], f.get('default'))

    def save(self, inst, values, user):
        for f in values['fields']:
            v = values['data'][f['name']]
            setattr(inst, f['name'], v)
        if self._set_user:
            inst.updated_by = user
        values.get('before_save', lambda i: None)(inst)
        inst.save()
        if self._after_save:
            self._after_save()


def _load_company():
    return CompanyInfo.objects.first() or CompanyInfo()


def _load_delivery():
    obj = DeliverySettings.objects.filter(is_active=True).first()
    if obj is None:
        obj = DeliverySettings(city_charges=dict(_DEFAULT_CITY_CHARGES))
    return obj


_STORES = {
    'system': _SystemStore(),
    'security': _ModelStore(SecuritySettings.get_settings, set_user=True),
    'company': _ModelStore(_load_company),
    'delivery': _ModelStore(_load_delivery, after_save=lambda: cache.delete('delivery_settings')),
}


# ============================================================ special parts
def _modules_context():
    from ..context_processors import module_visibility, unit_enabled
    visible = module_visibility()
    rows = [{
        'id': m['key'], 'name': m['label'], 'icon': m['icon'],
        'description': m['description'], 'group': m['group'],
        'shop': unit_enabled(m['key'], 'shop'),
        'factory': unit_enabled(m['key'], 'factory'),
        'visible': visible.get(m['key'], True),
    } for m in get_module_catalog()]
    groups = [{'name': g, 'items': [r for r in rows if r['group'] == g]} for g in MODULE_GROUPS]
    return {'module_groups': [g for g in groups if g['items']], 'module_count': len(rows)}


def _save_modules(request):
    """The Shop / Factory switch of each module (unchecked = off is saved too)."""
    for k in get_module_keys():
        shop_on = request.POST.get('mode_shop_%s' % k) == 'on'
        factory_on = request.POST.get('mode_factory_%s' % k) == 'on'
        SystemSetting.set_value('mode_shop_%s' % k, shop_on, request.user)
        SystemSetting.set_value('mode_factory_%s' % k, factory_on, request.user)
        # old global switch in sync with the union (for old code)
        SystemSetting.set_value('show_%s_module' % k, shop_on or factory_on, request.user)
    cache.delete('module_visibility')


def _parse_city_charges(post):
    """(dict, errors). Format: {'karachi': 100.0, ..., 'other': 200.0}"""
    errors, charges = [], {}
    names = post.getlist('city_name[]')
    values = post.getlist('city_charge[]')
    for i, city in enumerate(names):
        key = city.strip().lower()
        if not key or i >= len(values):
            continue
        try:
            amount = float(values[i])
        except (TypeError, ValueError):
            errors.append('City "%s": enter a valid charge.' % key)
            continue
        if amount < 0 or amount != amount or amount in (float('inf'), float('-inf')):
            errors.append('City "%s": invalid charge.' % key)
            continue
        charges[key] = amount
    try:
        other = float(post.get('other_city_charge', '200'))
        if other < 0 or other != other or other in (float('inf'), float('-inf')):
            raise ValueError
    except (TypeError, ValueError):
        errors.append('Enter a valid charge for the other cities.')
        other = 200.0
    charges['other'] = other
    return charges, errors


def _city_context(inst):
    charges = inst.city_charges or {}
    cities = sorted(({'name': c, 'charge': v} for c, v in charges.items() if c != 'other'),
                    key=lambda x: x['name'])
    return {'city_list': cities, 'other_charge': charges.get('other', 200)}


def _resolve_links(tab):
    out = []
    for label, url_name in tab.get('links', []):
        try:
            out.append({'label': label, 'url': reverse(url_name)})
        except NoReverseMatch:
            continue
    return out


# ============================================================ form building
def _build_groups(tab, store, inst, posted=None, errors=None):
    """Prepares the fields group-wise for the template."""
    errors = errors or {}
    groups, index = [], {}
    for f in tab['fields']:
        if posted is not None:
            value = (posted.get(f['name']) == 'on') if f['type'] == 'bool' else posted.get(f['name'], '')
        else:
            value = store.get(inst, f)
        if value is None:
            value = ''
        ctx = dict(f)
        ctx['value'] = value
        ctx['error'] = errors.get(f['name'])
        if f['type'] == 'select':
            ctx['options'] = [{'value': v, 'label': l, 'selected': str(value) == v} for v, l in f['choices']]
        if f['type'] == 'decimal':
            ctx['step'] = 'any'
        elif f['type'] == 'int':
            ctx['step'] = '1'
        gname = f.get('group', 'General')
        if gname not in index:
            index[gname] = {'name': gname, 'fields': []}
            groups.append(index[gname])
        index[gname]['fields'].append(ctx)
    return groups


# ============================================================ main view
@login_required
def settings_center(request, tab=None):
    user = request.user
    visible_tabs = [t for t in TABS if _allowed(user, t['access'])]
    if not visible_tabs:
        messages.error(request, 'Access denied! You do not have permission to view settings.')
        return redirect('dashboard')

    tab_def = TAB_BY_KEY.get(tab) if tab else visible_tabs[0]
    if tab_def is None or not _allowed(user, tab_def['access']):
        messages.error(request, 'Access denied! You do not have permission for this tab.')
        return redirect('settings_center')

    store = _STORES.get(tab_def['store'])
    inst = store.load() if store else None
    special = tab_def.get('special')

    posted, errors, error_list = None, {}, []

    if request.method == 'POST' and store is not None:
        data, fields_ok = {}, []
        for f in tab_def['fields']:
            value, err = _coerce(f, request.POST)
            if err:
                errors[f['name']] = err
                error_list.append(err)
            else:
                data[f['name']] = value
                fields_ok.append(f)

        before_save = None
        if special == 'city_charges':
            charges, city_errors = _parse_city_charges(request.POST)
            error_list.extend(city_errors)

            def before_save(i, _c=charges):
                i.city_charges = _c
                i.is_active = True

        # Logo goes last: if the other fields are wrong, the old logo file is not deleted
        if special == 'logo' and not error_list:
            try:
                from .dashboard import _apply_company_logo
                _apply_company_logo(request, inst)
            except ValueError as exc:
                error_list.append(str(exc))
            except Exception as exc:  # PIL is not installed, etc.
                logger.error('Logo apply error: %s', exc)
                error_list.append('Logo lagane me masla aaya.')

        if not error_list:
            try:
                with transaction.atomic():
                    values = {'fields': fields_ok, 'data': data}
                    if before_save:
                        values['before_save'] = before_save
                    store.save(inst, values, user)
                    if special == 'modules':
                        _save_modules(request)
                messages.success(request, '✅ %s settings saved.' % tab_def['label'])
                return redirect('settings_center_tab', tab=tab_def['key'])
            except Exception as exc:
                logger.error('Settings save error (%s): %s', tab_def['key'], exc)
                error_list.append('Could not save. Please try again.')

        for e in error_list:
            messages.error(request, '❌ ' + e)
        posted = request.POST  # on error, show the user's entered values again

    context = {
        'company_name': getattr(CompanyInfo.objects.first(), 'name', None) or 'ERP System',
        'tabs': [{'key': t['key'], 'label': t['label'], 'icon': t['icon'], 'active': t['key'] == tab_def['key']}
                 for t in visible_tabs],
        'tab': tab_def,
        'groups': _build_groups(tab_def, store, inst, posted, errors) if store else [],
        'links': _resolve_links(tab_def),
        'special': special,
    }
    if special == 'modules':
        context.update(_modules_context())
    elif special == 'city_charges':
        context.update(_city_context(inst))
    elif special == 'logo':
        context['company'] = inst if inst.pk else None
    return render(request, 'settings/center.html', context)


# ============================================================ purane URLs -> Settings Center
def _legacy_redirect(tab_key):
    @login_required
    def view(request, *args, **kwargs):
        return redirect('settings_center_tab', tab=tab_key)
    return view


module_settings_redirect = _legacy_redirect('modules')
company_settings_redirect = _legacy_redirect('company')
delivery_settings_redirect = _legacy_redirect('delivery')
security_settings_redirect = _legacy_redirect('security')
voice_settings_redirect = _legacy_redirect('voice')
