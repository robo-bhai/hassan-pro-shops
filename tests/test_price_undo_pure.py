"""Price undo tests that need no Django.

Run from the project root:  python -I tests/test_price_undo_pure.py
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


pu = _load('price_undo', 'app/utils/price_undo.py')
pr = _load('pricing', 'app/utils/pricing.py')
VALID = pr.check_selling_price


def row(id, batch, old, new, field='batch_selling_price', product='Urea', ref=None):
    return {'id': id, 'price_field': field, 'batch_id': batch, 'old': old, 'new': new,
            'product_name': product, 'batch_ref': ref or f'#{batch}'}


def st(price, cost='100'):
    return {'price': D(str(price)), 'cost': D(cost)}


def status(items):
    return [i['status'] for i in items]


class PlanUndo(unittest.TestCase):
    def test_simple_revert(self):
        items = pu.plan_undo([row(1, 10, '120', '150')], {10: st('150')}, VALID)
        self.assertEqual(status(items), [pu.ST_REVERT])
        self.assertEqual(items[0]['target'], D('120.00'))
        self.assertEqual(items[0]['current'], D('150.00'))

    def test_changed_again_is_left_alone(self):
        items = pu.plan_undo([row(1, 10, '120', '150')], {10: st('170')}, VALID)
        self.assertEqual(status(items), [pu.ST_CHANGED])
        self.assertIn('170.00', items[0]['message'])

    def test_already_reverted(self):
        items = pu.plan_undo([row(1, 10, '120', '150')], {10: st('120')}, VALID)
        self.assertEqual(status(items), [pu.ST_ALREADY])

    def test_missing_batch(self):
        self.assertEqual(status(pu.plan_undo([row(1, 10, '120', '150')], {}, VALID)), [pu.ST_MISSING])
        self.assertEqual(status(pu.plan_undo([row(1, None, '120', '150')], {}, VALID)), [pu.ST_MISSING])

    def test_old_price_below_current_cost_is_blocked(self):
        # cost rose from 100 to 130 after the change, so the old 120 would sell at a loss
        items = pu.plan_undo([row(1, 10, '120', '150')], {10: st('150', cost='130')}, VALID)
        self.assertEqual(status(items), [pu.ST_BELOW_COST])
        self.assertIn('cost', items[0]['message'].lower())

    def test_old_price_zero_means_clear_and_is_allowed(self):
        items = pu.plan_undo([row(1, 10, '0', '150')], {10: st('150')}, VALID)
        self.assertEqual(status(items), [pu.ST_REVERT])
        self.assertEqual(items[0]['target'], D('0.00'))

    def test_only_batch_selling_price_is_supported(self):
        items = pu.plan_undo([row(1, 10, '5', '10', field='product_discount')], {10: st('150')}, VALID)
        self.assertEqual(status(items), [pu.ST_UNSUPPORTED])
        items = pu.plan_undo([row(1, 10, None, '10')], {10: st('10')}, VALID)
        self.assertEqual(status(items), [pu.ST_UNSUPPORTED])

    def test_two_changes_to_one_batch_roll_back_in_order(self):
        rows = [row(1, 10, '120', '150'), row(2, 10, '150', '180')]
        items = pu.plan_undo(rows, {10: st('180')}, VALID)
        self.assertEqual(status(items), [pu.ST_REVERT, pu.ST_REVERT])
        self.assertEqual([i['log_id'] for i in items], [1, 2])  # oldest first for display
        self.assertEqual([i['target'] for i in items], [D('120.00'), D('150.00')])

    def test_input_state_is_not_modified(self):
        state = {10: st('150')}
        pu.plan_undo([row(1, 10, '120', '150')], state, VALID)
        self.assertEqual(state[10]['price'], D('150'))

    def test_mixed_run(self):
        rows = [row(1, 10, '120', '150'), row(2, 11, '120', '150'), row(3, 12, '120', '150'), row(4, 13, '1', '2')]
        state = {10: st('150'), 11: st('999'), 12: st('120')}
        items = pu.plan_undo(rows, state, VALID)
        self.assertEqual(status(items), [pu.ST_REVERT, pu.ST_CHANGED, pu.ST_ALREADY, pu.ST_MISSING])
        s = pu.summarize(items)
        self.assertEqual((s['total'], s['to_revert'], s['skipped'], s['can_apply']), (4, 1, 3, True))

    def test_nothing_to_revert_cannot_apply(self):
        s = pu.summarize(pu.plan_undo([row(1, 10, '120', '150')], {10: st('777')}, VALID))
        self.assertFalse(s['can_apply'])

    def test_every_status_has_a_label(self):
        for s in (pu.ST_REVERT, pu.ST_ALREADY, pu.ST_CHANGED, pu.ST_MISSING, pu.ST_BELOW_COST, pu.ST_UNSUPPORTED):
            self.assertIn(s, pu.LABELS)


class Helpers(unittest.TestCase):
    def test_rule_and_reason(self):
        self.assertEqual(pu.undo_rule(run_id='abc'), {'undo_of_run': 'abc'})
        self.assertEqual(pu.undo_rule(log_id='7'), {'undo_of_log': 7})
        self.assertEqual(pu.undo_reason(run_id='12345678-aaaa'), 'Undo of run 12345678')
        self.assertEqual(pu.undo_reason(log_id=7, extra=' wrong rate '), 'Undo of change #7: wrong rate')
        self.assertLessEqual(len(pu.undo_reason(log_id=7, extra='x' * 999)), 255)


class Wiring(unittest.TestCase):
    def test_sources_compile(self):
        for rel in ('app/utils/price_undo.py', 'app/views_frontend/inventory/price_history.py'):
            ast.parse(_read(rel))

    def test_urls_registered(self):
        urls = _read('app/urls.py')
        self.assertRegex(urls, r"price-history/undo/run/<uuid:run_id>/.*views_frontend\.price_undo.*name='price_undo_run'")
        self.assertRegex(urls, r"price-history/undo/change/<int:log_id>/.*views_frontend\.price_undo.*name='price_undo_change'")

    def test_view_is_protected_and_atomic(self):
        src = _read('app/views_frontend/inventory/price_history.py')
        self.assertIn("@perm_required('view_price_history', post='manage_products')", src)
        body = src[src.index('def price_undo('):]
        self.assertIn('transaction.atomic()', body)
        self.assertIn('select_for_update', src)
        # prices and log rows are written in the same atomic block
        self.assertLess(body.index('transaction.atomic()'), body.index('batch.save(update_fields=[\'selling_price\'])'))
        self.assertLess(body.index('batch.save(update_fields=[\'selling_price\'])'), body.index('price_audit.record(entries)'))
        self.assertIn("source='undo'", body)

    def test_view_name_not_shadowed_by_import(self):
        src = _read('app/views_frontend/inventory/price_history.py')
        self.assertNotRegex(src, r'import price_undo\s*$')  # must be aliased

    def test_view_exported_by_package(self):
        self.assertIn('inventory.price_history', _read('app/views_frontend/__init__.py'))

    def test_templates(self):
        undo = _read('templates/inventory/price_undo.html')
        self.assertIn('{% csrf_token %}', undo)
        self.assertIn('summary.can_apply', undo)
        hist = _read('templates/inventory/price_history.html')
        self.assertIn("{% url 'price_undo_run' run_uuid %}", hist)
        self.assertIn("{% url 'price_undo_change' r.pk %}", hist)
        for t in (undo, hist):
            self.assertEqual(len(re.findall(r'{%\s*if\b', t)), len(re.findall(r'{%\s*endif\s*%}', t)))
            self.assertEqual(len(re.findall(r'{%\s*for\b', t)), len(re.findall(r'{%\s*endfor\s*%}', t)))


if __name__ == '__main__':
    unittest.main()
