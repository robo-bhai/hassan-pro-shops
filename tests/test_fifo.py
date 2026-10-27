import sys, importlib.util, types
# allocate_fifo ko Django ke baghair test karne ke liye sirf us function ko load karte hain
src = open(__file__.replace('tests/test_fifo.py', 'app/store_issue_service.py')).read()
start = src.index('EPS = 1e-9'); end = src.index('def _d(')
ns = {}; exec(src[start:end].replace('class StoreIssueError(Exception):\n    pass', ''), ns)
f = ns['allocate_fifo']

assert f([(1, 5), (2, 10)], 3) == ([(1, 3.0)], 0.0)
assert f([(1, 5), (2, 10)], 5) == ([(1, 5.0)], 0.0)
assert f([(1, 5), (2, 10)], 12) == ([(1, 5.0), (2, 7.0)], 0.0)
assert f([(1, 5), (2, 10)], 15) == ([(1, 5.0), (2, 10.0)], 0.0)
t, short = f([(1, 5), (2, 10)], 20); assert short == 5.0
assert f([], 1) == ([], 1.0)
assert f([(1, 0), (2, 4)], 2) == ([(2, 2.0)], 0.0)            # khali batch skip
t, s = f([(1, 0.1), (2, 0.2)], 0.3); assert s < 1e-9           # float drift
print("FIFO tests OK")
