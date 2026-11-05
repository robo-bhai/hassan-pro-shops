/* OCR product matching in the browser (feature: local catalog).
 *
 * A line-by-line port of app/utils/pos/ocr_core.py (normalize / tokens / trigrams / fold / idf / sizes / score / Index /
 * rank) so the
 * phone can rank products WITHOUT asking the server. tests/test_ocr_js_parity.py runs both versions on the same
 * data and fails if they ever disagree - change one, change the other.
 *
 * Also: OcrMatch.Local = download the compact product list from /ajax/ocr-catalog/, keep it in IndexedDB
 * (so the next visit starts instantly, even offline) and build the index in small slices (no UI freeze).
 */
(function (root) {
    'use strict';

    // ---- tuning: keep equal to ocr_core.py ----
    var PREFILTER_MIN = 0.25, PREFILTER_TOP = 60, MIN_LIST_SCORE = 45;
    var SIZE_BONUS = 5, SIZE_PENALTY = 30;
    var WORD_MATCH_MIN = 0.78, IDF_CAP = 4.0, FOLD_DISCOUNT = 0.97, CONF_LENIENT_BELOW = 65, CONF_RELAX = 0.06, CONF_FLOOR = 0.7;
    var STOP = {};
    ['the', 'and', 'for', 'with', 'new', 'pack', 'pcs', 'pc', 'rs', 'mrp', 'price', 'net', 'wt', 'exp', 'mfg', 'date',
        'batch', 'best', 'before', 'made', 'in', 'from', 'use', 'only'].forEach(function (w) { STOP[w] = 1; });

    function normalize(text) {
        text = (text || '').toLowerCase();
        text = text.replace(/[^a-z0-9\u0600-\u06ff]+/g, ' ');
        return text.replace(/\s+/g, ' ').trim();
    }
    function tokens(text) {
        return normalize(text).split(' ').filter(function (t) { return t.length >= 3 && !STOP[t]; });
    }
    function trigrams(s) {
        s = ' ' + s + ' ';
        var out = new Set();
        for (var i = 0; i < s.length - 2; i++) out.add(s.substr(i, 3));
        return out;
    }
    // Python round(): half goes to the even number (JS Math.round goes up)
    function pyRound(x) {
        var f = Math.floor(x), d = x - f;
        if (d < 0.5) return f;
        if (d > 0.5) return f + 1;
        return (f % 2 === 0) ? f : f + 1;
    }

    // ---- look-alike characters (ocr_core.fold) ----
    var FOLD_ONE = { '0': 'o', '1': 'l', 'i': 'l', '5': 's', '8': 'b', '2': 'z', '6': 'g' };
    function fold(tok) {
        if (tok.length < 3 || !/[a-z]/.test(tok)) return tok;
        tok = tok.split('rn').join('m').split('vv').join('w');
        return tok.replace(/[01i5826]/g, function (c) { return FOLD_ONE[c]; });
    }

    // ---- word rarity (ocr_core.idf_weight / IdfTable): integer maths only, so it equals Python exactly ----
    function idfWeight(n, df) {
        var r = Math.max(1, Math.floor(n / Math.max(1, df))), bits = 0;
        while (r > 0) { bits++; r = Math.floor(r / 2); }
        return Math.min(IDF_CAP, 1.0 + 0.5 * (bits - 1));
    }
    function IdfTable(n, df) { this.n = n; this.df = df; this.cache = new Map(); }
    IdfTable.prototype.get = function (word) {
        var w = this.cache.get(word);
        if (w === undefined) { w = idfWeight(this.n, this.df.get(word) || 1); this.cache.set(word, w); }
        return w;
    };

    // ---- pack sizes (ocr_core.quantities / size_adjust) ----
    var QTY_SRC = '(^|[^0-9.,])(\\d+(?:[.,]\\d+)?)\\s*(ml|ltrs?|litres?|liters?|l|kgs?|gms?|grams?|g)(?![a-z])';
    var QTY_MULT = { ml: 1, g: 1, gm: 1, gms: 1, gram: 1, grams: 1, l: 1000, ltr: 1000, ltrs: 1000, litre: 1000,
                     litres: 1000, liter: 1000, liters: 1000, kg: 1000, kgs: 1000 };
    var QTY_VOL = { ml: 1, l: 1, ltr: 1, ltrs: 1, litre: 1, litres: 1, liter: 1, liters: 1 };
    function quantities(text) {
        var re = new RegExp(QTY_SRC, 'gi'), seen = {}, keys = [], m;
        text = text || '';
        while ((m = re.exec(text)) !== null) {
            if (m[2].length > 9) continue;
            var unit = m[3].toLowerCase();
            var n = Math.floor(parseFloat(m[2].replace(',', '.')) * QTY_MULT[unit] + 0.5);
            if (n > 0) {
                var k = (QTY_VOL[unit] ? 'v' : 'm') + String(n);
                if (!seen[k]) { seen[k] = 1; keys.push(k); }
            }
        }
        return keys.sort();
    }
    function near(a, b) {
        if (a.charAt(0) !== b.charAt(0) || a.length !== b.length) return false;
        var d = 0;
        for (var i = 1; i < a.length; i++) if (a.charAt(i) !== b.charAt(i)) d++;
        return d === 1;
    }
    function sizeAdjust(s, oq, nq) {
        if (!s || !oq || !oq.length || !nq || !nq.length) return s;
        var matched = false, mismatch = false;
        ['v', 'm'].forEach(function (d) {
            var o = oq.filter(function (q) { return q.charAt(0) === d; });
            var n = nq.filter(function (q) { return q.charAt(0) === d; });
            if (!o.length || !n.length) return;
            if (n.some(function (x) { return o.indexOf(x) >= 0; })) matched = true;
            else if (!n.some(function (x) { return o.some(function (y) { return near(x, y); }); })) mismatch = true;
        });
        if (matched) return Math.min(100, s + SIZE_BONUS);
        if (mismatch) return Math.max(0, s - SIZE_PENALTY);
        return s;
    }
    // UPC-A '036000291452' and EAN-13 '0036000291452' are one code
    function barcodeKey(d) { return String(d || '').replace(/^0+/, ''); }
    // {word: confidence} as a plain object or a Map -> Map (or null)
    function toConfMap(w) {
        if (!w) return null;
        if (w instanceof Map) return w.size ? w : null;
        var m = new Map(), ks = Object.keys(w);
        for (var i = 0; i < ks.length; i++) m.set(ks[i], Number(w[ks[i]]));
        return m.size ? m : null;
    }

    // ---- difflib.SequenceMatcher(None, a, b).ratio() ----
    function longest(a, alo, ahi, b, blo, bhi) {          // earliest-in-a, then earliest-in-b, on ties (like difflib)
        var bi = alo, bj = blo, bk = 0, prev = [], i, j, cur, k;
        for (j = 0; j <= bhi - blo; j++) prev.push(0);
        for (i = alo; i < ahi; i++) {
            cur = [0];
            for (j = blo; j < bhi; j++) {
                if (a.charAt(i) === b.charAt(j)) {
                    k = prev[j - blo] + 1;
                    cur.push(k);
                    if (k > bk) { bi = i - k + 1; bj = j - k + 1; bk = k; }
                } else cur.push(0);
            }
            prev = cur;
        }
        return [bi, bj, bk];
    }
    function matchedChars(a, b) {
        var total = 0, stack = [[0, a.length, 0, b.length]], q, m, alo, ahi, blo, bhi;
        while (stack.length) {
            q = stack.pop(); alo = q[0]; ahi = q[1]; blo = q[2]; bhi = q[3];
            m = longest(a, alo, ahi, b, blo, bhi);
            if (m[2]) {
                total += m[2];
                if (alo < m[0] && blo < m[1]) stack.push([alo, m[0], blo, m[1]]);
                if (m[0] + m[2] < ahi && m[1] + m[2] < bhi) stack.push([m[0] + m[2], ahi, m[1] + m[2], bhi]);
            }
        }
        return total;
    }
    function ratio(a, b) {
        var t = a.length + b.length;
        if (!t) return 1.0;
        return 2.0 * matchedChars(a, b) / t;
    }

    function score(ocrText, ocrTokens, name, idf, wconf) {
        var n = normalize(name);
        if (!n) return 0;
        var o = normalize(ocrText);
        if (o.indexOf(n) >= 0) return Math.min(100, 90 + Math.floor(n.length / 3));
        var nameTokens = n.split(' ').filter(function (t) { return t.length >= 2; });
        if (!nameTokens.length) return 0;
        wconf = toConfMap(wconf);
        var folded = new Map(), hit = 0, total = 0, i, j, best, r, rf, c, thr, v, wt, fnt, fot, ot;
        for (i = 0; i < nameTokens.length; i++) {
            wt = idf ? idf.get(nameTokens[i]) : 1.0;
            total += wt;
            fnt = fold(nameTokens[i]);
            best = 0;
            for (j = 0; j < ocrTokens.length; j++) {
                ot = ocrTokens[j];
                c = wconf ? wconf.get(ot) : undefined;
                thr = WORD_MATCH_MIN - ((c !== undefined && c < CONF_LENIENT_BELOW) ? CONF_RELAX : 0.0);
                r = ratio(nameTokens[i], ot);
                if (r < 0.95) {
                    fot = folded.get(ot);
                    if (fot === undefined) { fot = fold(ot); folded.set(ot, fot); }
                    if (fnt !== nameTokens[i] || fot !== ot) {
                        rf = ratio(fnt, fot) * FOLD_DISCOUNT;
                        if (rf > r) r = rf;
                    }
                }
                if (r >= thr) {
                    v = (c === undefined) ? r : r * (CONF_FLOOR + (1.0 - CONF_FLOOR) * ((c < 0 ? 0 : c > 100 ? 100 : c) / 100.0));
                    if (v > best) best = v;
                }
            }
            hit += wt * best;
        }
        var coverage = hit / total;
        var whole = (o.length <= n.length * 2.5) ? ratio(n, o) : 0.0;
        return pyRound(100 * Math.max(coverage * 0.95, whole));
    }

    // catalog item from the server: [id, name, barcode, [aliases]]
    function makeEntry(id, name, barcode, aliases) {
        var norm = normalize(name);
        if (!norm) return null;
        var e = { id: id, name: name, barcode: String(barcode || '').replace(/\D/g, ''),
                  names: [[name, norm, trigrams(norm)]], qty: quantities(name) };
        (aliases || []).forEach(function (a) {
            var an = normalize(a);
            if (an) e.names.push([a, an, trigrams(an)]);
        });
        return e;
    }

    function Index(entries) {
        this.entries = entries; this.owner = []; this.size = []; this.postings = new Map(); this.byBarcode = new Map();
        var df = new Map();
        for (var ei = 0; ei < entries.length; ei++) {
            var seen = new Set();
            entries[ei].names[0][1].split(' ').forEach(function (w) { if (w.length >= 2) seen.add(w); });
            seen.forEach(function (w) { df.set(w, (df.get(w) || 0) + 1); });
            this.add(entries[ei], ei);
        }
        this.idf = new IdfTable(entries.length, df);
    }
    Index.prototype.add = function (e, ei) {
        var bk = barcodeKey(e.barcode);
        if (bk) {
            var l = this.byBarcode.get(bk);
            if (!l) this.byBarcode.set(bk, l = []);
            l.push(e);
        }
        for (var k = 0; k < e.names.length; k++) {
            var ntg = e.names[k][2];
            if (!ntg.size) continue;
            var gid = this.owner.length;
            this.owner.push(ei); this.size.push(ntg.size);
            var self = this;
            ntg.forEach(function (t) {
                var p = self.postings.get(t);
                if (!p) self.postings.set(t, p = []);
                p.push(gid);
            });
        }
    };
    Index.prototype.candidates = function (tg) {
        var counts = new Map(), self = this;
        tg.forEach(function (t) {
            var p = self.postings.get(t);
            if (p) for (var i = 0; i < p.length; i++) counts.set(p[i], (counts.get(p[i]) || 0) + 1);
        });
        var best = new Map();
        counts.forEach(function (n, gid) {
            var c = n / self.size[gid];
            if (c >= PREFILTER_MIN) {
                var ei = self.owner[gid];
                if (c > (best.get(ei) || 0.0)) best.set(ei, c);
            }
        });
        var order = Array.from(best.entries()).sort(function (a, b) { return (b[1] - a[1]) || (a[0] - b[0]); });
        return order.slice(0, PREFILTER_TOP).map(function (kv) { return self.entries[kv[0]]; });
    };

    // -> { text, ranked: [[score, entry], ...] best first }
    function rank(rawText, index, wconf) {
        var text = normalize(rawText), toks = tokens(rawText), oq = quantities(rawText);
        wconf = toConfMap(wconf);
        var runs = (String(rawText || '').replace(/[\s\-]/g, '').match(/\d{8,14}/g)) || [];
        var scored = new Map(), i, j;
        for (i = 0; i < runs.length; i++) {
            var hits = index.byBarcode.get(barcodeKey(runs[i])) || [];
            for (j = 0; j < hits.length; j++) scored.set(hits[j].id, [100, hits[j]]);
        }
        if (text && toks.length) {
            var cands = index.candidates(trigrams(text));
            for (i = 0; i < cands.length; i++) {
                var e = cands[i];
                if (scored.has(e.id)) continue;
                var s = 0;
                for (j = 0; j < e.names.length; j++) s = Math.max(s, score(text, toks, e.names[j][0], index.idf, wconf));
                s = sizeAdjust(s, oq, e.qty);
                if (s >= MIN_LIST_SCORE) scored.set(e.id, [s, e]);
            }
        }
        var ranked = Array.from(scored.values()).sort(function (a, b) { return (b[0] - a[0]) || (b[1].name.length - a[1].name.length); });
        return { text: text, ranked: ranked };
    }

    // ================= browser only: download + IndexedDB + sliced index build =================
    var Local = {
        index: null, loading: null, busy: false, loadedAt: 0, ver: null, SLICE: 3000, MAX_AGE_MS: 10 * 60 * 1000,
        ready: function () { return !!Local.index; }
    };
    function idb() {
        return new Promise(function (res, rej) {
            if (!root.indexedDB) return rej(new Error('no indexedDB'));
            var rq = root.indexedDB.open('ocr_local', 1);
            rq.onupgradeneeded = function () { rq.result.createObjectStore('kv'); };
            rq.onsuccess = function () { res(rq.result); };
            rq.onerror = function () { rej(rq.error); };
        });
    }
    function kvGet(k) {
        return idb().then(function (db) {
            return new Promise(function (res, rej) {
                var r = db.transaction('kv').objectStore('kv').get(k);
                r.onsuccess = function () { res(r.result); }; r.onerror = function () { rej(r.error); };
            });
        });
    }
    function kvSet(k, v) {
        return idb().then(function (db) {
            return new Promise(function (res, rej) {
                var tx = db.transaction('kv', 'readwrite');
                tx.objectStore('kv').put(v, k);
                tx.oncomplete = function () { res(); }; tx.onerror = function () { rej(tx.error); };
            });
        });
    }
    function buildSliced(items) {
        return new Promise(function (resolve) {
            var entries = [], i = 0;
            (function step() {
                var end = Math.min(i + Local.SLICE, items.length);
                for (; i < end; i++) {
                    var it = items[i], e = makeEntry(it[0], it[1], it[2], it[3]);
                    if (e) entries.push(e);
                }
                if (i < items.length) setTimeout(step, 0); else resolve(new Index(entries));
            })();
        });
    }
    // url = '/ajax/ocr-catalog/'. Uses the saved copy first (instant, works offline), then asks the server whether it
    // changed - at most once per MAX_AGE_MS. Product renames therefore show up within ~10 minutes (aliases at once,
    // because they change the catalog version).
    Local.load = function (url) {
        var fresh = Local.loadedAt && (Date.now() - Local.loadedAt < Local.MAX_AGE_MS);
        if (Local.loading && (fresh || Local.busy)) return Local.loading;
        Local.busy = true;
        Local.loading = (async function () {
            try {
                if (!Local.index) {
                    var saved = null;
                    try { saved = await kvGet('catalog'); } catch (e) { saved = null; }
                    if (saved && saved.items) {
                        Local.index = await buildSliced(saved.items);
                        Local.ver = saved.ver;
                        if (Date.now() - (saved.ts || 0) < Local.MAX_AGE_MS) { Local.loadedAt = saved.ts; return Local.index; }
                    }
                }
                try {
                    var r = await fetch(url + '?ver=' + encodeURIComponent(Local.ver || ''), { credentials: 'same-origin' });
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    var d = await r.json();
                    if (d.unchanged) {
                        Local.loadedAt = Date.now();
                        kvGet('catalog').then(function (rec) { if (rec) { rec.ts = Local.loadedAt; return kvSet('catalog', rec); } })
                            .catch(function () {});
                    } else if (d.items) {
                        Local.index = await buildSliced(d.items); Local.ver = d.ver; Local.loadedAt = Date.now();
                        kvSet('catalog', { ver: d.ver, ts: Local.loadedAt, items: d.items }).catch(function () {});
                    }
                } catch (e) { if (!Local.index) throw e; }   // offline with a saved copy -> keep using it
                return Local.index;
            } finally { Local.busy = false; }
        })();
        Local.loading.catch(function () { Local.loading = null; });
        return Local.loading;
    };
    Local.rank = function (text, wconf) { return Local.index ? rank(text, Local.index, wconf) : null; };

    var API = { normalize: normalize, tokens: tokens, trigrams: trigrams, ratio: ratio, score: score, fold: fold,
                quantities: quantities, sizeAdjust: sizeAdjust, barcodeKey: barcodeKey, idfWeight: idfWeight,
                makeEntry: makeEntry, Index: Index, rank: rank, Local: Local };
    if (typeof module !== 'undefined' && module.exports) module.exports = API;
    else root.OcrMatch = API;
})(typeof self !== 'undefined' ? self : this);
