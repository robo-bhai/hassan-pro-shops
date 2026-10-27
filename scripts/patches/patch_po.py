"""Installs the professional Purchase Order module. Safe to run twice (backups are .bak_po)."""
import os, re, shutil, sys

def backup(path):
    if os.path.exists(path) and not os.path.exists(path + '.bak_po'):
        shutil.copy2(path, path + '.bak_po')

# 1) register the module (loaded after purchasing => overrides the old PO views)
p = 'app/views_frontend/__init__.py'
s = open(p, encoding='utf-8').read()
if '"po_pro"' not in s:
    backup(p)
    s = s.replace('    "purchasing",\n', '    "purchasing",\n    "po_pro",\n', 1)
    open(p, 'w', encoding='utf-8').write(s)
    print('registered po_pro in views_frontend/__init__.py')
else:
    print('po_pro already registered')

# 2) new URLs
p = 'app/urls.py'
s = open(p, encoding='utf-8').read()
if 'purchase_order_print' not in s:
    backup(p)
    anchor = "    path('orders/purchase/', views_frontend.purchase_order_list, name='purchase_order_list'),\n"
    if anchor not in s:
        sys.exit('ERROR: PO list url line not found in urls.py')
    new = anchor + (
        "    path('orders/purchase/products/', views_frontend.purchase_order_products, name='purchase_order_products'),\n"
        "    path('orders/purchase/<int:pk>/edit/', views_frontend.purchase_order_edit, name='purchase_order_edit'),\n"
        "    path('orders/purchase/<int:pk>/print/', views_frontend.purchase_order_print, name='purchase_order_print'),\n"
        "    path('orders/purchase/<int:pk>/duplicate/', views_frontend.purchase_order_duplicate, name='purchase_order_duplicate'),\n")
    s = s.replace(anchor, new, 1)
    # 'products/' must come before 'create/' and '<int:pk>/' – it is, because it is inserted right after the list url
    open(p, 'w', encoding='utf-8').write(s)
    print('added 4 PO urls')
else:
    print('PO urls already present')
