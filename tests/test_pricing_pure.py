"""Selling-price rule tests that need no Django.

Run from the project root:  python -I tests/test_pricing_pure.py
"""
import importlib.util
import os
import unittest
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location('pricing', os.path.join(ROOT, 'app/utils/pricing.py'))
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


class ParseMoney(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(pr.parse_money('1,250.5'), D('1250.50'))
        self.assertEqual(pr.parse_money(' 10 '), D('10.00'))
        self.assertEqual(pr.parse_money(0), D('0.00'))

    def test_bad(self):
        for bad in (None, '', '  ', 'abc', '-1', 'NaN', 'Infinity'):
            with self.assertRaises(pr.PriceError, msg=repr(bad)):
                pr.parse_money(bad)


class CheckSellingPrice(unittest.TestCase):
    def test_below_cost_rejected(self):
        with self.assertRaises(pr.PriceError):
            pr.check_selling_price('100', '99.99')

    def test_at_or_above_cost_ok(self):
        self.assertEqual(pr.check_selling_price('100', '100'), D('100.00'))
        self.assertEqual(pr.check_selling_price('100', '120.456'), D('120.46'))

    def test_zero_clears(self):
        self.assertEqual(pr.check_selling_price('100', '0'), D('0.00'))

    def test_too_large(self):
        with self.assertRaises(pr.PriceError):
            pr.check_selling_price('100', '100000000')


class Compute(unittest.TestCase):
    def test_percent(self):
        self.assertEqual(pr.compute_selling_price('100', 'percent', '20'), D('120.00'))
        self.assertEqual(pr.compute_selling_price('99.99', 'percent', '20'), D('119.99'))

    def test_amount(self):
        self.assertEqual(pr.compute_selling_price('100', 'amount', '15.5'), D('115.50'))

    def test_fixed(self):
        self.assertEqual(pr.compute_selling_price('100', 'fixed', '150'), D('150.00'))

    def test_fixed_below_cost_rejected(self):
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'fixed', '90')

    def test_rounding_goes_up_never_down(self):
        self.assertEqual(pr.compute_selling_price('101', 'percent', '20', '5'), D('125.00'))   # 121.2 -> 125
        self.assertEqual(pr.compute_selling_price('101', 'percent', '20', '1'), D('122.00'))   # 121.2 -> 122
        self.assertEqual(pr.compute_selling_price('100', 'percent', '20', '10'), D('120.00'))  # exact stays
        self.assertEqual(pr.compute_selling_price('101', 'percent', '20', '10'), D('130.00'))

    def test_rounded_price_never_below_cost(self):
        for cost in ('0.01', '3.33', '99.99', '1234.56'):
            for step in ('none', '1', '5', '10'):
                self.assertGreaterEqual(pr.compute_selling_price(cost, 'percent', '0', step), D(cost))

    def test_zero_result_rejected(self):
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('0', 'percent', '20')

    def test_bad_mode_and_rounding(self):
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'weird', '20')
        with self.assertRaises(pr.PriceError):
            pr.compute_selling_price('100', 'percent', '20', '7')


class Margin(unittest.TestCase):
    def test_margin(self):
        self.assertEqual(pr.margin_percent('100', '125'), D('25.00'))
        self.assertEqual(pr.margin_percent('100', '0'), D('0.00'))
        self.assertEqual(pr.margin_percent('0', '50'), D('0.00'))


class WiredUp(unittest.TestCase):
    """The view and URL for the bulk tool exist and use the shared rules."""

    def test_wiring(self):
        views = open(os.path.join(ROOT, 'app/views_frontend/inventory/products.py'), encoding='utf-8').read()
        urls = open(os.path.join(ROOT, 'app/urls.py'), encoding='utf-8').read()
        tpl = open(os.path.join(ROOT, 'templates/inventory/batches.html'), encoding='utf-8').read()
        self.assertIn('def bulk_update_batch_selling_price', views)
        self.assertIn('pricing_rules.check_selling_price', views)
        self.assertIn("name='bulk_update_batch_sp'", urls)
        self.assertIn("{% url 'bulk_update_batch_sp' %}", tpl)
        self.assertIn("{% url 'update_batch_sp' %}", tpl)


if __name__ == '__main__':
    unittest.main()
