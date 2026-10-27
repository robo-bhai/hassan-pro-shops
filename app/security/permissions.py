"""Permission-matrix enforcement: decorators + helpers.

The Permission Matrix screen (Users -> Permission Matrix) stores, per role, which matrix keys
are granted.  This module is what actually *enforces* them on the views.

Usage
-----
    from ...security.permissions import perm_required

    @perm_required('view_sales')                       # login + permission (any one of the keys)
    def sale_list(request): ...

    @perm_required('edit_sales', 'manage_orders')      # any of
    @perm_required('view_sales', 'view_reports', require_all=True)   # all of

    @perm_required('view_cash', post='manage_cash')    # GET needs view_cash, POST/PUT/DELETE needs manage_cash

Stacking with ``@login_required`` is fine (and is what the codebase does):

    @login_required
    @perm_required('delete_sales')
    def sale_delete(request, pk): ...

In templates:

    {% load erp_filters %}
    {% if request.user|can:"create_sales" %} ... {% endif %}

Who gets what
-------------
* Superuser                -> everything.
* Built-in / custom roles  -> what the matrix saved for the role's group; until the matrix is
  saved for a role, ``ROLE_DEFAULTS`` from ``permission_catalog`` apply.
* Everybody logged in      -> ``BASIC_KEYS`` (the dashboard).
* A user in several role groups gets the union of them.

Settings
--------
``PERMISSION_MATRIX_MODE``:  'enforce' (default) | 'warn' (log the denial but let the user in -
handy for a first roll-out, check the log for "PERMISSION WOULD DENY") | 'off'.
"""
import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Permission
from django.contrib.auth.views import redirect_to_login
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

from .permission_catalog import ALL_KEYS, BASIC_KEYS, MATRIX_KEYS, ROLE_DEFAULTS, SAVED_SENTINEL

logger = logging.getLogger('app.permissions')

# Django Group name of the built-in roles  ->  role key used in ROLE_DEFAULTS.
BUILTIN_GROUP_ROLES = {
    'Owner': 'owner',
    'Store Manager': 'manager',
    'Accountant': 'accountant',
    'Salesman': 'salesman',
    'Warehouse Staff': 'warehouse',
}

_CACHE_ATTR = '_matrix_perm_cache'


def _matrix_content_type():
    # Must be the same content type the matrix save API uses (see views_frontend/people/users.py).
    from django.contrib.auth.models import Group
    return ContentType.objects.get_for_model(Group)


def get_permission_mode():
    mode = getattr(settings, 'PERMISSION_MATRIX_MODE', 'enforce')
    return mode if mode in ('enforce', 'warn', 'off') else 'enforce'


def get_user_perms(user):
    """frozenset of matrix keys the user holds. Cached on the user object (= once per request)."""
    if user is None or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return frozenset()
    cached = getattr(user, _CACHE_ATTR, None)
    if cached is not None:
        return cached

    if user.is_superuser:
        perms = frozenset(ALL_KEYS)
    else:
        perms = set(BASIC_KEYS)
        groups = dict(user.groups.values_list('pk', 'name'))
        if groups:
            stored = {}
            rows = (Permission.objects
                    .filter(content_type=_matrix_content_type(), group__in=list(groups),
                            codename__in=MATRIX_KEYS | {SAVED_SENTINEL})
                    .values_list('group__name', 'codename'))
            for gname, code in rows:
                stored.setdefault(gname, set()).add(code)
            for gname in groups.values():
                saved = stored.get(gname)
                if saved:                      # the matrix was saved for this role: the DB wins
                    perms |= saved & MATRIX_KEYS
                else:                          # never saved: built-in defaults (custom roles: nothing)
                    role = BUILTIN_GROUP_ROLES.get(gname)
                    if role in ROLE_DEFAULTS:
                        perms |= set(ROLE_DEFAULTS[role][0])
        perms = frozenset(perms)

    try:
        setattr(user, _CACHE_ATTR, perms)
    except Exception:                          # e.g. a lazy object that refuses attributes
        pass
    return perms


def has_matrix_perm(user, *keys, require_all=False):
    """True if the user holds any (or, with ``require_all``, every) one of the keys."""
    if not keys:
        return True
    held = get_user_perms(user)
    return all(k in held for k in keys) if require_all else any(k in held for k in keys)


def clear_perm_cache(user):
    """Forget the per-request cache (use after changing a user's roles inside the same request)."""
    if hasattr(user, _CACHE_ATTR):
        delattr(user, _CACHE_ATTR)


def _wants_json(request):
    return (request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('accept', '')
            or request.path.startswith(('/ajax/', '/api/')))


def _deny(request, keys, message):
    if _wants_json(request):
        return JsonResponse({'success': False, 'message': message, 'required': list(keys)}, status=403)
    match = getattr(request, 'resolver_match', None)
    if match is not None and match.url_name == 'dashboard':
        raise PermissionDenied(message)         # would loop: dashboard -> dashboard
    messages.error(request, message)
    return redirect('dashboard')


SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')


def perm_required(*keys, require_all=False, post=None, message=None):
    """Decorator: the user must be logged in AND hold a matrix permission.

    ``keys``  matrix keys (see ``permission_catalog``); a typo fails at import time, not at 3 a.m.
    ``post``  optional key (or tuple of keys, any-of) that is *additionally* required for unsafe
              methods (POST/PUT/PATCH/DELETE). For pages that show data on GET and change it on
              POST: ``@perm_required('view_cash', post='manage_cash')``.
    """
    if not keys:
        raise ImproperlyConfigured('perm_required() needs at least one permission key.')
    post_keys = (post,) if isinstance(post, str) else tuple(post or ())
    unknown = [k for k in keys + post_keys if k not in MATRIX_KEYS]
    if unknown:
        raise ImproperlyConfigured('perm_required(): unknown permission key(s) %s. '
                                   'Add them to security/permission_catalog.py.' % ', '.join(unknown))
    deny_msg = message or 'Access denied! You do not have permission for this action.'

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if _wants_json(request):
                    return JsonResponse({'success': False, 'message': 'Login required.'}, status=401)
                return redirect_to_login(request.get_full_path())
            mode = get_permission_mode()
            allowed = has_matrix_perm(user, *keys, require_all=require_all)
            if allowed and post_keys and request.method not in SAFE_METHODS:
                allowed = has_matrix_perm(user, *post_keys)
            if mode != 'off' and not allowed:
                if mode == 'warn':
                    logger.warning('PERMISSION WOULD DENY: user=%s view=%s needs=%s',
                                   user.get_username(), view.__name__, keys)
                else:
                    logger.info('Permission denied: user=%s view=%s needs=%s',
                                user.get_username(), view.__name__, keys)
                    return _deny(request, keys, deny_msg)
            return view(request, *args, **kwargs)
        wrapper.required_permissions = tuple(keys)       # introspection (tests / audit command)
        wrapper.required_post_permissions = post_keys
        return wrapper
    return decorator
