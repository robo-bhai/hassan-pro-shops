"""Minimum-margin policy tests that need no Django.

Run from the project root:  python -I tests/test_margin_policy_pure.py
"""
import ast
import importlib.util
import os
import re
import unittest
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _load('pricing', 'app/utils/pricing.py')
mp = _load('margin_policy', 'app/utils/margin_policy.py')
pu = _load('price_undo', 'app/utils/price_undo.py')


class Rules(unittest.TestCase):
    def test_min_price_rounds_up(self):
        self.assertEqual(pr.min_price_for('100', '5'), D('105.00'))
        self.assertEqual(pr.min_price_for('33.33', '5'), D('35.00'))      # 34.9965 -> up
        self.assertEqual(pr.min_price_for('100', None), D('100.00'))
        self.assertEqual(pr.min_price_for('100', '0'), D('100.00'))
        self.assertEqual(pr.min_price_for('0', '10'), D('0.00'))

    def test_shown_margin_never_below_rule(self):
        for cost in ('33.33', '7.77', '101.01', '999.99'):
            for pct in ('5', '7.5', '12.34'):
                floor = pr.min_price_for(cost, pct)
                self.assertGreaterEqual(pr.margin_percent(cost, floor), D(pct) - D('0.005'))
                self.assertGreaterEqual(floor, D(cost))

    def test_bad_settings_mean_no_rule(self):
        for bad in (None, '', '  ', 'abc', '-5', 'NaN', 'Infinity'):
            self.assertEqual(pr.normalize_margin(bad), D('0'), bad)
        self.assertEqual(pr.normalize_margin('1,5'), D('15'))   # thousands comma, same as parse_money

    def test_effective_category_wins(self):
        self.assertEqual(pr.effective_min_margin(None, '5'), D('5'))
        self.assertEqual(pr.effective_min_margin('', '5'), D('5'))
        self.assertEqual(pr.effective_min_margin('10', '5'), D('10'))
        self.assertEqual(pr.effective_min_margin('0', '5'), D('0'))     # explicit "no minimum"
        self.assertEqual(pr.effective_min_margin(None, None), D('0'))

    def test_check_with_margin(self):
        self.assertEqual(pr.check_selling_price('100', '105', '5'), D('105.00'))
        with self.assertRaises(pr.PriceError) as cm:
            pr.check_selling_price('100', '104.99', '5')
        self.assertIn('minimum margin of 5%', str(cm.exception))
        self.assertIn('105.00', str(cm.exception))

    def test_zero_clears_price_even_with_policy(self):
        self.assertEqual(pr.check_selling_price('100', '0', '50'), D('0.00'))

    def test_cost_rule_still_first(self):
        with self.assertRaises(pr.PriceError) as cm:
            pr.check_selling_price('100', '90', '5')
        self.assertIn('cost price', str(cm.exception))

    def test_old_calls_unchanged(self):
        self.assertEqual(pr.check_selling_price('100', '100'), D('100.00'))
        self.assertEqual(pr.compute_selling_price('100', 'percent', '20'), D('120.00'))

    def test_compute_respects_margin(self):
        self.assertEqual(pr.compute_selling_price('100', 'percent', '10', min_margin='5'), D('110.00'))
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'percent', '3', min_margin='5')
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'amount', '2', min_margin='5')
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'fixed', '104', min_margin='5')
        # rounding up can lift a price over the line
        self.assertEqual(pr.compute_selling_price('100', 'percent', '4.1', rounding='5', min_margin='5'), D('105.00'))


class Policy(unittest.TestCase):
    def test_resolution(self):
        p = mp.MarginPolicy('5', {1: '12', 2: '0', 3: None, 4: 'junk'})
        self.assertEqual(p.for_category_id(1), D('12'))
        self.assertEqual(p.for_category_id(2), D('0'))      # explicit zero
        self.assertEqual(p.for_category_id(3), D('5'))      # not set -> company
        self.assertEqual(p.for_category_id(4), D('5'))      # junk -> company
        self.assertEqual(p.for_category_id(99), D('5'))
        self.assertEqual(p.for_category_id(None), D('5'))

    def test_default_is_no_rule(self):
        self.assertEqual(mp.MarginPolicy().for_category_id(1), D('0'))
        self.assertEqual(mp.MarginPolicy('abc').company, D('0'))
        self.assertEqual(mp.MarginPolicy('-3').company, D('0'))

    def test_for_product(self):
        class P:  # noqa
            category_id = 1
        class Q:  # noqa
            category_id = None
        p = mp.MarginPolicy('5', {1: '12'})
        self.assertEqual(p.for_product(P()), D('12'))
        self.assertEqual(p.for_product(Q()), D('5'))


class UndoMargin(unittest.TestCase):
    def test_old_price_below_new_margin_policy_is_blocked(self):
        rows = [{'id': 1, 'price_field': 'batch_selling_price', 'batch_id': 10, 'old': '102', 'new': '150',
                 'product_name': 'Urea', 'batch_ref': '#10'}]
        state = {10: {'price': D('150'), 'cost': D('100'), 'min_margin': D('5')}}
        items = pu.plan_undo(rows, state, pr.check_selling_price)
        self.assertEqual(items[0]['status'], pu.ST_BELOW_COST)
        self.assertIn('minimum margin', items[0]['message'])

    def test_without_min_margin_in_state_behaves_as_before(self):
        rows = [{'id': 1, 'price_field': 'batch_selling_price', 'batch_id': 10, 'old': '102', 'new': '150',
                 'product_name': 'Urea', 'batch_ref': '#10'}]
        items = pu.plan_undo(rows, {10: {'price': D('150'), 'cost': D('100')}}, pr.check_selling_price)
        self.assertEqual(items[0]['status'], pu.ST_REVERT)

    def test_ok_when_old_price_meets_policy(self):
        rows = [{'id': 1, 'price_field': 'batch_selling_price', 'batch_id': 10, 'old': '106', 'new': '150',
                 'product_name': 'Urea', 'batch_ref': '#10'}]
        state = {10: {'price': D('150'), 'cost': D('100'), 'min_margin': D('5')}}
        self.assertEqual(pu.plan_undo(rows, state, pr.check_selling_price)[0]['status'], pu.ST_REVERT)


class Wiring(unittest.TestCase):
    def test_sources_compile(self):
        for rel in ('app/utils/pricing.py', 'app/utils/margin_policy.py', 'app/models/inventory/catalog.py',
                    'app/views_frontend/inventory/products.py', 'app/views_frontend/inventory/price_history.py',
                    'app/settings_catalog.py', 'app/admin/registrations.py',
                    'app/migrations/0036_category_min_margin.py'):
            ast.parse(_read(rel), rel)

    def test_migration_matches_model(self):
        mig = _read('app/migrations/0036_category_min_margin.py')
        self.assertIn("('app', '0035_pricechangelog')", mig)
        self.assertIn("name='min_margin_percent'", mig)
        model = _read('app/models/inventory/catalog.py')
        self.assertIn('min_margin_percent = models.DecimalField(', model)
        self.assertIn('max_digits=6, decimal_places=2, null=True, blank=True', model)
        self.assertIn("max_digits=6, null=True", mig)

    def test_every_price_path_uses_the_policy(self):
        src = _read('app/views_frontend/inventory/products.py')
        single = src[src.index('def update_batch_selling_price'):src.index('def bulk_update_batch_selling_price')]
        bulk = src[src.index('def bulk_update_batch_selling_price'):src.index('def product_update')]
        self.assertIn('MarginPolicy.load()', single)
        self.assertIn('check_selling_price(batch.price, new_price, min_pct)', single)
        self.assertIn('MarginPolicy.load()', bulk)
        self.assertIn('min_margin=policy.for_product(batch.product)', bulk)
        self.assertIn('MarginPolicy.load()', src[src.index('def batch_list'):src.index('def _batch_price_payload')])
        undo = _read('app/views_frontend/inventory/price_history.py')
        self.assertIn("'min_margin': policy.for_product(b.product)", undo)

    def test_model_clean_checks_policy_only_when_price_changes(self):
        src = _read('app/models/inventory/catalog.py')
        body = src[src.index('def from_db(cls, db, field_names, values)'):src.index('def save(self, *args, **kwargs):\n        """Run validation')]
        self.assertIn('_loaded_selling_price', body)
        self.assertIn('if self._selling_price_changed():', body)
        self.assertIn('MarginPolicy.load().for_product(self.product)', body)
        # a sale that only reduces stock must never be blocked by a newly raised policy
        self.assertLess(body.index('def _selling_price_changed'), body.index('def clean'))

    def test_settings_tab_and_admin(self):
        cat = _read('app/settings_catalog.py')
        self.assertIn("'key': 'pricing'", cat)
        self.assertIn("'name': 'min_margin_percent'", cat)
        self.assertEqual(mp.COMPANY_KEY, 'min_margin_percent')
        self.assertIn('admin.site.register(Category, CategoryAdmin)', _read('app/admin/registrations.py'))

    def test_template_uses_min_price(self):
        t = _read('templates/inventory/batches.html')
        self.assertIn('data-min=', t)
        self.assertIn('row.dataset.min', t)
        self.assertEqual(len(re.findall(r'{%\s*if\b', t)), len(re.findall(r'{%\s*endif\s*%}', t)))


if __name__ == '__main__':
    unittest.main()
