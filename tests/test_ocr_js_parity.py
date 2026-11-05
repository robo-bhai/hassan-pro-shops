"""The browser matcher (static/ocr/ocr_match.js) must rank exactly like app/utils/pos/ocr_core.py.

Run from the project root:  python -I tests/test_ocr_js_parity.py      (needs `node`; skipped if it is missing)
"""
import importlib.util
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load('app/utils/pos/ocr_core.py', 'ocr_core')

BRANDS = ['Sunsilk', 'Lux', 'Dettol', 'Surf Excel', 'Tapal', 'Shan', 'National', 'Dalda', 'Lipton', 'Nestle',
          'Olpers', 'Knorr', 'Safeguard', 'Head Shoulders', 'Colgate', 'Pepsodent', 'Rooh Afza', 'Ariel']
KINDS = ['Shampoo', 'Soap', 'Handwash', 'Washing Powder', 'Tea', 'Masala', 'Rice', 'Oil', 'Milk', 'Toothpaste',
         'Syrup', 'Biscuit', 'Noodles', 'Detergent']
SIZES = ['90ml', '180ml', '250ml', '1kg', '5kg', '500g', '200g', '1L', '12 pcs']
URDU = ['\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646', '\u0633\u0631\u0641 \u0627\u06a9\u0633\u0644']


def typo(s, rnd):
    s = list(s)
    for _ in range(rnd.choice([0, 0, 1, 2])):
        if len(s) > 3:
            i = rnd.randrange(len(s))
            op = rnd.choice('dsx')
            if op == 'd':
                del s[i]
            elif op == 's':
                s[i] = rnd.choice('abcdefghijklmnopqrstuvwxyz')
            else:
                s.insert(i, rnd.choice('aeiou'))
    return ''.join(s)


def make_data(seed=7, n=900):
    rnd = random.Random(seed)
    items, seen = [], set()
    while len(items) < n:
        name = '%s %s %s' % (rnd.choice(BRANDS), rnd.choice(KINDS), rnd.choice(SIZES))
        if name in seen:
            continue
        seen.add(name)
        barcode = ''.join(rnd.choice('0123456789') for _ in range(13)) if rnd.random() < 0.5 else ''
        aliases = [typo(name.lower(), rnd)] if rnd.random() < 0.2 else []
        if rnd.random() < 0.03:
            aliases.append(rnd.choice(URDU))
        items.append([len(items) + 1, name, barcode, aliases])
    queries = []
    for it in rnd.sample(items, 150):
        base = it[1] if rnd.random() < 0.7 else ' '.join(it[1].split()[:2])
        q = typo(base, rnd)
        r = rnd.random()
        if r < 0.15:
            q += ' MRP Rs 250 mfg date best before'
        elif r < 0.25 and it[2]:
            q = 'junk %s %s' % (it[2][:6] + ' ' + it[2][6:], q)
        elif r < 0.30:
            q = it[1].upper()
        queries.append(q)
    queries += ['sunsilk shampoo 1l', 'tapal tea 500 g', 'rice 5 kg', 'lux soap 1,5l', 'dettol handwash 250 ML',
                'colgate toothpaste 1000g', 'olpers milk 1.5 ltr', 'shan masala 190ml', '90ml 180ml 1kg',
                '', 'xx', 'qwerty zzz', 'rice', 'tea', 'soap 90ml', '\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646']
    return items, queries


JS_RUNNER = r"""
const M = require(process.argv[2] + '/static/ocr/ocr_match.js');
const data = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const entries = data.items.map(it => M.makeEntry(it[0], it[1], it[2], it[3])).filter(Boolean);
const idx = new M.Index(entries);
const out = data.queries.map(q => { const r = M.rank(q, idx);
    return { text: r.text, ranked: r.ranked.map(x => [x[0], x[1].id]) }; });
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class JsParity(unittest.TestCase):
    def test_same_ranking_as_python(self):
        items, queries = make_data()
        catalog = []
        for pid, name, barcode, aliases in items:
            e = core.make_entry(pid, name, barcode, aliases)
            if e:
                catalog.append(e)
        index = core.Index(catalog)
        want = []
        for q in queries:
            text, ranked = core.rank(q, index)
            want.append({'text': text, 'ranked': [[s, e['id']] for s, e in ranked]})

        with tempfile.TemporaryDirectory() as tmp:
            data_path = os.path.join(tmp, 'data.json')
            js_path = os.path.join(tmp, 'run.js')
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump({'items': items, 'queries': queries}, f)
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write(JS_RUNNER)
            res = subprocess.run(['node', js_path, ROOT, data_path], capture_output=True, text=True, timeout=300)
            self.assertEqual(res.returncode, 0, res.stderr)
            got = json.loads(res.stdout)

        self.assertEqual(len(got), len(want))
        bad = [(q, w, g) for q, w, g in zip(queries, want, got) if w != g]
        self.assertFalse(bad, 'JS and Python differ on %d of %d queries, first: %r' % (len(bad), len(queries), bad[:1]))
        self.assertTrue(any(w['ranked'] for w in want), 'the test data never matched anything')

    def test_same_sizes_as_python(self):
        probes = ['Pepsi 180ml', 'PEPSI 180 ML', '1.5 ltr', '1,5L', '1L', '1000ml', '500gm tea', '1kg', '1000 g',
                  'x250ml 3kg', '12 large', 'Rs 250', 'batch 180', '0.35 l', '2.5kg', '750 gms', '1 litre', '']
        with tempfile.TemporaryDirectory() as tmp:
            js_path = os.path.join(tmp, 'q.js')
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write("const M = require(process.argv[2] + '/static/ocr/ocr_match.js');"
                        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[3]).map(t => M.quantities(t))));")
            res = subprocess.run(['node', js_path, ROOT, json.dumps(probes)], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), [core.quantities(t) for t in probes])

    def test_same_ranking_with_word_confidence(self):
        items, queries = make_data(seed=11, n=600)
        wconfs = [{t: 30 + (sum(map(ord, t)) * 7) % 71 for t in core.tokens(q)} for q in queries]
        catalog = [e for e in (core.make_entry(*it) for it in items) if e]
        index = core.Index(catalog)
        want = []
        for q, w in zip(queries, wconfs):
            text, ranked = core.rank(q, index, w)
            want.append({'text': text, 'ranked': [[s, e['id']] for s, e in ranked]})
        runner = JS_RUNNER.replace('M.rank(q, idx)', 'M.rank(q, idx, data.wconfs[data.queries.indexOf(q)])')
        with tempfile.TemporaryDirectory() as tmp:
            data_path, js_path = os.path.join(tmp, 'data.json'), os.path.join(tmp, 'run.js')
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump({'items': items, 'queries': queries, 'wconfs': wconfs}, f)
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write(runner)
            res = subprocess.run(['node', js_path, ROOT, data_path], capture_output=True, text=True, timeout=300)
            self.assertEqual(res.returncode, 0, res.stderr)
            got = json.loads(res.stdout)
        bad = [(q, w, g) for q, w, g in zip(queries, want, got) if w != g]
        self.assertFalse(bad, 'JS and Python differ on %d of %d queries, first: %r' % (len(bad), len(queries), bad[:1]))

    def test_same_look_alike_folding_as_python(self):
        probes = ['m1lk', 'l1pt0n', 'rnilk', 'vvater', '250', 'ab', 'Rice5', 'lux', 'i1i1', '', '5ervice', '\u0644\u06a9\u0633']
        with tempfile.TemporaryDirectory() as tmp:
            js_path = os.path.join(tmp, 'q.js')
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write("const M = require(process.argv[2] + '/static/ocr/ocr_match.js');"
                        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[3]).map(t => M.fold(t))));")
            res = subprocess.run(['node', js_path, ROOT, json.dumps(probes)], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), [core.fold(t) for t in probes])

    def test_same_rarity_weights_as_python(self):
        pairs = [[1, 1], [4, 1], [900, 1], [900, 900], [900, 37], [60000, 3], [10, 0], [7, 2]]
        with tempfile.TemporaryDirectory() as tmp:
            js_path = os.path.join(tmp, 'q.js')
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write("const M = require(process.argv[2] + '/static/ocr/ocr_match.js');"
                        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[3]).map(p => M.idfWeight(p[0], p[1]))));")
            res = subprocess.run(['node', js_path, ROOT, json.dumps(pairs)], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), [core.idf_weight(a, b) for a, b in pairs])


    def test_upc_a_and_ean13_match_the_same_in_js_and_python(self):
        items = [[1, 'Cola 330ml', '0036000291452', []], [2, 'Juice 1L', '036000291999', []], [3, 'Tea', '', []]]
        queries = ['036000291452', '0036000291452', '0036000291999', '036000291999', '036000291453', '0000000000']
        catalog = [core.make_entry(*it) for it in items]
        want = []
        for q in queries:
            text, ranked = core.rank(q, core.Index(catalog))
            want.append({'text': text, 'ranked': [[sc, e['id']] for sc, e in ranked]})
        with tempfile.TemporaryDirectory() as tmp:
            data_path, js_path = os.path.join(tmp, 'data.json'), os.path.join(tmp, 'run.js')
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump({'items': items, 'queries': queries}, f)
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write(JS_RUNNER)
            res = subprocess.run(['node', js_path, ROOT, data_path], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout), want)
        self.assertEqual([w['ranked'][:1] for w in want[:4]], [[[100, 1]], [[100, 1]], [[100, 2]], [[100, 2]]])


if __name__ == '__main__':
    unittest.main()
