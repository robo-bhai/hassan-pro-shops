# app/module_roles.py
"""
Role-wise module access.

Module Settings (Settings > Modules) now has a "Roles" column: for every module you can pick which roles
(Django Groups: Owner, Manager, Salesman, Accountant, Warehouse ...) get that module.

Rules (one place, so sidebar + middleware agree):
  * Administrator (superuser)  -> always everything.
  * Owner group                -> always allowed (so the Owner can never lock himself out of a module).
  * No role selected for a module (default) -> every role gets it (nothing changes for existing installs).
  * Roles selected -> only users who are in one of those groups get the module; others see it hidden/blocked.
  * The On/Off switch still comes first: a module that is OFF is off for everybody.

Stored in SystemSetting:  module_roles_<key> = "manager,accountant"   (lower-case group names, comma separated)
"""
from django.core.cache import cache

ROLES_KEY = 'module_roles_%s'
CACHE_KEY = 'module_roles_map'
OWNER_GROUP = 'owner'


def list_roles():
    """All role names (Django Groups), Owner first. [{'name': 'Manager', 'key': 'manager'}, ...]"""
    from django.contrib.auth.models import Group
    names = list(Group.objects.order_by('name').values_list('name', flat=True))
    names.sort(key=lambda n: (n.lower() != OWNER_GROUP, n.lower()))
    return [{'name': n, 'key': n.lower()} for n in names]


def roles_map():
    """{module_key: [role_key, ...]} only for modules that have a role limit. 60 second cache."""
    data = cache.get(CACHE_KEY)
    if data is None:
        from app.models import SystemSetting
        data = {}
        for row in SystemSetting.objects.filter(setting_key__startswith='module_roles_'):
            roles = [r.strip().lower() for r in (row.setting_value or '').split(',') if r.strip()]
            if roles:
                data[row.setting_key[len('module_roles_'):]] = roles
        cache.set(CACHE_KEY, data, 60)
    return data


def shop_scope():
    """Role-scoped Shop Edition: {'roles': {..}, 'show': {..}} while it is ON for some roles, else {}."""
    data = cache.get('shop_scope')
    if data is None:
        from app.models import SystemSetting
        rows = dict(SystemSetting.objects.filter(
            setting_key__in=['shop_edition_on', 'shop_edition_roles', 'shop_edition_show']
        ).values_list('setting_key', 'setting_value'))
        roles = {r for r in (rows.get('shop_edition_roles') or '').split(',') if r}
        show = {r for r in (rows.get('shop_edition_show') or '').split(',') if r}
        data = {'roles': roles, 'show': show} if ('shop_edition_on' in rows and roles) else {}
        cache.set('shop_scope', data, 60)
    return data


def save_roles(module_key, role_keys, user=None):
    """Save the allowed roles of one module. Empty list = all roles."""
    from app.models import SystemSetting
    value = ','.join(sorted({r.strip().lower() for r in role_keys if r and r.strip()}))
    row, _ = SystemSetting.objects.get_or_create(setting_key=ROLES_KEY % module_key)
    row.setting_value = value
    if user is not None and getattr(user, 'is_authenticated', False):
        row.updated_by = user
    row.save()


def clear_cache():
    cache.delete(CACHE_KEY)
    cache.delete('shop_scope')


def user_role_keys(user):
    cached = getattr(user, '_module_role_keys', None)
    if cached is None:
        cached = {n.lower() for n in user.groups.values_list('name', flat=True)}
        try:
            user._module_role_keys = cached
        except Exception:
            pass
    return cached


def role_allows(user, key, rmap=None):
    """May this user's role(s) use module ``key``? (On/Off switch is checked separately.)"""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    scope = shop_scope()
    if scope and key not in scope['show'] and (user_role_keys(user) & scope['roles']):
        return False                      # role-scoped Shop Edition hides this module for this role
    rmap = roles_map() if rmap is None else rmap
    allowed = rmap.get(key)
    if not allowed:                       # no role limit -> everybody
        return True
    mine = user_role_keys(user)
    return OWNER_GROUP in mine or bool(mine & set(allowed))


def apply_roles(user, vis):
    """Return a copy of the visibility dict with modules hidden that this user's role may not use."""
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'is_superuser', False):
        return vis
    rmap = roles_map()
    if not rmap and not shop_scope():
        return vis
    out = dict(vis)
    for key, on in vis.items():
        if key != '_mode' and on and not role_allows(user, key, rmap):
            out[key] = False
    return out
