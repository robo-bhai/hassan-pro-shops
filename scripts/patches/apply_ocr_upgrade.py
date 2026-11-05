"""Applies the OCR upgrade (A: alias learning, local Tesseract, Urdu, logging) to the EXISTING files.

Run from the project root, after copying the new files from the zip:
    python scripts/patches/apply_ocr_upgrade.py            # patch
    python scripts/patches/apply_ocr_upgrade.py --check    # only report, change nothing

Every edit looks for an exact piece of text. If it is not found the script says so and changes NOTHING in that
file (so a file you edited by hand is never half-patched). Safe to run twice.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = '--check' in sys.argv

TEMPLATE = 'templates/sales/create.html'

EDITS = {
    'app/models/__init__.py': [
        ('    "inventory.agri",\n]', '    "inventory.agri",\n    "inventory.ocr",\n]', 'inventory.ocr'),
    ],
    'app/admin/__init__.py': [
        ('    "store_ops",\n    "registrations",', '    "store_ops",\n    "ocr",\n    "registrations",', '"ocr"'),
    ],
    'app/urls.py': [
        ("    path('ajax/ocr-match-product/', views_frontend.ocr_match_product, name='ocr_match_product'),\n",
         "    path('ajax/ocr-match-product/', views_frontend.ocr_match_product, name='ocr_match_product'),\n"
         "    path('ajax/ocr-feedback/', views_frontend.ocr_feedback, name='ocr_feedback'),\n", 'ocr_feedback'),
    ],
    TEMPLATE: [
        # ---- 1. local Tesseract first, CDN as fallback ------------------------------------------------
        ("    const OCR_OPTS = {};\n"
         "    const OCR_LIB_URLS = ['https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js',\n",
         "    // Files come from static/tesseract/ (run scripts/utilities/fetch_tesseract_assets.py once). If they are\n"
         "    // missing the page falls back to the CDN, so nothing breaks while you set it up.\n"
         "    const OCR_LOCAL = \"{% static 'tesseract/' %}\";\n"
         "    const OCR_OPTS = { workerPath: OCR_LOCAL + 'worker.min.js', corePath: OCR_LOCAL + 'core/',\n"
         "                       langPath: OCR_LOCAL + 'lang/', gzip: false, workerBlobURL: false };\n"
         "    const OCR_LANGS = ['eng+urd', 'eng'];        // Urdu + English first; plain English if urd is not available\n"
         "    const OCR_LIB_URLS = [OCR_LOCAL + 'tesseract.min.js',\n"
         "                          'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js',\n",
         'OCR_LOCAL'),
        ("            const opts = Object.assign({ logger: ocrOnProgress }, OCR_OPTS);\n"
         "            const wk = await Tesseract.createWorker('eng', 1, opts);\n",
         "            const wk = await ocrCreateWorker();\n",
         'ocrCreateWorker()'),
        ("    function ocrLoadWorker() {\n",
         "    // tries: local files + eng+urd, local + eng, then CDN defaults + eng+urd, CDN + eng\n"
         "    async function ocrCreateWorker() {\n"
         "        const sets = [OCR_OPTS, {}], errs = [];\n"
         "        for (const o of sets) {\n"
         "            for (const lang of OCR_LANGS) {\n"
         "                try {\n"
         "                    const opts = Object.assign({ logger: ocrOnProgress }, o);\n"
         "                    const wk = await Promise.race([\n"
         "                        Tesseract.createWorker(lang, 1, opts),\n"
         "                        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 30000))\n"
         "                    ]);\n"
         "                    ocrDebug('reader: ' + lang + (o === OCR_OPTS ? ' (local files)' : ' (CDN)'));\n"
         "                    return wk;\n"
         "                } catch (e) { errs.push(lang + ': ' + (e && e.message || e)); }\n"
         "            }\n"
         "        }\n"
         "        throw new Error('Text reader could not start (' + errs.join('; ') + ')');\n"
         "    }\n\n"
         "    function ocrLoadWorker() {\n",
         'async function ocrCreateWorker'),
        # ---- 2. Urdu letters must survive the text cleaning --------------------------------------------
        ("filter(w => /[a-z]{2,}/i.test(w) ||", "filter(w => /[a-z\\u0600-\\u06ff]{2,}/i.test(w) ||", 'a-z\\u0600-\\u06ff]{2,}'),
        (".map(w => w.replace(/[^a-z0-9.\\-]/gi, ''))", ".map(w => w.replace(/[^a-z0-9.\\-\\u0600-\\u06ff]/gi, ''))", '0-9.\\-\\u0600-\\u06ff'),
        ("const letters = text.replace(/[^a-z]/gi, '').length;", "const letters = text.replace(/[^a-z\\u0600-\\u06ff]/gi, '').length;", 'letters = text.replace(/[^a-z\\u0600-\\u06ff]'),
        # ---- 3. tell the server where the text came from + remember which log row is on screen ---------
        ("    let ocrAddedCount = 0, ocrRecent = {}, ocrVote = { id: 0, count: 0, t: 0 }, ocrSig = null, ocrLast = null;\n",
         "    let ocrAddedCount = 0, ocrRecent = {}, ocrVote = { id: 0, count: 0, t: 0 }, ocrSig = null, ocrLast = null;\n"
         "    let ocrLogId = 0;                                  // OcrScanLog row of the matches now on screen\n",
         'let ocrLogId'),
        ("const pending = await ocrMatch(r.text, force);", "const pending = await ocrMatch(r.text, force, { source: 'camera', conf: r.conf });", "source: 'camera'"),
        ("else { await ocrMatch(r.text, true); }", "else { await ocrMatch(r.text, true, { source: 'photo', conf: r.conf }); }", "source: 'photo'"),
        ("        ocrMatch(v, true);\n    }\n", "        ocrMatch(v, true, { source: 'manual' });\n    }\n", "source: 'manual'"),
        ("    async function ocrMatch(text, force) {\n", "    async function ocrMatch(text, force, meta) {\n        meta = meta || {};\n", 'meta = meta || {}'),
        ("'&text=' + encodeURIComponent(text));",
         "'&source=' + (meta.source || 'camera') + (meta.conf != null ? '&conf=' + meta.conf : '') + '&text=' + encodeURIComponent(text));",
         "'&source=' + (meta.source"),
        ("        if (!d.success) {\n            ocrRenderMatches([]);\n",
         "        if (!d.success) {\n            ocrLogId = 0;\n            ocrRenderMatches([]);\n", 'ocrLogId = 0;'),
        ("        ocrRenderMatches(d.products);\n        const top = d.products[0];\n",
         "        ocrLogId = d.log_id || 0;\n        ocrRenderMatches(d.products);\n        const top = d.products[0];\n", 'ocrLogId = d.log_id'),
        # ---- 3b. too many scans (rate limit) -> friendly message instead of "Network/server error" ---------
        ("            if (!r.ok) throw new Error('HTTP ' + r.status);\n            d = await r.json();\n",
         "            if (r.status === 429) { ocrStatus('Too many scans - wait a few seconds.', 'warn'); return false; }\n"
         "            if (!r.ok) throw new Error('HTTP ' + r.status);\n            d = await r.json();\n",
         'r.status === 429'),
        # ---- 4. send the decision (this is what the server learns from) ---------------------------------
        ("    function ocrAddProduct(p, fromAuto) {\n",
         "    // Tells the server which product was finally chosen (log + alias learning). Never blocks the sale.\n"
         "    function ocrSendFeedback(p, fromAuto) {\n"
         "        if (!ocrLogId) return;\n"
         "        const body = new URLSearchParams({ log_id: ocrLogId, product_id: p.id, how: fromAuto ? 'auto' : 'tap' });\n"
         "        ocrLogId = 0;\n"
         "        fetch('/ajax/ocr-feedback/', { method: 'POST', body: body,\n"
         "            headers: { 'X-CSRFToken': getCookie('csrftoken') } }).catch(() => {});\n"
         "    }\n\n"
         "    function ocrAddProduct(p, fromAuto) {\n",
         'function ocrSendFeedback'),
        ("        const remaining = parseFloat(p.batch_remaining_qty) || 0;\n        if (remaining <= 0 && !(parseFloat(p.stock) > 0)) {\n            ocrStatus('Out of stock: ' + p.name, 'err');",
         "        ocrSendFeedback(p, fromAuto);\n"
         "        const remaining = parseFloat(p.batch_remaining_qty) || 0;\n        if (remaining <= 0 && !(parseFloat(p.stock) > 0)) {\n            ocrStatus('Out of stock: ' + p.name, 'err');",
         'ocrSendFeedback(p, fromAuto);'),
    ],
}


def main():
    problems = 0
    for rel, edits in EDITS.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print('MISSING FILE   ', rel); problems += 1; continue
        with open(path, encoding='utf-8', newline='') as f:
            text = f.read()
        crlf = '\r\n' in text
        work = text.replace('\r\n', '\n')
        todo, done, bad = [], 0, []
        for old, new, marker in edits:
            if marker in work and new in work:
                done += 1
            elif work.count(old) == 1:
                todo.append((old, new))
            else:
                bad.append(old.strip().splitlines()[0][:70] + ('  (found %d times)' % work.count(old)))
        if bad:
            problems += 1
            print('NOT PATCHED    %s - text not found, nothing changed:' % rel)
            for b in bad:
                print('    ', b)
            continue
        for old, new in todo:
            work = work.replace(old, new, 1)
        print('%-14s %s  (%d new edits, %d already there)' % ('would patch' if CHECK and todo else ('ok' if not todo else 'patched'), rel, len(todo), done))
        if todo and not CHECK:
            if crlf:
                work = work.replace('\n', '\r\n')
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(work)
    print('\nDone.' if not problems else '\n%d file(s) need a manual look.' % problems)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
