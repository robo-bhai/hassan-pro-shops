"""
Dashboard update 2. Run from the project folder AFTER patch_dashboard.py:  python patch_dashboard2.py
Safe to run twice. Makes app/views_frontend/dashboard.py.bak_dash2 first.

 1. Passes the logged-in user to the dashboard extras (for the "My shift" card).
 2. "Refresh" link: opening the dashboard with ?refresh=1 clears the 5 minute cache.
"""
import shutil, sys

P = 'app/views_frontend/dashboard.py'
s = open(P, encoding='utf-8').read()
if 'dashboard_extras(today, request.user)' in s:
    print('dashboard.py is already updated. Nothing to do.')
    sys.exit(0)

PAIRS = [
    ("_extras = dashboard_extras(today)", "_extras = dashboard_extras(today, request.user)"),
    ("    cache_key = f'dashboard_stats_{today}'\n    base_stats = cache.get(cache_key)\n",
     "    cache_key = f'dashboard_stats_{today}'\n"
     "    if request.GET.get('refresh'):          # the Refresh link on the dashboard\n"
     "        cache.delete(cache_key)\n"
     "        cache.delete(f'dashboard_extra_{today}')\n"
     "    base_stats = cache.get(cache_key)\n"),
]
for old, new in PAIRS:
    if s.count(old) != 1:
        sys.exit('Could not find the expected code in dashboard.py. Run patch_dashboard.py first.\n'
                 'Nothing was changed.')
shutil.copy(P, P + '.bak_dash2')
for old, new in PAIRS:
    s = s.replace(old, new)
open(P, 'w', encoding='utf-8').write(s)
print('Done. Backup: ' + P + '.bak_dash2')
