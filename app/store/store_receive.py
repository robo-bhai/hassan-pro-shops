"""
store_receive.py - Link between Purchase / PO / GRN and "which store the goods go to".

Qaida
-----
* In a named store (PMS/RMS/FGS/Technical...) only someone who is at least
  "keeper" in that store team can receive goods (superuser: all). Ordinary warehouses (without a profile) work for everyone as before.
* Only the stores where the user can receive appear in the warehouse dropdown of Purchase, PO and GRN.
"""
from . import store_access as _sa
from ..models import StoreProfile, Warehouse


def can_receive(user, warehouse_id):
    """Can this user receive purchase / GRN goods in this warehouse?"""
    if warehouse_id is None:
        return False
    try:
        warehouse_id = int(warehouse_id)
    except (TypeError, ValueError):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if warehouse_id in _sa.unavailable_warehouse_ids():
        return False
    if warehouse_id not in _sa.restricted_warehouse_ids():
        return True                                  # aam warehouse
    return _sa.can(user, warehouse_id, 'keeper')


def receivable_warehouses(user):
    """Warehouse queryset: where the user can receive purchase/GRN."""
    qs = Warehouse.objects.select_related('store_profile').order_by('name')
    if getattr(user, 'is_superuser', False):
        return qs
    blocked = set(_sa.unavailable_warehouse_ids())
    named = _sa.restricted_warehouse_ids()
    ok_named = set(_sa.allowed_ids(user, 'keeper') or [])
    blocked |= (named - ok_named)
    return qs.exclude(pk__in=blocked) if blocked else qs
