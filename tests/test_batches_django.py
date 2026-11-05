"""
Django tests for Stock Batches (steps 4.2, 4.4, 4.5, 4.6 of the review).

Copy this file to app/tests_batches.py and run:
    python manage.py test app.tests_batches

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
import csv
import io
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from app.models import (Customer, Inventory, Product, Sale, SaleItem, SaleItemBatchUsage,
                        StockBatch, Warehouse)


class BatchTestBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'b@x.com', 'x')      # holds every permission
        self.plain = User.objects.create_user('clerk', password='x')            # basic permissions only
        self.wh = Warehouse.objects.create(name='Main')
        self.p = Product.objects.create(name='Urea')
        self.b1 = StockBatch.add_batch(self.p, 6, 100, warehouse=self.wh)
        self.b2 = StockBatch.add_batch(self.p, 4, 110, warehouse=self.wh)
        Inventory.update_stock(self.p, 10, self.wh)
        self.client.force_login(self.admin)


class BatchListTests(BatchTestBase):
    def test_bad_filters_do_not_crash(self):
        for qs in ('?warehouse=abc', '?category=x&vendor=%00', '?date_from=notadate',
                   '?sort=;drop&dir=sideways', '?stock_status=zzz', '?per_page=-5', '?page=999'):
            self.assertEqual(self.client.get(reverse('batch_list') + qs).status_code, 200, qs)

    def test_every_sort_key_works_both_ways(self):
        for key in ('id', 'product', 'remaining', 'cost', 'selling', 'value', 'age'):
            for d in ('asc', 'desc'):
                r = self.client.get(reverse('batch_list'), {'sort': key, 'dir': d})
                self.assertEqual(r.status_code, 200, (key, d))

    def test_stats_json(self):
        r = self.client.get(reverse('batch_list'), {'stats': 1})
        data = r.json()
        for k in ('total_batches', 'active_batches', 'slow_stock_value', 'slow_batches'):
            self.assertIn(k, data)

    def test_slow_moving_filter_only_old_in_stock_batches(self):
        # give b1 a purchase 120 days ago, b2 one 10 days ago
        from app.models import Purchase, PurchaseItem, Vendor
        vendor = Vendor.objects.create(name='V')
        for batch, days in ((self.b1, 120), (self.b2, 10)):
            pur = Purchase.objects.create(vendor=vendor, warehouse=self.wh, bill_no=f'B{days}',
                                          pur_date=now() - timedelta(days=days))
            item = PurchaseItem.objects.create(purchase=pur, product=self.p, qty=batch.qty, price=batch.price)
            StockBatch.objects.filter(pk=batch.pk).update(purchase_item=item)
        r = self.client.get(reverse('batch_list'), {'stock_status': 'stale'})
        ids = [b.id for b in r.context['page_obj']]
        self.assertIn(self.b1.id, ids)
        self.assertNotIn(self.b2.id, ids)
        self.assertEqual(r.context['slow_batches'], 1)

    def test_read_only_user_is_denied_or_read_only(self):
        self.client.force_login(self.plain)
        r = self.client.get(reverse('batch_list'))
        if r.status_code == 200:
            self.assertFalse(r.context['can_edit_prices'])


class BatchExportTests(BatchTestBase):
    def test_permission_required(self):
        self.client.force_login(self.plain)
        self.assertIn(self.client.get(reverse('batch_export')).status_code, (302, 403))

    def test_csv_blocks_formula_injection(self):
        self.p.name = '=HYPERLINK("http://evil")'
        self.p.save()
        r = self.client.get(reverse('batch_export'))
        self.assertEqual(r.status_code, 200)
        text = r.content.decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(text)))
        self.assertIn('Age (days)', rows[0])
        self.assertTrue(all(not c.startswith('=') for row in rows for c in row))
        self.assertIn("'=HYPERLINK", text)


class BulkPriceTests(BatchTestBase):
    def post(self, **body):
        return self.client.post(reverse('bulk_update_batch_sp'), data=json.dumps(body),
                                content_type='application/json')

    def test_dry_run_saves_nothing(self):
        r = self.post(batch_ids=[self.b1.id], mode='percent', value='20', dry_run=True)
        self.assertEqual(r.status_code, 200)
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.selling_price, Decimal('0.00'))

    def test_real_update_and_bad_input(self):
        self.assertEqual(self.post(batch_ids=[self.b1.id], mode='percent', value='20').status_code, 200)
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.selling_price, Decimal('120.00'))
        self.assertEqual(self.post(batch_ids=[], mode='percent', value='20').status_code, 400)
        self.assertEqual(self.post(batch_ids=['x'], mode='percent', value='20').status_code, 400)
        self.assertEqual(self.post(batch_ids=[self.b1.id], mode='nope', value='20').status_code, 400)

    def test_user_without_permission_is_refused(self):
        self.client.force_login(self.plain)
        r = self.post(batch_ids=[self.b1.id], mode='percent', value='20')
        self.assertEqual(r.status_code, 403)


class FloatDriftTests(BatchTestBase):
    def test_tiny_leftover_becomes_sold_out(self):
        self.b1.remaining_qty = 0.0000001
        self.b1.save()
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.remaining_qty, 0)

    def test_sale_allocation_ignores_tiny_leftover(self):
        StockBatch.objects.filter(pk=self.b1.pk).update(remaining_qty=0.00000001)   # bypass save()
        got = StockBatch.get_batches_for_sale(self.p, 4, self.wh)
        self.assertEqual([b.id for b, _ in got], [self.b2.id])


class SaleSplitTests(BatchTestBase):
    """Step 4.2: a sale of 10 that takes 6 + 4 from two batches."""

    def test_report_counts_each_batch_share_only(self):
        cust = Customer.objects.create(name='Ali')
        sale = Sale.objects.create(warehouse=self.wh, bill_no='S-1', customer=cust)
        item = SaleItem.objects.create(sale=sale, product=self.p, qty=10, price=Decimal('150'))
        usage = {u.batch_id: u.qty for u in SaleItemBatchUsage.objects.filter(sale_item=item)}
        self.assertEqual(usage, {self.b1.id: 6.0, self.b2.id: 4.0})

        r1 = self.client.get(reverse('batch_sale_report', args=[self.b1.pk]))
        r2 = self.client.get(reverse('batch_sale_report', args=[self.b2.pk]))
        self.assertEqual(r1.context['batch_summary']['sold_qty'], 6.0)     # was 10 before the fix
        self.assertEqual(r2.context['batch_summary']['sold_qty'], 4.0)
        self.assertEqual(r1.context['batch_summary']['sold_value'] + r2.context['batch_summary']['sold_value'],
                         item.total_amt)

    def test_profit_is_costed_batch_by_batch(self):
        """Step C: 6 @ cost 100 + 4 @ cost 110, sold at 150 -> 6x50 + 4x40 = 460."""
        cust = Customer.objects.create(name='Pay')
        sale = Sale.objects.create(warehouse=self.wh, bill_no='S-2', customer=cust)
        item = SaleItem.objects.create(sale=sale, product=self.p, qty=10, price=Decimal('150'))
        self.assertEqual(item.profit, Decimal('460.00'))
        r1 = self.client.get(reverse('batch_sale_report', args=[self.b1.pk]))
        r2 = self.client.get(reverse('batch_sale_report', args=[self.b2.pk]))
        self.assertEqual(r1.context['batch_summary']['total_profit'], Decimal('300.00'))   # 6 x 50
        self.assertEqual(r2.context['batch_summary']['total_profit'], Decimal('160.00'))   # 4 x 40

    def test_old_multi_batch_line_is_flagged_not_counted(self):
        cust = Customer.objects.create(name='Old')
        sale = Sale.objects.create(warehouse=self.wh, bill_no='S-OLD', customer=cust)
        item = SaleItem.objects.create(sale=sale, product=self.p, qty=10, price=Decimal('150'))
        SaleItemBatchUsage.objects.filter(sale_item=item).delete()           # pretend: pre-fix sale
        r = self.client.get(reverse('batch_sale_report', args=[self.b1.pk]))
        self.assertEqual(r.context['unknown_split_count'], 1)
        self.assertEqual(r.context['batch_summary']['sold_qty'], 0)
