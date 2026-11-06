"""
store_access.py - store-wise access control.

Qaida:
* Superuser: can see and operate all stores.
* Everyone else: only the data of the stores whose team they belong to (StoreMember).
* Darje: viewer (dekhna) < keeper (issue karna) < manager (issue + cancel).
"""
from ..models import StoreMember, StoreProfile

RANK = {'viewer': 1, 'keeper': 2, 'manager': 3}


def business_mode():
    from ..context_processors import module_visibility
    return module_visibility().get('_mode', 'both')


def unavailable_warehouse_ids():
    """Stores that are not for the current business mode (Shop/Factory) - they stay hidden from everyone."""
    mode = business_mode()
    if mode == 'both':
        return set()
    return {p.warehouse_id for p in StoreProfile.objects.all() if not p.available_in(mode)}


def memberships(user):
    """{warehouse_id: level} - queried only once per request."""
    if not getattr(user, 'is_authenticated', False):
        return {}
    cached = getattr(user, '_store_memberships', None)
    if cached is None:
        cached = dict(StoreMember.objects.filter(user=user, is_active=True)
                      .values_list('warehouse_id', 'level'))
        try:
            user._store_memberships = cached
        except AttributeError:
            pass
    return cached


def allowed_ids(user, need='viewer'):
    """None = all stores (superuser). Otherwise the list of warehouse ids where the user has at least the `need` level."""
    if getattr(user, 'is_superuser', False):
        return None
    need_rank = RANK[need]
    return [w for w, lvl in memberships(user).items() if RANK.get(lvl, 0) >= need_rank]


def can(user, warehouse_id, need='viewer'):
    ids = allowed_ids(user, need)
    return ids is None or warehouse_id in ids


def restricted_warehouse_ids():
    """Warehouses that are named stores (PMS/RMS/FGS/...)."""
    return set(StoreProfile.objects.values_list('warehouse_id', flat=True))


def hide_other_stores(user, queryset, field='pk'):
    """
    For old warehouse pages: only the team of a named store can see it.
    Ordinary warehouses (without a profile) are visible to everyone as before.
    """
    if getattr(user, 'is_superuser', False):
        return queryset
    hidden = restricted_warehouse_ids() - set(memberships(user).keys())
    return queryset.exclude(**{field + '__in': hidden}) if hidden else queryset


def can_view_warehouse(user, warehouse_id):
    if getattr(user, 'is_superuser', False):
        return True
    return warehouse_id not in restricted_warehouse_ids() or warehouse_id in memberships(user)


# ---------------------------------------------------------------------------
# Store-wise MODULE access (sidebar + URL)
# ---------------------------------------------------------------------------
def module_scope(user):
    """
    None  -> no restriction (superuser, or someone who is not in any named store team).
    set() -> the set of module keys this user gets (union of all their stores).
    """
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'is_superuser', False):
        return None
    cached = getattr(user, '_store_module_scope', False)
    if cached is not False:
        return cached
    mode = business_mode()
    profiles = [p for p in StoreProfile.objects.filter(
        is_active=True, warehouse__members__user=user, warehouse__members__is_active=True,
    ).distinct() if p.available_in(mode)]
    in_any_store = StoreProfile.objects.filter(
        warehouse__members__user=user, warehouse__members__is_active=True).exists()
    if not in_any_store:
        scope = None
    elif not profiles:
        scope = set()          # in a store team but that store is closed in this mode
    else:
        scope = {'store_issue'}        # The Stores dashboard is the home page of store users
        for p in profiles:
            scope |= p.effective_modules()
    try:
        user._store_module_scope = scope
    except AttributeError:
        pass
    return scope


def restrict_visibility(user, vis):
    """module_visibility() dict: narrow it to the store of the user (returns a new dict)."""
    scope = module_scope(user)
    if scope is None:
        return vis
    return {k: (v and k in scope) if k != '_mode' else v for k, v in vis.items()}
