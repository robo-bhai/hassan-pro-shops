"""
Django test: python manage.py test app.tests_store_issue
(file ko app/ me copy karke naam tests_store_issue.py rakhein)
"""
from django.contrib.auth.models import User
from django.test import TestCase

from app.models import (Department, Inventory, Product, StockBatch, StoreIssue, Warehouse)
from app.store import store_issue_service as svc


class StoreIssueTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('keeper', password='x')
        self.rms = Warehouse.objects.create(name='RMS test')
        self.pms = Warehouse.objects.create(name='PMS test')
        self.dept = Department.objects.create(name='Production test')
        self.p1 = Product.objects.create(name='Resin')
        self.p2 = Product.objects.create(name='Carton')
        # Resin: 2 batches in RMS (10 @ 100, 10 @ 120)
        for qty, price in ((10, 100), (10, 120)):
            StockBatch.add_batch(self.p1, qty, price, warehouse=self.rms)
        Inventory.update_stock(self.p1, 20, self.rms)
        StockBatch.add_batch(self.p2, 5, 10, warehouse=self.pms)
        Inventory.update_stock(self.p2, 5, self.pms)

    def stock(self, p, wh):
        return Inventory.objects.get(product=p, warehouse=wh).stock

    def test_issue_uses_fifo_and_reduces_stock(self):
        issue = svc.create_issue(user=self.user, from_warehouse=self.rms, issue_type='production',
                                 items=[(self.p1, 15, '')], department=self.dept)
        self.assertEqual(self.stock(self.p1, self.rms), 5)
        self.assertEqual(float(issue.total_cost), 10 * 100 + 5 * 120)
        remaining = list(StockBatch.objects.filter(product=self.p1).order_by('id').values_list('remaining_qty', flat=True))
        self.assertEqual(remaining, [0, 5])
        self.assertTrue(issue.issue_no.startswith('SI-'))

    def test_shortage_rolls_back_everything(self):
        with self.assertRaises(svc.StoreIssueError):
            svc.create_issue(user=self.user, from_warehouse=self.rms, issue_type='production',
                             items=[(self.p1, 5, ''), (self.p2, 1, '')], department=self.dept)  # p2 RMS me nahi
        self.assertEqual(self.stock(self.p1, self.rms), 20)
        self.assertEqual(StoreIssue.objects.count(), 0)

    def test_other_store_untouched(self):
        svc.create_issue(user=self.user, from_warehouse=self.pms, issue_type='packing',
                         items=[(self.p2, 2, '')], received_by='Ali')
        self.assertEqual(self.stock(self.p2, self.pms), 3)
        self.assertEqual(self.stock(self.p1, self.rms), 20)

    def test_receiver_required(self):
        with self.assertRaises(svc.StoreIssueError):
            svc.create_issue(user=self.user, from_warehouse=self.rms, issue_type='office',
                             items=[(self.p1, 1, '')])

    def test_cancel_restores_same_batches(self):
        issue = svc.create_issue(user=self.user, from_warehouse=self.rms, issue_type='production',
                                 items=[(self.p1, 15, '')], department=self.dept)
        svc.cancel_issue(issue.pk, self.user, 'galat entry')
        self.assertEqual(self.stock(self.p1, self.rms), 20)
        remaining = list(StockBatch.objects.filter(product=self.p1).order_by('id').values_list('remaining_qty', flat=True))
        self.assertEqual(remaining, [10, 10])
        with self.assertRaises(svc.StoreIssueError):
            svc.cancel_issue(issue.pk, self.user, 'dobara')

    def test_cannot_issue_more_than_available(self):
        with self.assertRaises(svc.StoreIssueError):
            svc.create_issue(user=self.user, from_warehouse=self.rms, issue_type='production',
                             items=[(self.p1, 21, '')], department=self.dept)


class StoreAccessTests(TestCase):
    """Har store ki team sirf apna data dekhe; superuser sab."""

    def setUp(self):
        from app.models import StoreMember, StoreProfile
        from app.store import store_access
        self.sa = store_access
        self.su = User.objects.create_superuser('boss', 'b@x.com', 'x')
        self.fgs_user = User.objects.create_user('fgs_user', password='x')
        self.pms_user = User.objects.create_user('pms_user', password='x')
        self.nobody = User.objects.create_user('nobody', password='x')
        self.fgs = Warehouse.objects.create(name='FGS t')
        self.pms = Warehouse.objects.create(name='PMS t')
        self.plain = Warehouse.objects.create(name='Plain t')
        StoreProfile.objects.create(warehouse=self.fgs, code='FGSX', store_type='FGS')
        StoreProfile.objects.create(warehouse=self.pms, code='PMSX', store_type='PMS')
        StoreMember.objects.create(user=self.fgs_user, warehouse=self.fgs, level='manager')
        StoreMember.objects.create(user=self.pms_user, warehouse=self.pms, level='viewer')
        self.dept = Department.objects.create(name='D t')
        self.prod = Product.objects.create(name='Item t')
        StockBatch.add_batch(self.prod, 5, 10, warehouse=self.pms)
        Inventory.update_stock(self.prod, 5, self.pms)

    def test_superuser_sees_all(self):
        self.assertIsNone(self.sa.allowed_ids(self.su))

    def test_member_sees_only_own_store(self):
        self.assertEqual(self.sa.allowed_ids(self.fgs_user), [self.fgs.pk])
        self.assertEqual(self.sa.allowed_ids(self.nobody), [])

    def test_levels(self):
        self.assertTrue(self.sa.can(self.fgs_user, self.fgs.pk, 'manager'))
        self.assertTrue(self.sa.can(self.pms_user, self.pms.pk, 'viewer'))
        self.assertFalse(self.sa.can(self.pms_user, self.pms.pk, 'keeper'))   # viewer issue nahi kar sakta
        self.assertFalse(self.sa.can(self.fgs_user, self.pms.pk, 'viewer'))   # dusre store ka nahi

    def test_legacy_pages_hide_other_stores(self):
        ids = set(self.sa.hide_other_stores(self.fgs_user, Warehouse.objects.all()).values_list('pk', flat=True))
        self.assertIn(self.fgs.pk, ids)
        self.assertIn(self.plain.pk, ids)        # aam warehouse pehle jaisa
        self.assertNotIn(self.pms.pk, ids)       # PMS chhupa

    def test_other_team_cannot_open_issue(self):
        issue = svc.create_issue(user=self.su, from_warehouse=self.pms, issue_type='packing',
                                 items=[(self.prod, 1, '')], received_by='Ali')
        self.client.force_login(self.fgs_user)
        self.assertEqual(self.client.get(f'/store-issue/{issue.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/store-issue/{issue.pk}/print/').status_code, 404)
        self.client.force_login(self.pms_user)
        self.assertEqual(self.client.get(f'/store-issue/{issue.pk}/').status_code, 200)
        self.client.force_login(self.su)
        self.assertEqual(self.client.get(f'/store-issue/{issue.pk}/').status_code, 200)

    def test_viewer_cannot_cancel(self):
        issue = svc.create_issue(user=self.su, from_warehouse=self.pms, issue_type='packing',
                                 items=[(self.prod, 1, '')], received_by='Ali')
        self.client.force_login(self.pms_user)           # viewer
        self.client.post(f'/store-issue/{issue.pk}/cancel/', {'reason': 'x'})
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'issued')
