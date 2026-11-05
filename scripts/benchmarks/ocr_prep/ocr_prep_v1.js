/* OCR picture preparation (feature: heavy work off the main thread).
 *
 * The same file is used in two ways:
 *   1. as a Web Worker  -> new Worker('.../ocr_prep.js'); post {bmp, w, h}; get back {st, thr, sharp}
 *   2. as a normal <script> -> OcrPrep.process() is the fallback for old browsers without OffscreenCanvas
 *
 * process(): grey -> stretch contrast 2%..98% -> flip dark-background labels -> sharpness (variance of the
 * Laplacian) -> Otsu threshold. Identical maths to the old inline version in create.html.
 */
(function (root) {
    'use strict';

    // rgba: Uint8ClampedArray (w*h*4). -> { st: Uint8ClampedArray(w*h), thr, sharp }
    function process(rgba, w, h) {
        var n = w * h, gray = new Uint8ClampedArray(n), hist = new Uint32Array(256), sum = 0, i, j;
        for (i = 0, j = 0; j < n; i += 4, j++) {
            var g = (rgba[i] * 0.299 + rgba[i + 1] * 0.587 + rgba[i + 2] * 0.114) | 0;
            gray[j] = g; hist[g]++; sum += g;
        }
        var acc = 0, lo = 0, hi = 255;
        for (i = 0; i < 256; i++) { acc += hist[i]; if (acc >= n * 0.02) { lo = i; break; } }
        acc = 0;
        for (i = 255; i >= 0; i--) { acc += hist[i]; if (acc >= n * 0.02) { hi = i; break; } }
        var range = Math.max(hi - lo, 40), invert = (sum / n) < 105;
        var st = new Uint8ClampedArray(n), h2 = new Uint32Array(256);
        for (j = 0; j < n; j++) {
            var v = (gray[j] - lo) * 255 / range;
            v = v < 0 ? 0 : (v > 255 ? 255 : v);
            if (invert) v = 255 - v;
            st[j] = v; h2[st[j]]++;
        }
        var ls = 0, lq = 0, cnt = 0, x, y;
        for (y = 1; y < h - 1; y += 2) {
            for (x = 1; x < w - 1; x += 2) {
                i = y * w + x;
                var l = 4 * st[i] - st[i - 1] - st[i + 1] - st[i - w] - st[i + w];
                ls += l; lq += l * l; cnt++;
            }
        }
        var sharp = cnt ? (lq / cnt - Math.pow(ls / cnt, 2)) : 0;
        var sumAll = 0, t;
        for (t = 0; t < 256; t++) sumAll += t * h2[t];
        var wB = 0, sumB = 0, maxB = 0, thr = 128;
        for (t = 0; t < 256; t++) {
            wB += h2[t]; if (!wB) continue;
            var wF = n - wB; if (!wF) break;
            sumB += t * h2[t];
            var mB = sumB / wB, mF = (sumAll - sumB) / wF;
            var between = wB * wF * (mB - mF) * (mB - mF);
            if (between > maxB) { maxB = between; thr = t; }
        }
        return { st: st, thr: thr, sharp: sharp };
    }

    var API = { process: process };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; return; }
    root.OcrPrep = API;

    // ---- worker mode ----
    if (typeof WorkerGlobalScope !== 'undefined' && root instanceof WorkerGlobalScope) {
        var cv = null, cx = null;
        root.onmessage = function (ev) {
            var m = ev.data, id = m.id;
            try {
                if (!cv || cv.width !== m.w || cv.height !== m.h) {
                    cv = new OffscreenCanvas(m.w, m.h);
                    cx = cv.getContext('2d', { willReadFrequently: true });
                }
                cx.drawImage(m.bmp, 0, 0, m.w, m.h);
                if (m.bmp.close) m.bmp.close();
                var px = cx.getImageData(0, 0, m.w, m.h).data;
                var r = process(px, m.w, m.h);
                root.postMessage({ id: id, st: r.st.buffer, thr: r.thr, sharp: r.sharp }, [r.st.buffer]);
            } catch (e) {
                root.postMessage({ id: id, error: String(e && e.message || e) });
            }
        };
    }
})(typeof self !== 'undefined' ? self : this);
