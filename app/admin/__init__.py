"""Admin package (split from the former single admin.py).

Import ORDER matters: site.py must run before every module that uses `site=admin.site`.
helpers -> site (replaces admin.site) -> legacy ->
all other admin modules -> registrations.
"""
from importlib import import_module as _im

_MODULES = [
    "helpers",
    "site",
    "legacy",
    "accounting",
    "auth_admin",
    "budgeting",
    "catalog",
    "core",
    "purchasing",
    "sales",
    "services",
    "shareholders",
    "registrations",
]

_mods = [_im(f"{__name__}.{_m}") for _m in _MODULES]

# Some admin classes (e.g. CustomAdminSite) refer to classes from other files only when a method
# runs, not at import time. Share class names across modules after everything is loaded, so no
# circular imports are needed.
_shared = {}
for _mod in _mods:
    for _k, _v in vars(_mod).items():
        if isinstance(_v, type) and _v.__module__ == _mod.__name__:
            _shared.setdefault(_k, _v)
for _mod in _mods:
    _d = vars(_mod)
    for _k, _v in _shared.items():
        _d.setdefault(_k, _v)

del _im, _mod, _k, _v, _d
