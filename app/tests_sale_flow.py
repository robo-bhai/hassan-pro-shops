"""
End-to-end tests: sale -> stock/batches -> ledger, return, shift closing.

Install:   copy this file to  app/tests_sale_flow.py
Run:       python manage.py test app.tests_sale_flow -v 2

These use the REAL models, signals and shift views (no mocks), so they catch the problems the
"pure" tests cannot: stock going wrong, a half-saved sale, a ledger that does not balance.

NOTE: written by reading the code, without a Django project to run it in (settings.py was not in
the zip). If a fixture line fails on a field name, fix it in setUp - the assertions are what matter.
Requires Django >= 3.2 (captureOnCommitCallbacks).

Fixture numbers (all hand-calculated, so a wrong number means a real bug):
    Batch A: 6 units @ Rs100      Batch B: 4 units @ Rs110      -> stock 10
    Sale of 8 units @ Rs150 (FIFO: 6 from A + 2 from B)
        revenue = 8 x 150           = 1200.00
        cost    = 6x100 + 2x110     =  820.00     (unit cost 102.50)
        profit  = 1200 - 820        =  380.00
    Return of 3 units @ Rs150
        refund  = 3 x 150           =  450.00
        cost    = 820 x 3/8         =  307.50
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from app import posting
from app.models import (Customer, GLPosting, Inventory, JournalEntry, JournalEntryItem, PaymentMethod,
                        PostingRule, Product, Sale, SaleItem, SalePayment, SaleRetrn, SaleRetrnItem,
                        ShiftCashMovement, CashierShift, StockBatch, Warehouse)

D = Decimal


class SaleFlowBase(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_superuser('cashier', 'c@x.com', 'x')   # superuser = every permission
        self.wh = Warehouse.objects.create(name='Main')
        self.p = Product.objects.create(name='Urea')
        self.b1 = StockBatch.add_batch(self.p, 6, 100, warehouse=self.wh)
        self.b2 = StockBatch.add_batch(self.p, 4, 110, warehouse=self.wh)
        Inventory.update_stock(self.p, 10, self.wh)
        self.cust = Customer.objects.create(name='Ali', customer_code='C-001')
        self.cash = PaymentMethod.objects.create(name='cash')
        self.card = PaymentMethod.objects.create(name='card')
        posting.setup_defaults()                                   # chart of accounts + PostingRule mapping
        # force_login() builds a request with no IP, and the login-tracking signal then tries to save
        # LoginAttempt(ip_address=NULL), which breaks the test transaction. Login tracking is not what
        # these tests are about, so switch it off for the test.
        patcher = mock.patch('app.security.signals_security.track_login_attempt')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.cashier)

    # -- helpers ---------------------------------------------------------------------------------
    def stock(self):
        return Inventory.get_stock(self.p, self.wh)

    def make_sale(self, qty=8, price=150, discount=0, pay=None, user=None):
        """Create a sale the way the POS does: Sale -> SaleItem -> SalePayment(s). Ledger posts on commit."""
        pay = pay or {}
        user = user or self.cashier
        with self.captureOnCommitCallbacks(execute=True):
            sale = Sale.objects.create(warehouse=self.wh, customer=self.cust, created_by=user,
                                       discount_value=D(discount), paid=D(sum(pay.values()) if pay else 0))
            SaleItem.objects.create(sale=sale, product=self.p, qty=qty, price=D(price))
            for method, amount in pay.items():
                SalePayment.objects.create(sale=sale, method=method, amount=D(amount), created_by=user)
        return Sale.objects.get(pk=sale.pk)

    def make_return(self, sale, qty, price=150):
        with self.captureOnCommitCallbacks(execute=True):
            ret = SaleRetrn.objects.create(bill_no='SR-1', sale=sale, customer=sale.customer,
                                           warehouse=sale.warehouse, return_reason='damaged')
            SaleRetrnItem.objects.create(sale_return=ret, product=self.p, qty=D(qty), price=D(price))
        return ret

    def acct(self, key):
        return PostingRule.objects.get(key=key).account

    def net(self, key, customer=None):
        """Debit minus credit on the account mapped to `key` (optionally for one customer's lines)."""
        items = JournalEntryItem.objects.filter(account=self.acct(key))
        if customer is not None:
            items = items.filter(customer=customer)
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
class SaleTests(SaleFlowBase):
    def test_sale_takes_stock_fifo_and_records_cost_and_profit(self):
        sale = self.make_sale(pay={self.cash: 1200})
        item = sale.saleitem_set.get()
        self.assertEqual(self.stock(), 2)
        self.b1.refresh_from_db(); self.b2.refresh_from_db()
        self.assertEqual((self.b1.remaining_qty, self.b2.remaining_qty), (0, 2))     # oldest batch first
        self.assertEqual(item.total_amt, D('1200.00'))
        self.assertEqual(item.cost_amount, D('820.00'))
        self.assertEqual(item.profit, D('380.00'))
        usage = {u.batch_id: u.qty for u in item.batch_usages.all()}
        self.assertEqual(usage, {self.b1.id: 6, self.b2.id: 2})

    def test_sale_posts_revenue_cogs_and_cash_to_the_ledger(self):
        sale = self.make_sale(pay={self.cash: 1200})
        self.assertEqual(GLPosting.objects.filter(source_type='sale', source_id=sale.pk, is_active=True).count(), 1)
        self.assertEqual(GLPosting.objects.filter(source_type='sale_cogs', source_id=sale.pk, is_active=True).count(), 1)
        self.assertEqual(self.net('sales_revenue'), D('-1200.00'))     # revenue is a credit
        self.assertEqual(self.net('cogs'), D('820.00'))
        self.assertEqual(self.net('inventory'), D('-820.00'))          # stock value went down by the cost
        self.assertEqual(self.net('cash'), D('1200.00'))
        self.assertEqual(self.net('receivable', self.cust), D('0.00'))  # paid in full -> customer owes nothing
        self.assert_books_balance()

    def test_credit_sale_leaves_receivable_for_the_customer(self):
        self.make_sale(pay={self.cash: 200})
        self.assertEqual(self.net('receivable', self.cust), D('1000.00'))
        self.assert_books_balance()

    def test_discount_is_in_the_sale_total_and_the_books(self):
        sale = self.make_sale(discount=100, pay={self.cash: 1100})
        self.assertEqual(sale.total_amount(), D('1100.00'))
        self.assertEqual(self.net('receivable', self.cust), D('0.00'))
        self.assert_books_balance()

    def test_not_enough_stock_is_refused_and_nothing_moves(self):
        with self.assertRaises(ValidationError):
            self.make_sale(qty=11)
        self.assertEqual(self.stock(), 10)
        self.b1.refresh_from_db(); self.b2.refresh_from_db()
        self.assertEqual((self.b1.remaining_qty, self.b2.remaining_qty), (6, 4))
        self.assertEqual(JournalEntry.objects.count(), 0)              # no ledger entry for a failed sale

    def test_price_below_batch_selling_price_is_refused_and_stock_is_not_lost(self):
        StockBatch.objects.filter(pk=self.b1.pk).update(selling_price=D('140.00'))
        with self.assertRaises(ValidationError):
            self.make_sale(qty=2, price=120)
        self.assertEqual(self.stock(), 10)                              # the atomic block rolled the stock back
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.remaining_qty, 6)

    def test_posting_the_same_sale_again_does_not_double_book(self):
        sale = self.make_sale(pay={self.cash: 1200})
        before = JournalEntry.objects.count()
        posting.post_document('sale', sale, repost=True)
        posting.post_document('sale_cogs', sale, repost=True)
        self.assertEqual(JournalEntry.objects.count(), before)
        self.assertEqual(self.net('sales_revenue'), D('-1200.00'))


# =================================================================================================
class SaleReturnTests(SaleFlowBase):
    def test_partial_return_puts_stock_back_at_original_cost(self):
        sale = self.make_sale(pay={self.cash: 1200})
        self.make_return(sale, 3)
        self.assertEqual(self.stock(), 5)                               # 2 left + 3 returned
        back = StockBatch.objects.filter(product=self.p, warehouse=self.wh, price=D('102.50')).first()
        self.assertIsNotNone(back, 'Returned goods must come back at the original unit cost (820/8)')
        self.assertEqual(back.remaining_qty, 3)

    def test_return_posts_refund_and_reverses_cost(self):
        sale = self.make_sale(pay={self.cash: 1200})
        ret = self.make_return(sale, 3)
        self.assertEqual(GLPosting.objects.filter(source_type='sale_return', source_id=ret.pk, is_active=True).count(), 1)
        self.assertEqual(self.net('sales_returns'), D('450.00'))        # contra-revenue debit
        self.assertEqual(self.net('cogs'), D('820.00') - D('307.50'))   # cost reversed pro-rata
        self.assertEqual(self.net('inventory'), D('-820.00') + D('307.50'))
        self.assertEqual(self.net('receivable', self.cust), D('-450.00'))   # customer is owed the refund
        self.assert_books_balance()

    def test_cannot_return_more_than_was_sold_and_stock_stays_put(self):
        sale = self.make_sale(pay={self.cash: 1200})
        self.make_return(sale, 6)
        stock_before = self.stock()
        with self.assertRaises(ValidationError):
            self.make_return(sale, 3)                                   # 6 + 3 > 8 sold
        self.assertEqual(self.stock(), stock_before)                    # stock was added before validation: must roll back
        self.assertEqual(SaleRetrnItem.objects.filter(sale_return__sale=sale).aggregate(t=Sum('qty'))['t'], D('6.00'))

    def test_return_at_a_different_price_is_refused(self):
        sale = self.make_sale(pay={self.cash: 1200})
        stock_before = self.stock()
        with self.assertRaises(ValidationError):
            self.make_return(sale, 1, price=100)
        self.assertEqual(self.stock(), stock_before)

    def test_deleting_a_return_item_takes_the_stock_back_out_and_reverses_the_entry(self):
        sale = self.make_sale(pay={self.cash: 1200})
        ret = self.make_return(sale, 3)
        with self.captureOnCommitCallbacks(execute=True):
            ret.return_items.get().delete()
        self.assertEqual(self.stock(), 2)
        self.assertEqual(self.net('sales_returns'), D('0.00'))
        self.assert_books_balance()


# =================================================================================================
class ShiftClosingTests(SaleFlowBase):
    def open_shift(self, opening='500'):
        r = self.client.post(reverse('shift_open'), {'warehouse': self.wh.pk, 'opening_cash': opening})
        self.assertEqual(r.status_code, 200, r.content)
        return CashierShift.objects.get(user=self.cashier, status='open')

    def move(self, kind, amount, reason='test'):
        return self.client.post(reverse('shift_movement'), {'kind': kind, 'amount': amount, 'reason': reason})

    def close(self, counted, shift=None):
        url = reverse('shift_close') if shift is None else reverse('shift_close_pk', args=[shift.pk])
        return self.client.post(url, {'counted_cash': counted, 'notes': 'end of day'})

    def test_cannot_open_two_shifts(self):
        self.open_shift()
        r = self.client.post(reverse('shift_open'), {'warehouse': self.wh.pk, 'opening_cash': '0'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(CashierShift.objects.filter(user=self.cashier, status='open').count(), 1)

    def test_full_day_cash_card_and_drawer_movements(self):
        shift = self.open_shift('500')
        self.make_sale(pay={self.cash: 1000, self.card: 200})           # 1200 sale: 1000 cash + 200 card
        self.assertEqual(self.move('in', '200').status_code, 200)
        self.assertEqual(self.move('out', '50', 'tea').status_code, 200)

        # live figure shown to the cashier while the shift is open:  500 + 1000 + 200 - 50 = 1650
        live = self.client.get(reverse('shift_status')).json()
        self.assertEqual(live['cash_in_drawer'], 1650.0)
        self.assertEqual(live['sales_count'], 1)

        r = self.close('1640')                                          # counted Rs10 short
        self.assertEqual(r.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.status, 'closed')
        self.assertEqual(shift.sales_count, 1)
        self.assertEqual(shift.total_sales, D('1200.00'))
        self.assertEqual(shift.cash_sales, D('1000.00'))
        self.assertEqual(shift.card_sales, D('200.00'))                 # card money is NOT in the drawer
        self.assertEqual(shift.cash_in, D('200.00'))
        self.assertEqual(shift.cash_out, D('50.00'))
        self.assertEqual(shift.expected_cash, D('1650.00'))
        self.assertEqual(shift.counted_cash, D('1640.00'))
        self.assertEqual(shift.difference, D('-10.00'))
        self.assertEqual(shift.closed_by, self.cashier)

    def test_closed_shift_is_frozen_and_cannot_be_closed_twice(self):
        shift = self.open_shift('0')
        self.make_sale(pay={self.cash: 1200})
        self.close('1200')
        shift.refresh_from_db()
        frozen = (shift.total_sales, shift.cash_sales, shift.expected_cash, shift.difference)

        self.make_sale(qty=1, pay={self.cash: 150})                     # a later sale must not leak into the old shift
        r = self.close('9999', shift)
        self.assertEqual(r.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual((shift.total_sales, shift.cash_sales, shift.expected_cash, shift.difference), frozen)
        self.assertEqual(shift.counted_cash, D('1200.00'))

    def test_cash_out_more_than_the_drawer_holds_is_refused(self):
        self.open_shift('100')
        r = self.move('out', '500')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ShiftCashMovement.objects.count(), 0)

    def test_negative_or_missing_counted_cash_does_not_close_the_shift(self):
        shift = self.open_shift('0')
        self.close('-5')
        shift.refresh_from_db()
        self.assertEqual(shift.status, 'open')

    def test_other_cashiers_sales_are_not_in_my_shift(self):
        shift = self.open_shift('0')
        other = User.objects.create_superuser('other', 'o@x.com', 'x')
        self.make_sale(qty=2, pay={self.cash: 300}, user=other)
        self.close('0')
        shift.refresh_from_db()
        self.assertEqual(shift.sales_count, 0)
        self.assertEqual(shift.cash_sales, D('0.00'))

    def test_return_refund_must_be_entered_as_cash_out_today(self):
        """Documents CURRENT behaviour: a sale return does not change the shift's expected cash.
        If the cashier hands cash back, they must also record a drawer 'cash out', otherwise the
        drawer will look short at closing. Change this test if you decide returns should adjust the shift."""
        self.open_shift('0')
        sale = self.make_sale(pay={self.cash: 1200})
        self.make_return(sale, 3)
        self.assertEqual(self.client.get(reverse('shift_status')).json()['cash_in_drawer'], 1200.0)
        self.assertEqual(self.move('out', '450', 'refund SR-1').status_code, 200)
        self.assertEqual(self.client.get(reverse('shift_status')).json()['cash_in_drawer'], 750.0)


# =================================================================================================
class ResaveTests(SaleFlowBase):
    """A sale line that is saved again must not take its stock a second time (this was a real bug:
    SaleItem.save() took stock on every save)."""

    def test_resaving_a_sale_item_does_not_take_stock_twice(self):
        sale = self.make_sale(qty=4, pay={self.cash: 600})
        self.assertEqual(self.stock(), 6)
        item = sale.saleitem_set.get()
        item.save()                                                     # e.g. admin "Save" with no change
        self.assertEqual(self.stock(), 6, 'Stock dropped again after re-saving an unchanged sale item')
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.remaining_qty, 2)                      # 6 - 4, not 6 - 8
        self.assertEqual(sum(u.qty for u in item.batch_usages.all()), 4)

    def test_changing_qty_on_a_saved_item_adjusts_stock_by_the_difference(self):
        sale = self.make_sale(qty=4, pay={self.cash: 600})
        item = sale.saleitem_set.get()
        item.qty = 6
        item.save()
        self.assertEqual(self.stock(), 4)                               # 10 - 6
        self.b1.refresh_from_db(); self.b2.refresh_from_db()
        self.assertEqual((self.b1.remaining_qty, self.b2.remaining_qty), (0, 4))
        item.qty = 2
        item.save()
        self.assertEqual(self.stock(), 8)                               # 10 - 2
        self.b1.refresh_from_db(); self.b2.refresh_from_db()
        self.assertEqual((self.b1.remaining_qty, self.b2.remaining_qty), (4, 4))
