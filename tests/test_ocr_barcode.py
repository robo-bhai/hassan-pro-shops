"""Barcode reading: check digits, what is accepted, when a code is reported (static/ocr/ocr_barcode.js) and the
UPC-A == EAN-13 matching rule in ocr_core.py.

Run from the project root:  python -I tests/test_ocr_barcode.py      (the JS parts need `node`; skipped without it)
"""
import importlib.util
import json
import os
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


def run_js(code, arg=None):
    """Run `code` with B = the barcode module and A = the parsed argument; print JSON(result)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 't.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write("const B = require(process.argv[2] + '/static/ocr/ocr_barcode.js');"
                    "const A = JSON.parse(process.argv[3] || 'null');"
                    "Promise.resolve((function(){" + code + "})()).then(r => process.stdout.write(JSON.stringify(r)));")
        res = subprocess.run(['node', path, ROOT, json.dumps(arg)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


# real, well-known codes (check digit correct)
EAN13 = '4006381333931'
UPCA = '036000291452'
EAN8 = '73513537'


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class BarcodeJsTests(unittest.TestCase):
    def test_check_digit(self):
        got = run_js("return A.map(c => B.gtinValid(c));", [EAN13, UPCA, EAN8, '4006381333932', '036000291453', '12345', 'abc', ''])
        self.assertEqual(got, [True, True, True, False, False, False, False, False])

    def test_accept_rules(self):
        cases = [['ean_13', EAN13], ['upc_a', UPCA], ['ean_8', EAN8],
                 ['ean_13', '4006381333932'],          # wrong check digit (half-read bars)
                 ['ean_13', UPCA],                     # wrong length for the format
                 ['code_128', '8961234567890'],        # digits, no check digit needed
                 ['code_128', 'AB12345678'],           # letters: not a product barcode here
                 ['code_128', '123456'],               # shorter than 8: the matcher would not treat it as a barcode
                 ['code_39', ' 12345678 '],
                 ['qr_code', '12345678']]
        want = [EAN13, UPCA, EAN8, '', '', '8961234567890', '', '', '12345678', '12345678']
        got = run_js("return A.map(c => B.accept(c[0], c[1]));", cases)
        # qr_code is never requested from the detector; accept() itself only checks digits, so it passes like code_39
        self.assertEqual(got, want)

    def test_tracker_reports_once_per_appearance(self):
        got = run_js("""
            const t = new B.Tracker(800), out = [];
            const feed = (c, ms) => { const r = t.feed(c, ms); if (r) t.ack(true); out.push(r ? r.again : null); };
            feed('A', 0); feed('A', 150); feed('A', 300);      // held in front of the camera: one report
            feed('A', 2000);                                    // gone for >800 ms and back: reported again, again=true
            feed('B', 2100);                                    // another code: reported, again=false
            return out;""")
        self.assertEqual(got, [False, None, None, True, False])

    def test_tracker_offers_the_code_again_until_it_is_used(self):
        got = run_js("""
            const t = new B.Tracker(800), out = [];
            let r = t.feed('A', 0); out.push(!!r); t.ack(false);          // page was busy -> not used
            r = t.feed('A', 150); out.push(!!r); t.ack(false);            // offered again
            r = t.feed('A', 300); out.push(!!r); t.ack(true);             // used now
            r = t.feed('A', 450); out.push(!!r);                          // nothing more
            return out;""")
        self.assertEqual(got, [True, True, True, False])

    def test_scanner_with_a_fake_detector(self):
        got = run_js("""
            return new Promise(resolve => {
                const seen = [];
                let n = 0;
                const frames = [[{format:'ean_13', rawValue:'4006381333932'}],      // bad check digit: ignored
                                [{format:'ean_13', rawValue:'4006381333931'}],
                                [{format:'ean_13', rawValue:'4006381333931'}],
                                []];
                const detector = { detect: async () => frames[Math.min(n++, frames.length - 1)] };
                const sc = B.create({ video: { readyState: 4 }, detector, interval: 5,
                                      onCode: (code, info) => { seen.push([code, info.again]); return true; } });
                sc.start().then(ok => setTimeout(() => { sc.stop(); resolve({ ok, seen }); }, 150));
            });""")
        self.assertTrue(got['ok'])
        self.assertEqual(got['seen'], [['4006381333931', False]])

    def test_unsupported_browser_answers_false(self):
        got = run_js("return B.create({ video: {readyState: 4}, onCode: () => true }).start();")
        self.assertIs(got, False)               # a real False, not an unresolved promise


class UpcEanMatchingTests(unittest.TestCase):
    def test_barcode_key_ignores_leading_zeros(self):
        self.assertEqual(core.barcode_key('0036000291452'), core.barcode_key('036000291452'))
        self.assertEqual(core.barcode_key(''), '')
        self.assertEqual(core.barcode_key('0000'), '')

    def test_upc_a_scan_finds_a_product_stored_as_ean13_and_back(self):
        a = core.make_entry(1, 'Cola 330ml', '0036000291452')        # stored as EAN-13
        b = core.make_entry(2, 'Juice 1L', '036000291999')           # stored as UPC-A
        for scan, want in (('036000291452', 1), ('0036000291452', 1), ('0036000291999', 2), ('036000291999', 2)):
            _t, ranked = core.rank(scan, [a, b])
            self.assertEqual([(s, e['id']) for s, e in ranked][:1], [(100, want)], scan)
            _t, again = core.rescore(scan, [a, b])
            self.assertEqual([(s, e['id']) for s, e in again][:1], [(100, want)], scan)

    def test_other_numbers_do_not_match(self):
        a = core.make_entry(1, 'Cola 330ml', '036000291452')
        _t, ranked = core.rank('036000291453', [a])
        self.assertEqual(ranked, [])

    def test_all_zero_barcode_never_matches(self):
        a = core.make_entry(1, 'Odd Thing', '00000000')
        _t, ranked = core.rank('0000000000', [a])
        self.assertEqual(ranked, [])


class BarcodeWiringTests(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return f.read()

    def test_both_pages_load_and_use_the_barcode_reader(self):
        for rel in ('templates/sales/pos.html',):
            page = self.read(rel)
            for needle in ("static 'ocr/ocr_barcode.js'", 'id="ocrBarcode"', 'OcrBarcode.create(', 'function ocrOnBarcode(',
                           'ocrBarcodeStart();', 'ocrBarcodeStop();', "localStorage.setItem('ocrBarcode'"):
                self.assertIn(needle, page, rel + ': ' + needle)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'static/ocr/ocr_barcode.js')))


if __name__ == '__main__':
    unittest.main()
