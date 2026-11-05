"""Frontend views: User Management.

Professional rewrite. What changed compared to the old version:

* One source of truth for roles (``UM_ROLES``) instead of 5 copy-pasted if/elif chains.
* One access decorator (``_um_admin_only``) instead of the check repeated in every view.
* No N+1 queries: groups are prefetched, roles are resolved in Python.
* State-changing actions (delete / toggle / bulk) are POST-only (CSRF safe).
* Privilege-escalation guards: only a superuser can create/edit/delete/reset a superuser,
  nobody can lock themselves out, and the last active administrator is always protected.
* Passwords are validated with Django's AUTH_PASSWORD_VALIDATORS (not just ``len >= 6``).
* Every important action is written to ``AccessLog`` (audit trail).
* The permission matrix can only touch its own known permission keys (it used to be able to
  grant real Django permissions such as ``add_permission`` by codename) and only a
  superuser may save it.
* Internal exception text is no longer shown to the browser.

URL names, template names and template context keys are unchanged, except that the
edit / reset-password pages now receive ``target_user`` (the old ``user`` key shadowed the
logged-in user in base.html).
"""
from ...models import *  # noqa: F401,F403  (project convention)
import csv
import json
import logging
import re
import zlib
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now

from ...models import CompanyInfo
from ...security.permissions import get_permission_mode, has_matrix_perm

logger = logging.getLogger(__name__)


# =====================================================================================
# Role catalogue  (single source of truth)
# =====================================================================================
# key   : value used in forms / URLs / filters
# label : text shown in the UI
# group : django Group name that represents the role (None = no group)
# icon  : bootstrap icon class
UM_ROLES = {
    'admin':      {'label': 'Administrator',   'group': None,              'icon': 'bi-shield-lock'},
    'owner':      {'label': 'Owner',           'group': 'Owner',           'icon': 'bi-building'},
    'manager':    {'label': 'Store Manager',   'group': 'Store Manager',   'icon': 'bi-people'},
    'accountant': {'label': 'Accountant',      'group': 'Accountant',      'icon': 'bi-calculator'},
    'salesman':   {'label': 'Salesman',        'group': 'Salesman',        'icon': 'bi-person-badge'},
    'warehouse':  {'label': 'Warehouse Staff', 'group': 'Warehouse Staff', 'icon': 'bi-box'},
    'staff':      {'label': 'Staff',           'group': None,              'icon': 'bi-person'},
}
# Resolution order when a user somehow has several role groups (most powerful first).
UM_ROLE_ORDER = ['admin', 'owner', 'manager', 'accountant', 'salesman', 'warehouse', 'staff']
UM_ASSIGNABLE = [k for k in UM_ROLE_ORDER if k != 'staff']
UM_ROLE_GROUP_NAMES = {r['group'] for r in UM_ROLES.values() if r['group']}

# Custom roles (added from the UI) are plain Django Groups whose name starts with this prefix.
# No new model / migration is needed; the prefix keeps them apart from any other Group.
UM_CUSTOM_PREFIX = 'Role: '
UM_CUSTOM_KEY = 'custom_'            # role key = custom_<group pk>
UM_CUSTOM_ICON = 'bi-tag'
UM_CUSTOM_NAME_RE = re.compile(r'^\w[\w .&()/-]{1,49}$')

# Built-in roles an Administrator may delete. 'admin' (full access) and 'staff' (the default
# for a user without any role) are always kept. Deleted keys are remembered in SystemSetting.
UM_DELETABLE = ('owner', 'manager', 'accountant', 'salesman', 'warehouse')
UM_DELETED_SETTING = 'um_deleted_roles'
# key -> (bootstrap colour, card title, card description) for the role picker on create/edit.
UM_ROLE_CARD = {
    'admin':      ('danger',    'Administrator', 'Full system access'),
    'owner':      ('primary',   'Owner',         'All permissions'),
    'manager':    ('info',      'Store Manager', 'Manage operations'),
    'salesman':   ('success',   'Salesman',      'Sales only'),
    'accountant': ('warning',   'Accountant',    'Financial access'),
    'warehouse':  ('secondary', 'Warehouse',     'Inventory access'),
}

UM_USERNAME_RE = re.compile(r'^[\w.@+-]{3,150}$')
UM_PAGE_SIZE = 25
UM_BULK_LIMIT = 200
UM_AVATAR_COLORS = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b', '#fa709a', '#f6a23d', '#2fb5a3']


# =====================================================================================
# Helpers
# =====================================================================================
def _um_company_name():
    info = CompanyInfo.objects.first()
    return info.name if info else 'ERP System'


def _um_is_manager(user):
    """Who may open the User Management screens: active superuser or Owner."""
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.groups.filter(name='Owner').exists()
    )


def _um_custom_label(group_name):
    return group_name[len(UM_CUSTOM_PREFIX):]


def _um_custom_group_by_key(key):
    """Group behind a ``custom_<pk>`` role key, or None."""
    if not isinstance(key, str) or not key.startswith(UM_CUSTOM_KEY):
        return None
    try:
        pk = int(key[len(UM_CUSTOM_KEY):])
    except ValueError:
        return None
    return Group.objects.filter(pk=pk, name__startswith=UM_CUSTOM_PREFIX).first()


def _um_custom_roles():
    """Custom roles for the UI: [{id, key, label, group, icon, user_count, perm_count}]."""
    groups = list(Group.objects.filter(name__startswith=UM_CUSTOM_PREFIX)
                  .annotate(user_count=Count('user')).order_by('name'))
    stored = _um_stored_matrix([g.name for g in groups]) if groups else {}
    return [{
        'id': g.pk, 'key': f'{UM_CUSTOM_KEY}{g.pk}', 'label': _um_custom_label(g.name),
        'group': g.name, 'icon': UM_CUSTOM_ICON, 'user_count': g.user_count,
        'perm_count': len(stored.get(g.name, ())),
    } for g in groups]


def _um_deleted_builtin():
    """Keys of built-in roles an Administrator has deleted."""
    raw = SystemSetting.get_value(UM_DELETED_SETTING, '') or ''
    return {k for k in raw.split(',') if k in UM_DELETABLE}


def _um_set_deleted_builtin(keys, user=None):
    SystemSetting.set_value(UM_DELETED_SETTING, ','.join(sorted(keys)), user=user)


def _um_role_cards():
    """Role picker cards for create/edit: built-ins that still exist, then custom roles."""
    deleted = _um_deleted_builtin()
    cards = [{'key': k, 'label': title, 'icon': UM_ROLES[k]['icon'], 'color': color, 'desc': desc}
             for k, (color, title, desc) in UM_ROLE_CARD.items() if k not in deleted]
    cards += [{'key': r['key'], 'label': r['label'], 'icon': r['icon'], 'color': 'dark', 'desc': 'Custom role'}
              for r in _um_custom_roles()]
    return cards


def _um_builtin_roles():
    """Built-in roles for the Manage Roles popup (with user counts / deleted state)."""
    deleted = _um_deleted_builtin()
    counts = dict(Group.objects.filter(name__in=UM_ROLE_GROUP_NAMES)
                  .annotate(n=Count('user')).values_list('name', 'n'))
    rows = []
    for key in UM_ROLE_ORDER:
        meta = UM_ROLES[key]
        if key == 'admin':
            users_n = User.objects.filter(is_superuser=True).count()
        elif meta['group']:
            users_n = counts.get(meta['group'], 0)
        else:
            users_n = None
        rows.append({'key': key, 'label': meta['label'], 'icon': meta['icon'], 'user_count': users_n,
                     'deletable': key in UM_DELETABLE, 'deleted': key in deleted})
    return rows


def _um_valid_role(role):
    """A role the form may assign: a built-in assignable role or an existing custom role."""
    if role in UM_ASSIGNABLE:
        return role not in _um_deleted_builtin()
    return _um_custom_group_by_key(role) is not None


def _um_role_meta(role):
    """{'label', 'group', 'icon'} for a built-in or custom role key (None if unknown)."""
    if role in UM_ROLES:
        return UM_ROLES[role]
    group = _um_custom_group_by_key(role)
    if group:
        return {'label': _um_custom_label(group.name), 'group': group.name, 'icon': UM_CUSTOM_ICON}
    return None


def _um_role_info(user):
    """(key, meta) of a user. Uses prefetched groups when available (no extra query)."""
    if user.is_superuser:
        return 'admin', UM_ROLES['admin']
    groups = list(user.groups.all())
    names = {g.name for g in groups}
    for key in UM_ROLE_ORDER:
        group = UM_ROLES[key]['group']
        if group and group in names:
            return key, UM_ROLES[key]
    for g in sorted(groups, key=lambda g: g.name):
        if g.name.startswith(UM_CUSTOM_PREFIX):
            return f'{UM_CUSTOM_KEY}{g.pk}', {
                'label': _um_custom_label(g.name), 'group': g.name, 'icon': UM_CUSTOM_ICON}
    return 'staff', UM_ROLES['staff']


def _um_role_of(user):
    """Role key of a user."""
    return _um_role_info(user)[0]


def _um_decorate(user):
    """Attach role / role_display / role_icon / role_css (used by list.html)."""
    key, meta = _um_role_info(user)
    user.role = key
    user.role_css = 'custom' if key.startswith(UM_CUSTOM_KEY) else key
    user.role_display = meta['label']
    user.role_icon = meta['icon']
    return user


def _um_avatar_color(username):
    # zlib.crc32 is stable across processes, unlike hash() which is randomised per run.
    return UM_AVATAR_COLORS[zlib.crc32(username.encode('utf-8')) % len(UM_AVATAR_COLORS)]


def _um_fmt_dt(value, empty=''):
    return value.strftime('%Y-%m-%d %I:%M %p') if value else empty


def _um_client_ip(request):
    try:
        from ...utils.security import get_client_ip
        return get_client_ip(request) or '0.0.0.0'
    except Exception:  # pragma: no cover - logging must never break a request
        return request.META.get('REMOTE_ADDR') or '0.0.0.0'


def _um_audit(request, action, target=None, **details):
    """Write an audit record. Failure to log must never break the user's action."""
    try:
        payload = dict(details)
        if target is not None:
            payload.update(target_id=target.pk, target_username=target.username)
        AccessLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            module='user_management',
            details=payload,
            ip_address=_um_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:500],
            session_id=((request.session.session_key or '')[:100]) if hasattr(request, 'session') else '',
            is_sensitive=True,
        )
    except Exception:
        logger.exception('Could not write user-management audit log (%s)', action)


def _um_admin_only(view=None, *, json_response=False, post_only=False, perm=None):
    """Decorator: login + Owner/superuser check (+ optional POST-only).

    ``json_response=True`` returns JSON errors (for the AJAX endpoints) instead of redirects.
    ``perm`` is an extra Permission-Matrix key (or tuple, any-of) the user must hold, e.g.
    ``@_um_admin_only(perm='manage_users')``. Owners / superusers hold all of them by default.
    Works both as ``@_um_admin_only`` and ``@_um_admin_only(post_only=True)``.
    """
    perm_keys = (perm,) if isinstance(perm, str) else tuple(perm or ())
    def decorator(func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if post_only and request.method != 'POST':
                if json_response:
                    return JsonResponse({'success': False, 'message': 'Invalid method!'}, status=405)
                messages.error(request, 'Invalid request method.')
                return redirect('user_list')
            if not _um_is_manager(request.user):
                if json_response:
                    return JsonResponse({'success': False, 'message': 'Access denied!'}, status=403)
                messages.error(request, 'Access denied! Only administrators can manage users.')
                return redirect('dashboard')
            if perm_keys and get_permission_mode() == 'enforce' and not has_matrix_perm(request.user, *perm_keys):
                if json_response:
                    return JsonResponse({'success': False, 'message': 'Access denied!'}, status=403)
                messages.error(request, 'Access denied! Your role does not have this permission.')
                return redirect('dashboard')
            return func(request, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator(view) if view else decorator


def _um_active_superusers():
    return User.objects.filter(is_superuser=True, is_active=True)


def _um_can_touch(actor, target):
    """Only a superuser may manage another superuser."""
    return actor.is_superuser or not target.is_superuser


def _um_would_orphan_admin(targets_qs):
    """True if deactivating/deleting/demoting `targets_qs` would leave zero active superusers."""
    return not _um_active_superusers().exclude(pk__in=targets_qs.values('pk')).exists()


def _um_set_role(user, role):
    """Apply a role: swap only the *role* groups, keep any other group the user has."""
    stale = list(user.groups.filter(Q(name__in=UM_ROLE_GROUP_NAMES) | Q(name__startswith=UM_CUSTOM_PREFIX)))
    if stale:
        user.groups.remove(*stale)
    group_name = (_um_role_meta(role) or {}).get('group')
    if group_name:
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
    if role == 'admin':
        user.is_superuser = True
        user.is_staff = True
    else:
        user.is_superuser = False


def _um_validate_identity(username, email, *, exclude_pk=None, check_email=True):
    """Return a list of error strings for username / email."""
    errors = []
    if not username or not UM_USERNAME_RE.match(username):
        errors.append('Username must be 3-150 characters (letters, digits and . @ + - _ only).')
    else:
        qs = User.objects.filter(username__iexact=username)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            errors.append('Username already exists!')
    if email:
        try:
            validate_email(email)
        except ValidationError:
            errors.append('Enter a valid email address.')
        else:
            if check_email:
                qs = User.objects.filter(email__iexact=email)
                if exclude_pk:
                    qs = qs.exclude(pk=exclude_pk)
                if qs.exists():
                    errors.append('This email is already used by another user.')
    return errors


def _um_validate_new_password(password, confirm, user=None):
    if not password:
        return ['Password is required.']
    errors = []
    if password != confirm:
        errors.append('Passwords do not match!')
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        errors.extend(exc.messages)
    return errors


def _um_flash_errors(request, errors):
    for err in errors:
        messages.error(request, f'❌ {err}')


def _um_split_name(full_name, fallback=('', '')):
    full_name = (full_name or '').strip()
    if not full_name:
        return fallback
    parts = full_name.split(None, 1)
    return parts[0][:150], (parts[1][:150] if len(parts) > 1 else '')


def _um_staff_users():
    """Staff accounts only: customer-portal logins are managed elsewhere."""
    return User.objects.filter(customer_profile__isnull=True)


def _um_base_queryset():
    return _um_staff_users().prefetch_related('groups').order_by('-is_active', 'username')


def _um_apply_filters(qs, search, role_filter, status_filter):
    if search:
        qs = qs.filter(
            Q(username__icontains=search) | Q(email__icontains=search) |
            Q(first_name__icontains=search) | Q(last_name__icontains=search)
        )
    if role_filter == 'admin':
        qs = qs.filter(is_superuser=True)
    elif role_filter == 'staff':
        qs = qs.filter(is_superuser=False).exclude(
            Q(groups__name__in=UM_ROLE_GROUP_NAMES) | Q(groups__name__startswith=UM_CUSTOM_PREFIX))
    elif role_filter in UM_ROLES and UM_ROLES[role_filter]['group']:
        qs = qs.filter(is_superuser=False, groups__name=UM_ROLES[role_filter]['group'])
    elif role_filter.startswith(UM_CUSTOM_KEY):
        group = _um_custom_group_by_key(role_filter)
        qs = qs.filter(is_superuser=False, groups=group) if group else qs.none()
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)
    return qs.distinct()


def _um_csv_safe(value):
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


# =====================================================================================
# Create / Edit / Delete / Toggle / Reset password
# =====================================================================================
@_um_admin_only(perm='create_users')
def user_create(request):
    """Create a new user with a role."""
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        confirm = request.POST.get('confirm_password') or ''
        email = (request.POST.get('email') or '').strip()
        role = request.POST.get('role') or ''
        is_active = request.POST.get('is_active') == 'on'
        first_name, last_name = _um_split_name(request.POST.get('full_name', ''))

        errors = []
        if not _um_valid_role(role):
            errors.append('Please select a valid role.')
        if role == 'admin' and not request.user.is_superuser:
            errors.append('Only an Administrator can create another Administrator.')
        errors += _um_validate_identity(username, email)
        errors += _um_validate_new_password(
            password, confirm,
            User(username=username, email=email, first_name=first_name, last_name=last_name),
        )
        if errors:
            _um_flash_errors(request, errors)
            return redirect('user_create')

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                    first_name=first_name, last_name=last_name, is_active=is_active,
                )
                _um_set_role(user, role)
                user.save()
        except IntegrityError:
            messages.error(request, '❌ Username already exists!')
            return redirect('user_create')
        except Exception:
            logger.exception('user_create failed')
            messages.error(request, '❌ Could not create the user. Please try again.')
            return redirect('user_create')

        _um_audit(request, 'user_created', user, role=role, is_active=is_active)
        messages.success(request, f'✅ User "{user.username}" created successfully!')
        return redirect('user_list')

    return render(request, 'users/user_create.html', {
        'company_name': _um_company_name(),
        'custom_roles': _um_custom_roles(),
        'role_cards': _um_role_cards(),
    })


@_um_admin_only(perm='manage_users')
def user_edit(request, pk):
    """Edit user details."""
    target = get_object_or_404(User.objects.prefetch_related('groups'), pk=pk)

    if not _um_can_touch(request.user, target):
        messages.error(request, 'Only an Administrator can edit another Administrator.')
        return redirect('user_list')

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        role = request.POST.get('role') or ''
        is_active = request.POST.get('is_active') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        first_name, last_name = _um_split_name(
            request.POST.get('full_name', ''), fallback=(target.first_name, target.last_name)
        )
        is_self = target.pk == request.user.pk
        old_role = _um_role_of(target)

        errors = []
        if not _um_valid_role(role):
            errors.append('Please select a valid role.')
        if role == 'admin' and old_role != 'admin' and not request.user.is_superuser:
            errors.append('Only an Administrator can promote someone to Administrator.')
        errors += _um_validate_identity(
            username, email, exclude_pk=target.pk,
            check_email=(email.lower() != (target.email or '').lower()),
        )
        if is_self and not is_active:
            errors.append('You cannot deactivate your own account.')
        if is_self and old_role == 'admin' and role != 'admin':
            errors.append('You cannot remove your own Administrator role.')
        if target.is_superuser and (role != 'admin' or not is_active) \
                and _um_would_orphan_admin(User.objects.filter(pk=target.pk)):
            errors.append('At least one active Administrator must remain.')
        if errors:
            _um_flash_errors(request, errors)
            return redirect('user_edit', pk=pk)

        try:
            with transaction.atomic():
                target.username = username
                target.email = email
                target.first_name = first_name
                target.last_name = last_name
                target.is_active = is_active
                target.is_staff = is_staff
                _um_set_role(target, role)
                target.save()
        except IntegrityError:
            messages.error(request, '❌ Username already exists!')
            return redirect('user_edit', pk=pk)
        except Exception:
            logger.exception('user_edit failed (pk=%s)', pk)
            messages.error(request, '❌ Could not update the user. Please try again.')
            return redirect('user_edit', pk=pk)

        _um_audit(request, 'user_updated', target, old_role=old_role, new_role=role, is_active=is_active)
        messages.success(request, f'✅ User "{target.username}" updated successfully!')
        return redirect('user_list')

    return render(request, 'users/user_edit.html', {
        'company_name': _um_company_name(),
        'target_user': target,
        'user_role': _um_role_of(target),
        'custom_roles': _um_custom_roles(),
        'role_cards': _um_role_cards(),
    })


@_um_admin_only(post_only=True, perm='delete_users')
def user_delete(request, pk):
    """Delete a user (POST only)."""
    target = get_object_or_404(User, pk=pk)

    if target.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account!')
        return redirect('user_list')
    if not _um_can_touch(request.user, target):
        messages.error(request, 'Only an Administrator can delete another Administrator.')
        return redirect('user_list')
    if target.is_superuser and _um_would_orphan_admin(User.objects.filter(pk=target.pk)):
        messages.error(request, 'At least one active Administrator must remain.')
        return redirect('user_list')

    username = target.username
    try:
        with transaction.atomic():
            target.delete()
    except (ProtectedError, IntegrityError):
        messages.error(
            request,
            f'❌ "{username}" has linked records and cannot be deleted. Deactivate the user instead.',
        )
        return redirect('user_list')

    _um_audit(request, 'user_deleted', username=username, deleted_id=pk)
    messages.success(request, f'🗑️ User "{username}" deleted successfully!')
    return redirect('user_list')


@_um_admin_only(post_only=True, perm='manage_users')
def user_toggle_status(request, pk):
    """Activate / deactivate a user (POST only)."""
    target = get_object_or_404(User, pk=pk)

    if target.pk == request.user.pk:
        messages.error(request, 'You cannot change your own status!')
        return redirect('user_list')
    if not _um_can_touch(request.user, target):
        messages.error(request, 'Only an Administrator can change another Administrator.')
        return redirect('user_list')
    if target.is_active and target.is_superuser \
            and _um_would_orphan_admin(User.objects.filter(pk=target.pk)):
        messages.error(request, 'At least one active Administrator must remain.')
        return redirect('user_list')

    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])

    status = 'activated' if target.is_active else 'deactivated'
    _um_audit(request, f'user_{status}', target)
    messages.success(request, f'✅ User "{target.username}" has been {status}!')
    return redirect('user_list')


@_um_admin_only(perm='manage_users')
def user_reset_password(request, pk):
    """Reset a user's password."""
    target = get_object_or_404(User, pk=pk)

    if not _um_can_touch(request.user, target):
        messages.error(request, "Only an Administrator can reset another Administrator's password.")
        return redirect('user_list')

    if request.method == 'POST':
        password = request.POST.get('password') or ''
        confirm = request.POST.get('confirm_password') or ''
        errors = _um_validate_new_password(password, confirm, user=target)
        if errors:
            _um_flash_errors(request, errors)
            return redirect('user_reset_password', pk=pk)

        target.set_password(password)  # also invalidates that user's existing sessions
        target.save(update_fields=['password'])
        _um_audit(request, 'password_reset', target)
        messages.success(request, f'✅ Password reset for "{target.username}" successfully!')
        return redirect('user_list')

    return render(request, 'users/user_reset_password.html', {
        'company_name': _um_company_name(),
        'target_user': target,
    })


# =====================================================================================
# Custom roles: add / delete  (built-in roles are protected)
# =====================================================================================
def _um_reserved_role_names():
    names = set()
    for key, meta in UM_ROLES.items():
        names.update({key, meta['label'].lower(), (meta['group'] or '').lower()})
    names.update({'admin', 'administrator', 'superuser'})
    names.discard('')
    return {n.lower() for n in names}


def _um_roles_redirect():
    from django.urls import reverse
    return redirect(f"{reverse('user_list')}?manage_roles=1")


@_um_admin_only(post_only=True, perm='manage_roles')
def role_create(request):
    """Add a custom role (POST only)."""
    name = ' '.join((request.POST.get('name') or '').split())
    if not UM_CUSTOM_NAME_RE.match(name):
        messages.error(request, 'Role name must be 2-50 characters (letters, digits, space and . & ( ) / - only).')
        return _um_roles_redirect()
    if name.lower() in _um_reserved_role_names():
        messages.error(request, f'"{name}" is a built-in role name. Choose a different name.')
        return _um_roles_redirect()

    full_name = UM_CUSTOM_PREFIX + name
    if Group.objects.filter(name__iexact=full_name).exists():
        messages.error(request, f'Role "{name}" already exists.')
        return _um_roles_redirect()

    perm_keys = sorted({k for k in request.POST.getlist('permissions') if k in UM_MATRIX_KEYS})
    can_set_perms = request.user.is_superuser
    try:
        with transaction.atomic():
            group = Group.objects.create(name=full_name)
            if perm_keys and can_set_perms:
                ct = _um_matrix_ct()
                for key in perm_keys:
                    perm, _ = Permission.objects.get_or_create(
                        codename=key, content_type=ct,
                        defaults={'name': key.replace('_', ' ').title()[:255]},
                    )
                    group.permissions.add(perm)
    except IntegrityError:
        messages.error(request, f'Role "{name}" already exists.')
        return _um_roles_redirect()

    saved = len(perm_keys) if can_set_perms else 0
    _um_audit(request, 'role_created', role=name, group_id=group.pk, permissions=saved)
    if perm_keys and not can_set_perms:
        messages.warning(request, f'Role "{name}" added without permissions: only an Administrator can set permissions.')
    else:
        messages.success(request, f'✅ Role "{name}" added with {saved} permission(s). You can now assign it to users.')
    return _um_roles_redirect()


@_um_admin_only(post_only=True, perm='manage_roles')
def role_delete(request, pk):
    """Delete a custom role (POST only). Built-in roles and roles still in use are refused."""
    group = Group.objects.filter(pk=pk, name__startswith=UM_CUSTOM_PREFIX).first()
    if group is None:
        messages.error(request, 'Role not found. Built-in roles cannot be deleted.')
        return _um_roles_redirect()

    label = _um_custom_label(group.name)
    in_use = group.user_set.count()
    if in_use:
        messages.error(
            request,
            f'❌ Role "{label}" is still assigned to {in_use} user(s). Change their role first, then delete it.',
        )
        return _um_roles_redirect()

    group.delete()
    _um_audit(request, 'role_deleted', role=label, group_id=pk)
    messages.success(request, f'🗑️ Role "{label}" deleted.')
    return _um_roles_redirect()


@_um_admin_only(post_only=True, perm='manage_roles')
def role_delete_builtin(request, key):
    """Delete (hide) a built-in role (POST, Administrator only). 'admin' and 'staff' are always kept."""
    if not request.user.is_superuser:
        messages.error(request, 'Only an Administrator can delete built-in roles.')
        return _um_roles_redirect()
    if key not in UM_DELETABLE:
        messages.error(request, 'The Administrator and Staff roles cannot be deleted.')
        return _um_roles_redirect()

    deleted = _um_deleted_builtin()
    label = UM_ROLES[key]['label']
    if key in deleted:
        messages.info(request, f'Role "{label}" is already deleted.')
        return _um_roles_redirect()

    group = Group.objects.filter(name=UM_ROLES[key]['group']).first()
    in_use = group.user_set.count() if group else 0
    if in_use:
        messages.error(
            request,
            f'❌ Role "{label}" is still assigned to {in_use} user(s). Change their role first, then delete it.',
        )
        return _um_roles_redirect()

    # The Django Group itself is kept on purpose: other parts of the app (Django admin, has_perm
    # checks) may rely on its permissions, and "Restore" then brings everything back unchanged.
    _um_set_deleted_builtin(deleted | {key}, request.user)

    _um_audit(request, 'role_deleted', role=label, builtin=True, role_key=key)
    messages.success(request, f'🗑️ Built-in role "{label}" deleted. You can restore it from Manage Roles.')
    return _um_roles_redirect()


@_um_admin_only(post_only=True, perm='manage_roles')
def role_restore_builtin(request, key):
    """Bring back a deleted built-in role (POST, Administrator only)."""
    if not request.user.is_superuser:
        messages.error(request, 'Only an Administrator can restore built-in roles.')
        return _um_roles_redirect()
    deleted = _um_deleted_builtin()
    if key not in deleted:
        messages.error(request, 'That role is not deleted.')
        return _um_roles_redirect()

    _um_set_deleted_builtin(deleted - {key}, request.user)
    label = UM_ROLES[key]['label']
    _um_audit(request, 'role_restored', role=label, builtin=True, role_key=key)
    messages.success(request, f'✅ Role "{label}" restored with its saved permissions.')
    return _um_roles_redirect()


# =====================================================================================
# List / bulk / quick view / export / stats
# =====================================================================================
@_um_admin_only(perm='view_users')
def user_list(request):
    """List users with search, role and status filters."""
    search = (request.GET.get('search') or '').strip()
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')

    qs = _um_apply_filters(_um_base_queryset(), search, role_filter, status_filter)
    paginator = Paginator(qs, UM_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    for u in page_obj.object_list:  # only the rows on screen; groups are already prefetched
        _um_decorate(u)

    stats = _um_staff_users().aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(is_active=True)),
        inactive=Count('pk', filter=Q(is_active=False)),
        admins=Count('pk', filter=Q(is_superuser=True)),
    )

    return render(request, 'users/list.html', {
        'company_name': _um_company_name(),
        'page_obj': page_obj,
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'roles': [(k, UM_ROLES[k]['label']) for k in UM_ROLE_ORDER],
        'custom_roles': _um_custom_roles(),
        'builtin_roles': _um_builtin_roles(),
        'deleted_roles': sorted(_um_deleted_builtin()),
        'matrix_modules': UM_MATRIX_MODULES,
        'can_edit_permissions': request.user.is_superuser,
        'result_count': paginator.count,
        'total_count': stats['total'],
        'active_count': stats['active'],
        'inactive_count': stats['inactive'],
        'admin_count': stats['admins'],
    })


@_um_admin_only(json_response=True, post_only=True, perm='manage_users')
def bulk_user_action(request):
    """Bulk activate / deactivate / delete (AJAX, POST)."""
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid request!'}, status=400)

    action = data.get('action')
    if action not in ('activate', 'deactivate', 'delete'):
        return JsonResponse({'success': False, 'message': 'Invalid action!'}, status=400)

    try:
        ids = {int(i) for i in (data.get('user_ids') or [])}
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid user selection!'}, status=400)
    if not ids:
        return JsonResponse({'success': False, 'message': 'No users selected!'})
    if len(ids) > UM_BULK_LIMIT:
        return JsonResponse({'success': False, 'message': f'Select at most {UM_BULK_LIMIT} users at once.'})

    users = _um_staff_users().filter(pk__in=ids).exclude(pk=request.user.pk)  # never yourself, never customers
    skipped_admin = 0
    if not request.user.is_superuser:  # never administrators, unless you are one
        skipped_admin = users.filter(is_superuser=True).count()
        users = users.filter(is_superuser=False)
    if not users.exists():
        return JsonResponse({'success': False, 'message': 'No valid users found!'})

    admins_in_selection = users.filter(is_superuser=True)
    if action in ('deactivate', 'delete') and admins_in_selection.exists() \
            and _um_would_orphan_admin(admins_in_selection):
        return JsonResponse({'success': False, 'message': 'At least one active Administrator must remain.'})

    affected_ids = list(users.values_list('pk', flat=True))
    try:
        with transaction.atomic():
            if action == 'activate':
                count, verb = users.update(is_active=True), 'activated'
            elif action == 'deactivate':
                count, verb = users.update(is_active=False), 'deactivated'
            else:
                count, verb = len(affected_ids), 'deleted'
                users.delete()
    except (ProtectedError, IntegrityError):
        return JsonResponse({
            'success': False,
            'message': 'Some users have linked records and cannot be deleted. Deactivate them instead.',
        })
    except Exception:
        logger.exception('bulk_user_action failed')
        return JsonResponse({'success': False, 'message': 'Something went wrong. Nothing was changed.'}, status=500)

    _um_audit(request, f'bulk_{action}', user_ids=affected_ids, count=count)
    message = f'{count} user(s) {verb} successfully!'
    if skipped_admin:
        message += f' ({skipped_admin} administrator account(s) skipped.)'
    return JsonResponse({'success': True, 'message': message})


@_um_admin_only(json_response=True, perm='view_users')
def quick_view_user(request, user_id):
    """Quick-view details for the list page modal (AJAX)."""
    try:
        target = User.objects.prefetch_related('groups').get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found!'}, status=404)

    role = _um_role_of(target)
    return JsonResponse({
        'success': True,
        'id': target.id,
        'username': target.username,
        'full_name': target.get_full_name(),
        'email': target.email,
        'is_active': target.is_active,
        'is_staff': target.is_staff,
        'last_login': _um_fmt_dt(target.last_login, 'Never'),
        'date_joined': _um_fmt_dt(target.date_joined),
        'role': role,
        'role_display': _um_role_info(target)[1]['label'],
        'groups': [g.name for g in target.groups.all()],
        'avatar_color': _um_avatar_color(target.username),
    })


@_um_admin_only(perm='view_users')
def export_users(request):
    """Export the (filtered) user list to CSV."""
    qs = _um_apply_filters(
        _um_base_queryset(),
        (request.GET.get('search') or '').strip(),
        request.GET.get('role', ''),
        request.GET.get('status', ''),
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="users_export_{date.today()}.csv"'
    response.write('\ufeff')  # BOM so Excel opens UTF-8 names correctly
    writer = csv.writer(response)
    writer.writerow(['ID', 'Username', 'Full Name', 'Email', 'Role', 'Is Active', 'Last Login', 'Date Joined'])
    count = 0
    for u in qs:
        writer.writerow([
            u.id,
            _um_csv_safe(u.username),
            _um_csv_safe(u.get_full_name()),
            _um_csv_safe(u.email),
            _um_role_info(u)[1]['label'],
            'Yes' if u.is_active else 'No',
            _um_fmt_dt(u.last_login),
            _um_fmt_dt(u.date_joined),
        ])
        count += 1

    _um_audit(request, 'users_exported', rows=count)
    return response


@_um_admin_only(perm='view_users')
def user_activity(request, pk):
    """Login history and recent actions of one user (security review page)."""
    target = get_object_or_404(_um_staff_users(), pk=pk)
    logins = LoginAttempt.objects.filter(Q(user=target) | Q(username__iexact=target.username))[:30]
    actions = AccessLog.objects.filter(user=target)[:50]
    failed_recent = LoginAttempt.objects.filter(
        Q(user=target) | Q(username__iexact=target.username),
        is_success=False, attempted_at__gte=now() - timedelta(days=7),
    ).count()
    return render(request, 'users/user_activity.html', {
        'company_name': _um_company_name(),
        'target_user': target,
        'role_display': _um_role_info(target)[1]['label'],
        'logins': logins,
        'actions': actions,
        'failed_recent': failed_recent,
    })


@_um_admin_only(json_response=True, perm='view_users')
def user_activity_stats(request):
    """AJAX: user activity statistics."""
    seven_days_ago = now().date() - timedelta(days=7)
    s = _um_staff_users().aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(is_active=True)),
        inactive=Count('pk', filter=Q(is_active=False)),
        never=Count('pk', filter=Q(last_login__isnull=True)),
        recent=Count('pk', filter=Q(is_active=True, last_login__date__gte=seven_days_ago)),
    )
    return JsonResponse({
        'success': True,
        'total_users': s['total'],
        'active_users': s['active'],
        'inactive_users': s['inactive'],
        'active_last_7_days': s['recent'],
        'never_logged_in': s['never'],
        'active_percent': round(s['active'] / s['total'] * 100, 1) if s['total'] else 0,
    })


# =====================================================================================
# Permission matrix
# =====================================================================================
# The catalogue lives in security/permission_catalog.py (shared with the @perm_required decorator).
from ...security.permission_catalog import (  # noqa: E402
    MATRIX_MODULES as UM_MATRIX_MODULES, MATRIX_KEYS as UM_MATRIX_KEYS,
    ROLE_DEFAULTS as UM_ROLE_DEFAULTS, SAVED_SENTINEL as UM_MATRIX_SENTINEL,
)
from ...security.permissions import clear_perm_cache as _um_clear_perm_cache  # noqa: E402,F401


def _um_matrix_ct():
    # The matrix keeps its own permissions under one dedicated content type, so a matrix key
    # can never collide with (or be mistaken for) a real Django model permission.
    return ContentType.objects.get_for_model(Group)


def _um_stored_matrix(group_names):
    """{group_name: set(matrix keys saved in the DB)} for the given groups."""
    rows = (Permission.objects
            .filter(content_type=_um_matrix_ct(), codename__in=UM_MATRIX_KEYS | {UM_MATRIX_SENTINEL},
                    group__name__in=group_names)
            .values_list('group__name', 'codename'))
    stored = {}
    for gname, code in rows:
        bucket = stored.setdefault(gname, set())     # present = the matrix was saved for this role
        if code != UM_MATRIX_SENTINEL:
            bucket.add(code)
    return stored


def _um_matrix_role_map(custom=None):
    """{role key: group name} of the roles whose permissions can be edited (not admin, not deleted)."""
    deleted = _um_deleted_builtin()
    role_map = {k: UM_ROLES[k]['group'] for k in UM_ASSIGNABLE
                if k != 'admin' and k not in deleted and UM_ROLES[k]['group']}
    for r in (_um_custom_roles() if custom is None else custom):
        role_map[r['key']] = r['group']
    return role_map


def _um_matrix_group_names():
    return list(_um_matrix_role_map().values())


@_um_admin_only(perm='manage_roles')
def permission_matrix(request):
    """Permission matrix screen (saved changes are shown after reload)."""
    custom = _um_custom_roles()
    custom_meta = {r['key']: {'label': r['label'], 'group': r['group'], 'icon': r['icon']} for r in custom}
    group_names = list(_um_matrix_role_map(custom).values())
    deleted = _um_deleted_builtin()
    role_keys = [k for k in UM_ASSIGNABLE if k not in deleted] + list(custom_meta)
    stored = _um_stored_matrix(group_names)
    counts = dict(Group.objects.filter(name__in=group_names).annotate(n=Count('user')).values_list('name', 'n'))
    all_keys = [p['key'] for m in UM_MATRIX_MODULES for p in m['permissions']]

    roles = []
    for key in role_keys:
        meta = UM_ROLES.get(key) or custom_meta[key]
        if key == 'admin':
            full, partial = list(all_keys), []
            users_n = User.objects.filter(is_superuser=True).count()
        else:
            default_full, default_partial = UM_ROLE_DEFAULTS.get(key, ([], []))
            if meta['group'] in stored:  # something was saved from the matrix: the DB wins
                full = sorted(stored[meta['group']])
                partial = [p for p in default_partial if p not in stored[meta['group']]]
            else:
                full, partial = list(default_full), list(default_partial)
            users_n = counts.get(meta['group'], 0)
        roles.append({
            'key': key,
            'name': 'Warehouse' if key == 'warehouse' else meta['label'],
            'icon': meta['icon'],
            'permissions': full,
            'partial_permissions': partial,
            'user_count': users_n,
        })

    return render(request, 'users/permission_matrix.html', {
        'company_name': _um_company_name(),
        'roles': roles,
        'modules': UM_MATRIX_MODULES,
        'total_roles': len(roles),
        'total_permissions': len(all_keys),
        'custom_permissions': 0,
        'restricted_permissions': sum(1 for r in roles if len(r['permissions']) < 10),
        'is_admin': request.user.is_superuser,
    })


@_um_admin_only(json_response=True, perm='manage_roles')
def permission_matrix_api(request):
    """AJAX: roles and their stored matrix permissions."""
    group_names = _um_matrix_group_names()
    stored = _um_stored_matrix(group_names)
    groups = Group.objects.filter(name__in=group_names).annotate(user_count=Count('user'))
    return JsonResponse({
        'success': True,
        'roles': [{
            'id': g.id, 'name': g.name,
            'permissions': sorted(stored.get(g.name, [])),
            'user_count': g.user_count,
        } for g in groups],
        'modules': [{
            'name': m['name'],
            'permissions': [{'key': p['key'], 'name': p['name']} for p in m['permissions']],
        } for m in UM_MATRIX_MODULES],
    })


@_um_admin_only(json_response=True, post_only=True, perm='manage_roles')
def permission_matrix_save(request):
    """Save permission matrix changes. Administrators only."""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Only an Administrator can change permissions.'},
                            status=403)

    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid request!'}, status=400)

    changes = data.get('changes') or []
    if not isinstance(changes, list) or not changes:
        return JsonResponse({'success': False, 'message': 'No changes to save!'})

    ct = _um_matrix_ct()
    role_map = _um_matrix_role_map()
    applied = 0
    saved_groups = set()
    try:
        with transaction.atomic():
            for change in changes:
                if not isinstance(change, dict):
                    continue
                role_key = change.get('role')
                perm_key = change.get('permission')
                status = change.get('newStatus')
                # Whitelist everything: unknown roles / keys are ignored and the
                # Administrator role is immutable (it is always "all").
                group_name = role_map.get(role_key)
                if not group_name:  # unknown, deleted or Administrator role: ignored
                    continue
                if perm_key not in UM_MATRIX_KEYS or status not in ('full', 'partial', 'none'):
                    continue

                group, _ = Group.objects.get_or_create(name=group_name)
                perm, _ = Permission.objects.get_or_create(
                    codename=perm_key, content_type=ct,
                    defaults={'name': perm_key.replace('_', ' ').title()[:255]},
                )
                if status == 'full':
                    group.permissions.add(perm)
                else:  # 'partial' is a display-only state; only 'full' is stored
                    group.permissions.remove(perm)
                if group_name not in saved_groups:
                    # Mark the role as "saved" so removing every permission is respected
                    # instead of silently falling back to the built-in defaults.
                    sentinel, _ = Permission.objects.get_or_create(
                        codename=UM_MATRIX_SENTINEL, content_type=ct,
                        defaults={'name': 'Permission matrix saved'})
                    group.permissions.add(sentinel)
                    saved_groups.add(group_name)
                applied += 1
    except Exception:
        logger.exception('permission_matrix_save failed')
        return JsonResponse({'success': False, 'message': 'Could not save. Nothing was changed.'}, status=500)

    _um_audit(request, 'permission_matrix_saved', changes=applied)
    return JsonResponse({'success': True, 'message': f'Saved {applied} permission changes successfully!'})
