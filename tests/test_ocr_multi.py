"""Tests for several-products-in-one-picture (no Django needed).

Run from the project root:  python -I tests/test_ocr_multi.py      (the JS part needs `node`; skipped without it)
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_source(rel):
    """Source text of a file. 'app/views_frontend/pos_sales/ocr.py' now means the whole ocr/ package (all its files)."""
    if rel == 'app/views_frontend/pos_sales/ocr.py':
        d = os.path.join(ROOT, 'app/views_frontend/pos_sales/ocr')
        return '\n'.join(open(os.path.join(d, n), encoding='utf-8').read() for n in sorted(os.listdir(d)) if n.endswith('.py'))
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load('app/utils/pos/ocr_core.py', 'ocr_core')


def item(pid, name, score=95, confident=True, whole=False):
    return {'whole': whole, 'confident': confident, 'id': pid, 'name': name, 'score': score}


class ResolveMultiTests(unittest.TestCase):
    def test_two_sure_labels_are_both_added(self):
        r = core.resolve_multi([item(1, 'Urea Super Gold', whole=True, confident=False),
                                item(1, 'Urea Super Gold', 96), item(2, 'Imidacloprid Plus', 91)])
        self.assertEqual(sorted(r), [1, 2])

    def test_unsure_items_never_added(self):
        self.assertEqual(core.resolve_multi([item(1, 'A Product', confident=False), item(None, '', confident=False)]), [])

    def test_same_product_twice_is_added_once_best_score_wins(self):
        r = core.resolve_multi([item(5, 'Lux Soap', 88), item(5, 'Lux Soap', 97)])
        self.assertEqual(r, [1])

    def test_piece_of_a_longer_name_is_dropped_when_whole_is_sure(self):
        # whole text sure about "Urea Super Gold"; a label that only found the short product "Urea" inside it
        r = core.resolve_multi([item(1, 'Urea Super Gold', 98, whole=True), item(9, 'Urea', 92)])
        self.assertEqual(r, [0])

    def test_short_name_kept_when_whole_is_not_sure(self):
        r = core.resolve_multi([item(1, 'Urea Super Gold', 90, confident=False, whole=True),
                                item(9, 'Urea', 92), item(2, 'Dettol Soap', 95)])
        self.assertEqual(sorted(r), [1, 2])

    def test_empty(self):
        self.assertEqual(core.resolve_multi([]), [])


NODE = shutil.which('node')


@unittest.skipUnless(NODE, 'node not installed')
class SegmentJsTests(unittest.TestCase):
    def run_js(self, words, opts=None):
        script = ("const M=require(%r);const w=JSON.parse(process.argv[2]);"
                  "console.log(JSON.stringify(M.segment(w,%s).map(s=>s.text)));"
                  % (os.path.join(ROOT, 'static/ocr/ocr_multi.js'), json.dumps(opts or {})))
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
            f.write(script)
        try:
            out = subprocess.check_output([NODE, f.name, json.dumps(words)], text=True)
        finally:
            os.unlink(f.name)
        return json.loads(out)

    @staticmethod
    def w(t, x, y, wd=60, h=20, c=85):
        return {'text': t, 'confidence': c, 'bbox': {'x0': x, 'y0': y, 'x1': x + wd, 'y1': y + h}}

    def test_two_labels_side_by_side(self):
        W = self.w
        r = self.run_js([W('Urea', 20, 20), W('Super', 90, 20), W('Gold', 160, 20), W('50kg', 20, 50),
                         W('Imidacloprid', 420, 22, 120), W('Plus', 550, 22), W('250ml', 420, 52)])
        self.assertEqual(r, ['Urea Super Gold 50kg', 'Imidacloprid Plus 250ml'])

    def test_one_label_stays_one(self):
        W = self.w
        self.assertEqual(self.run_js([W('Basmati', 10, 10), W('Rice', 80, 10), W('5kg', 10, 40)]), ['Basmati Rice 5kg'])

    def test_stacked_far_apart(self):
        W = self.w
        r = self.run_js([W('Dettol', 10, 10), W('Soap', 80, 10), W('Lux', 10, 200), W('Shampoo', 80, 200)])
        self.assertEqual(r, ['Dettol Soap', 'Lux Shampoo'])

    def test_noise_and_low_confidence_dropped(self):
        W = self.w
        r = self.run_js([W('Dettol', 10, 10), W('Soap', 80, 10), W('xq', 400, 10, 30, 20, 85), W('Lux', 10, 200, c=20)])
        self.assertEqual(r, ['Dettol Soap'])

    def test_empty(self):
        self.assertEqual(self.run_js([]), [])


class WiringTests(unittest.TestCase):
    def read(self, rel):
        return read_source(rel)

    def test_view_url_and_page(self):
        self.assertIn('def ocr_multi(request):', self.read('app/views_frontend/pos_sales/ocr.py'))
        self.assertIn("views_frontend.ocr_multi", self.read('app/urls.py'))
        page = self.read('templates/sales/pos.html')
        for needle in ("ocr/ocr_multi.js", "/ajax/ocr-multi/", "id=\"ocrMulti\"", "function ocrMatchMulti"):
            self.assertIn(needle, page, needle)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'static/ocr/ocr_multi.js')))


if __name__ == '__main__':
    unittest.main(verbosity=1)
