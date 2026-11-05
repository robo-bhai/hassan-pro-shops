"""Batch age / slow-moving helpers + static checks (no Django needed).

Run from the project root:  python -I tests/test_batch_age_pure.py
"""
import importlib.util
import os
import re
import unittest
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


spec = importlib.util.spec_from_file_location('batch_age', os.path.join(ROOT, 'app/utils/batch_age.py'))
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)
TODAY = date(2026, 10, 31)


class AgeTests(unittest.TestCase):
    def test_age_days(self):
        self.assertEqual(ba.age_days(date(2026, 10, 1), TODAY), 30)
        self.assertEqual(ba.age_days(datetime(2026, 10, 1, 23, 59), TODAY), 30)   # datetime ok
        self.assertEqual(ba.age_days(TODAY, TODAY), 0)

    def test_unknown_or_future_date(self):
        self.assertIsNone(ba.age_days(None, TODAY))
        self.assertIsNone(ba.age_days('2026-10-01', TODAY))
        self.assertEqual(ba.age_days(date(2026, 12, 1), TODAY), 0)                # never negative

    def test_slow_moving(self):
        old = date(2026, 7, 1)                                                    # 122 days
        self.assertTrue(ba.is_slow_moving(old, 5, TODAY))
        self.assertFalse(ba.is_slow_moving(old, 0, TODAY))                        # sold out
        self.assertFalse(ba.is_slow_moving(old, 0.00001, TODAY))                  # float leftover
        self.assertFalse(ba.is_slow_moving(date(2026, 10, 1), 5, TODAY))          # only 30 days
        self.assertFalse(ba.is_slow_moving(None, 5, TODAY))                       # no purchase date

    def test_boundary_is_inclusive(self):
        self.assertTrue(ba.is_slow_moving(date(2026, 8, 2), 1, TODAY))            # exactly 90 days
        self.assertFalse(ba.is_slow_moving(date(2026, 8, 3), 1, TODAY))           # 89 days

    def test_cutoff_matches_is_slow_moving(self):
        cut = ba.stale_cutoff(TODAY)
        self.assertEqual(cut, date(2026, 8, 2))
        self.assertTrue(ba.is_slow_moving(cut, 1, TODAY))


class WiringTests(unittest.TestCase):
    """Cheap checks that the pieces are still connected (the real run needs Django)."""

    def test_eps_values_agree(self):
        m = re.search(r'^STOCK_EPS\s*=\s*([0-9.]+)', _read('app/models/inventory/catalog.py'), re.M)
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group(1)), ba.STOCK_EPS)

    def test_batches_page_has_age_pieces(self):
        view = _read('app/views_frontend/inventory/products.py')
        tpl = _read('templates/inventory/batches.html')
        for needle in ("'age':", "'stale'", 'slow_stock_value'):
            self.assertIn(needle, view)
        for needle in ('data-sort="age"', 'value="stale"', 'slow_stock_value'):
            self.assertIn(needle, tpl)

    def test_table_colspan_matches_columns(self):
        tpl = _read('templates/inventory/batches.html')
        head = tpl[tpl.index('<thead>'):tpl.index('</thead>')]
        cols = len(re.findall(r'<th[\s>]', head))
        self.assertEqual(cols, int(re.search(r'<td colspan="(\d+)"', tpl).group(1)))

    def test_new_migration_follows_0036(self):
        mig = _read('app/migrations/0037_saleitembatchusage.py')
        self.assertIn("('app', '0036_category_min_margin')", mig)
        self.assertIn('saleusage_batch_idx', _read('app/models/trade/sales.py'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
