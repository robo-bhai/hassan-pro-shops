"""
Django test: file ko app/tests_store_transfer.py naam se copy karein, phir
    python manage.py test app.tests_store_transfer
"""
from django.contrib.auth.models import User
from django.test import TestCase

from app.models import (Inventory, Product, Purchase, StockBatch, StoreMember, StoreProfile, StoreTransfer,
                        Warehouse)
from app.store import store_receive, store_transfer_service as svc


class StoreTransferTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('boss', 'b@x.com', 'x')
        self.rms = Warehouse.objects.create(name='RMS t')
        self.pms = Warehouse.objects.create(name='PMS t')
        self.p = Product.objects.create(name='Resin t')
        for qty, price in ((10, 100), (10, 120)):                     # RMS: 10@100, 10@120
            StockBatch.add_batch(self.p, qty, price, warehouse=self.rms)
        Inventory.update_stock(self.p, 20, self.rms)

    def stock(self, wh):
        inv = Inventory.objects.filter(product=self.p, warehouse=wh).first()
        return inv.stock if inv else 0

    def send(self, qty):
        return svc.dispatch_transfer(user=self.su, from_warehouse=self.rms, to_warehouse=self.pms,
                                     purpose='production', items=[(self.p, qty, '')])

    def test_dispatch_removes_from_source_not_yet_in_destination(self):
        t = self.send(15)
        self.assertEqual(self.stock(self.rms), 5)
        self.assertEqual(self.stock(self.pms), 0)             # raaste me
        self.assertEqual(t.status, 'in_transit')
        self.assertEqual(float(t.total_cost), 10 * 100 + 5 * 120)

    def test_receive_full_creates_batches_with_same_cost(self):
        t = self.send(15)
        svc.receive_transfer(t.pk, self.su, {})
        self.assertEqual(self.stock(self.pms), 15)
        prices = sorted(float(b.price) for b in StockBatch.objects.filter(product=self.p, warehouse=self.pms))
        self.assertEqual(prices, [100.0, 120.0])
        t.refresh_from_db(); self.assertEqual(t.status, 'received')

    def test_short_receive_needs_reason_and_returns_to_source(self):
        t = self.send(15)
        item = t.items.first()
        with self.assertRaises(svc.StoreTransferError):
            svc.receive_transfer(t.pk, self.su, {item.pk: 12})          # wajah ke baghair
        svc.receive_transfer(t.pk, self.su, {item.pk: 12}, {item.pk: 'toot gaya'})
        self.assertEqual(self.stock(self.pms), 12)
        self.assertEqual(self.stock(self.rms), 5 + 3)                   # kam wala maal wapas
        self.assertEqual(self.stock(self.rms) + self.stock(self.pms), 20)   # kul maal wahi

    def test_cancel_in_transit_restores_everything(self):
        t = self.send(15)
        svc.cancel_transfer(t.pk, self.su, 'galat')
        self.assertEqual(self.stock(self.rms), 20)
        rem = list(StockBatch.objects.filter(product=self.p, warehouse=self.rms).order_by('id').values_list('remaining_qty', flat=True))
        self.assertEqual(rem, [10, 10])
        with self.assertRaises(svc.StoreTransferError):
            svc.receive_transfer(t.pk, self.su, {})                      # cancel ke baad receive nahi

    def test_cannot_receive_twice(self):
        t = self.send(5)
        svc.receive_transfer(t.pk, self.su, {})
        with self.assertRaises(svc.StoreTransferError):
            svc.receive_transfer(t.pk, self.su, {})

    def test_shortage_rolls_back(self):
        with self.assertRaises(svc.StoreTransferError):
            self.send(25)
        self.assertEqual(self.stock(self.rms), 20)
        self.assertEqual(StoreTransfer.objects.count(), 0)

    def test_same_store_not_allowed(self):
        with self.assertRaises(svc.StoreTransferError):
            svc.dispatch_transfer(user=self.su, from_warehouse=self.rms, to_warehouse=self.rms,
                                  purpose='other', items=[(self.p, 1, '')])


class StoreReceiveAccessTests(TestCase):
    def setUp(self):
        self.fgs = Warehouse.objects.create(name='FGS t')
        self.plain = Warehouse.objects.create(name='Plain t')
        StoreProfile.objects.create(warehouse=self.fgs, code='FGSR', store_type='FGS')
        self.keeper = User.objects.create_user('keeper', password='x')
        self.viewer = User.objects.create_user('viewer', password='x')
        self.other = User.objects.create_user('other', password='x')
        StoreMember.objects.create(user=self.keeper, warehouse=self.fgs, level='keeper')
        StoreMember.objects.create(user=self.viewer, warehouse=self.fgs, level='viewer')

    def test_who_can_receive(self):
        self.assertTrue(store_receive.can_receive(self.keeper, self.fgs.pk))
        self.assertFalse(store_receive.can_receive(self.viewer, self.fgs.pk))     # viewer receive nahi
        self.assertFalse(store_receive.can_receive(self.other, self.fgs.pk))      # dusri team nahi
        self.assertTrue(store_receive.can_receive(self.other, self.plain.pk))     # aam warehouse pehle jaisa

    def test_dropdown_only_allowed(self):
        names = set(store_receive.receivable_warehouses(self.other).values_list('name', flat=True))
        self.assertIn('Plain t', names); self.assertNotIn('FGS t', names)
        names = set(store_receive.receivable_warehouses(self.keeper).values_list('name', flat=True))
        self.assertIn('FGS t', names)
