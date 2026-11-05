"""
Django tests for Step 2: multi-vendor cart + vendor orders.

Copy this file to app/tests_vendor_orders.py and run:
    python manage.py test app.tests_vendor_orders

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.models import (Category, Customer, CustomerProfile, Inventory, Notification, Product,
                        SaleOrder, SaleOrderItem, StockBatch, Vendor, VendorProfile, Warehouse)


def make_store(name, phone, **profile_over):
    vendor = Vendor.objects.create(name=name, contact_number=phone)
    user = User.objects.create_user(f'u_{phone}', f'{phone}@x.com', 'secret12')
    profile = VendorProfile.objects.create(
        vendor=vendor, user=user, business_name=name, is_approved=True, **profile_over)
    return vendor, user, profile


class Base(TestCase):
    def setUp(self):
        self.wh = Warehouse.objects.create(name='Main')
        self.cat = Category.objects.create(name='Food')

        self.v1, self.u1, self.p1 = make_store(
            'Ali Store', '03001111111', min_order_amount=Decimal('500'), delivery_fee=Decimal('80'))
        self.v2, self.u2, self.p2 = make_store('Bilal Mart', '03002222222', delivery_fee=Decimal('50'))

        self.item1 = self._product('Rice', self.v1, 300)
        self.item2 = self._product('Atta', self.v2, 700)
        self.shop_item = self._product('Shop Sugar', None, 100)

        self.cust_user = User.objects.create_user('cust', 'c@x.com', 'secret12')
        self.customer = Customer.objects.create(
            name='Zara', contact_number='03003333333', address='Lahore')
        CustomerProfile.objects.create(customer=self.customer, user=self.cust_user)

    def _product(self, name, vendor, price):
        p = Product.objects.create(
            name=name, category=self.cat, vendor=vendor, price=Decimal(price),
            is_active=True, approval_status='approved')
        Inventory.objects.create(product=p, warehouse=self.wh, stock=50)
        StockBatch.objects.create(product=p, warehouse=self.wh, qty=50, remaining_qty=50,
                                  price=Decimal(price) * Decimal('0.9'), selling_price=Decimal(price))
        return p

    def add(self, product, **extra):
        return self.client.post(
            reverse('add_to_cart'), data=json.dumps({'product_id': product.id, 'quantity': 1, **extra}),
            content_type='application/json')


class CartSingleStoreTests(Base):
    def test_same_store_adds_fine(self):
        self.assertTrue(self.add(self.item1).json()['success'])
        self.assertTrue(self.add(self.item1).json()['success'])

    def test_other_store_asks_to_clear_cart(self):
        self.add(self.item1)
        d = self.add(self.item2).json()
        self.assertFalse(d['success'])
        self.assertTrue(d['cart_conflict'])
        self.assertIn('Purana cart khali karun?', d['message'])
        self.assertEqual(list(self.client.session['cart']), [str(self.item1.id)])  # cart waisa hi

    def test_replace_cart_swaps_store(self):
        self.add(self.item1)
        d = self.add(self.item2, replace_cart=True).json()
        self.assertTrue(d['success'])
        self.assertEqual(list(self.client.session['cart']), [str(self.item2.id)])

    def test_shop_item_counts_as_its_own_store(self):
        self.add(self.item1)
        self.assertTrue(self.add(self.shop_item).json()['cart_conflict'])


class CartRulesTests(Base):
    def test_cart_shows_store_fee_and_min_order(self):
        self.add(self.item1)  # Rs 300 < min 500
        r = self.client.get(reverse('cart_view'))
        self.assertEqual(r.context['delivery_charges'], Decimal('80'))
        store = r.context['store']
        self.assertFalse(store['min_ok'])
        self.assertEqual(store['short_by'], Decimal('200'))

    def test_checkout_value_includes_store_fee(self):
        self.add(self.item1)
        self.add(self.item1)  # 600 >= 500
        r = self.client.get(reverse('cart_view'))
        self.assertTrue(r.context['store']['min_ok'])
        self.assertEqual(r.context['total_amount'], Decimal('680'))

    def test_closed_store_blocks_order(self):
        from app.customer import store_orders
        self.add(self.item1); self.add(self.item1)
        self.p1.store_status = 'closed'; self.p1.save()
        err = store_orders.validate_cart_for_order(self.client.session['cart'], Decimal('600'))
        self.assertIn('band hai', err)


class PlaceOrderTests(Base):
    def _login_and_cart(self, qty=2):
        self.client.login(username='cust', password='secret12')
        for _ in range(qty):
            self.add(self.item1)
        s = self.client.session
        s['order_verified'] = True
        s.save()

    def _place(self, **body):
        return self.client.post(reverse('place_order_direct'), data=json.dumps(body),
                                content_type='application/json')

    def test_order_gets_vendor_fee_and_vendor_notification(self):
        self._login_and_cart(2)
        d = self._place(payment_method='cod', delivery_type='standard').json()
        self.assertTrue(d['success'], d)
        o = SaleOrder.objects.get()
        self.assertEqual(o.vendor, self.v1)
        self.assertEqual(o.delivery_fee, Decimal('80'))
        self.assertEqual(o.payment_method, 'cod')
        self.assertTrue(Notification.objects.filter(user=self.u1, title__contains=o.order_no).exists())

    def test_below_minimum_is_refused(self):
        self._login_and_cart(1)  # 300 < 500
        d = self._place(payment_method='cod').json()
        self.assertFalse(d['success'])
        self.assertIn('minimum order', d['message'])
        self.assertEqual(SaleOrder.objects.count(), 0)


class VendorOrderActionTests(Base):
    def setUp(self):
        super().setUp()
        self.order = SaleOrder.objects.create(
            customer=self.customer, warehouse=self.wh, status='pending', vendor=self.v1,
            delivery_fee=Decimal('80'), payment_method='cod')
        SaleOrderItem.objects.create(order=self.order, product=self.item1, qty=2, price=Decimal('300'))
        self.client.login(username='u_03001111111', password='secret12')

    def act(self, action, **data):
        return self.client.post(reverse('vendor_order_action', args=[self.order.id, action]), data)

    def test_orders_list_only_shows_own_orders(self):
        other = SaleOrder.objects.create(customer=self.customer, warehouse=self.wh, vendor=self.v2)
        r = self.client.get(reverse('vendor_orders'))
        ids = [row['order'].id for row in r.context['orders']]
        self.assertIn(self.order.id, ids)
        self.assertNotIn(other.id, ids)

    def test_accept_then_ready(self):
        self.act('accept', prep_minutes='25')
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.prep_minutes), ('confirmed', 25))
        self.assertTrue(Notification.objects.filter(user=self.cust_user, title__contains='qubool').exists())
        self.act('ready')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')

    def test_reject_needs_reason(self):
        self.act('reject')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_reject_tells_customer_reason_and_refund(self):
        self.order.payment_method = 'jazzcash'; self.order.save()
        self.act('reject', reason_code='out_of_stock', reason_note='')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.order.reject_reason, 'Item abhi stock mein nahi')
        n = Notification.objects.get(user=self.cust_user, title__contains='reject')
        self.assertIn('Item abhi stock mein nahi', n.message)
        self.assertIn('wapas', n.message)  # online payment -> refund note

    def test_cannot_touch_other_vendors_order(self):
        self.client.logout()
        self.client.login(username='u_03002222222', password='secret12')
        r = self.act('accept')
        self.assertEqual(r.status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_cannot_ready_a_pending_order(self):
        self.act('ready')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')


class CustomerRejectedViewTests(Base):
    def test_customer_sees_reason_refund_and_other_stores(self):
        order = SaleOrder.objects.create(
            customer=self.customer, warehouse=self.wh, status='cancelled', vendor=self.v1,
            payment_method='cod', reject_reason='Store abhi bohat busy hai')
        SaleOrderItem.objects.create(order=order, product=self.item1, qty=1, price=Decimal('300'))
        self.client.login(username='cust', password='secret12')
        r = self.client.get(reverse('order_detail_customer', args=[order.id]))
        self.assertTrue(r.context['store_rejected'])
        self.assertContains(r, 'Store abhi bohat busy hai')
        self.assertIn(self.p2, r.context['suggested_stores'])
        self.assertNotIn(self.p1, r.context['suggested_stores'])

    def test_customer_cannot_cancel_after_vendor_accepts(self):
        order = SaleOrder.objects.create(
            customer=self.customer, warehouse=self.wh, status='confirmed', vendor=self.v1)
        self.client.login(username='cust', password='secret12')
        d = self.client.post(reverse('cancel_order_customer', args=[order.id])).json()
        self.assertFalse(d['success'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')
