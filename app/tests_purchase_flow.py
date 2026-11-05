"""
End-to-end tests: purchase and purchase return -> stock/batches -> ledger.

Install:   copy this file to  app/tests_purchase_flow.py
Run:       python manage.py test app.tests_purchase_flow -v 2

Real models and signals, no mocks. Written by reading the code (not run by the author), so if a
fixture line fails on a required field (for example Vendor), fix it in setUp - the assertions are
what matter.

Fixture numbers (hand-calculated):
    Purchase: 10 x Urea @ Rs100 = 1000.00           (stock 10, one batch of 10 @100)
    Return of 4 @ Rs100         =  400.00           (stock 6, owed to vendor 600)

Two classes at the bottom, PurchaseKnownRiskTests and PurchaseReturnKnownRiskTests, are written to
FAIL if a risk found while reading the code is real. A failure there is a finding, not a broken test.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from app import posting
from app.models import (Customer, GLPosting, Inventory, JournalEntry, JournalEntryItem, PaymentMethod,
                        PostingRule, Product, Purchase, PurchaseItem, PurchaseRetrn, PurchaseRetrnItem,
                        Sale, SaleItem, StockBatch, Vendor, VendorPayment, Warehouse)

D = Decimal


class PurchaseFlowBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('buyer', 'b@x.com', 'x')
        self.wh = Warehouse.objects.create(name='Main')
        self.p = Product.objects.create(name='Urea')
        self.p2 = Product.objects.create(name='DAP')
        self.vendor = Vendor.objects.create(name='Haji Traders', vendor_code='V-001')
        self.cash = PaymentMethod.objects.create(name='cash')
        posting.setup_defaults()                                   # chart of accounts + PostingRule mapping
        self._bill = 0

    # -- helpers ---------------------------------------------------------------------------------
    def stock(self, product=None):
        return Inventory.get_stock(product or self.p, self.wh)

    def make_purchase(self, lines=None, paid=0):
        """lines = [(product, qty, price), ...]; default is 10 x Urea @ 100."""
        lines = lines or [(self.p, 10, 100)]
        self._bill += 1
        with self.captureOnCommitCallbacks(execute=True):
            pur = Purchase.objects.create(vendor=self.vendor, warehouse=self.wh, bill_no=f'B-{self._bill}',
                                          created_by=self.user, paid=D(paid))
            for product, qty, price in lines:
                PurchaseItem.objects.create(purchase=pur, product=product, qty=qty, price=D(price))
        return Purchase.objects.get(pk=pur.pk)

    def make_return(self, purchase, qty, price=100, product=None, bill_no='PR-1'):
        with self.captureOnCommitCallbacks(execute=True):
            ret = PurchaseRetrn.objects.create(purchase=purchase, vendor=purchase.vendor, warehouse=self.wh,
                                               bill_no=bill_no, created_by=self.user, return_reason='damaged')
            PurchaseRetrnItem.objects.create(purchase_return=ret, product=product or self.p,
                                             qty=D(qty), price=D(price))
        return ret

    def batch(self, product=None):
        return StockBatch.objects.filter(product=product or self.p, warehouse=self.wh).order_by('id').first()

    def acct(self, key):
        return PostingRule.objects.get(key=key).account

    def net(self, key, vendor=None):
        """Debit minus credit on the account mapped to `key` (optionally for one vendor's lines)."""
        items = JournalEntryItem.objects.filter(account=self.acct(key))
        if vendor is not None:
            items = items.filter(vendor=vendor)
        d = items.filter(is_debit=True).aggregate(t=Sum('amount'))['t'] or D('0')
        c = items.filter(is_debit=False).aggregate(t=Sum('amount'))['t'] or D('0')
        return d - c

    def assert_books_balance(self):
        d = JournalEntryItem.objects.filter(is_debit=True).aggregate(t=Sum('amount'))['t'] or D('0')
        c = JournalEntryItem.objects.filter(is_debit=False).aggregate(t=Sum('amount'))['t'] or D('0')
        self.assertEqual(d, c, 'Total debits must equal total credits across the whole ledger')
        for e in JournalEntry.objects.all():
            ed = e.items.filter(is_debit=True).aggregate(t=Sum('amount'))['t'] or D('0')
            ec = e.items.filter(is_debit=False).aggregate(t=Sum('amount'))['t'] or D('0')
            self.assertEqual(ed, ec, f'Entry {e.entry_no} is unbalanced')


# =================================================================================================
class PurchaseTests(PurchaseFlowBase):
    def test_purchase_adds_stock_and_a_batch_at_the_buy_price(self):
        pur = self.make_purchase()
        self.assertEqual(self.stock(), 10)
        b = self.batch()
        self.assertEqual((b.qty, b.remaining_qty, b.price), (10, 10, D('100.00')))
        self.assertEqual(pur.total_amount(), D('1000.00'))
        self.assertEqual(pur.purchaseitem_set.get().total_amt, D('1000.00'))

    def test_purchase_posts_inventory_and_vendor_payable(self):
        pur = self.make_purchase()
        self.assertEqual(GLPosting.objects.filter(source_type='purchase', source_id=pur.pk, is_active=True).count(), 1)
        self.assertEqual(self.net('inventory'), D('1000.00'))                 # stock value up
        self.assertEqual(self.net('payable', self.vendor), D('-1000.00'))     # we owe the vendor
        self.assert_books_balance()

    def test_vendor_payment_reduces_what_we_owe_and_the_cash(self):
        pur = self.make_purchase()
        with self.captureOnCommitCallbacks(execute=True):
            VendorPayment.objects.create(vendor=self.vendor, purchase=pur, amount=D('400'),
                                         payment_method=self.cash, created_by=self.user)
        self.assertEqual(self.net('payable', self.vendor), D('-600.00'))
        self.assertEqual(self.net('cash'), D('-400.00'))
        self.assert_books_balance()

    def test_bill_with_two_products(self):
        pur = self.make_purchase([(self.p, 10, 100), (self.p2, 5, 200)])
        self.assertEqual(pur.total_amount(), D('2000.00'))
        self.assertEqual((self.stock(self.p), self.stock(self.p2)), (10, 5))
        self.assertEqual(self.net('payable', self.vendor), D('-2000.00'))
        self.assert_books_balance()

    def test_same_product_twice_on_one_bill_is_refused(self):
        pur = self.make_purchase()
        with self.assertRaises(ValidationError):
            PurchaseItem.objects.create(purchase=pur, product=self.p, qty=1, price=D('100'))
        self.assertEqual(self.stock(), 10)

    def test_zero_price_or_zero_quantity_is_refused_and_nothing_moves(self):
        with self.assertRaises(ValidationError):
            self.make_purchase([(self.p, 10, 0)])
        with self.assertRaises(ValidationError):
            self.make_purchase([(self.p, 0, 100)])
        self.assertEqual(self.stock(), 0)
        self.assertEqual(StockBatch.objects.count(), 0)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_changing_qty_on_a_saved_line_changes_stock_by_the_difference_and_the_ledger(self):
        pur = self.make_purchase()
        item = pur.purchaseitem_set.get()
        with self.captureOnCommitCallbacks(execute=True):
            item.qty = 15
            item.save()
        self.assertEqual(self.stock(), 15)
        b = self.batch()
        self.assertEqual((b.qty, b.remaining_qty), (15, 15))
        self.assertEqual(self.net('inventory'), D('1500.00'))                 # re-posted, not added on top
        self.assertEqual(self.net('payable', self.vendor), D('-1500.00'))
        with self.captureOnCommitCallbacks(execute=True):
            item.qty = 4
            item.save()
        self.assertEqual(self.stock(), 4)
        self.assertEqual(self.net('inventory'), D('400.00'))
        self.assert_books_balance()

    def test_resaving_a_purchase_line_unchanged_does_not_add_stock_again(self):
        pur = self.make_purchase()
        pur.purchaseitem_set.get().save()
        self.assertEqual(self.stock(), 10)
        self.assertEqual(self.batch().qty, 10)

    def test_posting_the_same_purchase_again_does_not_double_book(self):
        pur = self.make_purchase()
        before = JournalEntry.objects.count()
        posting.post_document('purchase', pur, repost=True)
        self.assertEqual(JournalEntry.objects.count(), before)
        self.assertEqual(self.net('payable', self.vendor), D('-1000.00'))


# =================================================================================================
class PurchaseReturnTests(PurchaseFlowBase):
    def setUp(self):
        super().setUp()
        self.pur = self.make_purchase()                                # 10 x Urea @ 100

    def test_return_takes_stock_and_batch_down(self):
        ret = self.make_return(self.pur, 4)
        self.assertEqual(self.stock(), 6)
        b = self.batch()
        self.assertEqual((b.qty, b.remaining_qty), (6, 6))
        self.assertEqual(ret.return_items.get().total_amt, D('400.00'))
        self.assertEqual(ret.total_return_amount(), D('400.00'))

    def test_return_posts_payable_debit_and_inventory_credit(self):
        ret = self.make_return(self.pur, 4)
        self.assertEqual(GLPosting.objects.filter(source_type='purchase_return', source_id=ret.pk, is_active=True).count(), 1)
        self.assertEqual(self.net('payable', self.vendor), D('-600.00'))      # 1000 owed - 400 returned
        self.assertEqual(self.net('inventory'), D('600.00'))
        self.assert_books_balance()

    def test_full_return_leaves_nothing_owed_and_no_stock(self):
        self.make_return(self.pur, 10)
        self.assertEqual(self.stock(), 0)
        self.assertEqual(self.net('payable', self.vendor), D('0.00'))
        self.assertEqual(self.net('inventory'), D('0.00'))

    def test_return_at_a_different_price_is_refused_and_stock_is_not_lost(self):
        with self.assertRaises(ValidationError):
            self.make_return(self.pur, 4, price=90)
        self.assertEqual(self.stock(), 10)                                     # rolled back
        self.assertEqual(self.batch().remaining_qty, 10)
        self.assertEqual(PurchaseRetrnItem.objects.count(), 0)

    def test_return_of_a_product_not_on_the_bill_is_refused(self):
        with self.assertRaises(ValidationError):
            self.make_return(self.pur, 1, product=self.p2)
        self.assertEqual(self.stock(self.p2), 0)
        self.assertEqual(self.stock(), 10)

    def test_returning_more_than_was_bought_in_one_go_is_refused(self):
        with self.assertRaises(ValidationError):
            self.make_return(self.pur, 11)
        self.assertEqual(self.stock(), 10)
        self.assertEqual(self.batch().remaining_qty, 10)

    def test_deleting_a_return_puts_stock_back_and_reverses_the_ledger(self):
        ret = self.make_return(self.pur, 4)
        with self.captureOnCommitCallbacks(execute=True):
            ret.delete()
        self.assertEqual(self.stock(), 10)
        b = self.batch()
        self.assertEqual((b.qty, b.remaining_qty), (10, 10))
        self.assertEqual(self.net('payable', self.vendor), D('-1000.00'))
        self.assertEqual(self.net('inventory'), D('1000.00'))
        self.assert_books_balance()


# =================================================================================================
class PurchaseKnownRiskTests(PurchaseFlowBase):
    """Written to FAIL if the risk is real. See the comment on each test."""

    def test_previous_balance_on_the_next_bill_is_what_is_still_owed(self):
        """Purchase.save() works out the vendor's previous balance with
        Sum('purchaseitem__total_amt') - Sum('paid') in ONE query. Joining the items repeats each
        bill's `paid` once per item line, so a bill with 2 lines and Rs400 paid counts 800 as paid.
        Expected here: 2 lines = 1000, paid 400 -> still owed 600. A wrong figure is 200."""
        self.make_purchase([(self.p, 5, 100), (self.p2, 5, 100)], paid=400)
        second = self.make_purchase([(self.p, 1, 100)])
        self.assertEqual(second.previous_balance, D('600.00'))


class PurchaseReturnKnownRiskTests(PurchaseFlowBase):
    def setUp(self):
        super().setUp()
        self.pur = self.make_purchase()                                # 10 x Urea @ 100

    def test_two_returns_together_cannot_exceed_what_was_bought(self):
        """validate_purchase_item() compares each return line with the quantity bought on the bill,
        but not with what was ALREADY returned against it (the sale-return code does check this).
        Stock is deliberately plentiful here (a second bill of 10 for the same product), so the
        'not enough stock' check cannot hide the problem. If this fails, bill 1 (10 units) can be
        returned 6 + 6 = 12 units and the vendor is credited for goods never bought on that bill."""
        self.make_purchase()                                            # a second bill of 10 -> stock 20
        self.assertEqual(self.stock(), 20)
        self.make_return(self.pur, 6, bill_no='PR-1')
        with self.assertRaises(ValidationError):
            self.make_return(self.pur, 6, bill_no='PR-2')
        self.assertEqual(self.stock(), 14)                                     # only the first return went through
        self.assertEqual(self.net('payable', self.vendor), D('-1400.00'))      # 2000 owed - 600 returned

    def test_cannot_return_stock_that_has_already_been_sold(self):
        """adjust_batches() only logs a warning when the batches hold less than the return quantity,
        so goods that are no longer on the shelf can still be returned to the vendor. Expected:
        buy 10, sell 8, try to return 5 -> refused, stock stays 2. If this fails, stock goes
        negative / the books show goods returned that were never there."""
        cust = Customer.objects.create(name='Ali', customer_code='C-001')
        sale = Sale.objects.create(warehouse=self.wh, customer=cust, created_by=self.user)
        SaleItem.objects.create(sale=sale, product=self.p, qty=8, price=D('150'))
        self.assertEqual(self.stock(), 2)
        with self.assertRaises(ValidationError):
            self.make_return(self.pur, 5)
        self.assertEqual(self.stock(), 2)
