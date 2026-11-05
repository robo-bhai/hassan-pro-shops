"""Price history (audit log) tests that need no Django.

Run from the project root:  python -I tests/test_price_audit_pure.py
"""
import ast
import importlib.util
import os
import re
import unittest
import uuid
from decimal import Decimal as D
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


_spec = importlib.util.spec_from_file_location('price_audit', os.path.join(ROOT, 'app/utils/price_audit.py'))
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)


class User:
    is_authenticated = True

    def __init__(self, username, full=''):
        self.username, self.full = username, full

    def get_full_name(self):
        return self.full

    def get_username(self):
        return self.username


class Anon:
    is_authenticated = False


class Helpers(unittest.TestCase):
    def test_real_change(self):
        self.assertFalse(pa.is_real_change('10', D('10.00')))
        self.assertFalse(pa.is_real_change(D('10.004'), D('10.00')))
        self.assertTrue(pa.is_real_change('10', '10.01'))
        self.assertTrue(pa.is_real_change(0, '5'))

    def test_client_ip(self):
        r = SimpleNamespace(META={'HTTP_X_FORWARDED_FOR': '1.2.3.4, 10.0.0.1', 'REMOTE_ADDR': '10.0.0.1'})
        self.assertEqual(pa.client_ip(r), '1.2.3.4')
        self.assertEqual(pa.client_ip(SimpleNamespace(META={'REMOTE_ADDR': '9.9.9.9'})), '9.9.9.9')
        self.assertIsNone(pa.client_ip(SimpleNamespace(META={})))
        self.assertIsNone(pa.client_ip(None))

    def test_user_label(self):
        self.assertEqual(pa.user_label(User('ali', 'Ali Khan')), 'Ali Khan')
        self.assertEqual(pa.user_label(User('ali')), 'ali')
        self.assertEqual(pa.user_label(Anon()), '')
        self.assertEqual(pa.user_label(None), '')

    def test_run_id_unique(self):
        self.assertNotEqual(pa.new_run_id(), pa.new_run_id())
        self.assertIsInstance(pa.new_run_id(), uuid.UUID)

    def test_rule_dict_is_json_safe(self):
        import json
        json.dumps(pa.rule_dict('percent', D('20'), None))
        self.assertEqual(pa.rule_dict('percent', '20', None)['rounding'], 'none')


class BuildEntry(unittest.TestCase):
    def test_fields(self):
        product = SimpleNamespace(name='Rice 5kg')
        batch = SimpleNamespace(pk=7)
        run = pa.new_run_id()
        e = pa.build_entry(price_field='batch_selling_price', source='bulk', old='100', new=D('120.456'),
                           product=product, batch=batch, cost='90', user=User('ali', 'Ali Khan'),
                           ip='1.2.3.4', run_id=run, rule={'mode': 'percent'}, reason='x' * 400)
        self.assertEqual(e['old_value'], D('100.00'))
        self.assertEqual(e['new_value'], D('120.46'))
        self.assertEqual(e['cost_price'], D('90.00'))
        self.assertEqual(e['product_name'], 'Rice 5kg')
        self.assertEqual(e['batch_ref'], '#7')
        self.assertEqual(e['changed_by_name'], 'Ali Khan')
        self.assertEqual(e['run_id'], run)
        self.assertEqual(len(e['reason']), 255)

    def test_anonymous_user_is_not_stored_as_fk(self):
        e = pa.build_entry(price_field='product_price', source='system', old=None, new=5, user=Anon())
        self.assertIsNone(e['changed_by'])
        self.assertIsNone(e['old_value'])
        self.assertEqual(e['batch_ref'], '')

    def test_record_empty_does_nothing(self):
        self.assertEqual(pa.record([]), [])


class Wiring(unittest.TestCase):
    """Cheap guards so a refactor can't silently remove the logging."""

    def test_every_source_file_compiles(self):
        for rel in ('app/models/inventory/price_log.py', 'app/utils/price_audit.py',
                    'app/views_frontend/inventory/price_history.py',
                    'app/views_frontend/inventory/products.py', 'app/migrations/0035_pricechangelog.py',
                    'app/admin/price_log.py', 'app/security/permission_catalog.py'):
            ast.parse(_read(rel), rel)

    def test_model_fields_match_migration(self):
        model = _read('app/models/inventory/price_log.py')
        mig = _read('app/migrations/0035_pricechangelog.py')
        fields = re.findall(r'^    (\w+) = models\.', model, re.M)
        fields = [f for f in fields if f != 'objects']
        for f in fields:
            self.assertIn(f"('{f}',", mig, f'{f} missing from migration 0035')

    def test_log_model_is_append_only(self):
        src = _read('app/models/inventory/price_log.py')
        self.assertIn('def delete', src)
        self.assertIn('can not be edited', src)
        self.assertIn('def update', src)

    def test_single_and_bulk_views_log_inside_transaction(self):
        src = _read('app/views_frontend/inventory/products.py')
        single = src.split('def update_batch_selling_price')[1].split('def bulk_update_batch_selling_price')[0]
        bulk = src.split('def bulk_update_batch_selling_price')[1].split('def product_update')[0]
        self.assertIn("source='single'", single)
        self.assertIn('price_audit.record', single)
        self.assertLess(single.index('transaction.atomic'), single.index('price_audit.record'))
        self.assertIn("source='bulk'", bulk)
        self.assertIn('run_id=run_id', bulk)
        self.assertIn('price_audit.record(log_entries)', bulk)
        # dry run must not log
        self.assertLess(bulk.index('if not dry_run:'), bulk.index('log_entries.append'))

    def test_migration_chain(self):
        # 0035 must exist and sit right after 0034; later steps (0036 ...) chain on top of it
        names = sorted(n for n in os.listdir(os.path.join(ROOT, 'app/migrations')) if re.match(r'\d{4}_', n))
        self.assertIn('0035_pricechangelog.py', names)
        self.assertGreaterEqual(names[-1], '0035_pricechangelog.py')
        self.assertIn("'0034_remove_stores_module'", _read('app/migrations/0035_pricechangelog.py'))

    def test_registered_everywhere(self):
        self.assertIn('inventory.price_log', _read('app/models/__init__.py'))
        self.assertIn('inventory.price_history', _read('app/views_frontend/__init__.py'))
        self.assertIn('"price_log"', _read('app/admin/__init__.py'))
        self.assertIn('views_frontend.price_history_list', _read('app/urls.py'))
        self.assertIn("'view_price_history'", _read('app/security/permission_catalog.py'))


if __name__ == '__main__':
    unittest.main()
