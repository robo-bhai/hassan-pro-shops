"""
OCR product matching for the Sale screen (v4).

The camera + text reading (Tesseract.js) runs in the browser. This view receives the text that was read and
returns the best matching products.  The matching itself lives in app/utils/pos/ocr_core.py (no Django, unit-tested).

URLs (add to urls.py):
    path('ajax/ocr-match-product/', views_frontend.ocr_match_product, name='ocr_match_product'),
    path('ajax/ocr-feedback/',      views_frontend.ocr_feedback,      name='ocr_feedback'),

v3 adds
    * every search is written to OcrScanLog (what was read, what was found, what the cashier did)
    * ocr_feedback: the page tells us which product was finally chosen. When the cashier CORRECTED the machine,
      the text is counted as an alias suggestion for that product. After ALIAS_AUTO_HITS confirmations it becomes a
      real ProductAlias, so the next scan of that packaging is found at once.
    * logging / learning can never break scanning: they are wrapped so a database problem only shows in the log.

v4 (speed + stock awareness)
    * the product catalog + trigram index live in server memory (rebuilt every CATALOG_TTL seconds, or at once
      when an alias is added) - no more unpickling 60,000 products from the cache on every scan
    * only names that share trigrams with the text are compared (inverted index), barcode = dict lookup
    * 3 database queries for the whole result (products, batches, stock) instead of ~4 per product
    * products that have stock in the selected warehouse get +STOCK_BOOST points (180ml in stock beats 90ml sold out)
    * rate limit per user (RATE_MATCH / RATE_FEEDBACK requests per minute) -> HTTP 429

v5 (local catalog + dashboard)
    * ocr_catalog  : the compact product list (id, name, barcode, aliases) for the phone. The phone ranks products
                     itself (static/ocr/ocr_match.js, identical to ocr_core.rank - tests/test_ocr_js_parity.py)
    * ocr_details  : the phone sends only the ids of its best products; the server re-scores them (core.rescore),
                     adds stock/price/batch, decides "confident", writes the log. Same JSON as ocr_match_product.
    * ocr_dashboard / ocr_alias_action : accuracy dashboard + one-click approve / reject of alias suggestions

Response of ocr_match_product:
    {"success": true, "confident": bool, "text": "...", "log_id": 12, "products": [ {...}, ... ]}

Package map (this was one 465-line file, ocr.py):
    config.py     tuning numbers and the permission list
    common.py     small helpers shared by every view (int parsing, rate limit, permission check)
    catalog.py    in-memory product index + ocr_catalog
    payload.py    batches / stock / price JSON for products
    scan.py       ocr_match_product, ocr_details (scan -> best products, writes the scan log)
    feedback.py   ocr_feedback + alias learning
    dashboard.py  ocr_dashboard + ocr_alias_action

The views are registered one by one in app/views_frontend/__init__.py (so views_frontend.ocr_* keeps working).
"""
