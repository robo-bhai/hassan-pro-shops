"""Agri Edition tests that need no Django (same style as the other files in tests/).

Run from the project root:  python -I tests/test_agri_pure.py
"""
import ast
import importlib.util
import os
import re
import unittest
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


calc = _load('app/agri/calc.py', 'agri_calc')


class ExpiryStatusTests(unittest.TestCase):
    today = date(2026, 10, 27)

    def st(self, d):
        return calc.expiry_status(d, self.today)

    def test_none(self):
        self.assertEqual(self.st(None), ('none', None))

    def test_expired_yesterday(self):
        self.assertEqual(self.st(date(2026, 10, 26)), ('expired', -1))

    def test_today_is_not_expired(self):
        self.assertEqual(self.st(self.today), ('d30', 0))

    def test_bucket_edges(self):
        self.assertEqual(self.st(date(2026, 11, 26))[0], 'd30')    # +30
        self.assertEqual(self.st(date(2026, 11, 27))[0], 'd60')    # +31
        self.assertEqual(self.st(date(2026, 12, 26))[0], 'd60')    # +60
        self.assertEqual(self.st(date(2026, 12, 27))[0], 'd90')    # +61
        self.assertEqual(self.st(date(2027, 1, 25))[0], 'd90')     # +90
        self.assertEqual(self.st(date(2027, 1, 26))[0], 'ok')      # +91


class ParseTests(unittest.TestCase):
    def test_date(self):
        self.assertEqual(calc.parse_date(''), (True, None))
        self.assertEqual(calc.parse_date(None), (True, None))
        self.assertEqual(calc.parse_date('2026-11-05'), (True, date(2026, 11, 5)))
        self.assertEqual(calc.parse_date('05-11-2026'), (False, None))
        self.assertEqual(calc.parse_date('2026-02-30'), (False, None))

    def test_dec(self):
        self.assertEqual(calc.to_dec('1,500.50'), Decimal('1500.50'))
        self.assertEqual(calc.to_dec('abc'), Decimal('0.00'))
        self.assertEqual(calc.to_dec(''), Decimal('0.00'))
        self.assertEqual(calc.to_dec('NaN'), Decimal('0.00'))
        self.assertEqual(calc.to_dec('Infinity'), Decimal('0.00'))

    def test_whatsapp_number(self):
        self.assertEqual(calc.wa_number('0300-1234567'), '923001234567')
        self.assertEqual(calc.wa_number('+92 300 1234567'), '923001234567')
        self.assertEqual(calc.wa_number('00923001234567'), '923001234567')
        self.assertEqual(calc.wa_number('3001234567'), '923001234567')
        self.assertEqual(calc.wa_number(''), '')
        self.assertEqual(calc.wa_number(None), '')


class CreditDecisionTests(unittest.TestCase):
    d = staticmethod(calc.credit_decision)

    def test_no_limit_means_always_ok(self):
        self.assertEqual(self.d(0, 999999, 500000)[0], 'ok')
        self.assertEqual(self.d(None, 1, 1)[0], 'ok')

    def test_cash_sale_is_ok_even_if_over_limit(self):
        self.assertEqual(self.d(1000, 5000, 0)[0], 'ok')

    def test_within_limit(self):
        self.assertEqual(self.d(100000, 40000, 60000)[0], 'ok')      # exactly at the limit is fine

    def test_over_limit_blocks(self):
        action, msg = self.d(100000, 40000, 60001)
        self.assertEqual(action, 'block')
        self.assertIn('100,000', msg)
        self.assertIn('1 zyada', msg)

    def test_warn_mode_does_not_block(self):
        self.assertEqual(self.d(100000, 90000, 20000, 'warn')[0], 'warn')

    def test_off_mode(self):
        self.assertEqual(self.d(100000, 90000, 20000, 'off')[0], 'ok')

    def test_unknown_mode_falls_back_to_block(self):
        self.assertEqual(self.d(100, 90, 20, 'whatever')[0], 'block')

    def test_negative_outstanding_is_treated_as_zero(self):
        self.assertEqual(self.d(1000, -500, 900)[0], 'ok')


class WriteOffValueTests(unittest.TestCase):
    def test_value(self):
        with open(os.path.join(ROOT, 'app/agri/writeoff.py'), encoding='utf-8') as fh:
            src = fh.read()
        start = src.index('def writeoff_value'); end = src.index('@transaction.atomic')
        ns = {'Decimal': Decimal, 'ROUND_HALF_UP': __import__('decimal').ROUND_HALF_UP}
        exec(src[start:end], ns)
        f = ns['writeoff_value']
        self.assertEqual(f(2.5, '1200.00'), Decimal('3000.00'))
        self.assertEqual(f(0.333, '10.00'), Decimal('3.33'))
        self.assertEqual(f(1, '0.005'), Decimal('0.01'))


class StaticChecks(unittest.TestCase):
    """No Django here, so we check the wiring by reading the source."""

    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
            return fh.read()

    def test_every_python_file_parses(self):
        for rel in ('app/agri/views.py', 'app/agri/rules.py', 'app/agri/calc.py', 'app/agri/writeoff.py',
                    'app/agri/urls.py', 'app/models/inventory/agri.py', 'app/migrations/0029_agri_complete.py',
                    'app/management/commands/agri_alerts.py', 'app/views_frontend/pos_sales/pos.py',
                    'app/views_frontend/pos_sales/sales.py', 'app/views_frontend/purchase/po_pro.py',
                    'app/migrations/0030_agri_usage_snapshot.py', 'app/store/store_issue_service.py',
                    'app/store/store_transfer_service.py', 'app/store/store_ops_service.py',
                    'app/views_frontend/purchase/grn.py'):
            ast.parse(self.read(rel), rel)

    def test_migration_covers_new_model_fields(self):
        mig = self.read('app/migrations/0029_agri_complete.py')
        grn = self.read('app/models/trade/purchase_orders.py')
        prod = self.read('app/models/inventory/catalog.py')
        for name in ('batch_no', 'expiry_date'):
            self.assertIn("model_name='goodsreceiveditem', name='%s'" % name, mig)
            self.assertRegex(grn, r'\n\s+%s = models\.' % name)
        for name in ('active_ingredient', 'registration_no', 'pack_size', 'target_crops'):
            self.assertIn("model_name='product', name='%s'" % name, mig)
            self.assertRegex(prod, r'\n\s+%s = models\.' % name)
        wo = self.read('app/models/inventory/agri.py')
        for fld in re.findall(r'\n    (\w+) = models\.', wo):
            self.assertIn("('%s'," % fld, mig, 'migration is missing ExpiryWriteOff.%s' % fld)

    def test_migration_chain(self):
        mig = self.read('app/migrations/0029_agri_complete.py')
        self.assertIn("('app', '0028_agri_edition')", mig)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'app/migrations/0028_agri_edition.py')))
        leaves = sorted(f for f in os.listdir(os.path.join(ROOT, 'app/migrations')) if f[:4] in ('0029', '0030'))
        self.assertEqual(leaves, ['0029_agri_complete.py', '0030_agri_usage_snapshot.py'])
        self.assertIn("('app', '0029_agri_complete')", self.read('app/migrations/0030_agri_usage_snapshot.py'))

    def test_usage_snapshot_fields_in_migration_and_models(self):
        mig = self.read('app/migrations/0030_agri_usage_snapshot.py')
        for model, rel in (('storeissuebatchusage', 'app/models/inventory/store_issue.py'),
                           ('storetransferbatchusage', 'app/models/inventory/store_transfer.py')):
            src = self.read(rel)
            for name in ('batch_no', 'expiry_date'):
                self.assertIn("model_name='%s', name='%s'" % (model, name), mig)
                self.assertRegex(src, r'\n\s+%s = models\.' % name)

    def test_store_services_use_fefo_and_snapshot(self):
        for rel in ('app/store/store_issue_service.py', 'app/store/store_transfer_service.py'):
            src = self.read(rel)
            self.assertIn("expiry_date').asc(nulls_last=True)", src, rel)
            self.assertIn('usage-snapshot', src, rel)
        self.assertIn('usage-snapshot', self.read('app/store/store_ops_service.py'))

    def test_model_registered(self):
        self.assertIn('"inventory.agri"', self.read('app/models/__init__.py'))

    def test_every_agri_url_has_a_view(self):
        urls = self.read('app/agri/urls.py')
        views = self.read('app/agri/views.py')
        for fn in re.findall(r'views\.(\w+)', urls):
            self.assertRegex(views, r'\ndef %s\(' % fn)

    def test_urls_used_in_templates_exist(self):
        urls = self.read('app/agri/urls.py')
        names = set(re.findall(r"name='(\w+)'", urls))
        for root, _, files in os.walk(os.path.join(ROOT, 'templates')):
            for f in files:
                if not f.endswith('.html'):
                    continue
                with open(os.path.join(root, f), encoding='utf-8', errors='ignore') as fh:
                    txt = fh.read()
                for n in re.findall(r"\{% url '(agri_\w+)'", txt):
                    self.assertIn(n, names, '%s uses unknown url name %s' % (f, n))

    def test_sale_paths_keep_expiry_and_credit_rules(self):
        pos = self.read('app/views_frontend/pos_sales/pos.py')
        sales = self.read('app/views_frontend/pos_sales/sales.py')
        self.assertIn('check_credit_limit', pos)
        self.assertIn('check_credit_limit', sales)
        self.assertLess(sales.index('check_credit_limit'), sales.index('Sale.objects.create('),
                        'credit check must run before the sale is saved')
        self.assertIn('apply_harvest_due', pos)
        self.assertIn('apply_harvest_due', sales)

    def test_stock_batch_creators_carry_expiry(self):
        for rel in ('app/models/trade/sale_returns.py', 'app/models/trade/purchase_returns.py',
                    'app/store/store_transfer_service.py', 'app/views_frontend/pos_sales/shop_tools.py',
                    'app/views_frontend/purchase/grn.py', 'app/views_frontend/purchase/po_pro.py'):
            self.assertIn('agri-edition', self.read(rel), rel)


if __name__ == '__main__':
    unittest.main()
