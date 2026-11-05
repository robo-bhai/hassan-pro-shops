# app/module_gate.py
"""
Who may use the Security / System Tools modules.

Rule (one place, so views, sidebar and middleware agree):
  * Administrator (superuser)  -> always.
  * Owner of the customer account -> only when the Administrator turned the module ON
    in Settings > Modules (mode_shop_<key>).
  * Everybody else -> never.

Imports of the project are lazy and the functions take an optional ``vis`` dict, so the logic can be
tested without a database.
"""

OWNER_GROUP = 'Owner'


def _visibility():
    try:
        from app.context_processors import module_visibility
    except ImportError:                      # packaged layout: app/config/context_processors.py
        from app.config.context_processors import module_visibility
    return module_visibility()


def is_owner(user):
    """True for a logged-in user in the 'Owner' group."""
    return bool(getattr(user, 'is_authenticated', False) and user.groups.filter(name=OWNER_GROUP).exists())


def module_on_for(user, key, vis=None):
    """Is module ``key`` available to this user? The Administrator always gets it."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    vis = _visibility() if vis is None else vis
    return bool(vis.get(key, False))


def can_use_security(user, vis=None):
    """Security pages: Administrator, or the Owner while the Security module is ON."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return is_owner(user) and module_on_for(user, 'security', vis)
