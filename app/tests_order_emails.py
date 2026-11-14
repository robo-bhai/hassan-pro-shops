"""
Naye order par email: vendor aur admin ko.
Run:  python manage.py test app.tests_order_emails -v 2
(Django yahan install nahi tha, is liye likhe gaye magar chalaye nahi gaye.)
Asli models ki jagah chhote fake objects, taake sirf email logic check ho.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings, RequestFactory

from app.customer import store_orders

MAIL = 'django.core.mail.backends.locmem.EmailBackend'


class FakeItems:
    def __init__(self, rows):
        self.rows = rows

    def select_related(self, *a):
        return self.rows


def fake_order(vendor_id=5):
    items = FakeItems([SimpleNamespace(product=SimpleNamespace(name='Burger <b>'), qty=2, price=Decimal('300'))])
    customer = SimpleNamespace(name='Zara', contact_number='+923001111111', address='Lahore')
    return SimpleNamespace(id=1, order_no='SO-100', vendor_id=vendor_id, customer=customer, items=items,
                           payment_method='cod')


@override_settings(EMAIL_BACKEND=MAIL)
class OrderEmailTests(TestCase):
    def setUp(self):
        User.objects.create_user('boss', 'boss@x.com', 'x', is_superuser=True, is_staff=True)
        self.request = RequestFactory().get('/')

    def _run(self, order, vendor_email='shop@x.com'):
        prof = SimpleNamespace(user=SimpleNamespace(email=vendor_email), user_id=1, vendor=SimpleNamespace(),
                               business_name='Store A')
        with mock.patch.object(store_orders, 'get_store_profile', return_value=prof), \
                mock.patch.object(store_orders, 'order_payable_total', return_value=Decimal('600')):
            with self.captureOnCommitCallbacks(execute=True):
                store_orders.email_new_order(order, self.request)

    def test_vendor_and_admin_both_get_mail(self):
        self._run(fake_order())
        to = sorted(addr for m in mail.outbox for addr in m.to)
        self.assertEqual(to, ['boss@x.com', 'shop@x.com'])

    def test_html_in_item_name_is_escaped(self):
        self._run(fake_order())
        html = mail.outbox[0].alternatives[0][0]
        self.assertNotIn('Burger <b>', html)

    def test_shop_own_order_only_admin(self):
        self._run(fake_order(vendor_id=0))
        self.assertEqual([m.to for m in mail.outbox], [['boss@x.com']])

    def test_vendor_without_email_does_not_break_order(self):
        self._run(fake_order(), vendor_email='')
        self.assertEqual([m.to for m in mail.outbox], [['boss@x.com']])


@override_settings(EMAIL_BACKEND=MAIL, ORDER_ALERT_EMAILS=['owner@x.com'])
class AdminRecipientTests(TestCase):
    """Superuser ki email na ho, shop admin (staff) ho, ya sirf ORDER_ALERT_EMAILS ho - alert phir bhi jaye."""

    def test_staff_and_setting_emails_are_included(self):
        User.objects.create_user('root', '', 'x', is_superuser=True, is_staff=True)   # email nahi
        User.objects.create_user('shopadmin', 'shopadmin@x.com', 'x', is_staff=True)  # shop admin
        User.objects.create_user('plain', 'plain@x.com', 'x')                          # normal user: nahi
        emails = store_orders.admin_alert_emails()
        self.assertIn('shopadmin@x.com', emails)
        self.assertIn('owner@x.com', emails)
        self.assertNotIn('plain@x.com', emails)

    def test_order_admin_users_has_staff_but_not_plain(self):
        User.objects.create_user('shopadmin', 's@x.com', 'x', is_staff=True)
        User.objects.create_user('plain', 'p@x.com', 'x')
        names = {u.username for u in store_orders.order_admin_users()}
        self.assertIn('shopadmin', names)
        self.assertNotIn('plain', names)
