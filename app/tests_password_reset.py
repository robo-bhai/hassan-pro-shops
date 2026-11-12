"""
Forgot-password tests: customer, vendor, rider aur admin/staff.

Run:  python manage.py test app.tests_password_reset -v 2

NOTE: settings.py zip mein nahi tha, is liye yeh tests likhe gaye magar chalaye nahi gaye.
Agar kisi fixture line par field ka naam ghalat nikle to setUp mein theek karein.
Cache locmem aur email locmem backend par override hain (Redis/SMTP ki zaroorat nahi).
"""
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import (Customer, CustomerOTP, CustomerProfile, OTPAuditLog, RiderProfile,
                        SecurityAlert, Vendor, VendorProfile)
from app.security import admin_reset
from app.utils import password_reset as pr

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
MAIL = 'django.core.mail.backends.locmem.EmailBackend'
OLD_PW = 'OldPassw0rd-1'
NEW_PW = 'Br4nd-New-Pass#42'
NO_WA = dict(WHATSAPP_PHONE_NUMBER_ID='', WHATSAPP_ACCESS_TOKEN='', WHATSAPP_OTP_TEMPLATE='')


def msgs(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def latest_code(phone, purpose):
    return CustomerOTP.objects.filter(phone=phone, purpose=purpose).latest('created_at').otp_code


@override_settings(CACHES=LOCMEM, EMAIL_BACKEND=MAIL, **NO_WA)
class ShopResetTests(TestCase):
    """Customer + vendor."""
    PHONE = '+923001111111'
    VPHONE = '+923002222222'

    def setUp(self):
        cache.clear()
        self.cuser = User.objects.create_user('cust1', 'c@x.com', OLD_PW)
        cust = Customer.objects.create(name='Zara', contact_number=self.PHONE, email='c@x.com', address='Lahore')
        CustomerProfile.objects.create(customer=cust, user=self.cuser)
        self.vuser = User.objects.create_user('vend1', 'v@x.com', OLD_PW)
        vendor = Vendor.objects.create(name='Store A', vendor_code='V-001', contact_number=self.VPHONE)
        VendorProfile.objects.create(vendor=vendor, user=self.vuser, business_name='Store A')

    def _request(self, phone):
        return self.client.post(reverse('customer_forgot_password'), {'phone': phone})

    def _reset(self, code, password=NEW_PW, confirm=None):
        return self.client.post(reverse('customer_reset_password'), {
            'code': code, 'password': password, 'confirm_password': password if confirm is None else confirm})

    def test_customer_full_flow(self):
        self._request('03001111111')
        r = self._reset(latest_code(self.PHONE, 'forgot_password'))
        self.assertRedirects(r, reverse('customer_login'), fetch_redirect_response=False)
        self.cuser.refresh_from_db()
        self.assertTrue(self.cuser.check_password(NEW_PW))
        self.assertTrue(OTPAuditLog.objects.filter(phone=self.PHONE, action='verify_success').exists())
        self.assertTrue(any('badal gaya' in m.subject for m in mail.outbox))

    def test_wrong_code_does_not_change_password(self):
        self._request('03001111111')
        self._reset('000000')
        self.cuser.refresh_from_db()
        self.assertTrue(self.cuser.check_password(OLD_PW))
        self.assertTrue(OTPAuditLog.objects.filter(phone=self.PHONE, action='verify_fail').exists())

    def test_lock_after_five_wrong_codes(self):
        self._request('03001111111')
        good = latest_code(self.PHONE, 'forgot_password')
        bad = '000000' if good != '000000' else '111111'
        for _ in range(5):
            self._reset(bad)
        self._reset(good)       # sahi code, magar lock
        self.cuser.refresh_from_db()
        self.assertTrue(self.cuser.check_password(OLD_PW))

    def test_expired_code(self):
        self._request('03001111111')
        CustomerOTP.objects.filter(phone=self.PHONE).update(expires_at=timezone.now() - timedelta(minutes=1))
        self._reset(latest_code(self.PHONE, 'forgot_password'))
        self.cuser.refresh_from_db()
        self.assertTrue(self.cuser.check_password(OLD_PW))

    def test_weak_or_mismatched_password_rejected_and_code_survives(self):
        self._request('03001111111')
        code = latest_code(self.PHONE, 'forgot_password')
        self._reset(code, password='12345')
        self._reset(code, password=NEW_PW, confirm='Different-Pass#9')
        self.cuser.refresh_from_db()
        self.assertTrue(self.cuser.check_password(OLD_PW))
        self.assertRedirects(self._reset(code), reverse('customer_login'), fetch_redirect_response=False)

    def test_unknown_phone_same_response_and_no_code(self):
        known = self._request('03001111111')
        unknown = self._request('03009999999')
        self.assertEqual(msgs(known)[-1], msgs(unknown)[-1])
        self.assertFalse(CustomerOTP.objects.filter(phone='+923009999999').exists())

    def test_staff_account_cannot_reset_here(self):
        self.cuser.is_staff = True
        self.cuser.save()
        self._request('03001111111')
        self.assertFalse(CustomerOTP.objects.filter(phone=self.PHONE).exists())

    def test_old_verify_url_redirects_to_reset(self):
        r = self.client.get(reverse('customer_forgot_verify'))
        self.assertEqual(r.status_code, 302)

    def test_vendor_full_flow(self):
        self._request('03002222222')
        r = self._reset(latest_code(self.VPHONE, 'forgot_password'))
        self.assertRedirects(r, reverse('vendor_login'), fetch_redirect_response=False)
        self.vuser.refresh_from_db()
        self.assertTrue(self.vuser.check_password(NEW_PW))

    def test_per_phone_attempt_limit(self):
        account = pr.find_account(self.PHONE, pr.SHOP_KINDS)
        pr.request_code(account)
        last = ''
        for _ in range(pr.PER_PHONE_VERIFY + 1):
            ok, last = pr.complete_reset(account, '000000', NEW_PW, NEW_PW, ip='1.2.3.4')
            self.assertFalse(ok)
        self.assertIn('Bohat zyada', last)
        self.assertTrue(OTPAuditLog.objects.filter(phone=self.PHONE, action='locked').exists())


@override_settings(CACHES=LOCMEM, EMAIL_BACKEND=MAIL, **NO_WA)
class RiderResetTests(TestCase):
    PHONE = '+923004444444'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('rider1', password=OLD_PW)
        self.rider = RiderProfile.objects.create(user=self.user, name='Bilal', phone=self.PHONE)

    def _request(self, phone='03004444444'):
        return self.client.post(reverse('rider_forgot_password'), {'phone': phone})

    def _reset(self, code, password=NEW_PW):
        return self.client.post(reverse('rider_reset_password'),
                                {'code': code, 'password': password, 'confirm_password': password})

    def test_rider_flow_with_manager_code(self):
        self._request()
        otp = CustomerOTP.objects.get(phone=self.PHONE, purpose='rider_reset')
        self.assertFalse(otp.is_sent_to_customer)       # WhatsApp/email nahi -> manager batayega
        r = self._reset(otp.otp_code)
        self.assertRedirects(r, reverse('rider_login'), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PW))

    def test_manager_page_shows_pending_code(self):
        self._request()
        boss = User.objects.create_user('boss', 'b@x.com', OLD_PW, is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        r = self.client.get(reverse('rider_manage'))
        self.assertEqual(len(r.context['pending_resets']), 1)

    def test_wrong_code_rejected(self):
        self._request()
        self._reset('000000')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PW))

    def test_inactive_or_unknown_rider_gets_no_code(self):
        self.rider.is_active = False
        self.rider.save()
        self._request()
        self._request('03008888888')
        self.assertFalse(CustomerOTP.objects.filter(purpose='rider_reset').exists())

    def test_rider_code_not_valid_for_shop_purpose(self):
        self._request()
        code = latest_code(self.PHONE, 'rider_reset')
        ok, _o, _m = CustomerOTP.find_and_verify(self.PHONE, code, purpose='forgot_password')
        self.assertFalse(ok)


@override_settings(CACHES=LOCMEM, EMAIL_BACKEND=MAIL)
class AdminResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('boss', 'boss@x.com', OLD_PW, is_staff=True, is_superuser=True)

    def _request(self, username='boss'):
        return self.client.post(reverse('admin_forgot_password'), {'username': username})

    def _code_from_mail(self):
        return re.search(r'code: (\d{6})', mail.outbox[-1].body).group(1)

    def _reset(self, code, password=NEW_PW):
        return self.client.post(reverse('admin_reset_password'), {
            'code': code, 'password': password, 'confirm_password': password})

    def test_flow(self):
        self._request()
        r = self._reset(self._code_from_mail())
        self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(NEW_PW))
        self.assertTrue(SecurityAlert.objects.filter(alert_type='password_change', user=self.admin).exists())
        self.assertTrue(any('badal gaya' in m.subject for m in mail.outbox))

    def test_wrong_email_code(self):
        self._request()
        self._reset('000000')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD_PW))

    def test_code_dies_after_five_wrong_attempts(self):
        self._request()
        good = self._code_from_mail()
        bad = '000000' if good != '000000' else '111111'
        for _ in range(admin_reset.MAX_CODE_ATTEMPTS):
            self._reset(bad)
        self._reset(good)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD_PW))

    def test_weak_password_rejected(self):
        self._request()
        self._reset(self._code_from_mail(), password='abc')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(OLD_PW))

    def test_no_mail_for_non_staff_or_missing_email_or_unknown(self):
        User.objects.create_user('shopper', 'shop@x.com', OLD_PW)                # staff nahi
        User.objects.create_user('noemail', '', OLD_PW, is_staff=True)           # email nahi
        for name in ('shopper', 'noemail', 'ghost'):
            self._request(name)
        self.assertEqual(len(mail.outbox), 0)

    def test_same_response_for_known_and_unknown(self):
        a = msgs(self._request('boss'))[-1]
        b = msgs(self._request('ghost'))[-1]
        self.assertEqual(a, b)

    def test_request_limit_per_account(self):
        for _ in range(admin_reset.REQ_PER_USER + 2):
            self._request()
        self.assertEqual(len(mail.outbox), admin_reset.REQ_PER_USER)
