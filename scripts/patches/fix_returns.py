"""
Fixes the sale-return and purchase-return pages so stock really changes.
Run from the project folder:  python fix_returns.py     (safe to run twice, makes .bak_returns copies)

Why: the two pages saved the return lines with bulk_create(), which skips the model's save().
The save() is the code that moves the stock, so a return changed the money but NOT the stock.
"""
import shutil, sys

def patch(path, pairs):
    s = open(path, encoding='utf-8').read()
    todo = [(o, n) for o, n in pairs if o in s]
    if not todo:
        if all(n in s for _, n in pairs):
            print(path, 'already fixed')
            return
        sys.exit(f'{path}: could not find the expected text. Nothing changed there.')
    for old, new in todo:
        if s.count(old) != 1:
            sys.exit(f'{path}: unexpected text ({old[:50]!r}). Nothing changed there.')
    shutil.copy(path, path + '.bak_returns')
    for old, new in todo:
        s = s.replace(old, new)
    open(path, 'w', encoding='utf-8').write(s)
    print(path, 'fixed')

SAVE_LOOP = '''# FIXED_RETURN_STOCK: save each line so the stock really moves; all lines or none
                from django.db import transaction as _tx
                try:
                    with _tx.atomic():
                        for _line in items_to_create:
                            _line.save()
                except Exception:
                    %s.delete()
                    raise'''

patch('app/views_frontend/returns.py', [
    ('SaleRetrnItem.objects.bulk_create(items_to_create)', SAVE_LOOP % 'sale_return'),
    ('PurchaseRetrnItem.objects.bulk_create(items_to_create)', SAVE_LOOP % 'purchase_return'),
])

patch('app/models/sales.py', [
    ('if self.qty + already_returned > sale_item.qty:',
     "if self.qty + Decimal(str(already_returned)) > Decimal(str(sale_item.qty)) + Decimal('0.005'):"),
    ('f"Quantity exceeds sale: Available {sale_item.qty - already_returned}, "',
     'f"Quantity exceeds sale: Available {Decimal(str(sale_item.qty)) - Decimal(str(already_returned))}, "'),
])
patch('app/models/purchasing.py', [
    ('        if self.qty > purchase_item.qty:\n            raise ValidationError(\n                f"Quantity exceeds purchase limit',
     "        if self.qty > Decimal(str(purchase_item.qty)) + Decimal('0.005'):\n            raise ValidationError(\n                f\"Quantity exceeds purchase limit"),
])
