"""
Django test: file ko app/tests_store_ops.py naam se copy karein, phir
    python manage.py test app.tests_store_ops
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from app.store import store_ops_service as ops
from app.store import store_issue_service as isv
from app.models import (Account, AccountType, Department, Inventory, JournalEntry, Product, StockBatch,
                        StoreAccountRule, StoreCount, StoreIssue, StoreMember, StoreReturn, StoreSetting,
                        Warehouse)


class Base(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('boss', 'b@x.com', 'x')
        self.keeper = User.objects.create_user('keeper', password='x')
        self.mgr = User.objects.create_user('mgr', password='x')
        self.mgr2 = User.objects.create_user('mgr2', password='x')
        self.wh = Warehouse.objects.create(name='RMS ops')
        StoreMember.objects.create(user=self.keeper, warehouse=self.wh, level='keeper')
        StoreMember.objects.create(user=self.mgr, warehouse=self.wh, level='manager')
        StoreMember.objects.create(user=self.mgr2, warehouse=self.wh, level='manager')
        self.dept = Department.objects.create(name='Prod ops')
        self.p = Product.objects.create(name='Resin ops')
        for qty, price in ((10, 100), (10, 120)):
            StockBatch.add_batch(self.p, qty, price, warehouse=self.wh)
        Inventory.update_stock(self.p, 20, self.wh)

    def stock(self):
        return Inventory.objects.get(product=self.p, warehouse=self.wh).stock

    def issue(self, qty, user=None):
        return isv.create_issue(user=user or self.su, from_warehouse=self.wh, issue_type='production',
                                items=[(self.p, qty, '')], department=self.dept)


class ApprovalTests(Base):
    def test_keeper_over_limit_needs_approval_manager_does_not(self):
        s = StoreSetting.get(); s.approval_mode = 'above_limit'; s.approval_limit = Decimal('500'); s.save()
        est = ops.estimate_cost(self.wh, [(self.p, 10)])                 # 10 x 100 = 1000
        self.assertEqual(est, Decimal('1000.00'))
        self.assertTrue(ops.needs_approval(self.keeper, self.wh, est))
        self.assertFalse(ops.needs_approval(self.mgr, self.wh, est))
        self.assertFalse(ops.needs_approval(self.keeper, self.wh, Decimal('400')))

    def test_request_does_not_move_stock_until_approved(self):
        req = ops.create_request(user=self.keeper, from_warehouse=self.wh, issue_type='production',
                                 items=[(self.p, 5, '')], department=self.dept)
        self.assertEqual(self.stock(), 20)
        ops.approve_request(req.pk, self.mgr)
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved'); self.assertEqual(self.stock(), 15)
        self.assertIsNotNone(req.issue)

    def test_cannot_approve_own_request(self):
        req = ops.create_request(user=self.mgr, from_warehouse=self.wh, issue_type='production',
                                 items=[(self.p, 5, '')], department=self.dept)
        with self.assertRaises(ops.StoreOpsError):
            ops.approve_request(req.pk, self.mgr)
        ops.approve_request(req.pk, self.mgr2)                           # doosra manager kar sakta hai

    def test_reject_needs_reason(self):
        req = ops.create_request(user=self.keeper, from_warehouse=self.wh, issue_type='production',
                                 items=[(self.p, 5, '')], department=self.dept)
        with self.assertRaises(ops.StoreOpsError):
            ops.reject_request(req.pk, self.mgr, '')
        ops.reject_request(req.pk, self.mgr, 'zaroorat nahi')
        self.assertEqual(self.stock(), 20)


class CountTests(Base):
    def test_shortage_uses_fifo_and_surplus_adds_batch(self):
        c = ops.start_count(self.keeper, self.wh)
        line = c.lines.get(product=self.p)
        ops.save_counts(c.pk, {line.pk: 17}, {line.pk: 'toot gaya'})        # 3 kam
        ops.submit_count(c.pk, self.keeper)
        with self.assertRaises(ops.StoreOpsError):
            ops.post_count(c.pk, self.keeper, {}, {})                        # submit karne wala khud post nahi
        ops.post_count(c.pk, self.mgr, {}, {})
        c.refresh_from_db()
        self.assertEqual(self.stock(), 17); self.assertEqual(c.status, 'posted')
        self.assertEqual(c.loss_value, Decimal('300.00'))                    # 3 x 100 (purana batch)
        c2 = ops.start_count(self.keeper, self.wh)
        l2 = c2.lines.get(product=self.p)
        ops.save_counts(c2.pk, {l2.pk: 19}, {l2.pk: 'mila'})
        ops.submit_count(c2.pk, self.keeper)
        ops.post_count(c2.pk, self.mgr, {l2.pk: Decimal('110')}, {})
        self.assertEqual(self.stock(), 19)

    def test_difference_needs_reason_and_all_lines_counted(self):
        c = ops.start_count(self.keeper, self.wh)
        with self.assertRaises(ops.StoreOpsError):
            ops.submit_count(c.pk, self.keeper)                              # ginti likhi hi nahi
        line = c.lines.get(product=self.p)
        ops.save_counts(c.pk, {line.pk: 15})
        ops.submit_count(c.pk, self.keeper)
        with self.assertRaises(ops.StoreOpsError):
            ops.post_count(c.pk, self.mgr, {}, {})                           # wajah ke baghair
        self.assertEqual(self.stock(), 20)

    def test_one_open_count_per_store(self):
        ops.start_count(self.keeper, self.wh)
        with self.assertRaises(ops.StoreOpsError):
            ops.start_count(self.keeper, self.wh)


class ReturnTests(Base):
    def test_return_restores_same_batches_and_blocks_cancel(self):
        issue = self.issue(15)                                              # 10@100 + 5@120
        item = issue.items.first()
        ret = ops.create_return(user=self.keeper, issue_id=issue.pk, quantities={item.pk: 6})
        self.assertEqual(self.stock(), 11)
        self.assertEqual(ret.total_cost, Decimal('720.00'))                  # aakhri 5@120 + 1@100
        with self.assertRaises(isv.StoreIssueError):
            isv.cancel_issue(issue.pk, self.su, 'x')                         # return ke baad cancel nahi
        with self.assertRaises(ops.StoreOpsError):
            ops.create_return(user=self.keeper, issue_id=issue.pk, quantities={item.pk: 10})   # sirf 9 baqi

    def test_return_more_than_issued_blocked(self):
        issue = self.issue(5); item = issue.items.first()
        with self.assertRaises(ops.StoreOpsError):
            ops.create_return(user=self.keeper, issue_id=issue.pk, quantities={item.pk: 6})


class AccountingTests(Base):
    def setUp(self):
        super().setUp()
        at_a = AccountType.objects.create(name='Asset t', code='A1', account_class='asset')
        at_e = AccountType.objects.create(name='Expense t', code='E1', account_class='expense')
        self.inv = Account.objects.create(code='1400', name='Inventory t', account_type=at_a)
        self.exp = Account.objects.create(code='5100', name='Consumption t', account_type=at_e)
        StoreAccountRule.objects.create(kind='inventory', key='', account=self.inv)
        StoreAccountRule.objects.create(kind='expense', key='', account=self.exp)

    def test_off_by_default_no_entry(self):
        self.issue(5)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_issue_posts_balanced_entry_and_cancel_reverses(self):
        s = StoreSetting.get(); s.accounting_enabled = True; s.save()
        issue = self.issue(15)
        e = JournalEntry.objects.get(reference=issue.issue_no)
        self.assertEqual(e.status, 'posted'); self.assertTrue(e.is_balanced())
        self.assertEqual(e.total_debit(), issue.total_cost)
        isv.cancel_issue(issue.pk, self.su, 'galat')
        e.refresh_from_db(); self.assertEqual(e.status, 'reversed')

    def test_missing_mapping_blocks_issue_and_keeps_stock(self):
        StoreAccountRule.objects.filter(kind='expense').delete()
        s = StoreSetting.get(); s.accounting_enabled = True; s.save()
        with self.assertRaises(isv.StoreIssueError):
            self.issue(5)
        self.assertEqual(self.stock(), 20); self.assertEqual(StoreIssue.objects.count(), 0)
