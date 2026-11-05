"""OCR upgrade: several products in ONE picture + faster reading.

Run from the project root, after copying the new files from the zip:
    python scripts/patches/apply_ocr_multi.py            # patch
    python scripts/patches/apply_ocr_multi.py --check    # only report, change nothing

Every edit looks for an exact piece of text. If one is not found the script says so and changes NOTHING in that
file (a file you edited by hand is never half-patched). Safe to run twice.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = '--check' in sys.argv
TEMPLATE = 'templates/sales/create.html'

# ---------------------------------------------------------------------------------------------- new JS (template)
JS_MULTI = r'''
    // ---------- several products in ONE picture (v6) ----------
    // The words Tesseract read are cut into one text per product label (static/ocr/ocr_multi.js); every label is
    // ranked on the phone, ONE request (/ajax/ocr-multi/) re-scores them all and the server says which may be
    // added by themselves (sure ones only, a product once). Doubtful labels stay as tap-buttons.
    function ocrMultiOn() { const c = document.getElementById('ocrMulti'); return !!c && c.checked && typeof OcrMulti !== 'undefined'; }
    function ocrMultiChanged() { ocrSavePrefs(); ocrRegionChanged(); }

    // ---------- store / warehouse choice inside the scan window ----------
    // Mirrors the "Warehouse" select of the sale form (the sale itself is made from that warehouse).
    function ocrSyncWarehouse() {
        const sel = document.getElementById('ocrWarehouse'), main = document.getElementById('warehouseSelect');
        if (!sel || !main) return;
        sel.innerHTML = '';
        Array.from(main.options).forEach(o => {
            if (!o.value) return;
            const n = document.createElement('option'); n.value = o.value; n.textContent = o.text;
            sel.appendChild(n);
        });
        sel.value = main.value;
    }
    function ocrWarehouseChanged() {
        const sel = document.getElementById('ocrWarehouse'), main = document.getElementById('warehouseSelect');
        if (!sel || !main || sel.value === main.value) return;
        if (cartItems.length) {
            if (!confirm('Changing the store will clear the cart (items belong to one store). Continue?')) { sel.value = main.value; return; }
            cartItems.length = 0;
            ocrSession = []; ocrUndoStack = []; ocrRecent = {}; ocrVotes = {};
            ocrAfterCartChange();
        }
        main.value = sel.value;
        main.dispatchEvent(new Event('change'));
        ocrRenderMatches([]); ocrHadRead = false; ocrSceneBreak = false;
        ocrStatus('Store: ' + (sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : ''), 'ok');
    }

    // reading result -> one product (old path) or several (new path). Returns true while a sure match waits for its 2nd read.
    async function ocrHandleRead(r, force, source) {
        const meta = { source: source, conf: r.conf };
        if (ocrMultiOn() && r.words && r.words.length) {
            const segs = OcrMulti.segment(r.words);
            if (segs.length >= 2) return ocrMatchMulti(r, segs, force, meta);
        }
        return ocrMatch(r.text, force, meta);
    }

    function ocrIdsFor(text) {
        if (typeof OcrMatch === 'undefined' || !OcrMatch.Local.ready()) return null;
        const lr = OcrMatch.Local.rank(text);
        return { text: lr.text, ids: lr.ranked.slice(0, 10).map(x => x[1].id) };
    }

    async function ocrMatchMulti(r, segs, force, meta) {
        const w = document.getElementById('warehouseSelect').value;
        ocrStatus('Searching ' + segs.length + ' labels...', 'busy');
        document.getElementById('ocrText').textContent = segs.map(s => s.text).join('  |  ');
        const items = [{ text: r.text, whole: true }].concat(segs.map(s => ({ text: s.text })));
        let usable = 0;
        for (const it of items) {
            const loc = ocrIdsFor(it.text);
            if (!loc) { return ocrMatch(r.text, force, meta); }       // phone catalog not ready -> old single path
            it.ids = loc.ids; if (loc.ids.length) usable++;
        }
        if (!usable) { return ocrMatch(r.text, force, meta); }
        let d;
        try {
            const resp = await fetch('/ajax/ocr-multi/', { method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ warehouse_id: w, source: meta.source, conf: meta.conf, items: items }) });
            if (resp.status === 429) { ocrStatus('Too many scans - wait a few seconds.', 'warn'); return false; }
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            d = await resp.json();
        } catch (e) { ocrStatus('Network/server error: ' + (e.message || e), 'err'); return false; }
        if (!ocrActive || !d.success) return false;

        const addSet = new Set(d.add || []);
        const auto = document.getElementById('ocrAuto').checked;
        const now = Date.now();
        let pending = false, added = [], doubtful = [];
        d.items.forEach((res, i) => {
            if (i === 0 && !addSet.has(0)) return;                   // the whole text only matters when it is sure
            if (!res.success || !res.products || !res.products.length) return;
            const top = res.products[0];
            if (!addSet.has(i)) {
                if (i > 0) doubtful.push({ text: res.text, log_id: res.log_id || 0, products: res.products.slice(0, 3) });
                return;
            }
            if (!auto && !force) { doubtful.push({ text: res.text, log_id: res.log_id || 0, products: res.products.slice(0, 3) }); return; }
            const v = ocrVotes[top.id];
            if (v && now - v.t < 5000) { v.count++; v.t = now; } else ocrVotes[top.id] = { count: 1, t: now };
            const sure = top.score >= OCR_SURE_SCORE || (top.score >= OCR_SURE_SCORE2 && (meta.conf || 0) >= OCR_SURE_CONF);
            if (force || ocrVotes[top.id].count >= 2 || sure) {
                delete ocrVotes[top.id];
                if (ocrAddProduct(top, !force, res.log_id || 0, true)) added.push(top.name);
            } else pending = true;
        });
        if (!doubtful.length) ocrRenderMatches([]);
        else ocrRenderMulti(doubtful);
        if (added.length) {
            ocrStatus('✅ Added ' + added.length + ': ' + added.join(', ') + (doubtful.length ? ' · ' + doubtful.length + ' to confirm' : ''), 'ok');
        } else if (pending) {
            ocrStatus('Keep steady to confirm...', 'busy');
        } else if (doubtful.length) {
            ocrStatus('Tap the correct product', 'warn');
            ocrFeedback('warn');
        } else {
            ocrStatus('No product found. Tap 📷 Read now, or type the name below.', 'err');
        }
        return pending;
    }

    // doubtful labels: a small heading (what was read) + its best 3 products as tap buttons
    function ocrRenderMulti(groups) {
        const box = document.getElementById('ocrMatches');
        box.innerHTML = '';
        groups.forEach(g => {
            const h = document.createElement('div');
            h.className = 'ocr-match-meta'; h.style.margin = '4px 2px 0';
            h.textContent = '“' + g.text + '”';
            box.appendChild(h);
            g.products.forEach(p => {
                const b = document.createElement('button');
                b.type = 'button'; b.className = 'ocr-match';
                const n = document.createElement('span'); n.className = 'ocr-match-name'; n.textContent = p.name;
                const m = document.createElement('span'); m.className = 'ocr-match-meta';
                m.textContent = (p.has_selling_price ? 'Rs. ' + parseFloat(p.price).toFixed(2) : 'No price') + ' · Stock ' + p.stock + (p.unit ? ' ' + p.unit : '');
                b.appendChild(n); b.appendChild(m);
                b.onclick = () => { ocrAddProduct(p, false, g.log_id); };
                box.appendChild(b);
            });
        });
    }
'''

EDITS = {
    TEMPLATE: [
        # 1. script tag
        ("<script src=\"{% static 'ocr/ocr_prep.js' %}\"></script>    <!-- picture preparation: web worker + fallback -->\n",
         "<script src=\"{% static 'ocr/ocr_prep.js' %}\"></script>    <!-- picture preparation: web worker + fallback -->\n"
         "<script src=\"{% static 'ocr/ocr_multi.js' %}\"></script>   <!-- several products in one picture -->\n",
         'script tag ocr_multi.js'),
        # 2. checkbox
        ("                    <label class=\"mb-0\"><input type=\"checkbox\" id=\"ocrAuto\" checked> Auto-add</label>\n",
         "                    <label class=\"mb-0\"><input type=\"checkbox\" id=\"ocrAuto\" checked> Auto-add</label>\n"
         "                    <label class=\"mb-0\" title=\"Several different products in one picture\"><input type=\"checkbox\" id=\"ocrMulti\" checked onchange=\"ocrMultiChanged()\"> 🧺 Multi</label>\n",
         'Multi checkbox'),
        # 3. constants
        ("    const OCR_SURE_CONF = 70;\n",
         "    const OCR_SURE_CONF = 70;\n"
         "    const OCR_MULTI_W = 1000;         // live picture width in Multi mode (several labels need more pixels)\n"
         "    const OCR_ADD_PAUSE_MS = 800;     // pause after an add (was 1200)\n",
         'constants'),
        ("    let ocrNoMatchSent = '', ocrWarnText = '';\n",
         "    let ocrNoMatchSent = '', ocrWarnText = '';\n    let ocrVotes = {};                                     // Multi mode: {product id: {count, t}} - a 2nd confirming read per product\n",
         'ocrVotes'),
        # 4. prefs
        ("            if (ast !== null) document.getElementById('ocrAssist').checked = ast !== '0';\n",
         "            if (ast !== null) document.getElementById('ocrAssist').checked = ast !== '0';\n"
         "            const mu = localStorage.getItem('ocrMulti');\n"
         "            if (mu !== null && document.getElementById('ocrMulti')) document.getElementById('ocrMulti').checked = mu !== '0';\n",
         'load prefs'),
        ("            localStorage.setItem('ocrAssist', document.getElementById('ocrAssist').checked ? '1' : '0');\n",
         "            localStorage.setItem('ocrAssist', document.getElementById('ocrAssist').checked ? '1' : '0');\n"
         "            if (document.getElementById('ocrMulti')) localStorage.setItem('ocrMulti', document.getElementById('ocrMulti').checked ? '1' : '0');\n",
         'save prefs'),
        ("        ocrRenderSession(); ocrUpdateUndoBar();\n        ocrCamPromise = ocrOpenCamera();",
         "        ocrRenderSession(); ocrUpdateUndoBar(); ocrVotes = {}; ocrRegionChanged();\n        ocrCamPromise = ocrOpenCamera();",
         'reset on open'),
        # 5. region: Multi looks at the full frame
        ("        const full = document.getElementById('ocrRegion').value === 'full';\n        const rw = full ? 1 : 0.86",
         "        const full = document.getElementById('ocrRegion').value === 'full' || ocrMultiOn();\n        const rw = full ? 1 : 0.86",
         'region rect'),
        ("        const full = document.getElementById('ocrRegion').value === 'full';\n        document.getElementById('ocrGuide').classList.toggle('full', full);\n        ocrHadRead = false;\n    }\n",
         "        const full = document.getElementById('ocrRegion').value === 'full' || ocrMultiOn();\n        document.getElementById('ocrGuide').classList.toggle('full', full);\n        ocrHadRead = false;\n    }\n" + JS_MULTI,
         'region guide + multi code'),
        # 6. faster recognize: skip hOCR / TSV generation (not used), keep text + word boxes
        ("        const r = await wk.recognize(canvas);\n",
         "        const r = await wk.recognize(canvas, {}, { text: true, blocks: true, hocr: false, tsv: false });   // hocr/tsv are never used -> skip them (faster)\n",
         'recognize output'),
        # 7. keep the word boxes of the best pass
        ("hRatio: ocrTextHeightRatio(d, cv.height) };\n",
         "hRatio: ocrTextHeightRatio(d, cv.height), words: d.words || null };\n",
         'best.words'),
        ("                 hRatio: best ? best.hRatio : null };\n",
         "                 hRatio: best ? best.hRatio : null, words: best ? best.words : null };\n",
         'return words'),
        # 8. live read -> multi or single
        ("        const r = await ocrReadFrom(v, rect, force, force ? 1100 : OCR_LIVE_W);\n",
         "        const r = await ocrReadFrom(v, rect, force, force ? 1100 : (ocrMultiOn() ? OCR_MULTI_W : OCR_LIVE_W));\n",
         'live width'),
        ("        const pending = await ocrMatch(r.text, force, { source: 'camera', conf: r.conf });\n",
         "        const pending = await ocrHandleRead(r, force, 'camera');\n",
         'live handle'),
        ("            else { await ocrMatch(r.text, true, { source: 'photo', conf: r.conf }); }\n",
         "            else { await ocrHandleRead(r, true, 'photo'); }\n",
         'photo handle'),
        # 9. add: per-label log id, returns true/false, no per-add status when called from Multi
        ("    function ocrSendFeedback(p, fromAuto) {\n        if (!ocrLogId) return;\n        const body = new URLSearchParams({ log_id: ocrLogId, product_id: p.id, how: fromAuto ? 'auto' : 'tap' });\n        ocrLogId = 0;\n",
         "    function ocrSendFeedback(p, fromAuto, logId) {\n        const lid = logId || ocrLogId;\n        if (!lid) return;\n        const body = new URLSearchParams({ log_id: lid, product_id: p.id, how: fromAuto ? 'auto' : 'tap' });\n        if (!logId) ocrLogId = 0;\n",
         'feedback logId'),
        ("    function ocrAddProduct(p, fromAuto) {\n", "    function ocrAddProduct(p, fromAuto, logId, quiet) {\n", 'addProduct signature'),
        ("            ocrStatus('Already added: ' + p.name, 'warn');\n            ocrHadRead = true;\n            return;\n        }\n        ocrSendFeedback(p, fromAuto);\n",
         "            if (!quiet) ocrStatus('Already added: ' + p.name, 'warn');\n            ocrHadRead = true;\n            return false;\n        }\n        ocrSendFeedback(p, fromAuto, logId);\n",
         'addProduct cooldown'),
        ("            ocrStatus('Out of stock: ' + p.name, 'err');\n            showToast('❌ Out of stock: ' + p.name, 'error');\n            ocrFeedback('err');\n            return;\n",
         "            const where = p.other_warehouses ? ' - stock is in: ' + p.other_warehouses : '';\n            ocrStatus('Out of stock in the selected warehouse: ' + p.name + where, 'err');\n            showToast('❌ Out of stock here: ' + p.name + where, 'error');\n            ocrFeedback('err');\n            return false;\n",
         'addProduct out of stock'),
        ("            }), 350);\n            return;\n        }\n        const idx0 = ocrCartIdx(p.id)",
         "            }), 350);\n            return false;\n        }\n        const idx0 = ocrCartIdx(p.id)",
         'addProduct no price'),
        ("            ocrStatus('✅ Added: ' + p.name + (after > 1 ? ' (×' + (Math.round(after * 100) / 100) + ' in cart)' : ''), 'ok');\n            ocrFeedback('ok');\n            ocrRenderMatches([]);\n            ocrPaused = true; ocrHadRead = true;\n            setTimeout(() => { ocrPaused = false; if (ocrActive) ocrStatus('Show the next product', ''); }, 1200);\n        } else {\n            ocrStatus('Could not add ' + p.name, 'err');\n            ocrFeedback('err');\n        }\n    }\n",
         "            if (!quiet) {\n                ocrStatus('✅ Added: ' + p.name + (after > 1 ? ' (×' + (Math.round(after * 100) / 100) + ' in cart)' : ''), 'ok');\n                ocrRenderMatches([]);\n            }\n            ocrFeedback('ok');\n            ocrPaused = true; ocrHadRead = true;\n            setTimeout(() => { ocrPaused = false; if (ocrActive) ocrStatus('Show the next product', ''); }, OCR_ADD_PAUSE_MS);\n            return true;\n        } else {\n            ocrStatus('Could not add ' + p.name, 'err');\n            ocrFeedback('err');\n            return false;\n        }\n    }\n",
         'addProduct success'),
        # 10. store / warehouse select inside the scan window
        ("                <div class=\"ocr-status\" id=\"ocrStatus\">Starting camera...</div>\n",
         "                <div class=\"ocr-controls\"><label class=\"mb-0 fw-bold\" for=\"ocrWarehouse\">🏬 Store:</label>"
         "<select id=\"ocrWarehouse\" class=\"form-select form-select-sm\" style=\"flex:1;\" onchange=\"ocrWarehouseChanged()\"></select></div>\n"
         "                <div class=\"ocr-status\" id=\"ocrStatus\">Starting camera...</div>\n",
         'store select (html)'),
        ("        ocrAudioInit(); ocrLoadPrefs();\n",
         "        ocrAudioInit(); ocrLoadPrefs(); ocrSyncWarehouse();\n",
         'store select (sync on open)'),
    ],
    'app/urls.py': [
        ("    path('ajax/ocr-details/', views_frontend.ocr_details, name='ocr_details'),\n",
         "    path('ajax/ocr-details/', views_frontend.ocr_details, name='ocr_details'),\n"
         "    path('ajax/ocr-multi/', views_frontend.ocr_multi, name='ocr_multi'),\n",
         'ocr_multi url'),
    ],
}


def patch(rel, edits):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        print('  MISSING FILE', rel)
        return False
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    out, todo, bad = text, 0, []
    for old, new, label in edits:
        if new in out:
            print('  already  ', label)
            continue
        n = out.count(old)
        if n != 1:
            bad.append((label, n))
            continue
        out = out.replace(old, new, 1)
        todo += 1
        print('  ok       ', label)
    if bad:
        for label, n in bad:
            print('  NOT FOUND' if n == 0 else '  AMBIGUOUS', label, '(%d matches)' % n)
        print('  -> %s left UNCHANGED' % rel)
        return False
    if todo and not CHECK:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
    return True


def main():
    ok = True
    for rel, edits in EDITS.items():
        print(rel)
        ok = patch(rel, edits) and ok
    print('\nDONE' if ok else '\nSOME FILES WERE NOT PATCHED (see above)')
    if CHECK:
        print('(--check: nothing was written)')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
