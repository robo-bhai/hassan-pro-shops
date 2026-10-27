# app/ structure

## Logic
- ai/        AI engines + chatbots
- ledger/    posting (double-entry), GL signals, subledger, posting tests
- store/     warehouse logic: access, receive, issue (FIFO), transfer, accounting, exports, barcode
- security/  2FA, security utils/views, admin OTP, security signals, permission matrix (permission_catalog.py, permissions.py -> @perm_required, see PERMISSIONS.md)
- i18n/      languages and translation service

## Views
- views_frontend/   (urls.py: views_frontend.some_view  -> pehle jaisa kaam karta hai)
    pos_sales/ sales, pos, shift, shop_tools, returns, installments, services
    purchase/  purchases, vendors, vendor_reports, purchase_orders, grn, monthly_plans, po_pro, supply_chain
    finance/   accounting, cash, expenses, self_expenses, budgets, budget_goals, expense_masters,
               closing, subledger, profit_analysis, loans
    shareholder/ shareholders, certificates, share_transfers, meetings, terms, support_tickets,
               registration_requests, cash_balances, cash_requests, cash_deductions, cash_reports,
               shareholder_portal, dividends
    inventory/ products, warehouses, store_issue, store_transfer, store_ops, production
    people/    hr, users
    ai/        ai_insights, operations, ai_purchasing, cash_ai, shareholder_ai, board_cso
    system/    dashboard, dashboard_extras, reports, notifications, chat, backup, audit,
               language, translations, settings_center, masters_api
- customer/    customer auth, customer portal, order tracking, delivery
- backoffice/  bi, document, loan, subscription, testing
- views.py     home + 404/500 handlers (same jagah)

## Models  (app.models.X ab bhi kaam karta hai, models/__init__.py sab re-export karta hai)
- models/finance/    accounting, budgeting, gl_posting
- models/trade/      customers, sales, sale_orders, sale_returns, installments, targets,
                     vendors, purchases, purchase_orders, purchase_returns, monthly_plans,
                     customer_portal, delivery, pos_shift, supply_chain, services
- models/inventory/  catalog, store_issue, store_ops, store_transfer, production
- models/people/     hr, shareholders, shares, dividends, drip, cash, loans, discounts
- models/ai_bi/      insights, operations, purchase_ai, cash_ai, shareholder_ai, board, cso_tech, bi
- models/system/     core, security, documents, translation, constants, audit_qa

## Naye import
from app.ledger import posting_core
from app.store import store_access
from app.models import Product              # pehle jaisa
Naya view/model add karne par: file sahi group mein rakho aur __init__.py ki _MODULES list mein
"group.file" likho (models/ aur views_frontend/ dono mein).
Models mein agar ek class dusre chunk ki class ko seedha use kare (ForeignKey(Class), base class), to
wahan "from .other_chunk import Class" likhna hoga (jaise people/dividends.py mein Shareholder).
