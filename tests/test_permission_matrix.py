"""Permission-matrix enforcement tests.  Run:  python manage.py test tests.test_permission_matrix
(Django TestCase: needs the project's DB settings.)"""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from app.security.permission_catalog import MATRIX_KEYS, ROLE_DEFAULTS
from app.security.permissions import get_user_perms, has_matrix_perm, perm_required


def make_user(name, group=None, **kw):
    u = User.objects.create_user(name, f'{name}@x.com', 'Str0ng!Pass#1', **kw)
    if group:
        u.groups.add(Group.objects.get_or_create(name=group)[0])
    return u


class CatalogTests(TestCase):
    def test_role_defaults_only_use_known_keys(self):
        for role, (full, partial) in ROLE_DEFAULTS.items():
            self.assertFalse(set(full + partial) - MATRIX_KEYS, role)

    def test_unknown_key_fails_at_decoration_time(self):
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured):
            perm_required('veiw_sales')


class ResolutionTests(TestCase):
    def test_superuser_has_everything(self):
        su = User.objects.create_superuser('boss', 'b@x.com', 'Str0ng!Pass#1')
        self.assertEqual(get_user_perms(su), frozenset(MATRIX_KEYS))

    def test_role_defaults_until_matrix_saved(self):
        u = make_user('sam', 'Salesman')
        self.assertTrue(has_matrix_perm(u, 'create_sales'))
        self.assertFalse(has_matrix_perm(u, 'view_financials'))

    def test_roleless_user_only_has_dashboard(self):
        u = make_user('nobody')
        self.assertTrue(has_matrix_perm(u, 'view_dashboard'))
        self.assertFalse(has_matrix_perm(u, 'view_sales'))

    def test_saved_matrix_wins_over_defaults_even_when_emptied(self):
        boss = User.objects.create_superuser('boss', 'b@x.com', 'Str0ng!Pass#1')
        self.client.force_login(boss)
        # one "none" change marks the role as saved -> defaults no longer apply
        self.client.post(reverse('permission_matrix_save'),
                         json.dumps({'changes': [{'role': 'salesman', 'permission': 'create_sales',
                                                  'newStatus': 'none'}]}), content_type='application/json')
        u = make_user('sam', 'Salesman')
        self.assertFalse(has_matrix_perm(u, 'create_sales'))
        self.assertFalse(has_matrix_perm(u, 'view_sales'))      # nothing falls back to the defaults

    def test_union_of_groups(self):
        u = make_user('both', 'Salesman')
        u.groups.add(Group.objects.get_or_create(name='Accountant')[0])
        self.assertTrue(has_matrix_perm(u, 'create_sales', 'manage_cash', require_all=True))


class EnforcementTests(TestCase):
    def test_anonymous_goes_to_login(self):
        self.assertEqual(self.client.get(reverse('sale_list')).status_code, 302)

    def test_salesman_can_open_sales_but_not_finance(self):
        self.client.force_login(make_user('sam', 'Salesman'))
        self.assertEqual(self.client.get(reverse('sale_list')).status_code, 200)
        r = self.client.get(reverse('cash_dashboard'))
        self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)

    def test_accountant_can_view_cash(self):
        self.client.force_login(make_user('acc', 'Accountant'))
        self.assertEqual(self.client.get(reverse('cash_dashboard')).status_code, 200)

    def test_ajax_gets_json_403(self):
        self.client.force_login(make_user('sam', 'Salesman'))
        r = self.client.get(reverse('cash_dashboard'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 403)
        self.assertFalse(r.json()['success'])

    def test_superuser_passes_everywhere(self):
        self.client.force_login(User.objects.create_superuser('boss', 'b@x.com', 'Str0ng!Pass#1'))
        self.assertEqual(self.client.get(reverse('cash_dashboard')).status_code, 200)

    @override_settings(PERMISSION_MATRIX_MODE='off')
    def test_mode_off_disables_enforcement(self):
        self.client.force_login(make_user('sam', 'Salesman'))
        self.assertEqual(self.client.get(reverse('cash_dashboard')).status_code, 200)

    def test_user_management_respects_matrix_keys(self):
        owner = make_user('owner1', 'Owner')
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse('user_list')).status_code, 200)
