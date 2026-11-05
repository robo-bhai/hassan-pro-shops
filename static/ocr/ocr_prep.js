/* OCR picture preparation v2 (heavy work off the main thread).
 *
 * The same file is used in two ways:
 *   1. as a Web Worker  -> new Worker('.../ocr_prep.js'); post {bmp, w, h, opts}; get back {st, bin, thr, sharp, skew, q}
 *   2. as a normal <script> / node module -> OcrPrep.process() is the fallback for old browsers without OffscreenCanvas
 *
 * Pipeline (every step can be switched off through opts, see CFG):
 *   1. grey                      BT.601 luma
 *   2. contrast stretch 2%..98%  + flip dark-background labels so the text is always dark on light
 *      -> sharpness (variance of the Laplacian) is measured HERE, exactly like v1, so OCR_MIN_SHARP keeps its meaning
 *   3. background flattening     removes shadows / uneven light / gradients (closing-style background estimate, divide)
 *   4. noise estimate            robust (median) Immerkaer estimate; light 3x3 smoothing only when the picture is noisy
 *   5. unsharp mask              only when the picture is a little soft (not blurry enough to be rejected, not sharp)
 *   6. deskew                    projection-profile angle search (+-15 deg), bilinear rotation, only when clearly gained
 *   7. binarisation              Sauvola adaptive threshold (integral images) -> `bin`; global Otsu value kept in `thr`
 *   8. quality report            brightness / contrast / glare / noise / skew + human-readable flags
 *
 * process(rgba, w, h, opts) -> { st, bin, thr, sharp, skew, q }
 *   st   Uint8ClampedArray(w*h)  enhanced grey, dark text on light background   (OCR pass "gray", "inv" = 255 - st)
 *   bin  Uint8ClampedArray(w*h)  0 / 255 adaptive black-and-white                (OCR pass "bin")
 *   thr  Otsu threshold of `st` (old field, still returned)
 *   q    { sharp, brightness, contrast, glare, noise, skew, inverted, flags: [...], ms }
 *
 * opts.enhance === false gives the v1 behaviour exactly (st = stretched grey, thr = Otsu, no bin) - used by tests / A-B.
 * Pure functions, no DOM -> tested with node (tests/test_ocr_prep.py).
 */
(function (root) {
    'use strict';

    var CFG = {
        CLIP: 0.02,              // contrast stretch clips this share of the darkest / brightest pixels
        MIN_RANGE: 40,           // never stretch a range smaller than this (flat pictures stay flat)
        INVERT_MEAN: 105,        // mean brightness below this = light text on dark label -> invert
        FLATTEN: true,
        FLATTEN_BLOCK_DIV: 60,   // block size for the background grid = min(w,h) / this
        FLATTEN_DILATE: 3,       // grid cells: dark strokes thinner than ~(block * (2*this+1)) vanish from the background
        FLATTEN_BLUR: 3,         // grid cells of box blur on the background
        FLATTEN_MIN_SPREAD: 0.1, // background varies less than 10% of the grey range -> the light is even, skip the step
        FLATTEN_FLOOR: 40,       // background is never taken darker than this (no divide-by-tiny)
        DENOISE: true,
        NOISE_SIGMA: 6.0,        // estimated sigma above this -> 3x3 smoothing
        SHARPEN: false,          // off: the benchmark showed no gain (slightly worse) - kept as an option for very soft cameras
        SHARPEN_BELOW: 700,      // v1 sharpness (variance of Laplacian) below this -> unsharp mask (soft picture)
        SHARPEN_AMOUNT: 0.8,
        DESKEW: true,
        SKEW_MAX: 15,            // degrees searched on each side
        SKEW_MIN: 0.75,          // smaller angles are left alone
        SKEW_GAIN: 1.2,          // the straightened profile must be this much "sharper" than the original
        SKEW_POINTS: 8000,       // dark pixels sampled for the angle search
        BOX: true,
        BOX_ROW_SHARE: 0.06,     // a row holds text when it has this share of the busiest row's ink (and at least 2 px)
        BOX_COL_SHARE: 0.04,
        BOX_MIN_LINE: 6,         // text lines lower than this (px) are specks
        BOX_MARGIN: 0.6,         // margin around the text, x line height (min 6 px)
        BINARIZE: true,
        SAUVOLA_K: 0.2,
        SAUVOLA_DIV: 6,          // window = min(w,h) / this (odd, clamped)
        SAUVOLA_MIN: 15,
        SAUVOLA_MAX: 61,
        GLARE_LEVEL: 250,        // raw grey >= this counts as glare
        GLARE_SHARE: 0.04,       // more than 4% glare = flag ...
        GLARE_MAX_SHARE: 0.45,   // ... unless that much of the picture is white (plain white paper / label)
        DARK_BRIGHTNESS: 45,
        LOW_CONTRAST: 60,
        BLURRY_SHARP: 40         // same number as OCR_MIN_SHARP in the pages (only used for the flag)
    };

    function now() { return (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now(); }
    function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

    // ---------- small building blocks (all exported for tests) ----------

    function otsu(hist, n) {
        var sumAll = 0, t;
        for (t = 0; t < 256; t++) sumAll += t * hist[t];
        var wB = 0, sumB = 0, maxB = 0, thr = 128;
        for (t = 0; t < 256; t++) {
            wB += hist[t]; if (!wB) continue;
            var wF = n - wB; if (!wF) break;
            sumB += t * hist[t];
            var mB = sumB / wB, mF = (sumAll - sumB) / wF;
            var between = wB * wF * (mB - mF) * (mB - mF);
            if (between > maxB) { maxB = between; thr = t; }
        }
        return thr;
    }

    function histogram(a) {
        var h = new Uint32Array(256);
        for (var i = 0; i < a.length; i++) h[a[i]]++;
        return h;
    }

    // variance of the Laplacian over every 2nd pixel (same maths as v1)
    function sharpness(st, w, h) {
        var ls = 0, lq = 0, cnt = 0, x, y, i;
        for (y = 1; y < h - 1; y += 2) {
            for (x = 1; x < w - 1; x += 2) {
                i = y * w + x;
                var l = 4 * st[i] - st[i - 1] - st[i + 1] - st[i - w] - st[i + w];
                ls += l; lq += l * l; cnt++;
            }
        }
        return cnt ? (lq / cnt - Math.pow(ls / cnt, 2)) : 0;
    }

    // Robust noise sigma (Immerkaer): median of |3x3 Laplacian-of-Laplacian| so text edges (a minority) do not count.
    function noiseSigma(g, w, h) {
        if (w < 5 || h < 5) return 0;
        var bins = new Uint32Array(256), cnt = 0, x, y, i;
        for (y = 1; y < h - 1; y += 2) {
            for (x = 1; x < w - 1; x += 2) {
                i = y * w + x;
                var r = g[i - w - 1] - 2 * g[i - w] + g[i - w + 1]
                    - 2 * g[i - 1] + 4 * g[i] - 2 * g[i + 1]
                    + g[i + w - 1] - 2 * g[i + w] + g[i + w + 1];
                r = r < 0 ? -r : r;
                bins[r > 255 ? 255 : r | 0]++; cnt++;
            }
        }
        var half = cnt / 2, acc = 0, med = 0;
        for (i = 0; i < 256; i++) { acc += bins[i]; if (acc >= half) { med = i; break; } }
        return med / 0.6745 / 6;
    }

    // 3x3 binomial blur [1 2 1]/4 in both directions (edge pixels copied)
    function blur3(src, w, h) {
        var tmp = new Float32Array(w * h), out = new Uint8ClampedArray(w * h), x, y, i;
        for (y = 0; y < h; y++) {
            for (x = 0; x < w; x++) {
                i = y * w + x;
                var l = x > 0 ? src[i - 1] : src[i], r = x < w - 1 ? src[i + 1] : src[i];
                tmp[i] = (l + 2 * src[i] + r) / 4;
            }
        }
        for (y = 0; y < h; y++) {
            for (x = 0; x < w; x++) {
                i = y * w + x;
                var u = y > 0 ? tmp[i - w] : tmp[i], d = y < h - 1 ? tmp[i + w] : tmp[i];
                out[i] = (u + 2 * tmp[i] + d) / 4 + 0.5;
            }
        }
        return out;
    }

    // out = src + amount * (src - blur(src))
    function unsharp(src, w, h, amount) {
        var b = blur3(src, w, h), out = new Uint8ClampedArray(w * h);
        for (var i = 0; i < out.length; i++) out[i] = src[i] + amount * (src[i] - b[i]);
        return out;
    }

    function maxFilter1D(src, gw, gh, r, horizontal) {
        var out = new Float32Array(src.length), x, y, k, m, p;
        for (y = 0; y < gh; y++) {
            for (x = 0; x < gw; x++) {
                m = 0;
                for (k = -r; k <= r; k++) {
                    p = horizontal ? (x + k < 0 || x + k >= gw ? -1 : y * gw + x + k)
                                   : (y + k < 0 || y + k >= gh ? -1 : (y + k) * gw + x);
                    if (p >= 0 && src[p] > m) m = src[p];
                }
                out[y * gw + x] = m;
            }
        }
        return out;
    }

    function boxBlur1D(src, gw, gh, r, horizontal) {
        var out = new Float32Array(src.length), x, y, k, s, c, p;
        for (y = 0; y < gh; y++) {
            for (x = 0; x < gw; x++) {
                s = 0; c = 0;
                for (k = -r; k <= r; k++) {
                    p = horizontal ? (x + k < 0 || x + k >= gw ? -1 : y * gw + x + k)
                                   : (y + k < 0 || y + k >= gh ? -1 : (y + k) * gw + x);
                    if (p >= 0) { s += src[p]; c++; }
                }
                out[y * gw + x] = s / c;
            }
        }
        return out;
    }

    // Background (paper / label colour) on a coarse grid: block maximum -> dilate -> blur. Dark text strokes vanish,
    // shadows and gradients stay.  Returns { g, gw, gh, f } where one grid cell = f pixels.
    function background(st, w, h, cfg) {
        var f = Math.max(2, Math.round(Math.min(w, h) / cfg.FLATTEN_BLOCK_DIV));
        var gw = Math.ceil(w / f), gh = Math.ceil(h / f), g = new Float32Array(gw * gh), gx, gy, x, y;
        for (gy = 0; gy < gh; gy++) {
            for (gx = 0; gx < gw; gx++) {
                var m = 0, x1 = Math.min(w, (gx + 1) * f), y1 = Math.min(h, (gy + 1) * f);
                for (y = gy * f; y < y1; y += 2) { var o = y * w; for (x = gx * f; x < x1; x += 2) { var v = st[o + x]; if (v > m) m = v; } }   // every 2nd pixel is enough for a max
                g[gy * gw + gx] = m;
            }
        }
        g = maxFilter1D(maxFilter1D(g, gw, gh, cfg.FLATTEN_DILATE, true), gw, gh, cfg.FLATTEN_DILATE, false);
        g = boxBlur1D(boxBlur1D(g, gw, gh, cfg.FLATTEN_BLUR, true), gw, gh, cfg.FLATTEN_BLUR, false);
        return { g: g, gw: gw, gh: gh, f: f };
    }

    // divide by the background -> even light, paper = 255, text darker.
    // Returns null when the light is already even (background varies less than FLATTEN_MIN_SPREAD): nothing to do.
    function flatten(st, w, h, cfg) {
        var bg = background(st, w, h, cfg), g = bg.g, gw = bg.gw, gh = bg.gh, f = bg.f, x, y, gmin = 1e9, gmax = 0;
        for (var k = 0; k < g.length; k++) { if (g[k] < gmin) gmin = g[k]; if (g[k] > gmax) gmax = g[k]; }
        if (cfg.FLATTEN_MIN_SPREAD > 0 && gmax - gmin < cfg.FLATTEN_MIN_SPREAD * 255) return null;
        var out = new Uint8ClampedArray(w * h);
        var xi = new Int32Array(w), xt = new Float32Array(w);       // column lookups, computed once
        for (x = 0; x < w; x++) { var fx = clamp((x + 0.5) / f - 0.5, 0, gw - 1), x0 = fx | 0; xi[x] = x0; xt[x] = fx - x0; }
        for (y = 0; y < h; y++) {
            var fy = clamp((y + 0.5) / f - 0.5, 0, gh - 1), y0 = fy | 0, y1 = Math.min(gh - 1, y0 + 1), ty = fy - y0;
            var ra = y0 * gw, rb = y1 * gw, o = y * w;
            for (x = 0; x < w; x++) {
                var i0 = xi[x], i1 = i0 + 1 < gw ? i0 + 1 : i0, tx = xt[x];
                var b = (g[ra + i0] * (1 - tx) + g[ra + i1] * tx) * (1 - ty) + (g[rb + i0] * (1 - tx) + g[rb + i1] * tx) * ty;
                if (b < cfg.FLATTEN_FLOOR) b = cfg.FLATTEN_FLOOR;
                out[o + x] = st[o + x] * 255 / b;
            }
        }
        return out;
    }

    // percentile stretch of an 8-bit buffer, in place. returns {lo, hi}
    function stretchInPlace(a, clip, minRange) {
        var n = a.length, hist = histogram(a), acc = 0, lo = 0, hi = 255, i;
        for (i = 0; i < 256; i++) { acc += hist[i]; if (acc >= n * clip) { lo = i; break; } }
        acc = 0;
        for (i = 255; i >= 0; i--) { acc += hist[i]; if (acc >= n * clip) { hi = i; break; } }
        var range = Math.max(hi - lo, minRange);
        for (i = 0; i < n; i++) a[i] = (a[i] - lo) * 255 / range;
        return { lo: lo, hi: hi };
    }

    // Skew angle of the text lines in degrees (>0 = the lines run down to the right) and how much sharper the row
    // profile gets when straightened (gain 1 = nothing found).
    function estimateSkew(st, w, h, thr, cfg) {
        var step = Math.max(1, Math.round(Math.max(w, h) / 500)), xs = [], ys = [], x, y, a;
        for (y = 0; y < h; y += step) for (x = 0; x < w; x += step) if (st[y * w + x] < thr) { xs.push(x); ys.push(y); }
        if (xs.length > cfg.SKEW_POINTS) {                       // thin out evenly
            var keep = cfg.SKEW_POINTS, sx = [], sy = [];
            for (var k = 0; k < keep; k++) { var j = (k * xs.length / keep) | 0; sx.push(xs[j]); sy.push(ys[j]); }
            xs = sx; ys = sy;
        }
        var n = xs.length;
        if (n < 60) return { angle: 0, gain: 1 };
        // bin width = sampling step: a bin narrower than the grid the points were sampled on would favour 0 degrees
        var span = Math.ceil(Math.sqrt(w * w + h * h)) + 4, bins = new Int32Array(Math.ceil(span * 2 / step) + 2);
        function score(deg) {
            var r = deg * Math.PI / 180, s = Math.sin(r), c = Math.cos(r), i, b, sc = 0;
            bins.fill(0);
            for (i = 0; i < n; i++) bins[(((ys[i] * c - xs[i] * s) + span) / step) | 0]++;
            for (b = 0; b < bins.length; b++) sc += bins[b] * bins[b];
            return sc;
        }
        var base = score(0), best = 0, bestS = base;
        for (a = -cfg.SKEW_MAX; a <= cfg.SKEW_MAX; a += 1) { var s1 = score(a); if (s1 > bestS) { bestS = s1; best = a; } }
        var c0 = best;
        for (a = Math.max(-cfg.SKEW_MAX, c0 - 1); a <= Math.min(cfg.SKEW_MAX, c0 + 1); a += 0.25) { var s2 = score(a); if (s2 > bestS) { bestS = s2; best = a; } }
        return { angle: best, gain: base > 0 ? bestS / base : 1 };
    }

    // rotate so that lines running down to the right by `deg` become horizontal; bilinear, empty corners = fill
    function rotate(src, w, h, deg, fill) {
        var r = deg * Math.PI / 180, s = Math.sin(r), c = Math.cos(r), cx = (w - 1) / 2, cy = (h - 1) / 2;
        var out = new Uint8ClampedArray(w * h), x, y;
        for (y = 0; y < h; y++) {
            for (x = 0; x < w; x++) {
                var u = x - cx, v = y - cy;
                var sx = u * c - v * s + cx, sy = u * s + v * c + cy;
                if (sx < 0 || sy < 0 || sx > w - 1 || sy > h - 1) { out[y * w + x] = fill; continue; }
                var x0 = sx | 0, y0 = sy | 0, x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1), tx = sx - x0, ty = sy - y0;
                var p = src[y0 * w + x0] * (1 - tx) + src[y0 * w + x1] * tx;
                var q = src[y1 * w + x0] * (1 - tx) + src[y1 * w + x1] * tx;
                out[y * w + x] = p * (1 - ty) + q * ty + 0.5;
            }
        }
        return out;
    }

    // Sauvola local threshold with integral images. Text (dark) -> 0, paper -> 255.
    function sauvola(st, w, h, cfg) {
        var win = Math.round(Math.min(w, h) / cfg.SAUVOLA_DIV);
        win = clamp(win, cfg.SAUVOLA_MIN, cfg.SAUVOLA_MAX); if (!(win & 1)) win++;
        var half = win >> 1, W = w + 1, S = new Float64Array(W * (h + 1)), S2 = new Float64Array(W * (h + 1)), x, y;
        for (y = 0; y < h; y++) {
            var rs = 0, rq = 0;
            for (x = 0; x < w; x++) {
                var v = st[y * w + x]; rs += v; rq += v * v;
                S[(y + 1) * W + x + 1] = S[y * W + x + 1] + rs;
                S2[(y + 1) * W + x + 1] = S2[y * W + x + 1] + rq;
            }
        }
        var out = new Uint8ClampedArray(w * h), k = cfg.SAUVOLA_K, kd = k / 128, kk = 1 - k;
        var xa = new Int32Array(w), xb = new Int32Array(w), xw = new Int32Array(w);          // window columns, computed once
        for (x = 0; x < w; x++) { xa[x] = Math.max(0, x - half); xb[x] = Math.min(w, x + half + 1); xw[x] = xb[x] - xa[x]; }
        for (y = 0; y < h; y++) {
            var ra = Math.max(0, y - half) * W, rb = Math.min(h, y + half + 1) * W, hh = (rb - ra) / W, o = y * w;
            for (x = 0; x < w; x++) {
                var x0 = xa[x], x1 = xb[x], inv = 1 / (xw[x] * hh);
                var mean = (S[rb + x1] - S[ra + x1] - S[rb + x0] + S[ra + x0]) * inv;
                var v2 = (S2[rb + x1] - S2[ra + x1] - S2[rb + x0] + S2[ra + x0]) * inv - mean * mean;
                out[o + x] = st[o + x] > mean * (kk + kd * Math.sqrt(v2 > 0 ? v2 : 0)) ? 255 : 0;   // mean * (1 + k * (sd / 128 - 1))
            }
        }
        return out;
    }

    // Where the text is. From the black/white picture (0 = ink): rows / columns that hold real ink (specks are ignored),
    // the box around them + a margin, the typical line height and the number of text lines.
    // Tesseract's time grows with the picture area, so the page hands it only this box.
    //   -> { x0, y0, x1, y1 (exclusive), lineH, lines } or null when there is no text
    function textBox(bin, w, h, cfg) {
        var rows = new Uint32Array(h), cols = new Uint32Array(w), x, y, i, maxR = 0, maxC = 0;
        for (y = 0; y < h; y++) {
            var o = y * w, c = 0;
            for (x = 0; x < w; x++) if (bin[o + x] === 0) { c++; cols[x]++; }
            rows[y] = c; if (c > maxR) maxR = c;
        }
        for (x = 0; x < w; x++) if (cols[x] > maxC) maxC = cols[x];
        if (maxR < 3) return null;
        var rt = Math.max(2, Math.round(maxR * cfg.BOX_ROW_SHARE)), ct = Math.max(2, Math.round(maxC * cfg.BOX_COL_SHARE));
        // text lines = runs of rows above the threshold (gaps of up to 2 rows are bridged: i-dots, thin strokes)
        var runs = [], start = -1, gap = 0;
        for (y = 0; y < h; y++) {
            if (rows[y] >= rt) { if (start < 0) start = y; gap = 0; }
            else if (start >= 0 && ++gap > 2) { runs.push([start, y - gap]); start = -1; gap = 0; }
        }
        if (start >= 0) runs.push([start, h - 1 - gap]);
        runs = runs.filter(function (r) { return r[1] - r[0] + 1 >= cfg.BOX_MIN_LINE; });
        if (!runs.length) return null;
        var heights = runs.map(function (r) { return r[1] - r[0] + 1; }).sort(function (a, b) { return a - b; });
        var lineH = heights[heights.length >> 1];
        var ry0 = runs[0][0], ry1 = runs[runs.length - 1][1], cx0 = -1, cx1 = -1;
        for (x = 0; x < w; x++) {
            var cnt = 0; for (i = 0; i < 3 && x + i < w; i++) cnt += cols[x + i];
            if (cnt >= ct * 2) { if (cx0 < 0) cx0 = x; cx1 = x; }
        }
        if (cx0 < 0) return null;
        var mg = Math.max(6, Math.round(lineH * cfg.BOX_MARGIN));
        return { x0: Math.max(0, cx0 - mg), y0: Math.max(0, ry0 - mg), x1: Math.min(w, cx1 + 1 + mg), y1: Math.min(h, ry1 + 1 + mg),
                 lineH: lineH, lines: runs.length };
    }

    function thresholdGlobal(st, thr) {
        var out = new Uint8ClampedArray(st.length);
        for (var i = 0; i < out.length; i++) out[i] = st[i] > thr ? 255 : 0;
        return out;
    }

    // ---------- the pipeline ----------

    // rgba: Uint8ClampedArray (w*h*4)
    function process(rgba, w, h, opts) {
        var t0 = now(), c = {}, k;
        for (k in CFG) c[k] = CFG[k];
        if (opts) for (k in opts) c[k] = opts[k];
        var enhance = !(opts && opts.enhance === false);

        // 1. grey + raw statistics
        var n = w * h, gray = new Uint8ClampedArray(n), hist = new Uint32Array(256), sum = 0, i, j;
        for (i = 0, j = 0; j < n; i += 4, j++) {
            var g = (rgba[i] * 0.299 + rgba[i + 1] * 0.587 + rgba[i + 2] * 0.114) | 0;
            gray[j] = g; hist[g]++; sum += g;
        }
        var brightness = sum / n, glareN = 0;
        for (i = c.GLARE_LEVEL; i < 256; i++) glareN += hist[i];
        var acc = 0, lo = 0, hi = 255;
        for (i = 0; i < 256; i++) { acc += hist[i]; if (acc >= n * c.CLIP) { lo = i; break; } }
        acc = 0;
        for (i = 255; i >= 0; i--) { acc += hist[i]; if (acc >= n * c.CLIP) { hi = i; break; } }

        // 2. stretch + polarity (same maths as v1) -> sharpness is measured on this picture
        var range = Math.max(hi - lo, c.MIN_RANGE), invert = brightness < c.INVERT_MEAN;
        // a flat picture (range < MIN_RANGE) is anchored on the paper side, so plain paper stays white and is not
        // blown up into black (same result as v1 whenever the picture has real contrast)
        var off = invert ? lo : Math.max(lo, hi - range), st = new Uint8ClampedArray(n);
        if (!invert && hi - lo < range) off = hi - range;
        for (j = 0; j < n; j++) {
            var v = (gray[j] - off) * 255 / range;
            v = v < 0 ? 0 : (v > 255 ? 255 : v);
            st[j] = invert ? 255 - v : v;
        }
        var sharp = sharpness(st, w, h);
        var q = { sharp: sharp, brightness: Math.round(brightness), contrast: hi - lo, glare: glareN / n, noise: 0, skew: 0,
                  inverted: invert, flags: [], box: null, ms: 0 };

        var thr, bin = null;
        if (!enhance) {
            thr = otsu(histogram(st), n);
            q.ms = now() - t0;
            return { st: st, bin: null, thr: thr, sharp: sharp, skew: 0, q: q };
        }

        // 3. even out the light
        if (c.FLATTEN && w >= 24 && h >= 24) {
            var fl = flatten(st, w, h, c);
            if (fl) { st = fl; stretchInPlace(st, c.CLIP, c.MIN_RANGE); }
        }
        // 4. noise: smooth only when the picture is really noisy
        q.noise = Math.round(noiseSigma(st, w, h) * 10) / 10;
        var smoothed = false;
        if (c.DENOISE && q.noise > c.NOISE_SIGMA) { st = blur3(st, w, h); smoothed = true; }
        // 5. soft picture -> a little unsharp mask (never on a noisy one: it would sharpen the noise)
        if (c.SHARPEN && !smoothed && sharp < c.SHARPEN_BELOW) st = unsharp(st, w, h, c.SHARPEN_AMOUNT);

        // 6 + 7. black & white (Sauvola) - its text mask is also what the skew search looks at, because it is not
        // fooled by shadows the way one global threshold is - then straighten and binarise again if it was rotated
        thr = otsu(histogram(st), n);
        var small = w < 8 || h < 8;
        if (c.BINARIZE || c.DESKEW) bin = small ? thresholdGlobal(st, thr) : sauvola(st, w, h, c);
        if (c.DESKEW && w >= 40 && h >= 24) {
            var sk = estimateSkew(bin, w, h, 128, c);
            q.skew = sk.angle;
            if (Math.abs(sk.angle) >= c.SKEW_MIN && Math.abs(sk.angle) < c.SKEW_MAX && sk.gain >= c.SKEW_GAIN) {
                st = rotate(st, w, h, sk.angle, 255);
                thr = otsu(histogram(st), n);
                bin = sauvola(st, w, h, c);
            } else {
                q.skew = 0;                                  // nothing found, or the best angle sits on the search limit (unreliable)
            }
        }
        if (c.BOX && bin) { q.box = textBox(bin, w, h, c); }
        if (!c.BINARIZE) bin = null;

        // 8. quality flags (the page turns them into hints)
        if (q.brightness < c.DARK_BRIGHTNESS && !invert) q.flags.push('dark');
        if (q.glare > c.GLARE_SHARE && q.glare < c.GLARE_MAX_SHARE) q.flags.push('glare');   // a mostly white label is not glare
        if (q.contrast < c.LOW_CONTRAST) q.flags.push('low_contrast');
        if (sharp < c.BLURRY_SHARP) q.flags.push('blurry');
        if (q.noise > c.NOISE_SIGMA) q.flags.push('noisy');
        if (Math.abs(q.skew) >= 5) q.flags.push('tilted');
        q.ms = Math.round((now() - t0) * 10) / 10;
        return { st: st, bin: bin, thr: thr, sharp: sharp, skew: q.skew, box: q.box, q: q };
    }

    var API = {
        process: process, CFG: CFG,
        otsu: otsu, sharpness: sharpness, noiseSigma: noiseSigma, flatten: flatten, estimateSkew: estimateSkew,
        rotate: rotate, sauvola: sauvola, textBox: textBox, blur3: blur3, unsharp: unsharp
    };
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
                var r = process(px, m.w, m.h, m.opts);
                var transfer = [r.st.buffer];
                if (r.bin) transfer.push(r.bin.buffer);
                root.postMessage({ id: id, st: r.st.buffer, bin: r.bin ? r.bin.buffer : null, thr: r.thr, sharp: r.sharp,
                                   skew: r.skew, box: r.box, q: r.q }, transfer);
            } catch (e) {
                root.postMessage({ id: id, error: String(e && e.message || e) });
            }
        };
    }
})(typeof self !== 'undefined' ? self : this);
