# Pricing upgrade plan (professional ERP pricing)

Problems being fixed: no price history, no undo, no minimum-margin policy, no approval,
two places holding the price (StockBatch.selling_price vs Product.price/discount).

| Step | What | Status |
|------|------|--------|
| 1 | Price history / audit log (who, when, old, new, cost, bulk run id) + history page + CSV + read-only admin | DONE |
| 2 | Undo: roll back a whole bulk run (by run_id) or revert one change; undo is itself logged | DONE |
| 3 | Minimum margin policy: company rule (e.g. min 5%), optional per category; enforced in single, bulk, undo and model.clean | DONE |
| 4 | Approval: users with manage_products request; a new `approve_price_changes` permission applies; optional threshold | todo |
| 5 | One source of truth: a single `effective_price()` resolver used by POS/sales; Product price/discount changes also logged and synced with batches | todo |
| 6 | Reports + hardening: margin-below-policy report, price-change report, full tests, user guide update | todo |

## Step 1 files
- app/models/inventory/price_log.py        PriceChangeLog (append-only)
- app/migrations/0035_pricechangelog.py    one new table
- app/utils/price_audit.py                 build/record helpers (pure Python + one DB write)
- app/views_frontend/inventory/price_history.py + templates/inventory/price_history.html
- app/admin/price_log.py                   read-only admin
- permission `view_price_history` (accountant + warehouse roles by default; superuser always)
- hooks in update_batch_selling_price / bulk_update_batch_selling_price (same transaction as the price)
- tests/test_price_audit_pure.py

## Step 2 files (Undo)
- app/utils/price_undo.py                          pure planner: what is safe to revert, per row
- app/views_frontend/inventory/price_history.py    price_undo view (GET preview, POST apply, atomic + row lock)
- templates/inventory/price_undo.html              preview page
- app/urls.py                                      price_undo_run / price_undo_change
- templates/inventory/price_history.html           Undo buttons (whole run + single row)
- templates/inventory/batches.html                 "Undo" toast right after a bulk apply
- tests/test_price_undo_pure.py
Safety: a row is reverted only if the batch still holds the price that row set; later changes and prices now below cost are skipped.

## Step 3 files (Minimum margin policy)
- app/utils/pricing.py                     min_price_for / effective_min_margin; check_selling_price + compute_selling_price take `min_margin`
- app/utils/margin_policy.py               MarginPolicy.load(): company % (Settings > Pricing) + per-category %
- app/models/inventory/catalog.py          Category.min_margin_percent; StockBatch.clean checks the policy ONLY when the price changes
- app/migrations/0036_category_min_margin.py   one nullable column
- app/settings_catalog.py                  new "Pricing" tab (owner) with `min_margin_percent`
- app/admin/registrations.py               CategoryAdmin shows/edits the category %
- app/views_frontend/inventory/products.py single + bulk + Stock Batches page ("min Rs." hint now = cost + margin)
- app/views_frontend/inventory/price_history.py + app/utils/price_undo.py   undo will not restore a price below today's policy
- tests/test_margin_policy_pure.py
Rule: category % wins when filled (0 = no minimum for that category); else company %; 0 = no rule.
Margin = % of cost (same as StockBatch.profit_margin_percent); the minimum price is rounded UP to the paisa.
Safety: raising the policy never blocks sales/stock saves - old prices stay until someone changes them.
