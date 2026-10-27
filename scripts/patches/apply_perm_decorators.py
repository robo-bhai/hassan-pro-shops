#!/usr/bin/env python3
"""Apply @perm_required(...) to every staff view in app/views_frontend.

    python scripts/patches/apply_perm_decorators.py            # dry run: prints the mapping table
    python scripts/patches/apply_perm_decorators.py --apply    # writes the files (idempotent)

How it decides (edit RULES below, re-run; already decorated views are left alone):
  1. a per-module rule list  (regex on the function name -> action or explicit key(s) or SKIP)
  2. otherwise the function-name verb: delete / approve / create / edit / view
  3. the module's SPEC turns the action into a permission key.
Views that only *show* data but also handle POST get ``post=<edit key>``.
Self-service views (shareholder portal, notifications, own profile ...) are SKIPPED on purpose.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'app'
SKIP = 'SKIP'


def spec(view, create=None, edit=None, delete=None, approve=None):
    edit = edit or create or view
    return {'view': view, 'create': create or edit, 'edit': edit, 'delete': delete or edit,
            'approve': approve or edit}


def one(key):
    return spec(key)


# module -> (SPEC, [(regex, action|keys|SKIP), ...])
LOOKUP_PRODUCT = ('view_products', 'view_inventory', 'use_pos', 'create_sales', 'create_purchases', 'manage_orders')
MODULES = {
    'system/dashboard': (spec('view_dashboard'), [
        (r'^profile_view$', SKIP),
        (r'^module_settings$', 'view_settings'), (r'^toggle_setting$', 'edit_settings'),
        (r'^company_settings$', 'manage_company'), (r'^dashboard_view$', 'view_dashboard')]),
    'purchase/purchases': (spec('view_purchases', 'create_purchases', 'edit_purchases', 'delete_purchases',
                                'approve_purchases'), [
        (r'^(get_purchase_products|search_products_purchase)$',
         ('view_purchases', 'create_purchases', 'edit_purchases'))]),
    'purchase/vendor_reports': (one('view_vendors'), [(r'_pay$', 'manage_payments')]),
    'purchase/vendors': (spec('view_vendors', 'create_vendors', 'edit_vendors', 'delete_vendors'), []),
    'purchase/purchase_orders': (spec(('view_purchases', 'manage_purchase_orders'), 'manage_purchase_orders'), []),
    'purchase/po_pro': (spec(('view_purchases', 'manage_purchase_orders'), 'manage_purchase_orders'), [
        (r'^purchase_order_(products|print)$', 'view')]),
    'purchase/grn': (spec(('view_purchases', 'receive_goods'), ('receive_goods', 'manage_purchase_orders'),
                          delete='delete_purchases'), [(r'barcode|pdf', 'view')]),
    'purchase/monthly_plans': (spec(('view_purchases', 'manage_purchase_orders'), 'manage_purchase_orders',
                                    approve='approve_purchases'), [
        (r'^monthly_plan_(approve|complete|cancel)$', 'approve'),
        (r'^(check_stock_for_plan|investor_requirement_api|monthly_plan_(history|report_pdf|multi_product_info))$', 'view'),
        (r'^monthly_purchase_planner$', 'view')]),
    'purchase/supply_chain': (spec(('view_purchases', 'manage_supply_chain'), 'manage_supply_chain'), []),

    'shareholder/shareholder_portal': (None, [(r'.', SKIP)]),           # shareholder self-service
    'shareholder/certificates': (spec('view_shareholders', 'manage_shareholders'), []),
    'shareholder/shareholders': (spec('view_shareholders', 'manage_shareholders'), []),
    'shareholder/share_transfers': (spec('view_shareholders', 'manage_share_transfers'), [
        (r'^share_price_create$', 'manage_shareholders'), (r'^share_(list|price_list)$', 'view')]),
    'shareholder/meetings': (spec('view_shareholders', 'manage_shareholders'), []),
    'shareholder/terms': (spec('view_shareholders', 'manage_shareholders'), [
        (r'^terms_(preview|acceptance_(list|detail|export|stats_api))$', 'view'), (r'^terms_admin$', 'view')]),
    'shareholder/support_tickets': (spec('view_shareholders', 'manage_shareholders'), [
        (r'^shareholder_support_ticket_detail$', SKIP)]),
    'shareholder/registration_requests': (spec('view_shareholders', 'manage_shareholders'), [
        (r'bulk_action$', 'edit'), (r'_(list|stats_api)$', 'view')]),
    'shareholder/dividends': (spec('view_shareholders', 'manage_dividends'), [
        (r'_(list|dashboard|report|preview_api|stats_api|profit_api)$|^eligible_shareholders_api$|_detail$', 'view'),
        (r'^(my_discounts|drip_enroll|drip_unenroll)$', SKIP),
        (r'^discount_list$', 'view')]),
    'shareholder/cash_balances': (spec('view_shareholders', 'manage_shareholder_cash'), [
        (r'^shareholder_(deposit|withdraw|transfer_balance|adjust_balance|withdraw_from_balance)$', 'edit')]),
    'shareholder/cash_requests': (spec('view_shareholders', 'manage_shareholder_cash'), [
        (r'bulk_approve$', 'approve'), (r'.', 'view')]),
    'shareholder/cash_deductions': (spec('view_shareholders', 'manage_shareholder_cash'), [
        (r'^(process_purchase_deduction|toggle_shareholder_deduction|change_deduction_type|bulk_process_deductions)$', 'edit'),
        (r'^purchase_deduction_details$', 'view')]),
    'shareholder/cash_reports': (one('view_shareholders'), []),

    'system/masters_api': (one(('manage_products', 'manage_inventory', 'manage_warehouse', 'create_purchases')), []),
    'finance/cash': (spec('view_cash', 'manage_cash'), [(r'^cash_(add|withdraw|set_opening)$', 'edit')]),
    'system/reports': (one('view_reports'), [
        (r'^export_report_excel$', ('export_reports',)),
        (r'^(profit_loss_report|profit_loss|profit_trend_report)$', ('view_profit', 'view_financials'))]),
    'pos_sales/sales': (spec('view_sales', 'create_sales', 'edit_sales', 'delete_sales', 'edit_sales'), [
        (r'^(customer_wise_report|customer_outstanding_report)$', ('view_reports', 'view_customers')),
        (r'^(add_target|target_dashboard)$', 'manage_targets'),
        (r'^get_sale_products$', ('view_sales', 'create_sales', 'use_pos', 'manage_orders')),
        (r'^get_customer_balance$', ('view_customers', 'create_sales', 'use_pos', 'manage_orders')),
        (r'^customer_ledger_pay$', 'manage_payments'), (r'^sale_receive_payment$', ('edit_sales', 'manage_payments')),
        (r'^customer_ledger$', 'view_customers'),
        (r'^customer_list$', 'view_customers'), (r'^customer_create$', 'create_customers'),
        (r'^customer_update$', 'edit_customers'),
        (r'^(challan_convert_to_sale|sale_order_convert_invoice)$', 'create_sales'),
        (r'^(sale_order|challan)_.*(list|detail|pdf)$', ('view_sales', 'manage_orders')),
        (r'^challan_delete$', 'manage_orders'),
        (r'^(sale_order_(create|update|quick_status|create_challan))$', 'manage_orders')]),
    'finance/closing': (spec(('view_accounting', 'manage_closing'), 'manage_closing'), [
        (r'^(lock|unlock)_month$', 'manage_closing')]),
    'people/hr': (spec('view_employees', 'manage_employees'), [
        (r'^attendance_(mark|save)$', 'manage_attendance'),
        (r'^(attendance_today|attendance_report|employee_attendance)$', ('view_employees', 'manage_attendance')),
        (r'^leave_list$', ('view_employees', 'manage_leaves')), (r'^leave_', 'manage_leaves'),
        (r'^(payroll_|employee_payroll|payslip_|print_salary_slip)', 'manage_payroll')]),
    'inventory/warehouses': (spec('view_warehouse', 'manage_warehouse'), []),
    'pos_sales/returns': (spec('view_returns', 'create_returns', 'create_returns', 'delete_returns',
                               'approve_returns'), [
        (r'^get_.*_history$', ('view_returns', 'create_returns'))]),
    'inventory/production': (spec('view_production', 'manage_production'), [
        (r'^transfer_order_approve$', 'manage_production'), (r'^get_product_bom_template$', 'view')]),
    'inventory/products': (spec('view_products', 'manage_products'), [
        (r'^(get_product_stock|get_product_by_barcode|get_product_by_name|get_product_by_alias|get_product_aliases|'
         r'products_list_api|search_products_ajax|get_batch_selling_price)$', LOOKUP_PRODUCT),
        (r'^(inventory_list|batch_list)$', ('view_inventory', 'view_products')),
        (r'^product_export_', 'view'), (r'^product_import_export$', 'manage_products'),
        (r'^(update_batch_selling_price|create_product_alias|delete_product_alias|api_create_product)$', 'manage_products')]),
    'system/notifications': (None, [(r'.', SKIP)]),
    'pos_sales/installments': (spec('view_installments', 'manage_installments'), [
        (r'^(get_installment_plan|get_installment_details|get_available_plans)$',
         ('view_installments', 'manage_installments', 'create_sales', 'use_pos')),
        (r'^create_installment_sale$', ('manage_installments', 'create_sales')),
        (r'^whatsapp_', 'edit'), (r'^pay_emi$', 'edit')]),
    'shareholder/cash_balances#': (None, []),
    'finance/loans': (spec('view_loans', 'manage_loans'), [(r'^loan_(pay|return_pay|given_pay)$', 'edit')]),
    'pos_sales/services': (spec('view_services', 'manage_services'), [
        (r'^get_|^check_', ('view_services', 'manage_services')), (r'_report$', 'view'),
        (r'^service_inventory_(use|adjust)$', 'edit')]),
    'finance/expenses': (spec('view_expenses', 'manage_expenses', 'manage_expenses', 'manage_expenses',
                              'manage_payments'), [(r'^expense_pay$', 'approve')]),
    'finance/budgets': (spec(('view_financials', 'manage_budget'), 'manage_budget'), []),
    'finance/budget_goals': (spec(('view_financials', 'manage_budget'), 'manage_budget'), []),
    'finance/expense_masters': (spec('view_expenses', 'manage_expenses'), []),
    'finance/self_expenses': (one('view_financials'), []),
    'system/audit': (spec('view_audit_log', 'manage_system'), [
        (r'^audit_(plan_(start|complete)|finding_resolve)$', 'edit')]),
    'finance/accounting': (spec('view_accounting', 'manage_accounting'), [
        (r'^(generate_trial_balance|export_accounts_report)$', 'view'),
        (r'^journal_entry_(post|reverse)$|^financial_period_close$', 'approve')]),
    'ai/ai_insights': (one('use_ai'), [(r'^(chatbot_api|announce_alerts_api|voice_announcement_settings|risk_assessment_api)$', SKIP)]),
    'ai/operations': (spec(('use_ai', 'manage_ai_ops'), 'manage_ai_ops'), [
        (r'^(my_tasks|task_complete|checklist_today)$', SKIP)]),
    'ai/ai_purchasing': (spec('use_ai', 'manage_ai_ops', approve='approve_purchases'), [
        (r'^ai_(accept|reject)_suggestion$', 'approve')]),
    'ai/cash_ai': (spec(('use_ai', 'view_cash'), 'manage_ai_ops'), [
        (r'^business_ratios_dashboard$', ('use_ai', 'view_financials')),
        (r'^emergency_fund_settings$', 'manage_ai_ops'),
        (r'^cash_strategy_complete$|^strategy_allocation_(activate|preview)$', 'edit')]),
    'ai/shareholder_ai': (spec(('use_ai', 'view_shareholders'), 'manage_ai_ops'), []),
    'ai/board_cso': (one('view_board_room'), []),
    'system/chat': (one('manage_system'), []),
    'inventory/store_issue': (spec(('view_warehouse', 'manage_store_issue'), 'manage_store_issue'), [
        (r'^store_dashboard$', 'view_warehouse'), (r'^store_(access|profile_list|profile_form)$', 'manage_warehouse')]),
    'inventory/store_transfer': (spec(('view_warehouse', 'manage_transfers'), 'manage_transfers'), []),
    'inventory/store_ops': (spec(('view_warehouse', 'manage_store_ops'), 'manage_store_ops'), [
        (r'^store_settings$', 'manage_warehouse')]),
    'finance/profit_analysis': (one('view_profit'), []),
    'finance/subledger': (one('view_accounting'), []),
    'pos_sales/pos': (one('use_pos'), []),
    'pos_sales/shift': (spec(('manage_shifts', 'view_reports'), 'manage_shifts'), [
        (r'^shift_(status|open|movement|close)$', 'manage_shifts')]),
    'pos_sales/shop_tools': (spec(('use_pos', 'view_sales'), 'use_pos'), [
        (r'^stock_register$', ('view_inventory', 'view_products')), (r'^pos_void$', ('delete_sales', 'use_pos'))]),
    'system/settings_center': (spec('view_settings', 'edit_settings'), []),
    # outside views_frontend (paths are relative to app/):
    '../backoffice/views_bi': (one('view_analytics'), []),
    '../backoffice/views_document': (spec('view_documents', 'manage_documents'), [
        (r'^document_(download|preview)$', 'view')]),
    '../backoffice/views_loan': (spec('view_loans', 'manage_loans'), []),
    '../backoffice/views_subscription': (one('manage_system'), [(r'^subscription_expired$', SKIP)]),
    '../backoffice/views_testing': (one('manage_system'), []),
    # own guards already (superuser / admin only): people/users, system/backup, system/translations, system/language
}
MODULES.pop('shareholder/cash_balances#')
# keys are relative to app/views_frontend/ unless they start with '../' (= relative to app/)
MODULES = {(k[3:] if k.startswith('../') else 'views_frontend/' + k): v for k, v in MODULES.items()}

ACTION_WORDS = [
    ('delete', {'delete', 'remove'}),
    ('approve', {'approve', 'reject', 'complete', 'activate', 'cancel', 'lock', 'unlock', 'reverse', 'post',
                 'close', 'resolve', 'accept', 'ignore', 'verify', 'distribute'}),
    ('create', {'create', 'add', 'new', 'import', 'duplicate', 'submit', 'enroll', 'upload'}),
    ('edit', {'edit', 'update', 'set', 'toggle', 'change', 'mark', 'pay', 'receive', 'convert', 'adjust',
              'start', 'use', 'run', 'generate', 'process', 'reset', 'apply', 'feedback', 'status', 'quick',
              'save', 'bulk', 'withdraw', 'deposit', 'execute', 'deliver', 'invoice', 'send', 'sync', 'refresh',
              'renew', 'suspend', 'reactivate', 'disburse', 'make', 'generate'}),
]


def classify(name):
    tokens = set(name.split('_'))
    for action, words in ACTION_WORDS:
        if tokens & words:
            return action
    return 'view'


def is_login_required(dec):
    return ((isinstance(dec, ast.Name) and dec.id == 'login_required') or
            (isinstance(dec, ast.Attribute) and dec.attr == 'login_required'))


def has_perm_required(dec):
    t = dec.func if isinstance(dec, ast.Call) else dec
    return (isinstance(t, ast.Name) and t.id == 'perm_required')


def fmt_keys(keys):
    keys = (keys,) if isinstance(keys, str) else tuple(keys)
    return ', '.join(repr(k) for k in keys)


def decide(modname, fname, body_src):
    sp, rules = MODULES[modname]
    action = None
    for rx, target in rules:
        if re.search(rx, fname):
            if target == SKIP:
                return None
            if isinstance(target, str) and target in ('view', 'create', 'edit', 'delete', 'approve'):
                action = target
                break
            return target, None          # explicit keys
    if re.search(r"hasattr\(\s*request\.user,\s*['\"]shareholder_profile['\"]|request\.user\.shareholder_profile", body_src):
        return None                      # shareholder self-service / mixed view: has its own guard
    action = action or classify(fname)
    keys = sp[action]
    post = None
    if action == 'view' and re.search(r"request\.method\s*==\s*['\"]POST['\"]|request\.POST", body_src):
        post = sp['edit']
        if post == keys:
            post = None
    return keys, post


def process(path, modname, apply):
    src = path.read_text(encoding='utf-8')
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    edits, report = [], []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decs = node.decorator_list
        lr = [d for d in decs if is_login_required(d)]
        if not lr or any(has_perm_required(d) for d in decs):
            continue
        body_src = ''.join(lines[node.lineno - 1:node.end_lineno])
        res = decide(modname, node.name, body_src)
        if res is None:
            report.append((node.name, 'SKIP'))
            continue
        keys, post = res
        deco = '@perm_required(%s%s)' % (fmt_keys(keys), (', post=%s' % (repr(post) if isinstance(post, str) else repr(tuple(post)))) if post else '')
        edits.append((lr[0].end_lineno, deco))
        report.append((node.name, deco))
    if apply and edits:
        for lineno, deco in sorted(edits, reverse=True):
            lines.insert(lineno, deco + '\n')
        text = ''.join(lines)
        import_line = 'from %ssecurity.permissions import perm_required\n' % ('.' * len(Path(modname).parts))
        if import_line not in text:
            t2 = ast.parse(text)
            at = 0
            if t2.body and isinstance(t2.body[0], ast.Expr) and isinstance(getattr(t2.body[0], 'value', None), ast.Constant) \
                    and isinstance(t2.body[0].value.value, str):
                at = t2.body[0].end_lineno
            ls = text.splitlines(keepends=True)
            ls.insert(at, import_line)
            text = ''.join(ls)
        path.write_text(text, encoding='utf-8')
    return report


def main():
    apply = '--apply' in sys.argv
    total = 0
    for modname in MODULES:
        path = ROOT / (modname + '.py')
        rep = process(path, modname, apply)
        print('== %s' % modname)
        for name, deco in rep:
            print('   %-42s %s' % (name, deco))
            total += deco != 'SKIP'
    print('\n%s %d views' % ('Decorated' if apply else 'Would decorate', total))


if __name__ == '__main__':
    main()
