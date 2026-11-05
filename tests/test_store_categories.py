"""
Django tests for Store Categories (store type: Restaurants, Grocery, Pharmacy...).

Copy to app/tests_store_categories.py and run:
    python manage.py test app.tests_store_categories
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.models import (Category, Inventory, Product, StoreCategory, Vendor,
                        VendorProfile, Warehouse)


def make_store(name, phone, store_category=None, user=None):
    vendor = Vendor.objects.create(name=name, contact_number=phone)
    user = user or User.objects.create_user(f'u_{phone[-4:]}', f'{phone[-4:]}@x.com', 'secret12')
    profile = VendorProfile.objects.create(
        vendor=vendor, user=user, business_name=name, is_approved=True, store_category=store_category)
    prod = Product.objects.create(
        name=f'{name} item', vendor=vendor, category=Category.objects.get_or_create(name='Misc')[0],
        price=100, approval_status='approved', is_active=True)
    Inventory.objects.create(product=prod, warehouse=Warehouse.objects.get_or_create(name='Main')[0], stock=5)
    return profile


class StoreCategoryTests(TestCase):
    def setUp(self):
        self.food = StoreCategory.objects.get_or_create(name='Restaurants', defaults={'icon': '🍔'})[0]
        self.pharm = StoreCategory.objects.get_or_create(name='Pharmacy', defaults={'icon': '💊'})[0]
        self.burger = make_store('Burger Hub', '+923001110001', self.food)
        self.medico = make_store('Medico Plus', '+923001110002', self.pharm)

    def test_defaults_seeded_by_migration(self):
        self.assertTrue(StoreCategory.objects.filter(name='Grocery').exists())

    def test_filter_by_store_type(self):
        r = self.client.get(reverse('store_list'), {'type': self.food.id})
        self.assertContains(r, 'Burger Hub')
        self.assertNotContains(r, 'Medico Plus')

    def test_no_filter_shows_all(self):
        r = self.client.get(reverse('store_list'))
        self.assertContains(r, 'Burger Hub')
        self.assertContains(r, 'Medico Plus')

    def test_bad_type_value_is_ignored(self):
        for bad in ('abc', '99999', ''):
            r = self.client.get(reverse('store_list'), {'type': bad})
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'Burger Hub')

    def test_inactive_type_not_listed(self):
        self.pharm.is_active = False
        self.pharm.save()
        r = self.client.get(reverse('store_list'), {'type': self.pharm.id})
        self.assertContains(r, 'Burger Hub')      # inactive type -> filter ignore

    def test_deleting_type_keeps_store(self):
        self.food.delete()
        self.burger.refresh_from_db()
        self.assertIsNone(self.burger.store_category)

    def test_vendor_can_set_category_in_settings(self):
        self.client.login(username=self.burger.user.username, password='secret12')
        r = self.client.post(reverse('vendor_store_settings'), {
            'store_status': 'open', 'store_category': self.pharm.id,
            'min_order_amount': '0', 'delivery_fee': '0',
            'delivery_time_min': '30', 'delivery_time_max': '45'})
        self.assertEqual(r.status_code, 302)
        self.burger.refresh_from_db()
        self.assertEqual(self.burger.store_category, self.pharm)

    def test_store_detail_shows_type(self):
        r = self.client.get(reverse('store_detail', args=[self.burger.pk]))
        self.assertContains(r, 'Restaurants')
