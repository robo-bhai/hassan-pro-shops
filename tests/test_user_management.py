"""User Management tests.  Run:  python manage.py test tests.test_user_management
(Django TestCase: needs the project's DB settings.)"""
import json
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from app.models import SystemSetting


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@x.com', 'Str0ng!Pass#1')
        self.owner = User.objects.create_user('owner1', 'o@x.com', 'Str0ng!Pass#2')
        self.owner.groups.add(Group.objects.get_or_create(name='Owner')[0])
        self.clerk = User.objects.create_user('clerk', 'c@x.com', 'Str0ng!Pass#3')

    def post_json(self, name, payload, **kw):
        return self.client.post(reverse(name, **kw), json.dumps(payload), content_type='application/json')

    # --- access -------------------------------------------------------------------
    def test_non_manager_is_blocked(self):
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.get(reverse('user_list')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quick_view_user', args=[self.admin.pk])).status_code, 403)

    def test_delete_and_toggle_reject_get(self):
        self.client.force_login(self.admin)
        self.client.get(reverse('user_delete', args=[self.clerk.pk]))
        self.client.get(reverse('user_toggle_status', args=[self.clerk.pk]))
        self.clerk.refresh_from_db()
        self.assertTrue(self.clerk.is_active)
        self.assertTrue(User.objects.filter(pk=self.clerk.pk).exists())

    # --- privilege escalation ---------------------------------------------------
    def test_owner_cannot_create_admin(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('user_create'), {
            'username': 'sneaky', 'password': 'Str0ng!Pass#9', 'confirm_password': 'Str0ng!Pass#9',
            'role': 'admin', 'is_active': 'on'})
        self.assertFalse(User.objects.filter(username='sneaky').exists())

    def test_owner_cannot_reset_admin_password(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('user_reset_password', args=[self.admin.pk]),
                         {'password': 'N3w!Passw0rd#', 'confirm_password': 'N3w!Passw0rd#'})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('Str0ng!Pass#1'))

    def test_owner_cannot_save_permission_matrix(self):
        self.client.force_login(self.owner)
        r = self.post_json('permission_matrix_save',
                           {'changes': [{'role': 'salesman', 'permission': 'view_sales', 'newStatus': 'full'}]})
        self.assertEqual(r.status_code, 403)

    def test_matrix_ignores_real_django_permissions(self):
        self.client.force_login(self.admin)
        self.post_json('permission_matrix_save',
                       {'changes': [{'role': 'salesman', 'permission': 'add_permission', 'newStatus': 'full'}]})
        g = Group.objects.filter(name='Salesman').first()
        self.assertTrue(g is None or not g.permissions.filter(codename='add_permission').exists())

    # --- lockout protection ---------------------------------------------------------
    def test_cannot_delete_or_deactivate_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('user_delete', args=[self.admin.pk]))
        self.client.post(reverse('user_toggle_status', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_last_admin_cannot_be_demoted(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('user_edit', args=[self.admin.pk]),
                         {'username': 'boss', 'role': 'salesman', 'is_active': 'on'})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_bulk_skips_self(self):
        self.client.force_login(self.admin)
        r = self.post_json('bulk_user_action', {'action': 'delete', 'user_ids': [self.admin.pk]})
        self.assertFalse(r.json()['success'])
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    # --- happy paths + validation ----------------------------------------------
    def test_create_user_with_role_and_weak_password(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('user_create'), {
            'username': 'weak', 'password': '123456', 'confirm_password': '123456', 'role': 'salesman'})
        self.assertFalse(User.objects.filter(username='weak').exists())
        self.client.post(reverse('user_create'), {
            'username': 'ali', 'password': 'Str0ng!Pass#9', 'confirm_password': 'Str0ng!Pass#9',
            'role': 'salesman', 'is_active': 'on', 'full_name': 'Ali Raza'})
        ali = User.objects.get(username='ali')
        self.assertTrue(ali.groups.filter(name='Salesman').exists())
        self.assertEqual((ali.first_name, ali.last_name), ('Ali', 'Raza'))

    def test_role_change_keeps_non_role_groups(self):
        other = Group.objects.create(name='Night Shift')
        self.clerk.groups.add(other)
        self.client.force_login(self.admin)
        self.client.post(reverse('user_edit', args=[self.clerk.pk]),
                         {'username': 'clerk', 'role': 'accountant', 'is_active': 'on'})
        names = set(self.clerk.groups.values_list('name', flat=True))
        self.assertEqual(names, {'Night Shift', 'Accountant'})

    def test_export_neutralises_formulas(self):
        User.objects.create_user('=cmd', 'e@x.com', 'Str0ng!Pass#4')
        self.client.force_login(self.admin)
        body = self.client.get(reverse('export_users')).content.decode('utf-8')
        self.assertIn("'=cmd", body)

    def test_activity_page_and_audit_log(self):
        from app.models import AccessLog
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('user_activity', args=[self.clerk.pk])).status_code, 200)
        self.client.post(reverse('user_toggle_status', args=[self.clerk.pk]))
        self.assertTrue(AccessLog.objects.filter(module='user_management', action='user_deactivated').exists())


class CustomRoleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@x.com', 'Str0ng!Pass#1')
        self.clerk = User.objects.create_user('clerk', 'c@x.com', 'Str0ng!Pass#3')
        self.client.force_login(self.admin)

    def add_role(self, name):
        return self.client.post(reverse('role_create'), {'name': name})

    def test_add_role_and_assign_it(self):
        self.add_role('Cashier')
        group = Group.objects.get(name='Role: Cashier')
        self.client.post(reverse('user_edit', args=[self.clerk.pk]), {
            'username': 'clerk', 'email': 'c@x.com', 'role': f'custom_{group.pk}', 'is_active': 'on'})
        self.assertTrue(self.clerk.groups.filter(pk=group.pk).exists())
        r = self.client.get(reverse('user_list'), {'role': f'custom_{group.pk}'})
        self.assertContains(r, 'clerk')

    def test_builtin_and_duplicate_names_rejected(self):
        self.add_role('Salesman')
        self.add_role('administrator')
        self.add_role('Cashier')
        self.add_role('cashier')
        self.assertEqual(Group.objects.filter(name__startswith='Role: ').count(), 1)

    def test_delete_unused_role(self):
        self.add_role('Cashier')
        group = Group.objects.get(name='Role: Cashier')
        self.client.post(reverse('role_delete', args=[group.pk]))
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def test_cannot_delete_role_in_use(self):
        self.add_role('Cashier')
        group = Group.objects.get(name='Role: Cashier')
        self.clerk.groups.add(group)
        self.client.post(reverse('role_delete', args=[group.pk]))
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())

    def test_builtin_role_cannot_be_deleted(self):
        g = Group.objects.get_or_create(name='Salesman')[0]
        self.client.post(reverse('role_delete', args=[g.pk]))
        self.assertTrue(Group.objects.filter(pk=g.pk).exists())

    def test_delete_rejects_get_and_non_managers(self):
        self.add_role('Cashier')
        group = Group.objects.get(name='Role: Cashier')
        self.client.get(reverse('role_delete', args=[group.pk]))
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())
        self.client.force_login(self.clerk)
        self.client.post(reverse('role_delete', args=[group.pk]))
        self.client.post(reverse('role_create'), {'name': 'Hacker'})
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())
        self.assertFalse(Group.objects.filter(name='Role: Hacker').exists())

    def test_unknown_custom_role_is_not_assignable(self):
        self.client.post(reverse('user_edit', args=[self.clerk.pk]), {
            'username': 'clerk', 'email': 'c@x.com', 'role': 'custom_99999', 'is_active': 'on'})
        self.assertFalse(self.clerk.groups.exists())


class RolePermissionAndBuiltinTests(TestCase):
    """Permissions on custom roles, and deleting / restoring built-in roles."""

    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@x.com', 'Str0ng!Pass#1')
        self.owner = User.objects.create_user('owner1', 'o@x.com', 'Str0ng!Pass#2')
        self.owner.groups.add(Group.objects.get_or_create(name='Owner')[0])
        self.clerk = User.objects.create_user('clerk', 'c@x.com', 'Str0ng!Pass#3')
        self.client.force_login(self.admin)

    def post_json(self, name, payload, **kw):
        return self.client.post(reverse(name, **kw), json.dumps(payload), content_type='application/json')

    def make_role(self, name='Cashier', **extra):
        self.client.post(reverse('role_create'), dict({'name': name}, **extra))
        return Group.objects.get(name=f'Role: {name}')

    # --- permissions on custom roles -------------------------------------------
    def test_admin_sets_permissions_when_creating_role(self):
        g = self.make_role(permissions=['view_sales', 'create_sales', 'not_a_real_key'])
        self.assertEqual(set(g.permissions.values_list('codename', flat=True)), {'view_sales', 'create_sales'})

    def test_owner_cannot_set_permissions_on_new_role(self):
        self.client.force_login(self.owner)
        g = self.make_role(permissions=['view_sales'])
        self.assertEqual(g.permissions.count(), 0)

    def test_custom_role_appears_in_matrix_and_is_saveable(self):
        g = self.make_role()
        self.assertContains(self.client.get(reverse('permission_matrix')), 'Cashier')
        r = self.post_json('permission_matrix_save',
                           {'changes': [{'role': f'custom_{g.pk}', 'permission': 'view_sales', 'newStatus': 'full'}]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(g.permissions.filter(codename='view_sales').exists())

    # --- built-in roles -----------------------------------------------------------
    def test_delete_builtin_role_hides_it_and_blocks_assignment(self):
        Group.objects.get_or_create(name='Salesman')
        self.client.post(reverse('role_delete_builtin', args=['salesman']))
        self.assertIn('salesman', SystemSetting.get_value('um_deleted_roles', ''))
        self.assertTrue(Group.objects.filter(name='Salesman').exists())  # group (and its perms) kept
        self.client.post(reverse('user_create'), {
            'username': 'newbie', 'password': 'Str0ng!Pass#9', 'confirm_password': 'Str0ng!Pass#9',
            'role': 'salesman', 'is_active': 'on'})
        self.assertFalse(User.objects.filter(username='newbie').exists())

    def test_restore_builtin_role(self):
        self.client.post(reverse('role_delete_builtin', args=['accountant']))
        self.client.post(reverse('role_restore_builtin', args=['accountant']))
        self.assertNotIn('accountant', SystemSetting.get_value('um_deleted_roles', ''))

    def test_builtin_role_in_use_cannot_be_deleted(self):
        self.clerk.groups.add(Group.objects.get_or_create(name='Salesman')[0])
        self.client.post(reverse('role_delete_builtin', args=['salesman']))
        self.assertNotIn('salesman', SystemSetting.get_value('um_deleted_roles', ''))

    def test_admin_and_staff_roles_are_protected(self):
        for key in ('admin', 'staff'):
            self.client.post(reverse('role_delete_builtin', args=[key]))
        self.assertEqual(SystemSetting.get_value('um_deleted_roles', ''), '')

    def test_only_administrator_can_delete_or_restore_builtin(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('role_delete_builtin', args=['manager']))
        self.assertNotIn('manager', SystemSetting.get_value('um_deleted_roles', ''))
        self.client.force_login(self.admin)
        self.client.post(reverse('role_delete_builtin', args=['manager']))
        self.client.force_login(self.owner)
        self.client.post(reverse('role_restore_builtin', args=['manager']))
        self.assertIn('manager', SystemSetting.get_value('um_deleted_roles', ''))

    def test_deleted_builtin_is_ignored_by_matrix_save(self):
        self.client.post(reverse('role_delete_builtin', args=['warehouse']))
        self.post_json('permission_matrix_save',
                       {'changes': [{'role': 'warehouse', 'permission': 'view_sales', 'newStatus': 'full'}]})
        g = Group.objects.filter(name='Warehouse Staff').first()
        self.assertTrue(g is None or not g.permissions.filter(codename='view_sales').exists())

    def test_delete_builtin_rejects_get(self):
        self.client.get(reverse('role_delete_builtin', args=['owner']))
        self.assertEqual(SystemSetting.get_value('um_deleted_roles', ''), '')
