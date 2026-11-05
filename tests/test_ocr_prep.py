"""Picture preparation (static/ocr/ocr_prep.js): light flattening, deskew, adaptive black/white, quality flags.

Run from the project root:  python -I tests/test_ocr_prep.py      (needs `node`; skipped without it)
Pure maths on synthetic "text" (rows of dark word blocks) - no browser, no Django, no Tesseract.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which('node')

HELPERS = r"""
const P = require(process.argv[2] + '/static/ocr/ocr_prep.js');
// text-like page: `lines` rows of word blocks (dark on light), w x h
function page(w, h, lines, opt) {
  opt = opt || {}; const bg = opt.bg === undefined ? 235 : opt.bg, fg = opt.fg === undefined ? 30 : opt.fg;
  const g = new Uint8ClampedArray(w * h).fill(bg);
  const lh = Math.floor(h / (lines * 2 + 1));
  for (let l = 0; l < lines; l++) {
    const y0 = lh * (2 * l + 1); let x = Math.floor(w * 0.08);
    while (x < w * 0.9) {
      const ww = 14 + ((x * 7 + l * 13) % 40);
      for (let y = y0; y < y0 + lh; y++) for (let xx = x; xx < Math.min(w, x + ww); xx++) {
        // letter-like: vertical strokes with gaps
        if (((xx - x) % 6) < 3) g[y * w + xx] = fg;
      }
      x += ww + 14;
    }
  }
  return g;
}
function toRGBA(g) { const o = new Uint8ClampedArray(g.length * 4); for (let i = 0; i < g.length; i++) { o[4*i] = o[4*i+1] = o[4*i+2] = g[i]; o[4*i+3] = 255; } return o; }
function mean(a, f) { let s = 0, n = 0; for (let i = 0; i < a.length; i++) if (!f || f(i)) { s += a[i]; n++; } return n ? s / n : 0; }
const out = {};
"""


def run_node(body):
    d = tempfile.mkdtemp()
    try:
        path = os.path.join(d, 't.js')
        with open(path, 'w') as f:
            f.write(HELPERS + body + "\nconsole.log(JSON.stringify(out));")
        r = subprocess.run([NODE, path, ROOT], capture_output=True, text=True, timeout=120)
        if r.returncode:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(d, ignore_errors=True)


@unittest.skipUnless(NODE, 'node not installed')
class PrepTests(unittest.TestCase):
    def test_output_shapes_and_compat_fields(self):
        o = run_node("""
          const w = 400, h = 160, r = P.process(toRGBA(page(w, h, 3)), w, h);
          out.st = r.st.length; out.bin = r.bin.length; out.thr = typeof r.thr; out.sharp = r.sharp > 0;
          out.bin01 = Array.from(new Set(r.bin)).sort(); out.flags = Array.isArray(r.q.flags);
        """)
        self.assertEqual((o['st'], o['bin']), (400 * 160, 400 * 160))
        self.assertEqual(o['thr'], 'number')
        self.assertTrue(o['sharp'])
        self.assertEqual(o['bin01'], [0, 255])
        self.assertTrue(o['flags'])

    def test_enhance_off_is_the_v1_behaviour(self):
        o = run_node("""
          const w = 300, h = 120, r = P.process(toRGBA(page(w, h, 2)), w, h, { enhance: false });
          out.bin = r.bin; out.skew = r.skew; out.thr = typeof r.thr === 'number' && r.thr >= 0 && r.thr <= 255;
        """)
        self.assertIsNone(o['bin'])
        self.assertEqual(o['skew'], 0)
        self.assertTrue(o['thr'])

    def test_dark_label_is_flipped_to_dark_text_on_light(self):
        o = run_node("""
          const w = 400, h = 160, g = page(w, h, 3, { bg: 25, fg: 225 }), r = P.process(toRGBA(g), w, h);
          out.inverted = r.q.inverted; out.paper = mean(r.st, i => g[i] === 25); out.ink = mean(r.st, i => g[i] === 225);
        """)
        self.assertTrue(o['inverted'])
        self.assertGreater(o['paper'], 200)
        self.assertLess(o['ink'], 80)

    def test_flatten_removes_a_lighting_gradient(self):
        # same page, left side in shadow (x0.35) -> after flattening the paper level must be the same left and right
        o = run_node("""
          const w = 600, h = 200, g = page(w, h, 3), s = new Uint8ClampedArray(g);
          for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) s[y * w + x] = g[y * w + x] * (0.35 + 0.65 * x / (w - 1));
          const flat = P.flatten(Uint8ClampedArray.from(s), w, h, P.CFG);
          const paper = (a, x0, x1) => { let t = 0, n = 0; for (let y = 0; y < h; y++) for (let x = x0; x < x1; x++) if (g[y*w+x] === 235) { t += a[y*w+x]; n++; } return t / n; };
          out.rawL = paper(s, 0, 100); out.rawR = paper(s, 500, 600); out.flatL = paper(flat, 0, 100); out.flatR = paper(flat, 500, 600);
        """)
        self.assertGreater(o['rawR'] - o['rawL'], 80)                 # the shadow is really there
        self.assertLess(abs(o['flatR'] - o['flatL']), 12)             # ... and gone after flattening

    def test_adaptive_binary_keeps_text_under_a_shadow(self):
        o = run_node("""
          const w = 600, h = 200, g = page(w, h, 3), s = new Uint8ClampedArray(g);
          for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) s[y * w + x] = g[y * w + x] * (0.3 + 0.7 * x / (w - 1));
          const r = P.process(toRGBA(s), w, h);
          let inkOk = 0, ink = 0, paperOk = 0, paper = 0;
          for (let i = 0; i < g.length; i++) { if (g[i] === 30) { ink++; if (r.bin[i] === 0) inkOk++; } else { paper++; if (r.bin[i] === 255) paperOk++; } }
          out.ink = inkOk / ink; out.paper = paperOk / paper;
        """)
        self.assertGreater(o['ink'], 0.9)
        self.assertGreater(o['paper'], 0.95)

    def test_deskew_finds_the_angle_with_the_right_sign(self):
        o = run_node("""
          const w = 500, h = 240, base = page(w, h, 4), res = {};
          for (const a of [-10, -5, 6, 12]) {
            // P.rotate(+d) makes lines running down-right by d horizontal, so rotating by -d tilts them down-right
            const t = P.rotate(base, w, h, -a, 235);
            const r = P.process(toRGBA(t), w, h);
            res[a] = r.skew;
          }
          out.res = res;
        """)
        for a, got in o['res'].items():
            self.assertAlmostEqual(got, float(a), delta=1.5, msg='tilt %s -> %s' % (a, got))

    def test_straight_and_slightly_off_pictures_are_not_rotated(self):
        o = run_node("""
          const w = 500, h = 240, base = page(w, h, 4);
          out.straight = P.process(toRGBA(base), w, h).skew;
          out.tiny = P.process(toRGBA(P.rotate(base, w, h, -0.4, 235)), w, h).skew;
          const noise = new Uint8ClampedArray(w * h); let s = 12345;
          for (let i = 0; i < noise.length; i++) { s = (s * 1103515245 + 12345) & 0x7fffffff; noise[i] = 100 + (s % 60); }
          out.noise = P.process(toRGBA(noise), w, h).skew;
        """)
        self.assertEqual(o['straight'], 0)
        self.assertEqual(o['tiny'], 0)
        self.assertEqual(o['noise'], 0)

    def test_deskew_keeps_the_picture_size(self):
        o = run_node("""
          const w = 500, h = 240, t = P.rotate(page(w, h, 4), w, h, -9, 235), r = P.process(toRGBA(t), w, h);
          out.n = [r.st.length, r.bin.length];
        """)
        self.assertEqual(o['n'], [500 * 240, 500 * 240])

    def test_quality_flags(self):
        o = run_node("""
          const w = 400, h = 160, f = (g, opt) => P.process(toRGBA(g), w, h, opt).q.flags;
          out.dark = f(page(w, h, 3, { bg: 30, fg: 5 }));          // everything very dark, label not light-on-dark
          out.faded = f(page(w, h, 3, { bg: 150, fg: 120 }));
          const g = page(w, h, 3); for (let y = 20; y < 90; y++) for (let x = 100; x < 260; x++) g[y * w + x] = 255;   // blown-out spot ~ 7%
          out.glare = f(g);
          out.white = f(new Uint8ClampedArray(w * h).fill(255));    // plain white is not glare
          out.good = f(page(w, h, 3));
        """)
        self.assertIn('low_contrast', o['faded'])
        self.assertIn('glare', o['glare'])
        self.assertNotIn('glare', o['white'])
        self.assertNotIn('glare', o['good'])
        self.assertNotIn('low_contrast', o['good'])

    def test_text_box_wraps_the_text_and_ignores_specks(self):
        o = run_node("""
          const w = 800, h = 300, g = new Uint8ClampedArray(w * h).fill(235);
          // two text lines inside x 200..600, y 100..200
          for (const [y0, y1] of [[100, 140], [160, 200]]) for (let y = y0; y < y1; y++) for (let x = 200; x < 600; x++) if (((x - 200) % 12) < 5) g[y * w + x] = 20;
          // isolated specks far away
          for (const [x, y] of [[10, 10], [790, 290], [700, 20], [30, 280]]) g[y * w + x] = 20;
          const r = P.process(toRGBA(g), w, h), b = r.box;
          out.box = b; out.same = r.q.box === b;
          out.blank = P.process(toRGBA(new Uint8ClampedArray(w * h).fill(200)), w, h).box;
        """)
        b = o['box']
        self.assertTrue(o['same'])
        self.assertLessEqual(b['x0'], 200); self.assertGreaterEqual(b['x1'], 600)
        self.assertLessEqual(b['y0'], 100); self.assertGreaterEqual(b['y1'], 200)
        self.assertGreater(b['x0'], 100); self.assertLess(b['x1'], 700)        # specks did not stretch the box
        self.assertGreater(b['y0'], 40); self.assertLess(b['y1'], 260)
        self.assertEqual(b['lines'], 2)
        self.assertIsNone(o['blank'])                                           # nothing to read -> the page skips Tesseract

    def test_even_light_skips_flattening(self):
        o = run_node("""
          const w = 600, h = 200, g = page(w, h, 3);
          out.even = P.flatten(Uint8ClampedArray.from(g), w, h, P.CFG) === null;
        """)
        self.assertTrue(o['even'])

    def test_tiny_and_flat_pictures_do_not_crash(self):
        o = run_node("""
          const sizes = [[1, 1], [8, 8], [16, 40], [40, 16], [64, 24]], res = [];
          for (const [w, h] of sizes) { const r = P.process(new Uint8ClampedArray(w * h * 4).fill(128), w, h); res.push([r.st.length, r.bin ? r.bin.length : 0]); }
          out.res = res; out.sizes = sizes.map(s => s[0] * s[1]);
        """)
        self.assertEqual([r[0] for r in o['res']], o['sizes'])

    def test_sharpness_is_measured_before_enhancement(self):
        # OCR_MIN_SHARP (40) in the pages was tuned on the v1 number: it must not change with the new steps
        o = run_node("""
          const w = 400, h = 160, px = toRGBA(page(w, h, 3));
          out.v1 = P.process(px, w, h, { enhance: false }).sharp; out.v2 = P.process(px, w, h).sharp;
        """)
        self.assertEqual(o['v1'], o['v2'])

    def test_speed_budget(self):
        # a live frame (800 x 300) must be prepared well inside one camera tick even on a slow phone (~10x slower than CI)
        o = run_node("""
          const w = 800, h = 300, px = toRGBA(page(w, h, 4)); P.process(px, w, h);
          const t = process.hrtime.bigint(); for (let i = 0; i < 5; i++) P.process(px, w, h);
          out.ms = Number(process.hrtime.bigint() - t) / 1e6 / 5;
        """)
        self.assertLess(o['ms'], 80)


class PageWiringTests(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return f.read()

    def test_pages_use_the_shared_pipeline(self):
        for rel in ('templates/sales/pos.html',):
            page = self.read(rel)
            self.assertIn('OcrPrep.process(', page, rel)                 # main-thread fallback = same code as the worker
            self.assertIn('L.bin', page, rel)                            # adaptive black/white is what the "bin" pass reads
            self.assertIn('ocrQualityHint(', page, rel)
            self.assertNotIn('// Otsu threshold', page, rel)             # the old duplicated inline maths is gone
            self.assertIn("OCR_PASSES = [ { v: 'bin', psm: 6 }, { v: 'gray', psm: 6 }, { v: 'inv', psm: 6 } ]", page, rel)   # best pass first
            self.assertIn('v.q.box === null', page, rel)                 # empty live frame -> no Tesseract call
            self.assertIn('ocrPutGray(ocrCanvasBin, bin, L.w, L.h, false, box)', page, rel)   # only the text region is read
            self.assertIn('ocrTextHeightRatio(d, ocrLast.h)', page, rel)  # zoom assist still measured against the whole frame


if __name__ == '__main__':
    unittest.main()
