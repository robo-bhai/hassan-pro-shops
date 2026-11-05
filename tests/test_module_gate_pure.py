"""Administrator-bypass + Owner Security/System Tools switch: tests that need no Django project.

Run from the project root:  python -I tests/test_module_gate_pure.py
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load('module_gate', 'app/module_gate.py')
lite = _load('lite_edition', 'app/lite_edition.py')
catalog = _load('module_catalog', 'app/module_catalog.py')
BY_KEY = {m['key']: m for m in catalog.MODULE_CATALOG}
STATIC_KEYS = list(BY_KEY)


class _Groups:
    def __init__(self, names): self.names = names
    def filter(self, name=None): return self if name in self.names else _Groups([])
    def exists(self): return bool(self.names)


class FakeUser:
    def __init__(self, groups=(), superuser=False, auth=True):
        self.groups, self.is_superuser, self.is_authenticated = _Groups(list(groups)), superuser, auth


class Catalog(unittest.TestCase):
    def test_new_modules_exist_in_system_group(self):
        for k in ('security', 'system_tools'):
            self.assertEqual(BY_KEY[k]['group'], 'System')

    def test_security_default_off_system_tools_default_on(self):
        self.assertFalse(BY_KEY['security']['shop'])        # Owner never had these pages: stays closed until enabled
        self.assertTrue(BY_KEY['system_tools']['shop'])     # existing installs keep the permission matrix etc.

    def test_both_copies_in_sync(self):
        a, b = _read('app/module_catalog.py').split('\n', 1)[1], _read('app/module_config/module_catalog.py').split('\n', 1)[1]
        self.assertEqual(a, b)

    def test_prefixes_are_unique_across_modules(self):
        seen = {}
        for m in catalog.MODULE_CATALOG:
            for p in m['prefixes']:
                self.assertNotIn(p, seen, '%s also used by %s' % (p, seen.get(p)))
                seen[p] = m['key']

    def test_shop_edition_hides_both_by_default(self):
        _, hide = lite.shop_plan(STATIC_KEYS)
        self.assertIn('security', hide)
        self.assertIn('system_tools', hide)

    def test_shop_edition_core_modules_unchanged(self):
        show, _ = lite.shop_plan(STATIC_KEYS)
        self.assertEqual(sorted(show), sorted(lite.SHOP_CORE + lite.SHOP_OPTIONAL_ON))


class Gate(unittest.TestCase):
    OFF, ON = {'security': False}, {'security': True}

    def test_superuser_always(self):
        self.assertTrue(gate.can_use_security(FakeUser(superuser=True), self.OFF))
        self.assertTrue(gate.module_on_for(FakeUser(superuser=True), 'security', self.OFF))

    def test_owner_only_when_module_on(self):
        owner = FakeUser(['Owner'])
        self.assertFalse(gate.can_use_security(owner, self.OFF))
        self.assertTrue(gate.can_use_security(owner, self.ON))

    def test_other_roles_never(self):
        for g in ('Store Manager', 'Accountant', 'Salesman', 'Warehouse Staff'):
            self.assertFalse(gate.can_use_security(FakeUser([g]), self.ON), g)

    def test_anonymous_and_roleless_never(self):
        self.assertFalse(gate.can_use_security(FakeUser(auth=False), self.ON))
        self.assertFalse(gate.can_use_security(FakeUser(), self.ON))

    def test_missing_key_means_off(self):
        self.assertFalse(gate.module_on_for(FakeUser(['Owner']), 'security', {}))


class Wiring(unittest.TestCase):
    def test_middleware_skips_superuser_and_keeps_2fa_open(self):
        for rel in ('app/module_access.py', 'app/middleware/module_access.py'):
            s = _read(rel)
            self.assertIn('user.is_authenticated and not user.is_superuser', s)
            self.assertIn("ALWAYS_OPEN = ('/security/two-factor/', '/security/change-password/')", s)
            self.assertIn('not request.path.startswith(ALWAYS_OPEN)', s)

    def test_context_processors_give_admin_everything_and_expose_owner(self):
        for rel in ('app/context_processors.py', 'app/config/context_processors.py'):
            s = _read(rel)
            self.assertIn("if getattr(user, 'is_superuser', False):", s)
            self.assertIn("'IS_OWNER': _is_owner,", s)
            self.assertIn("'LITE_MODE': is_lite(),", s)

    def test_security_views_use_the_gate(self):
        for rel in ('app/views_security.py', 'app/views_modules/views_security.py', 'app/security/views_security.py'):
            s = _read(rel)
            self.assertEqual(s.count('can_use_security(request.user)'), 7)
            self.assertNotIn('if not request.user.is_superuser:', s)
            self.assertIn('from app.module_gate import can_use_security', s)

    def test_sidebar_wraps(self):
        s = _read('templates/components/sidebar.html')
        self.assertIn('{% if request.user.is_superuser or IS_OWNER and SHOW_SECURITY_MODULE %}', s)
        self.assertEqual(s.count('{% if SHOW_SYSTEM_TOOLS_MODULE %}'), 4)
        self.assertIn('{% if SHOW_SHAREHOLDERS_MODULE %}\n        <li><a href="{% url \'strategy_allocations_list\' %}"', s)
        # the whole System section sits behind the switch
        self.assertIn('{% if SHOW_SYSTEM_TOOLS_MODULE %}\n<li class="has-submenu">\n    <a href="#systemSubmenu"', s)
        # if / endif stay balanced
        import re
        opens = len(re.findall(r'\{%\s*if\s', s))
        closes = len(re.findall(r'\{%\s*endif\s*%\}', s))
        self.assertEqual(opens, closes)
        # the existing Lite wiring test must keep passing
        self.assertIn("{% if LITE_MODE %}{% include 'components/sidebar_lite_menu.html' %}{% else %}", s)


if __name__ == '__main__':
    unittest.main()
