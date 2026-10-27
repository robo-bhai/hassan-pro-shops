"""Django ke baghair: receive ke waqt miqdar usages me kaise banti hai (FIFO)."""


def allocate_fifo(batches, qty, EPS=1e-9):          # store_issue_service.allocate_fifo ki nakal (wahi logic)
    takes, left = [], float(qty)
    for key, remaining in batches:
        if left <= EPS:
            break
        if remaining <= EPS:
            continue
        take = min(left, float(remaining))
        takes.append((key, take)); left -= take
    return takes, max(left, 0.0)


usages = [(1, 5.0), (2, 10.0)]            # dispatch: batch1 se 5, batch2 se 10 (kul 15)
# poora mila
t, s = allocate_fifo(usages, 15); assert dict(t) == {1: 5.0, 2: 10.0} and s == 0
# 7 mila: pehla poora, doosre se 2; doosre ke 8 source ko wapas
t, s = allocate_fifo(usages, 7); got = dict(t)
assert got == {1: 5.0, 2: 2.0}
back = {k: q - got.get(k, 0) for k, q in usages}; assert back == {1: 0.0, 2: 8.0}
# 3 mila: sirf pehle batch se; pehle ke 2 aur doosre ke 10 wapas
t, s = allocate_fifo(usages, 3); got = dict(t); assert got == {1: 3.0}
back = {k: q - got.get(k, 0) for k, q in usages}; assert back == {1: 2.0, 2: 10.0}
# kuch nahi mila: sab wapas
t, s = allocate_fifo(usages, 0); assert t == []
print("transfer allocation tests OK")
