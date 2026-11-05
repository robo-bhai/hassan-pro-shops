/* ocr_multi.js - splits ONE camera reading into one text per product (so several products can be added at once).
 *
 * Tesseract gives every word with its box. Words that sit next to each other (same line) or right under each
 * other (stacked lines) belong to one product label; a clear gap starts a new product.
 * Pure functions, no DOM, no Django -> tested with node (tests/test_ocr_multi_js.py).
 *
 *   OcrMulti.segment(words, opts) -> [ {text, conf, n, box:{x0,y0,x1,y1}}, ... ]   left-to-right, top-to-bottom
 *     words : [{text, confidence, bbox:{x0,y0,x1,y1}}]   (Tesseract.js data.words)
 *
 * Tuning (OcrMulti.CFG): raise GAP_X / GAP_Y if ONE label gets cut into pieces, lower them if two products are
 * glued together.  Numbers are multiples of the typical word height.
 */
(function (root) {
    'use strict';
    var CFG = {
        MIN_WORD_CONF: 45,      // words below this confidence are noise
        GAP_X: 1.8,             // max horizontal gap inside one label (x word height)
        GAP_Y: 1.4,             // max vertical gap between two lines of one label (x word height)
        LINE_OVERLAP: 0.4,      // two words are on the same line if they overlap this much vertically
        COL_OVERLAP: 0.2,       // stacked lines belong together if they overlap this much horizontally
        MIN_LETTERS: 4,         // a segment with fewer letters is dropped
        MAX_SEGMENTS: 6,
        MAX_WORDS: 18           // per segment (the matcher never needs more)
    };

    var LETTER = /[a-z\u0600-\u06ff]/gi;

    function clean(w) {
        var t = String(w.text || '').replace(/[^a-z0-9.\-\u0600-\u06ff]/gi, '');
        if (!t) return '';
        var letters = (t.match(LETTER) || []).length;
        if (/^\d{8,14}$/.test(t)) return t;                                     // barcode digits
        if (/^\d+(\.\d+)?(ml|g|gm|kg|l|ltr)$/i.test(t)) return t;               // 500ml, 1kg
        return letters >= 2 ? t : '';
    }

    function median(a) {
        var s = a.slice().sort(function (x, y) { return x - y; });
        return s.length ? s[Math.floor(s.length / 2)] : 0;
    }

    function segment(words, opts) {
        var c = {}, k;
        for (k in CFG) c[k] = CFG[k];
        if (opts) for (k in opts) c[k] = opts[k];

        var ws = [];
        (words || []).forEach(function (w) {
            if (!w || !w.bbox || (w.confidence || 0) < c.MIN_WORD_CONF) return;
            var t = clean(w);
            if (!t) return;
            var b = w.bbox, h = b.y1 - b.y0, wd = b.x1 - b.x0;
            if (!(h > 0) || !(wd > 0)) return;
            ws.push({ t: t, x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, h: h, conf: w.confidence || 0 });
        });
        if (!ws.length) return [];

        var H = median(ws.map(function (w) { return w.h; })) || 10;

        // union-find
        var par = ws.map(function (_w, i) { return i; });
        function find(i) { while (par[i] !== i) { par[i] = par[par[i]]; i = par[i]; } return i; }
        function join(a, b) { a = find(a); b = find(b); if (a !== b) par[b] = a; }

        for (var i = 0; i < ws.length; i++) {
            for (var j = i + 1; j < ws.length; j++) {
                var a = ws[i], b = ws[j];
                var vOv = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);            // >0 = overlap
                var hOv = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
                var gapX = Math.max(a.x0, b.x0) - Math.min(a.x1, b.x1);           // >0 = space between
                var gapY = Math.max(a.y0, b.y0) - Math.min(a.y1, b.y1);
                var minH = Math.min(a.h, b.h), minW = Math.min(a.x1 - a.x0, b.x1 - b.x0);
                var sameLine = vOv >= c.LINE_OVERLAP * minH && gapX <= c.GAP_X * H;
                var stacked = gapY <= c.GAP_Y * H && hOv >= c.COL_OVERLAP * minW && gapY > -minH;
                if (sameLine || stacked) join(i, j);
            }
        }

        var groups = {};
        ws.forEach(function (w, i) { var r = find(i); (groups[r] = groups[r] || []).push(w); });

        var out = [];
        Object.keys(groups).forEach(function (r) {
            var g = groups[r];
            // reading order inside the label: line by line (words whose tops are within half a word height = same line)
            g.sort(function (p, q) {
                return Math.abs(p.y0 - q.y0) > H * 0.5 ? p.y0 - q.y0 : p.x0 - q.x0;
            });
            var txt = g.slice(0, c.MAX_WORDS).map(function (w) { return w.t; }).join(' ');
            var letters = (txt.match(LETTER) || []).length;
            if (letters < c.MIN_LETTERS) return;
            var box = g.reduce(function (m, w) {
                return { x0: Math.min(m.x0, w.x0), y0: Math.min(m.y0, w.y0), x1: Math.max(m.x1, w.x1), y1: Math.max(m.y1, w.y1) };
            }, { x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9 });
            var conf = g.reduce(function (s, w) { return s + w.conf; }, 0) / g.length;
            out.push({ text: txt, conf: Math.round(conf), n: g.length, box: box });
        });

        // biggest / most readable labels first when there are too many, then back to reading order
        out.sort(function (p, q) { return (q.n * q.conf) - (p.n * p.conf); });
        out = out.slice(0, c.MAX_SEGMENTS);
        out.sort(function (p, q) {
            return Math.abs(p.box.y0 - q.box.y0) > H ? p.box.y0 - q.box.y0 : p.box.x0 - q.box.x0;
        });
        return out;
    }

    var api = { segment: segment, CFG: CFG };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    root.OcrMulti = api;
})(typeof window !== 'undefined' ? window : this);
