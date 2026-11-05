"""
Django tests for the Vendor Portal.

Copy this file to app/tests_vendor_portal.py and run:
    python manage.py test app.tests_vendor_portal

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import (Category, Inventory, Product, StockBatch, Vendor,
                        VendorProfile, Warehouse)


def png_file(name='p.png'):
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


REG = {
    'business_name': 'Khan Traders', 'full_name': 'Ali Khan', 'phone': '03001234567',
    'email': 'ali@example.com', 'city': 'Lahore', 'address': 'House 1, Street 2, Lahore',
    'password': 'secret12', 'confirm_password': 'secret12',
}


class VendorAuthTests(TestCase):
    def test_register_creates_pending_vendor_and_logs_in(self):
        r = self.client.post(reverse('vendor_register'), REG)
        self.assertRedirects(r, reverse('vendor_dashboard'), fetch_redirect_response=False)
        prof = VendorProfile.objects.get(business_name='Khan Traders')
        self.assertFalse(prof.is_approved)
        self.assertEqual(prof.vendor.contact_number, '+923001234567')

    @override_settings(VENDOR_AUTO_APPROVE_ACCOUNTS=True)
    def test_auto_approve_setting(self):
        self.client.post(reverse('vendor_register'), REG)
        self.assertTrue(VendorProfile.objects.get().is_approved)

    def test_duplicate_phone_rejected(self):
        self.client.post(reverse('vendor_register'), REG)
        self.client.get(reverse('vendor_logout'))
        self.client.post(reverse('vendor_register'), dict(REG, email='other@example.com'))
        self.assertEqual(VendorProfile.objects.count(), 1)

    def test_login_ok_and_wrong_password(self):
        self.client.post(reverse('vendor_register'), REG)
        self.client.get(reverse('vendor_logout'))
        r = self.client.post(reverse('vendor_login'), {'phone': '0300-1234567', 'password': 'bad'})
        self.assertRedirects(r, reverse('vendor_login'), fetch_redirect_response=False)
        r = self.client.post(reverse('vendor_login'), {'phone': '03001234567', 'password': 'secret12'})
        self.assertRedirects(r, reverse('vendor_dashboard'), fetch_redirect_response=False)

    def test_login_ignores_offsite_next(self):
        self.client.post(reverse('vendor_register'), REG)
        self.client.get(reverse('vendor_logout'))
        r = self.client.post(reverse('vendor_login'), {
            'phone': '03001234567', 'password': 'secret12', 'next': 'https://evil.example/'})
        self.assertRedirects(r, reverse('vendor_dashboard'), fetch_redirect_response=False)

    def test_login_locks_after_repeated_failures(self):
        self.client.post(reverse('vendor_register'), REG)
        self.client.get(reverse('vendor_logout'))
        for _ in range(5):
            self.client.post(reverse('vendor_login'), {'phone': '03001234567', 'password': 'bad'})
        self.client.post(reverse('vendor_login'), {'phone': '03001234567', 'password': 'secret12'})
        r = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(r.status_code, 302)          # still not logged in

    def test_dashboard_needs_vendor(self):
        r = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(r.status_code, 302)
        User.objects.create_user('plain', password='x')
        self.client.login(username='plain', password='x')
        r = self.client.get(reverse('vendor_dashboard'))
        self.assertRedirects(r, reverse('shop_home'), fetch_redirect_response=False)


class VendorProductTests(TestCase):
    def setUp(self):
        self.wh = Warehouse.objects.create(name='Main')
        self.cat = Category.objects.create(name='Grocery')
        self.vendor = Vendor.objects.create(name='Khan Traders', contact_number='+923001234567')
        self.user = User.objects.create_user('vendor_1', 'v@x.com', 'secret12')
        self.profile = VendorProfile.objects.create(
            vendor=self.vendor, user=self.user, business_name='Khan Traders', is_approved=True)
        self.client.login(username='vendor_1', password='secret12')

    def _row(self, i, **over):
        """Ek product row ka POST data (multi-row form: p<i>-field)."""
        d = {'name': 'Rice 5kg', 'category': self.cat.id, 'price': '1500',
             'discount_percentage': '0', 'stock': '20', 'image': png_file()}
        d.update(over)
        return {f'p{i}-{k}': v for k, v in d.items()}

    def _post_rows(self, *rows):
        """rows = [dict of overrides, ...] -> ek hi submit mein sab."""
        data = {'row_ids': [str(i) for i in range(1, len(rows) + 1)]}
        for i, over in enumerate(rows, 1):
            data.update(self._row(i, **over))
        return self.client.post(reverse('vendor_product_add'), data)

    def _post_add(self, **over):
        return self._post_rows(over)

    def test_new_product_is_pending_and_hidden(self):
        self._post_add()
        p = Product.objects.get(name='Rice 5kg')
        self.assertEqual(p.vendor, self.vendor)
        self.assertEqual(p.approval_status, 'pending')
        self.assertFalse(p.is_active)
        self.assertEqual(Inventory.objects.get(product=p).stock, 20)
        b = StockBatch.objects.get(product=p)
        self.assertEqual((b.price, b.selling_price), (Decimal('1200'), Decimal('1500')))

    @override_settings(VENDOR_AUTO_APPROVE_PRODUCTS=True)
    def test_auto_approve_products(self):
        self._post_add()
        p = Product.objects.get(name='Rice 5kg')
        self.assertTrue(p.is_active)
        self.assertEqual(p.approval_status, 'approved')

    def test_invalid_price_rejected(self):
        self._post_add(price='0')
        self.assertFalse(Product.objects.filter(name='Rice 5kg').exists())

    def test_multiple_products_in_one_submit(self):
        r = self._post_rows({'name': 'Rice 5kg'}, {'name': 'Sugar 1kg', 'price': '150', 'stock': '50'},
                            {'name': 'Tea 500g', 'price': '900', 'stock': '10'})
        self.assertRedirects(r, reverse('vendor_dashboard'), fetch_redirect_response=False)
        self.assertEqual(Product.objects.filter(vendor=self.vendor).count(), 3)
        sugar = Product.objects.get(name='Sugar 1kg')
        self.assertEqual(Inventory.objects.get(product=sugar).stock, 50)
        self.assertEqual(StockBatch.objects.get(product=sugar).selling_price, Decimal('150'))

    def test_bad_row_does_not_block_good_rows(self):
        r = self._post_rows({'name': 'Rice 5kg'}, {'name': 'Bad one', 'price': 'abc'})
        self.assertEqual(r.status_code, 200)                       # form wapas, sirf ghalat row ke saath
        self.assertTrue(Product.objects.filter(name='Rice 5kg').exists())
        self.assertFalse(Product.objects.filter(name='Bad one').exists())
        self.assertEqual(len(r.context['rows']), 1)
        self.assertEqual(r.context['rows'][0]['v']['name'], 'Bad one')

    def test_blank_rows_are_ignored(self):
        data = {'row_ids': ['1', '2']}
        data.update(self._row(1))
        data.update({'p2-category': self.cat.id})                  # sirf category chuni, baaqi khali
        r = self.client.post(reverse('vendor_product_add'), data)
        self.assertRedirects(r, reverse('vendor_dashboard'), fetch_redirect_response=False)
        self.assertEqual(Product.objects.count(), 1)

    def test_all_blank_shows_error(self):
        r = self.client.post(reverse('vendor_product_add'), {'row_ids': ['1']})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_row_limit(self):
        from app.customer.views_vendor_portal import MAX_BULK_ROWS
        self._post_rows(*[{'name': f'Item {i}'} for i in range(MAX_BULK_ROWS + 3)])
        self.assertEqual(Product.objects.count(), MAX_BULK_ROWS)

    def test_unapproved_vendor_cannot_add(self):
        self.profile.is_approved = False
        self.profile.save()
        self._post_add()
        self.assertFalse(Product.objects.exists())

    def test_vendor_cannot_edit_others_product(self):
        other = Vendor.objects.create(name='Other', contact_number='+923009999999')
        p = Product.objects.create(name='Theirs', vendor=other)
        r = self.client.get(reverse('vendor_product_edit', args=[p.pk]))
        self.assertEqual(r.status_code, 404)
        r = self.client.post(reverse('vendor_product_toggle', args=[p.pk]))
        self.assertEqual(r.status_code, 404)

    def test_toggle_only_for_approved(self):
        p = Product.objects.create(name='X', vendor=self.vendor, approval_status='pending', is_active=False)
        self.client.post(reverse('vendor_product_toggle', args=[p.pk]))
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        Product.objects.filter(pk=p.pk).update(approval_status='approved', is_active=True)
        self.client.post(reverse('vendor_product_toggle', args=[p.pk]))
        p.refresh_from_db()
        self.assertFalse(p.is_active)

    def test_editing_name_of_approved_product_needs_review(self):
        self._post_add()
        p = Product.objects.get(name='Rice 5kg')
        Product.objects.filter(pk=p.pk).update(approval_status='approved', is_active=True)
        self.client.post(reverse('vendor_product_edit', args=[p.pk]), {
            'name': 'Rice 10kg', 'category': self.cat.id, 'price': '1500', 'discount_percentage': '0', 'stock': '0'})
        p.refresh_from_db()
        self.assertEqual((p.approval_status, p.is_active), ('pending', False))

    def test_price_change_keeps_product_live_and_updates_batch(self):
        self._post_add()
        p = Product.objects.get(name='Rice 5kg')
        Product.objects.filter(pk=p.pk).update(approval_status='approved', is_active=True)
        self.client.post(reverse('vendor_product_edit', args=[p.pk]), {
            'name': 'Rice 5kg', 'category': self.cat.id, 'price': '1600', 'discount_percentage': '0', 'stock': '0'})
        p.refresh_from_db()
        self.assertTrue(p.is_active)
        self.assertEqual(StockBatch.objects.get(product=p).selling_price, Decimal('1600'))


class VendorStoreTests(TestCase):
    """Step 1: vendor ka Store (settings, stores list/detail, band store se order nahi)."""

    def setUp(self):
        self.wh = Warehouse.objects.create(name='Main')
        self.cat = Category.objects.create(name='Grocery')
        self.vendor = Vendor.objects.create(name='Khan Traders', contact_number='+923001234567')
        self.user = User.objects.create_user('vendor_1', 'v@x.com', 'secret12')
        self.profile = VendorProfile.objects.create(
            vendor=self.vendor, user=self.user, business_name='Khan Traders', is_approved=True, city='Lahore')
        self.product = Product.objects.create(
            name='Rice 5kg', vendor=self.vendor, category=self.cat, price=1500,
            approval_status='approved', is_active=True)
        Inventory.objects.create(product=self.product, warehouse=self.wh, stock=10)

    def _login(self):
        self.client.login(username='vendor_1', password='secret12')

    def test_settings_saved(self):
        self._login()
        r = self.client.post(reverse('vendor_store_settings'), {
            'store_status': 'busy', 'store_description': 'Best rice', 'opens_at': '09:00', 'closes_at': '21:30',
            'min_order_amount': '500', 'delivery_fee': '100', 'delivery_time_min': '20', 'delivery_time_max': '40'})
        self.assertRedirects(r, reverse('vendor_store_settings'), fetch_redirect_response=False)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.store_status, 'busy')
        self.assertEqual(self.profile.delivery_fee, Decimal('100.00'))
        self.assertEqual(self.profile.delivery_time_max, 40)

    def test_bad_settings_rejected(self):
        self._login()
        self.client.post(reverse('vendor_store_settings'), {
            'store_status': 'open', 'opens_at': '09:00', 'closes_at': '',        # sirf ek time
            'min_order_amount': 'abc', 'delivery_time_min': '50', 'delivery_time_max': '10'})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.delivery_time_min, 30)                     # kuch save nahi hua

    def test_open_hours_including_overnight(self):
        from datetime import time
        from unittest import mock
        p = self.profile
        with mock.patch('django.utils.timezone.localtime') as lt:
            lt.return_value.time.return_value = time(23, 0)
            p.opens_at, p.closes_at = time(9, 0), time(21, 0)
            self.assertFalse(p.is_within_hours)
            p.opens_at, p.closes_at = time(18, 0), time(2, 0)                   # raat ko paar
            self.assertTrue(p.is_within_hours)
        p.store_status = 'closed'
        self.assertFalse(p.is_open_now)

    def test_store_list_and_detail(self):
        r = self.client.get(reverse('store_list'))
        self.assertContains(r, 'Khan Traders')
        r = self.client.get(reverse('store_detail', args=[self.profile.pk]))
        self.assertContains(r, 'Rice 5kg')

    def test_unapproved_store_hidden(self):
        self.profile.is_approved = False
        self.profile.save()
        self.assertNotContains(self.client.get(reverse('store_list')), 'Khan Traders')
        self.assertEqual(self.client.get(reverse('store_detail', args=[self.profile.pk])).status_code, 404)

    def test_closed_store_blocks_add_to_cart_and_buy_now(self):
        self.profile.store_status = 'closed'
        self.profile.save()
        r = self.client.post(reverse('add_to_cart'), {'product_id': self.product.id, 'quantity': 1})
        self.assertFalse(r.json()['success'])
        self.client.get(reverse('buy_now', args=[self.product.id]))
        self.assertFalse(self.client.session.get('cart'))

    def test_open_store_allows_add_to_cart(self):
        r = self.client.post(reverse('add_to_cart'), {'product_id': self.product.id, 'quantity': 1})
        self.assertTrue(r.json()['success'])
