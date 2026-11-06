"""
Tests for the license system: signature, machine binding, expiry/grace/read-only, trial, clock
rollback, the read-only gate and the activation page.

Run:   python manage.py test app.tests_license -v 2

The middleware and the view are called directly (RequestFactory), so these tests do not depend on the
project's URL names or MIDDLEWARE list.
"""
import json
import os
import tempfile
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from app.licensing import core, ed25519
from app.licensing.views import license_page
from app.middleware.license_gate import LicenseMiddleware

SK = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')   # RFC 8032 test key
PK = ed25519.public_key(SK)
OTHER_SK = bytes(range(32))
TODAY = date(2026, 10, 31)
ME = core.machine_id()


def token(days, machine=ME, sk=SK):
    return core.make_token(sk, 'Haji Traders', machine, TODAY + timedelta(days=days), issued=TODAY)


class SignatureTests(SimpleTestCase):
    def test_rfc8032_vectors(self):
        sig = bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        self.assertEqual(PK.hex(), 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
        self.assertEqual(ed25519.sign(SK, b''), sig)
        self.assertTrue(ed25519.verify(PK, b'', sig))
        self.assertFalse(ed25519.verify(PK, b'x', sig))

    def test_malformed_input_never_raises(self):
        self.assertFalse(ed25519.verify(PK, b'm', b'short'))
        self.assertFalse(ed25519.verify(b'short', b'm', b'\0' * 64))
        self.assertFalse(ed25519.verify(PK, b'm', b'\xff' * 64))


class TokenTests(SimpleTestCase):
    def test_roundtrip(self):
        data = core.parse_token(token(30), PK)
        self.assertEqual((data['c'], data['m'], data['e']), ('Haji Traders', ME, (TODAY + timedelta(days=30)).isoformat()))

    def test_edited_expiry_is_rejected(self):
        head, body, sig = token(30).split('.')
        data = core._b64d(body).decode().replace((TODAY + timedelta(days=30)).isoformat(), '2099-01-01')
        self.assertIsNone(core.parse_token(f'{head}.{core._b64e(data.encode())}.{sig}', PK))

    def test_key_from_another_vendor_or_garbage_is_rejected(self):
        self.assertIsNone(core.parse_token(token(30, sk=OTHER_SK), PK))
        for junk in ('', 'junk', 'LIC1.a.b', None, 'LIC2.' + token(30).split('.', 1)[1]):
            self.assertIsNone(core.parse_token(junk, PK))

    def test_machine_id_is_stable_and_well_formed(self):
        self.assertEqual(core.machine_id(), core.machine_id())
        self.assertRegex(core.machine_id(), r'^[0-9A-F]{4}(-[0-9A-F]{4}){3}$')

    def test_machine_seed_gives_the_same_id_every_time_and_differs_per_seed(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'LICENSE_MACHINE_SEED': 'seed-one'}):
            a = core.machine_id()
            self.assertEqual(a, core.machine_id())
        with mock.patch.dict(os.environ, {'LICENSE_MACHINE_SEED': 'seed-two'}):
            self.assertNotEqual(a, core.machine_id())


class EvaluateTests(SimpleTestCase):
    def ev(self, days, machine=ME, grace=7):
        return core.evaluate(token(days, machine), PK, ME, TODAY, grace)

    def test_valid_and_expiring_soon(self):
        self.assertEqual((self.ev(90).state, self.ev(90).reason), ('valid', 'ok'))
        self.assertEqual((self.ev(10).state, self.ev(10).reason), ('valid', 'expiring'))
        self.assertEqual(self.ev(0).state, 'valid')                              # the last day still works

    def test_grace_period_then_read_only(self):
        self.assertEqual(self.ev(-1).state, 'grace')
        self.assertEqual(self.ev(-7).state, 'grace')                             # 7th day after expiry: still works
        self.assertEqual((self.ev(-8).state, self.ev(-8).reason), ('readonly', 'expired'))
        self.assertEqual(self.ev(-3, grace=0).state, 'readonly')

    def test_wrong_machine_is_read_only_but_wildcard_works_anywhere(self):
        self.assertEqual(self.ev(90, 'AAAA-BBBB-CCCC-DDDD').reason, 'wrong_machine')
        self.assertEqual(self.ev(90, '*').state, 'valid')

    def test_invalid_key_is_read_only(self):
        s = core.evaluate('LIC1.bad.bad', PK, ME, TODAY)
        self.assertEqual((s.state, s.reason), ('readonly', 'invalid'))


# ----------------------------------------------------------------------------------------- gate / views
def run_gate(method='POST', path='/sales/pos/', status_getter=None, content_type='application/x-www-form-urlencoded',
             headers=None, html=None):
    seen = {}

    def view(request):
        seen['called'] = True
        return HttpResponse(html if html is not None else 'ok')

    request = getattr(RequestFactory(), method.lower())(path, content_type=content_type, **(headers or {})) if method != 'GET' \
        else RequestFactory().get(path, **(headers or {}))
    return LicenseMiddleware(view)(request), seen


class GateTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.file = os.path.join(self.dir, 'license.key')
        self.cfg = override_settings(LICENSE_PUBLIC_KEY=PK.hex(), LICENSE_FILE=self.file)
        self.cfg.enable()
        self.addCleanup(self.cfg.disable)
        core._cache.clear()

    def put(self, days, machine=ME):
        with open(self.file, 'w') as f:
            f.write(core.make_token(SK, 'Haji Traders', machine, date.today() + timedelta(days=days)))
        core._cache.clear()

    def test_gate_is_off_when_no_public_key_is_configured(self):
        with override_settings(LICENSE_PUBLIC_KEY=''):
            core._cache.clear()
            response, seen = run_gate('POST')
        self.assertTrue(seen.get('called'))
        self.assertFalse(response.has_header('X-License-Block'))

    def test_valid_license_lets_changes_through(self):
        self.put(90)
        response, seen = run_gate('POST')
        self.assertTrue(seen.get('called'))
        self.assertFalse(response.has_header('X-License-Block'))

    def test_grace_period_still_works_and_shows_a_bar(self):
        self.put(-3)
        response, seen = run_gate('GET', html='<html><body>page</body></html>')
        self.assertIn(b'License', response.content)
        self.assertIn(b'page', response.content)
        response, seen = run_gate('POST')
        self.assertTrue(seen.get('called'))

    def test_expired_license_is_read_only(self):
        self.put(-30)
        response, seen = run_gate('GET')                                         # viewing still works
        self.assertTrue(seen.get('called'))
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            response, seen = run_gate(method)
            self.assertEqual(response.status_code, 403, method)
            self.assertEqual(response['X-License-Block'], '1')
            self.assertFalse(seen.get('called'), method)

    def test_blocked_ajax_call_gets_json(self):
        self.put(-30)
        response, _ = run_gate('POST', headers={'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertFalse(json.loads(response.content)['success'])

    def test_login_license_page_and_shift_close_stay_open_when_read_only(self):
        self.put(-30)
        for path in ('/license/', '/admin/login/', '/sales/shift/close/', '/sales/shift/12/close/', '/static/x.js'):
            response, seen = run_gate('POST', path=path)
            self.assertTrue(seen.get('called'), path)
        response, seen = run_gate('POST', path='/sales/shift/open/')             # opening a new shift is a change: blocked
        self.assertEqual(response.status_code, 403)

    def test_key_for_another_computer_is_read_only(self):
        self.put(90, machine='AAAA-BBBB-CCCC-DDDD')
        response, _ = run_gate('POST')
        self.assertEqual(response.status_code, 403)

    def test_internal_error_in_the_gate_does_not_stop_the_shop(self):
        from unittest import mock
        with mock.patch('app.middleware.license_gate.core.get_status', side_effect=RuntimeError('boom')):
            response, seen = run_gate('POST')
        self.assertTrue(seen.get('called'))

    # -- trial and clock -------------------------------------------------------------------------
    def test_no_key_starts_a_trial_then_goes_read_only(self):
        s = core.get_status(today=TODAY)
        self.assertEqual((s.state, s.reason), ('trial', 'trial'))
        self.assertEqual(s.days_left, 14)
        s = core.get_status(today=TODAY + timedelta(days=15))
        self.assertEqual((s.state, s.reason), ('readonly', 'trial_expired'))

    def test_setting_the_clock_back_is_caught(self):
        core.get_status(today=TODAY)
        s = core.get_status(today=TODAY - timedelta(days=10))
        self.assertEqual(s.reason, 'clock')
        self.assertTrue(s.read_only)

    # -- activation page -------------------------------------------------------------------------
    def post_key(self, user, key):
        request = RequestFactory().post('/license/', {'key': key})
        request.user = user
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()
        return license_page(request)

    def test_superuser_can_activate_with_a_key_for_this_computer(self):
        boss = User.objects.create_superuser('boss', 'b@x.com', 'x')
        response = self.post_key(boss, core.make_token(SK, 'Haji Traders', ME, date.today() + timedelta(days=365)))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(os.path.exists(self.file))
        self.assertEqual(core.get_status().state, 'valid')

    def test_wrong_machine_or_forged_key_is_not_saved(self):
        boss = User.objects.create_superuser('boss', 'b@x.com', 'x')
        for key in (core.make_token(SK, 'X', 'AAAA-BBBB-CCCC-DDDD', date.today() + timedelta(days=365)),
                    core.make_token(OTHER_SK, 'X', ME, date.today() + timedelta(days=365)), 'junk'):
            response = self.post_key(boss, key)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(os.path.exists(self.file))

    def test_ordinary_user_cannot_change_the_license(self):
        clerk = User.objects.create_user('clerk', 'c@x.com', 'x')
        response = self.post_key(clerk, core.make_token(SK, 'X', ME, date.today() + timedelta(days=365)))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(os.path.exists(self.file))


class StartupValidationTests(SimpleTestCase):
    def test_malformed_public_key_stops_the_server_instead_of_switching_licensing_off(self):
        for bad in ('<woh 64 hex>', 'abc', 'z' * 64, PK.hex()[:-1]):
            with override_settings(LICENSE_PUBLIC_KEY=bad):
                with self.assertRaises(ImproperlyConfigured):
                    LicenseMiddleware(lambda r: HttpResponse('ok'))

    def test_empty_key_means_licensing_off_and_a_good_key_starts(self):
        for good in ('', PK.hex()):
            with override_settings(LICENSE_PUBLIC_KEY=good):
                LicenseMiddleware(lambda r: HttpResponse('ok'))
