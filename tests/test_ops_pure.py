"""Django ke baghair: approval ka faisla aur ginti ka hisaab."""
from decimal import Decimal


def needs_approval(mode, limit, est, is_manager, is_super):
    """store_ops_service.needs_approval ka wahi logic."""
    if mode == 'off':
        return False
    if is_super or is_manager:
        return False
    if mode == 'always':
        return True
    return est > limit


assert needs_approval('off', Decimal('0'), Decimal('999999'), False, False) is False
assert needs_approval('always', Decimal('0'), Decimal('1'), False, False) is True
assert needs_approval('always', Decimal('0'), Decimal('1'), True, False) is False     # manager khud issue kare
assert needs_approval('always', Decimal('0'), Decimal('1'), False, True) is False     # superuser
assert needs_approval('above_limit', Decimal('5000'), Decimal('5000'), False, False) is False   # barabar = approval nahi
assert needs_approval('above_limit', Decimal('5000'), Decimal('5000.01'), False, False) is True

# ginti: farq = ginti - system
def diff(counted, system): return round(counted - system, 6)
assert diff(8, 10) == -2          # kam (loss)
assert diff(12, 10) == 2          # zyada (gain)
assert diff(10, 10) == 0

# return: aakhri nikla pehle wapas (LIFO over usages)
def allocate_return(usages, qty):          # usages: [(id, qty, already_returned)] purane se naye
    left, out = qty, []
    for uid, uq, ret in reversed(usages):
        room = round(uq - ret, 6)
        if left <= 1e-9: break
        if room <= 1e-9: continue
        take = min(left, room); out.append((uid, take)); left -= take
    return out, left

u = [(1, 5.0, 0.0), (2, 10.0, 0.0)]
assert allocate_return(u, 4) == ([(2, 4.0)], 0)                 # naye batch me pehle
assert allocate_return(u, 12) == ([(2, 10.0), (1, 2.0)], 0)
assert allocate_return([(1, 5.0, 0.0), (2, 10.0, 8.0)], 5) == ([(2, 2.0), (1, 3.0)], 0)   # 2 me sirf 2 jagah
assert allocate_return(u, 20)[1] == 5.0                          # zyada wapsi: baqi rahi
print("store ops pure tests OK")
