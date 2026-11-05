import importlib.util, sys, datetime
from decimal import Decimal
from types import SimpleNamespace as NS

spec = importlib.util.spec_from_file_location('brl', __file__.replace('tests/test_batch_sale_report_pure.py', 'app/batch_report_logic.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

cust = NS(pk=1, name='Ali', customer_code='C1')
sale = NS(sale_date=datetime.datetime(2026, 10, 1, 10, 0), customer=cust, bill_no='B1')
# 10 qty sale at Rs 100, profit 300 -> 6 from batch A and 4 from batch B
item = NS(pk=7, sale=sale, product=NS(name='Urea'), qty=10.0, price=Decimal('100'),
          total_amt=Decimal('1000.00'), profit=Decimal('300.00'))
use_a = NS(qty=6.0, sale_item=item)
use_b = NS(qty=4.0, sale_item=item)

ra = m.build_batch_sale_rows([use_a]); rb = m.build_batch_sale_rows([use_b])
sa = m.summarize_batch_sale_rows(ra); sb = m.summarize_batch_sale_rows(rb)
assert sa['total_qty'] == 6.0 and sb['total_qty'] == 4.0          # pehle dono mein 10 aata tha
assert sa['total_sales'] == Decimal('600.00') and sb['total_sales'] == Decimal('400.00')
assert sa['total_profit'] == Decimal('180.00') and sb['total_profit'] == Decimal('120.00')
assert sa['total_sales'] + sb['total_sales'] == item.total_amt     # kuch ghalat gina nahi gaya
assert sa['total_orders'] == 1 and sa['daily'][0]['qty'] == 6.0
assert sa['customers'][0]['orders'] == 1 and sa['customers'][0]['amount'] == Decimal('600.00')

# single batch line: poori qty
full = m.summarize_batch_sale_rows(m.build_batch_sale_rows([NS(qty=10.0, sale_item=item)]))
assert full['total_qty'] == 10.0 and full['total_sales'] == Decimal('1000.00')

# edge: zero line qty, usage bigger than line (ratio capped at 1), empty
assert m.share_of_line(5, 0) == 0 and m.share_of_line(12, 10) == 1
e = m.summarize_batch_sale_rows([]); assert e['total_qty'] == 0 and e['daily'] == []

# --- Step C: real per-batch profit when the usage row carries its cost ---
# price 100: batch A cost 70 (6 pcs), batch B cost 80 (4 pcs) -> line cost 740, line profit 260
item2 = NS(pk=8, sale=sale, product=NS(name='Urea'), qty=10.0, price=Decimal('100'),
           total_amt=Decimal('1000.00'), profit=Decimal('260.00'))
ca = m.summarize_batch_sale_rows(m.build_batch_sale_rows([NS(qty=6.0, sale_item=item2, cost_price=Decimal('70'))]))
cb = m.summarize_batch_sale_rows(m.build_batch_sale_rows([NS(qty=4.0, sale_item=item2, cost_price=Decimal('80'))]))
assert ca['total_profit'] == Decimal('180.00') and cb['total_profit'] == Decimal('80.00')   # 6x30, 4x20 (not 60/40 of 260)
assert ca['total_profit'] + cb['total_profit'] == item2.profit
assert ca['total_sales'] == Decimal('600.00') and cb['total_sales'] == Decimal('400.00')
print("batch sale report tests OK")
