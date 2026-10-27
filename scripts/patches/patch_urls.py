"""Adds the 3 new URLs to app/urls.py (safe to run twice). Run from the project folder:  python patch_urls.py"""
import re, shutil, sys

P = 'app/urls.py'
s = open(P, encoding='utf-8').read()
if 'shop_tools.pos_void' in s:
    print('urls.py already patched. Nothing to do.')
    sys.exit(0)
if 'shop_tools' in s:          # first upgrade was installed: only add the new void line
    shutil.copy(P, P + '.bak_void')
    m = re.search(r"^([ \t]*)path\('sales/pos/bill/.*\n", s, re.M)
    if not m:
        sys.exit("Add this line to app/urls.py by hand: path('sales/pos/void/', shop_tools.pos_void, name='pos_void'),")
    s = s.replace(m.group(0), m.group(0) + f"{m.group(1)}path('sales/pos/void/', shop_tools.pos_void, name='pos_void'),\n", 1)
    if 'import shop_tools' not in s:
        s = s.replace('from app.views_frontend import shift as shift_views\n',
                      'from app.views_frontend import shift as shift_views\nfrom app.views_frontend import shop_tools\n', 1)
    open(P, 'w', encoding='utf-8').write(s)
    print('Done. Added the void URL.')
    sys.exit(0)

imp = 'from app.views_frontend import shift as shift_views\n'
if imp not in s:
    sys.exit('Could not find the shift import line in urls.py. Add the lines by hand (see README.txt).')
m = re.search(r"^([ \t]*)path\('sales/pos/checkout/'.*\n", s, re.M)
if not m:
    sys.exit("Could not find the 'sales/pos/checkout/' line in urls.py. Add the lines by hand (see README.txt).")

shutil.copy(P, P + '.bak_shop')
ind = m.group(1)
new = (f"{ind}path('sales/pos/recent/', shop_tools.recent_bills, name='pos_recent'),\n"
       f"{ind}path('sales/pos/bill/<int:pk>/', shop_tools.bill_detail, name='pos_bill'),\n"
       f"{ind}path('sales/pos/void/', shop_tools.pos_void, name='pos_void'),\n"
       f"{ind}path('inventory/stock-register/', shop_tools.stock_register, name='stock_register'),\n")
s = s.replace(m.group(0), m.group(0) + new, 1).replace(imp, imp + 'from app.views_frontend import shop_tools\n', 1)
open(P, 'w', encoding='utf-8').write(s)
print('Done. Backup saved as app/urls.py.bak_shop')
