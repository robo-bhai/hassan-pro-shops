"""Lite Edition tests that need no Django project.

Run from the project root:  python -I tests/test_lite_edition_pure.py
(The template-syntax test also runs when Django is installed; otherwise it is skipped.)
"""
import importlib.util
import os
import re
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


lite = _load('lite_edition', 'app/lite_edition.py')
catalog = _load('module_catalog', 'app/module_catalog.py')
STATIC_KEYS = [m['key'] for m in catalog.MODULE_CATALOG]

LITE_TEMPLATES = ['templates/components/sidebar_lite_menu.html', 'templates/index_lite.html',
                  'templates/settings/_edition.html']


class LitePlan(unittest.TestCase):
    def test_show_and_hide_cover_every_module_exactly_once(self):
        show, hide = lite.lite_plan(STATIC_KEYS)
        self.assertEqual(sorted(show + hide), sorted(STATIC_KEYS))
        self.assertFalse(set(show) & set(hide))

    def test_lite_show_keys_exist_in_catalog(self):
        self.assertFalse(set(lite.LITE_SHOW) - set(STATIC_KEYS))
        self.assertFalse(set(lite.LITE_OPTIONAL) - set(STATIC_KEYS))

    def test_everyday_modules_stay_on(self):
        show, _ = lite.lite_plan(STATIC_KEYS)
        for k in ('sales', 'inventory', 'purchase', 'cash', 'accounts', 'backup'):
            self.assertIn(k, show)

    def test_heavy_modules_hidden(self):
        _, hide = lite.lite_plan(STATIC_KEYS)
        for k in ('shareholders', 'dividends', 'production', 'hr', 'ai', 'bi', 'budgets', 'loans',
                  'supply_chain', 'audit', 'testing', 'operations'):
            self.assertIn(k, hide)

    def test_also_keeps_extra_modules(self):
        show, hide = lite.lite_plan(STATIC_KEYS, also=['installment', 'hr'])
        self.assertIn('installment', show)
        self.assertIn('hr', show)
        self.assertNotIn('installment', hide)

    def test_auto_detected_modules_are_hidden(self):
        show, hide = lite.lite_plan(STATIC_KEYS + ['auto_targets'])
        self.assertIn('auto_targets', hide)
        self.assertNotIn('auto_targets', show)

    def test_setting_keys_cover_state_to_restore(self):
        keys = lite.setting_keys_for(['sales'])
        self.assertIn('business_mode', keys)
        self.assertIn(lite.LITE_LANG_KEY, keys)
        self.assertIn('mode_shop_sales', keys)


class LiteTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        urls = _read('app/urls.py')
        cls.url_names = set(re.findall(r"name\s*=\s*['\"]([\w\-]+)['\"]", urls))

    def test_every_url_name_used_by_lite_templates_exists(self):
        for rel in LITE_TEMPLATES:
            for name in re.findall(r"\{%\s*url\s+'([\w\-]+)'", _read(rel)):
                self.assertIn(name, self.url_names, '%s uses unknown url name %r' % (rel, name))

    def test_module_flags_used_exist(self):
        for rel in LITE_TEMPLATES:
            for flag in re.findall(r'\{%\s*if\s+SHOW_(\w+)_MODULE', _read(rel)):
                self.assertIn(flag.lower(), STATIC_KEYS, '%s: SHOW_%s_MODULE has no module' % (rel, flag))

    def test_template_syntax_compiles(self):
        try:
            from django.conf import settings
            import django
            if not settings.configured:
                settings.configure(TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                                               'APP_DIRS': False,
                                               'OPTIONS': {'builtins': []}}],
                                   INSTALLED_APPS=['django.contrib.humanize'])
                django.setup()
            from django.template import Engine
        except ImportError:
            self.skipTest('Django not installed')
        engine = Engine(libraries={'humanize': 'django.contrib.humanize.templatetags.humanize'})
        for rel in LITE_TEMPLATES:
            engine.from_string(_read(rel))          # raises TemplateSyntaxError on a mistake


class LiteWiring(unittest.TestCase):
    def test_sidebar_swaps_menu_in_lite_mode(self):
        s = _read('templates/components/sidebar.html')
        self.assertIn("{% if LITE_MODE %}{% include 'components/sidebar_lite_menu.html' %}{% else %}", s)
        self.assertEqual(s.count('<ul class="sidebar-menu">'), 1)
        # the {% endif %} sits right before the footer, after the full menu
        self.assertRegex(s, r"\{% endif %\}\n    </ul>\n    \n    <div class=\"sidebar-footer\">")

    def test_context_processors_expose_lite_mode(self):
        for rel in ('app/context_processors.py', 'app/config/context_processors.py'):
            s = _read(rel)
            self.assertIn("'LITE_MODE': is_lite()", s)
            self.assertIn('import is_lite', s)

    def test_language_default_hook_in_both_copies(self):
        for rel in ('app/i18n/i18n_lang.py', 'app/i18n_lang.py'):
            s = _read(rel)
            self.assertIn('_site_default() or DEFAULT_LANG', s)
            self.assertIn('from app.lite_edition import default_language', s)

    def test_dashboard_renders_lite_page(self):
        s = _read('app/views_frontend/system/dashboard.py')
        self.assertIn("render(request, 'index_lite.html', lite_dashboard_context(localdate()))", s)

    def test_enable_uses_live_catalog_and_command_calls_it(self):
        self.assertIn('from app.module_catalog import get_module_keys', _read('app/lite_edition.py'))
        cmd = _read('app/management/commands/lite_edition.py')
        self.assertIn('enable_lite(', cmd)
        self.assertIn('disable_lite()', cmd)

    def test_edition_card_is_a_partial_without_its_own_form(self):
        part = _read('templates/settings/_edition.html')
        self.assertNotIn('<form', part)                      # lives inside the page's single form
        self.assertIn('name="edition"', part)
        self.assertIn('value="lite"', part)
        self.assertIn('value="full"', part)

    def test_settings_center_modules_tab_includes_edition_inside_form(self):
        tpl = _read('templates/settings/center.html')
        form_at = tpl.index('<form method="POST" class="sc-form"')
        inc_at = tpl.index("{% include 'settings/_edition.html' %}")
        self.assertGreater(inc_at, form_at)
        self.assertLess(inc_at, tpl.index('</form>', form_at))
        self.assertIn("special == 'modules'", tpl[inc_at - 80:inc_at])

    def test_settings_center_view_handles_edition_first(self):
        view = _read('app/views_frontend/system/settings_center.py')
        self.assertIn('apply_edition_post(request.POST, user)', view)
        self.assertLess(view.index('apply_edition_post'), view.index('store.save(inst'))
        self.assertIn('edition_context()', view)

    def test_old_module_settings_page_is_gone(self):
        # Module Settings was merged into the Settings Center (Modules tab)
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'templates/admin/module_settings.html')))
        self.assertNotIn('def module_settings(', _read('app/views_frontend/system/dashboard.py'))
        self.assertNotIn("name='module_settings'", _read('app/urls.py'))
        self.assertIn("'key': 'modules'", _read('app/settings_catalog.py'))  # lives inside the Settings Center

class NoFactoryMode(unittest.TestCase):
    def test_settings_ui_has_no_factory_or_business_mode(self):
        for rel in ('templates/settings/_modules_matrix.html', 'templates/settings/_edition.html'):
            t = _read(rel).lower()
            self.assertNotIn('factory', t, rel)
            self.assertNotIn('business_mode', t, rel)
        self.assertNotIn('<div class="mode-chip', _read('templates/components/sidebar.html'))
        for rel in ('app/settings_catalog.py', 'app/module_config/settings_catalog.py'):
            self.assertNotIn("'name': 'business_mode'", _read(rel))

    def test_visibility_always_uses_shop_switch(self):
        for rel in ('app/context_processors.py', 'app/config/context_processors.py'):
            s = _read(rel)
            self.assertIn("mode = 'shop'", s)
            self.assertNotIn("get_value('business_mode'", s)
            self.assertNotIn("unit_enabled(m, 'factory')", s)

    def test_saving_modules_writes_only_shop_switch(self):
        for rel in ('app/views_frontend/system/settings_center.py',):
            s = _read(rel)
            self.assertNotIn("request.POST.get('mode_factory_", s)
            self.assertNotIn("SystemSetting.set_value('mode_factory_", s)


if __name__ == '__main__':
    unittest.main()
