from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from . import views_frontend
from app import views_security
from app import views_bi  
from app import views_testing  
from app import views_document
from app import views_frontend

urlpatterns = [
    # ============================================
    # AUTHENTICATION
    # ============================================
    path('login/', auth_views.LoginView.as_view(
        template_name='auth/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    path('settings/toggle/<str:setting_key>/', views_frontend.toggle_setting, name='toggle_setting'),
    path('production/stock/consume/<int:pk>/', views_frontend.production_consume_stock, name='production_consume_stock'),
    path('settings/modules/', views_frontend.module_settings, name='module_settings'),
    path('cash/', views_frontend.cash_dashboard, name='cash_dashboard'),
    path('cash/add/', views_frontend.cash_add, name='cash_add'),
    path('cash/withdraw/', views_frontend.cash_withdraw, name='cash_withdraw'),
    path('cash/transactions/', views_frontend.cash_transactions, name='cash_transactions'),
    path('cash/set-opening/', views_frontend.cash_set_opening, name='cash_set_opening'),
    path('cash/report/', views_frontend.cash_report, name='cash_report'),
    path('ajax/cash-balance/', views_frontend.get_cash_balance, name='get_cash_balance'),
 
    # Salary Slip Print (HTML Version)
    path('hr/salary-slip/<int:pk>/', views_frontend.print_salary_slip_html, name='print_salary_slip'),
    
    path('prices/create/', views_frontend.share_price_create, name='share_price_create'),
    
    # Custom logout view
    path('logout/', views_frontend.custom_logout, name='logout'),
    path('shareholder/deposit/', views_frontend.shareholder_portal_deposit, name='shareholder_portal_deposit'),
    path('shareholder/withdraw/', views_frontend.shareholder_portal_withdraw, name='shareholder_portal_withdraw'),
    path('shareholder/buy-shares/', views_frontend.shareholder_portal_buy_shares, name='shareholder_portal_buy_shares'),
    path('shareholder/sell-shares/', views_frontend.shareholder_portal_sell_shares, name='shareholder_portal_sell_shares'),
    path('shareholder/get-share-price/', views_frontend.shareholder_get_share_price, name='shareholder_get_share_price'),
    path('shareholder/get-balance/', views_frontend.shareholder_get_balance, name='shareholder_get_balance'),
    
    
    # ============================================
    # SHAREHOLDER CASH BALANCE URLS
    # ============================================
    path('shareholders/balance/dashboard/', views_frontend.shareholder_balance_dashboard, name='shareholder_balance_dashboard'),
    path('shareholders/balance/<int:pk>/', views_frontend.shareholder_balance_detail, name='shareholder_balance_detail'),
    path('shareholders/balance/<int:pk>/deposit/', views_frontend.shareholder_deposit, name='shareholder_deposit'),
    path('shareholders/balance/<int:pk>/withdraw/', views_frontend.shareholder_withdraw, name='shareholder_withdraw'),
    path('shareholders/balance/<int:pk>/transfer/', views_frontend.shareholder_transfer_balance, name='shareholder_transfer_balance'),
    path('shareholders/balance/<int:pk>/adjust/', views_frontend.shareholder_adjust_balance, name='shareholder_adjust_balance'),
    path('shareholders/balance/<int:pk>/export/', views_frontend.shareholder_transactions_export, name='shareholder_transactions_export'),
    path('shareholders/balance/<int:pk>/pdf/', views_frontend.shareholder_balance_report_pdf, name='shareholder_balance_report_pdf'),
    path('api/shareholder-balance/', views_frontend.shareholder_balance_api, name='shareholder_balance_api'),
    
    # ============================================
    # SHAREHOLDER PORTAL URLS (NEW)
    # ============================================
    path('shareholder/login/', views_frontend.shareholder_login, name='shareholder_login'),
    path('shareholder/logout/', views_frontend.shareholder_logout, name='shareholder_logout'),
    path('shareholder/dashboard/', views_frontend.shareholder_portal_dashboard, name='shareholder_portal_dashboard'),
    path('shareholder/profile/', views_frontend.shareholder_portal_profile, name='shareholder_portal_profile'),
    path('shareholder/certificates/', views_frontend.shareholder_portal_certificates, name='shareholder_portal_certificates'),
    path('shareholder/transactions/', views_frontend.shareholder_portal_transactions, name='shareholder_portal_transactions'),
    path('shareholder/certificate/<int:pk>/download/', views_frontend.shareholder_portal_download_certificate, name='shareholder_portal_download_certificate'),
    
    # ============================================
    # DASHBOARD
    # ============================================
    path('', views_frontend.dashboard_view, name='dashboard'),
    
    # ============================================
    # TARGETS
    # ============================================
    path('targets/', views_frontend.target_dashboard, name='target_dashboard'),
    path('targets/add/', views_frontend.add_target, name='add_target'),
    
    # ============================================
    # SYSTEM STATUS APIS
    # ============================================
    path('api/system/db-status/', views_frontend.system_db_status, name='system_db_status'),
    path('api/system/cache-status/', views_frontend.system_cache_status, name='system_cache_status'),
    path('api/system/backup-status/', views_frontend.system_backup_status, name='system_backup_status'),
    path('api/system/queue-status/', views_frontend.system_queue_status, name='system_queue_status'),
    path('api/system/disk-status/', views_frontend.system_disk_status, name='system_disk_status'),
    path('api/system/memory-status/', views_frontend.system_memory_status, name='system_memory_status'),
    path('api/auth/health/', views_frontend.system_api_health, name='auth_health'),
    path('api/sales/health/', views_frontend.system_api_health, name='sales_health'),
    
    # ============================================
    # PRODUCTS API
    # ============================================
    path('api/products-list/', views_frontend.products_list_api, name='products_list_api'),
    
    # ============================================
    # DAILY CLOSING
    # ============================================
    path('daily-closing/', views_frontend.daily_closing_index, name='daily_closing'),
    path('daily-closing/create/', views_frontend.daily_closing_create, name='daily_closing_create'),
    path('daily-closing/<int:pk>/', views_frontend.daily_closing_detail, name='daily_closing_detail'),
    path('daily-closing/<int:pk>/pdf/', views_frontend.daily_closing_pdf, name='daily_closing_pdf'),
    path('daily-closing/list/', views_frontend.daily_closing_list, name='daily_closing_list'),
    path('ajax/daily-closing-data/', views_frontend.daily_closing_data, name='daily_closing_data'),
    
    # ============================================
    # AJAX - PRODUCT ALIAS (Voice Search)
    # ============================================
    path('ajax/get-product-by-alias/', views_frontend.get_product_by_alias, name='get-product-by-alias'),
    path('ajax/create-product-alias/', views_frontend.create_product_alias, name='create-product-alias'),
    path('ajax/get-product-aliases/', views_frontend.get_product_aliases, name='get-product-aliases'),
    path('ajax/delete-product-alias/', views_frontend.delete_product_alias, name='delete-product-alias'),
    
    # ============================================
    # AJAX - BATCH SELLING PRICE
    # ============================================
    path('ajax/get-batch-selling-price/', views_frontend.get_batch_selling_price, name='get_batch_selling_price'),
    
    # ============================================
    # INSTALLMENT PLAN URLs
    # ============================================
    path('ajax/get-installment-plan/', views_frontend.get_installment_plan, name='get_installment_plan'),
    path('ajax/create-installment-sale/', views_frontend.create_installment_sale, name='create_installment_sale'),
    path('ajax/pay-emi/', views_frontend.pay_emi, name='pay_emi'),
    path('ajax/get-installment-details/', views_frontend.get_installment_details, name='get_installment_details'),
    path('ajax/get-available-plans/', views_frontend.get_available_plans, name='get_available_plans'),
    
    path('installments/', views_frontend.installment_list, name='installment_list'),
    path('installments/<int:pk>/', views_frontend.installment_detail, name='installment_detail'),
    path('installments/<int:pk>/pdf/', views_frontend.installment_pdf, name='installment_pdf'),
    path('installment/create/', views_frontend.installment_create, name='installment_create'),
    path('installment/edit/<int:pk>/', views_frontend.installment_plan_edit, name='installment_plan_edit'),
    path('installment/delete/<int:pk>/', views_frontend.installment_plan_delete, name='installment_plan_delete'),
    path('plans/', views_frontend.installment_plan_list, name='installment_plan_list'),
    
    path('certificate/<int:pk>/', views_frontend.share_certificate_view, name='share_certificate'),
    path('certificate/<int:pk>/download/', views_frontend.share_certificate_download, name='share_certificate_download'),
    path('certificates/bulk/', views_frontend.share_certificate_bulk, name='share_certificate_bulk'),
    path('certificates/list/', views_frontend.share_certificate_list, name='share_certificate_list'),
    
    # ============================================
    # WHATSAPP REMINDERS
    # ============================================
    path('whatsapp/reminders/', views_frontend.whatsapp_reminders_view, name='whatsapp_reminders'),
    path('whatsapp/emi-reminder/<int:installment_id>/', views_frontend.whatsapp_emi_reminder, name='whatsapp_emi_reminder'),
    path('whatsapp/installment-summary/<int:installment_id>/', views_frontend.whatsapp_installment_summary, name='whatsapp_installment_summary'),
    
    # ============================================
    # NOTIFICATION URLs
    # ============================================
    path('api/notifications/', views_frontend.get_notifications_api, name='api_notifications'),
    path('api/notifications/<int:pk>/mark-read/', views_frontend.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/mark-all-read/', views_frontend.mark_all_notifications_read, name='mark_all_read'),
    path('api/notifications/mark-category-read/', views_frontend.mark_category_read, name='mark_category_read'),
    path('api/notifications/unread-count/', views_frontend.get_unread_count, name='unread_count'),
    path('api/notifications/categories/', views_frontend.get_notification_categories, name='notification_categories'),
    path('notifications/', views_frontend.notification_list_page, name='notification_list'),
    path('notifications/<int:pk>/delete/', views_frontend.delete_notification, name='delete_notification'),
    path('notifications/delete-all/', views_frontend.delete_all_notifications, name='delete_all_notifications'),
    
    # ============================================
    # PURCHASE ORDERS
    # ============================================
    path('orders/purchase/', views_frontend.purchase_order_list, name='purchase_order_list'),
    path('orders/purchase/create/', views_frontend.purchase_order_create, name='purchase_order_create'),
    path('orders/purchase/<int:pk>/', views_frontend.purchase_order_detail, name='purchase_order_detail'),
    path('orders/purchase/<int:pk>/status/<str:status>/', views_frontend.purchase_order_quick_status, name='purchase_order_quick_status'),
    path('orders/purchase/<int:pk>/create-grn/', views_frontend.purchase_order_create_grn, name='purchase_order_create_grn'),
    
    # ============================================
    # PURCHASES
    # ============================================
    path('purchases/', views_frontend.purchase_list, name='purchase_list'),
    path('purchases/create/', views_frontend.purchase_create, name='purchase_create'),
    path('purchases/<int:pk>/pdf/', views_frontend.purchase_pdf, name='purchase_pdf'),
    
    # ============================================
    # SALES
    # ============================================
    path('sales/', views_frontend.sale_list, name='sale_list'),
    path('sales/create/', views_frontend.sale_create, name='sale_create'),
    path('sales/<int:pk>/', views_frontend.sale_detail, name='sale_detail'),
    
    # ============================================
    # SALE ORDERS
    # ============================================
    path('orders/sale/', views_frontend.sale_order_list, name='sale_order_list'),
    path('orders/sale/create/', views_frontend.sale_order_create, name='sale_order_create'),
    path('orders/sale/<int:pk>/', views_frontend.sale_order_detail, name='sale_order_detail'),
    path('orders/sale/<int:pk>/update/', views_frontend.sale_order_update, name='sale_order_update'),
    path('orders/sale/<int:pk>/status/<str:status>/', views_frontend.sale_order_quick_status, name='sale_order_quick_status'),
    path('orders/sale/<int:pk>/create-challan/', views_frontend.sale_order_create_challan, name='sale_order_create_challan'),
    path('orders/sale/<int:pk>/convert-invoice/', views_frontend.sale_order_convert_invoice, name='sale_order_convert_invoice'),
    
    # ============================================
    # CHALLANS & GRN
    # ============================================
    path('challans/', views_frontend.challan_list, name='challan_list'),
    path('grn/', views_frontend.grn_list, name='grn_list'),
    
    # ============================================
    # CUSTOMERS
    # ============================================
    path('customers/', views_frontend.customer_list, name='customer_list'),
    path('customers/create/', views_frontend.customer_create, name='customer_create'),
    path('customers/<int:pk>/update/', views_frontend.customer_update, name='customer_update'),
    path('customers/<int:pk>/ledger/', views_frontend.customer_ledger, name='customer_ledger'),
    
    # ============================================
    # VENDORS
    # ============================================
    path('vendors/', views_frontend.vendor_list, name='vendor_list'),
    path('vendors/create/', views_frontend.vendor_create, name='vendor_create'),
    path('vendors/<int:pk>/update/', views_frontend.vendor_update, name='vendor_update'),
    path('vendors/<int:pk>/ledger/', views_frontend.vendor_ledger, name='vendor_ledger'),
    
    # ============================================
    # WAREHOUSES
    # ============================================
    path('warehouses/', views_frontend.warehouse_list, name='warehouse_list'),
    path('warehouses/create/', views_frontend.warehouse_create, name='warehouse_create'),
    path('warehouses/<int:pk>/update/', views_frontend.warehouse_update, name='warehouse_update'),
    path('warehouses/<int:pk>/inventory/', views_frontend.warehouse_inventory, name='warehouse_inventory'),
    
    # ============================================
    # PRODUCTS
    # ============================================
    path('products/', views_frontend.product_list, name='product_list'),
    path('products/create/', views_frontend.product_create, name='product_create'),
    path('products/<int:pk>/update/', views_frontend.product_update, name='product_update'),
    
    # ============================================
    # INVENTORY
    # ============================================
    path('inventory/', views_frontend.inventory_list, name='inventory_list'),
    path('batches/', views_frontend.batch_list, name='batch_list'),
    path('ajax/update-batch-selling-price/', views_frontend.update_batch_selling_price, name='update_batch_sp'),
    
    # ============================================
    # RETURNS (Purchase & Sale)
    # ============================================
    path('returns/purchase/', views_frontend.purchase_return_list, name='purchase_return_list'),
    path('returns/purchase/create/', views_frontend.purchase_return_create, name='purchase_return_create'),
    path('returns/purchase/<int:pk>/', views_frontend.purchase_return_detail, name='purchase_return_detail'),
    
    path('returns/sale/', views_frontend.sale_return_list, name='sale_return_list'),
    path('returns/sale/create/', views_frontend.sale_return_create, name='sale_return_create'),
    path('returns/sale/<int:pk>/', views_frontend.sale_return_detail, name='sale_return_detail'),
    path('returns/sale/<int:pk>/delete/', views_frontend.sale_return_delete, name='sale_return_delete'),
    path('ajax/get-sale-return-history/', views_frontend.get_sale_return_history, name='get_sale_return_history'),
        
    path('ajax/get-purchase-products/', views_frontend.get_purchase_products, name='get_purchase_products'),
    path('ajax/get-sale-products/', views_frontend.get_sale_products, name='get_sale_products'),
    
    # ============================================
    # SETTINGS
    # ============================================
    path('settings/', views_frontend.company_settings, name='company_settings'),
    
    # ============================================
    # USER MANAGEMENT (Roles)
    # ============================================
    path('users/', views_frontend.user_list, name='user_list'),
    path('users/create/', views_frontend.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views_frontend.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views_frontend.user_delete, name='user_delete'),
    path('users/<int:pk>/toggle-status/', views_frontend.user_toggle_status, name='user_toggle_status'),
    path('users/<int:pk>/reset-password/', views_frontend.user_reset_password, name='user_reset_password'),
    
    # ============================================
    # HR & STAFF MANAGEMENT
    # ============================================
    # Employees
    path('hr/employees/', views_frontend.employee_list, name='employee_list'),
    path('hr/employees/create/', views_frontend.employee_create, name='employee_create'),
    path('hr/employees/<int:pk>/', views_frontend.employee_detail, name='employee_detail'),
    path('hr/employees/<int:pk>/edit/', views_frontend.employee_edit, name='employee_edit'),
    path('hr/employees/<int:pk>/delete/', views_frontend.employee_delete, name='employee_delete'),
    
    # Attendance
    path('hr/attendance/mark/', views_frontend.attendance_mark, name='attendance_mark'),
    path('hr/attendance/today/', views_frontend.attendance_today, name='attendance_today'),
    path('hr/attendance/report/', views_frontend.attendance_report, name='attendance_report'),
    path('hr/attendance/employee/<int:pk>/', views_frontend.employee_attendance, name='employee_attendance'),
    path('ajax/attendance/save/', views_frontend.attendance_save, name='attendance_save'),
    
    # Leaves
    path('hr/leaves/', views_frontend.leave_list, name='leave_list'),
    path('hr/leaves/request/', views_frontend.leave_request, name='leave_request'),
    path('hr/leaves/request/<int:employee_id>/', views_frontend.leave_request, name='leave_request_for_employee'),
    path('hr/leaves/<int:pk>/approve/', views_frontend.leave_approve, name='leave_approve'),
    path('hr/leaves/<int:pk>/reject/', views_frontend.leave_reject, name='leave_reject'),
    
    # Payroll
    path('hr/payroll/', views_frontend.payroll_list, name='payroll_list'),
    path('hr/payroll/employee/<int:pk>/', views_frontend.employee_payroll, name='employee_payroll'),
    path('hr/payroll/add/<int:pk>/', views_frontend.payroll_add, name='payroll_add'),
    path('hr/payroll/<int:pk>/payslip/', views_frontend.payslip_generate, name='payslip_generate'),
    
    # ============================================
    # PRODUCTION MODULE
    # ============================================
    path('production/orders/', views_frontend.production_order_list, name='production_order_list'),
    path('production/orders/create/', views_frontend.production_order_create, name='production_order_create'),
    path('production/orders/<int:pk>/', views_frontend.production_order_detail, name='production_order_detail'),
    path('production/orders/<int:pk>/edit/', views_frontend.production_order_edit, name='production_order_edit'),
    path('production/orders/<int:pk>/delete/', views_frontend.production_order_delete, name='production_order_delete'),
    path('production/orders/<int:pk>/start/', views_frontend.production_order_start, name='production_order_start'),
    path('production/orders/<int:pk>/complete/', views_frontend.production_order_complete, name='production_order_complete'),
    
    path('production/bom/<int:pk>/add/', views_frontend.production_bom_add, name='production_bom_add'),
    path('production/bom/<int:pk>/edit/', views_frontend.production_bom_edit, name='production_bom_edit'),
    path('production/bom/<int:pk>/delete/', views_frontend.production_bom_delete, name='production_bom_delete'),
    
    path('production/operations/<int:pk>/add/', views_frontend.production_operation_add, name='production_operation_add'),
    path('production/operations/<int:pk>/start/', views_frontend.production_operation_start, name='production_operation_start'),
    path('production/operations/<int:pk>/complete/', views_frontend.production_operation_complete, name='production_operation_complete'),
    
    path('production/stock/consume/<int:pk>/', views_frontend.production_consume_stock, name='production_consume_stock'),
    path('production/stock/produce/<int:pk>/', views_frontend.production_produce_stock, name='production_produce_stock'),
    
    path('production/transfers/', views_frontend.transfer_order_list, name='transfer_order_list'),
    path('production/transfers/create/', views_frontend.transfer_order_create, name='transfer_order_create'),
    path('production/transfers/<int:pk>/', views_frontend.transfer_order_detail, name='transfer_order_detail'),
    path('production/transfers/<int:pk>/approve/', views_frontend.transfer_order_approve, name='transfer_order_approve'),
    path('production/transfers/<int:pk>/deliver/', views_frontend.transfer_order_deliver, name='transfer_order_deliver'),
    
    path('production/reports/', views_frontend.production_report, name='production_report'),
    path('production/reports/<int:pk>/pdf/', views_frontend.production_report_pdf, name='production_report_pdf'),
    
    path('ajax/get-product-stock/', views_frontend.get_product_stock, name='get_product_stock'),
    path('ajax/get-product-bom/', views_frontend.get_product_bom_template, name='get_product_bom_template'),
    
    # ============================================
    # AJAX ENDPOINTS (General)
    # ============================================
    path('ajax/get-product-barcode/', views_frontend.get_product_by_barcode, name='get_product_barcode'),
    path('ajax/get-customer-balance/', views_frontend.get_customer_balance, name='get_customer_balance'),
    
    # ============================================
    # DATABASE BACKUP (Cloud Setup)
    # ============================================
    path('database-backup/', views_frontend.database_backup_view, name='database_backup'),
    
    # ============================================
    # COMPLETE REPORTS SYSTEM (34 REPORTS)
    # ============================================
    # Section 1: Dashboard & Health Reports
    path('reports/dashboard/', views_frontend.reports_dashboard, name='reports_dashboard'),
    path('reports/business-health/', views_frontend.business_health, name='business_health'),
    path('reports/profit-loss/', views_frontend.profit_loss_report, name='profit_loss_report'),
    path('reports/cash-flow/', views_frontend.cash_flow_report, name='cash_flow_report'),
    
    # Section 2: Sales Reports
    path('reports/sales-summary/', views_frontend.sales_summary_report, name='sales_summary_report'),
    path('reports/sales-forecast/', views_frontend.sales_forecast_report, name='sales_forecast_report'),
    path('reports/profit-trend/', views_frontend.profit_trend_report, name='profit_trend_report'),
    path('reports/top-products/', views_frontend.top_products_report, name='top_products_report'),
    path('reports/sales-by-hour/', views_frontend.sales_by_hour_report, name='sales_by_hour_report'),
    path('reports/sales-by-day/', views_frontend.sales_by_day_report, name='sales_by_day_report'),
    path('reports/sales-by-week/', views_frontend.sales_by_week_report, name='sales_by_week_report'),
    
    # Section 3: Customer Reports
    path('reports/customer-wise/', views_frontend.customer_wise_report, name='customer_wise_report'),
    path('reports/customer-outstanding/', views_frontend.customer_outstanding_report, name='customer_outstanding_report'),
    path('reports/accounts-receivable-aging/', views_frontend.accounts_receivable_aging, name='accounts_receivable_aging'),
    
    # Section 4: Inventory Reports
    path('reports/inventory-status/', views_frontend.inventory_status_report, name='inventory_status_report'),
    path('reports/low-stock/', views_frontend.low_stock_report, name='low_stock_report'),
    path('reports/inventory-aging/', views_frontend.inventory_aging_report, name='inventory_aging_report'),
    path('reports/stock-aging/', views_frontend.stock_aging_report, name='stock_aging_report'),
    path('reports/best-selling-categories/', views_frontend.best_selling_categories_report, name='best_selling_categories_report'),
    
    # Section 5: Comparative Reports
    path('reports/yearly-comparison/', views_frontend.yearly_comparison_report, name='yearly_comparison_report'),
    path('reports/monthly-comparison/', views_frontend.monthly_comparison_report, name='monthly_comparison_report'),
    path('reports/best-selling-brands/', views_frontend.best_selling_brands_report, name='best_selling_brands_report'),
    path('reports/monthly-closing/', views_frontend.monthly_closing_report, name='monthly_closing_report'),
    
    # Section 6: Performance Reports
    path('reports/employee-performance/', views_frontend.employee_performance_report, name='employee_performance_report'),
    path('reports/salesman-performance/', views_frontend.salesman_performance_report, name='salesman_performance_report'),
    path('reports/warehouse-performance/', views_frontend.warehouse_performance_report, name='warehouse_performance_report'),
    
    # Section 7: Tax & Return Reports
    path('reports/sales-tax-summary/', views_frontend.sales_tax_summary, name='sales_tax_summary'),
    path('reports/purchase-tax-summary/', views_frontend.purchase_tax_summary, name='purchase_tax_summary'),
    path('reports/sales-return-analysis/', views_frontend.sales_return_analysis, name='sales_return_analysis'),
    path('reports/purchase-return-analysis/', views_frontend.purchase_return_analysis, name='purchase_return_analysis'),
    path('reports/accounts-payable-aging/', views_frontend.accounts_payable_aging, name='accounts_payable_aging'),
    path('reports/vendor-wise/', views_frontend.vendor_wise_report, name='vendor_wise_report'),
    
    # Section 8: Summary Reports
    path('reports/daily-summary/', views_frontend.daily_summary_report, name='daily_summary_report'),
    path('reports/weekly-summary/', views_frontend.weekly_summary_report, name='weekly_summary_report'),
    path('reports/monthly-summary/', views_frontend.monthly_summary_report, name='monthly_summary_report'),
    path('reports/quarterly-summary/', views_frontend.quarterly_summary_report, name='quarterly_summary_report'),
    path('reports/yearly-summary/', views_frontend.yearly_summary_report, name='yearly_summary_report'),
    
    # Section 9: Export
    path('reports/export/<str:report_name>/', views_frontend.export_report_excel, name='export_report_excel'),
    
    # ============================================
    # BACKWARD COMPATIBILITY (Old Report URLs for Dashboard)
    # ============================================
    path('reports/sales/', views_frontend.sales_summary_report, name='sales_report'),
    path('reports/profit-loss/', views_frontend.profit_loss_report, name='profit_loss'),
    path('reports/monthly-closing/', views_frontend.monthly_closing_report, name='monthly_closing'),
    path('reports/range/', views_frontend.range_report_view, name='range_report'),

    # ============================================
    # INLINE ADD APIS (For Product Form)
    # ============================================
    path('api/create-category/', views_frontend.api_create_category, name='api_create_category'),
    path('api/create-brand/', views_frontend.api_create_brand, name='api_create_brand'),
    path('api/create-unit/', views_frontend.api_create_unit, name='api_create_unit'),
    path('api/create-location/', views_frontend.api_create_location, name='api_create_location'),
    path('api/create-type/', views_frontend.api_create_type, name='api_create_type'),
    
    # ============================================
    # SHAREHOLDER URLS
    # ============================================
    path('shareholders/', views_frontend.shareholder_dashboard, name='shareholder_dashboard'),
    path('shareholders/list/', views_frontend.shareholder_list, name='shareholder_list'),
    path('shareholders/create/', views_frontend.shareholder_create, name='shareholder_create'),
    path('shareholders/<int:pk>/', views_frontend.shareholder_detail, name='shareholder_detail'),
    path('shareholders/<int:pk>/edit/', views_frontend.shareholder_edit, name='shareholder_edit'),
    path('shareholders/<int:pk>/delete/', views_frontend.shareholder_delete, name='shareholder_delete'),

    path('shares/', views_frontend.share_list, name='share_list'),

    path('transfers/', views_frontend.share_transfer_list, name='share_transfer_list'),
    path('transfers/create/', views_frontend.share_transfer_create, name='share_transfer_create'),
    path('transfers/<int:pk>/', views_frontend.share_transfer_detail, name='share_transfer_detail'),
    path('transfers/<int:pk>/approve/', views_frontend.share_transfer_approve, name='share_transfer_approve'),
    path('transfers/<int:pk>/complete/', views_frontend.share_transfer_complete, name='share_transfer_complete'),
    path('transfers/<int:pk>/reject/', views_frontend.share_transfer_reject, name='share_transfer_reject'),

    # ============================================
    # DIVIDEND URLS (Complete)
    # ============================================
    path('dividends/', views_frontend.dividend_list, name='dividend_list'),
    path('dividends/create/', views_frontend.dividend_create, name='dividend_create'),
    path('dividends/<int:pk>/', views_frontend.dividend_detail, name='dividend_detail'),
    path('dividends/<int:pk>/generate-payments/', views_frontend.generate_dividend_payments, name='generate_dividend_payments'),
    path('dividend-payment/<int:pk>/mark-paid/', views_frontend.mark_dividend_paid, name='mark_dividend_paid'),

    # ============================================
    # DIVIDEND PREVIEW API (NEW)
    # ============================================
    path('api/dividend-preview/', views_frontend.dividend_preview_api, name='dividend_preview_api'),

    # ============================================
    # SHARE PRICE & MEETINGS
    # ============================================
    path('prices/', views_frontend.share_price_list, name='share_price_list'),
    
    # Shareholder Meetings (Existing)
    path('meetings/', views_frontend.meeting_list, name='meeting_list'),
    path('meetings/create/', views_frontend.meeting_create, name='meeting_create'),
    path('meetings/<int:pk>/', views_frontend.meeting_detail, name='meeting_detail'),
    path('meetings/<int:pk>/attendance/', views_frontend.meeting_mark_attendance, name='meeting_mark_attendance'),

    # ============================================
    # SHAREHOLDER REPORTS
    # ============================================
    path('reports/shareholder/', views_frontend.shareholder_report, name='shareholder_report'),
    path('reports/shareholder/pdf/', views_frontend.shareholder_report_pdf, name='shareholder_report_pdf'),
    path('api/shareholder/dashboard/', views_frontend.shareholder_dashboard_api, name='shareholder_dashboard_api'),

    # ============================================
    # DRIP & BUYBACK URLS
    # ============================================
    path('drip/dashboard/', views_frontend.drip_dashboard, name='drip_dashboard'),
    path('drip/enroll/<int:drip_id>/', views_frontend.drip_enroll, name='drip_enroll'),
    path('drip/unenroll/<int:enrollment_id>/', views_frontend.drip_unenroll, name='drip_unenroll'),
    path('drip/process/<int:dividend_payment_id>/', views_frontend.drip_process, name='drip_process'),
    path('drip/bulk-process/', views_frontend.drip_bulk_process, name='drip_bulk_process'),
    
    path('buyback/', views_frontend.buyback_list, name='buyback_list'),
    path('buyback/create/', views_frontend.buyback_create, name='buyback_create'),
    path('buyback/<int:pk>/', views_frontend.buyback_detail, name='buyback_detail'),
    path('buyback/<int:pk>/offer/', views_frontend.buyback_offer, name='buyback_offer'),
    
    # ============================================
    # SHAREHOLDER DISCOUNT & LOAN URLS
    # ============================================
    path('discounts/', views_frontend.discount_list, name='discount_list'),
    path('discounts/apply/', views_frontend.apply_discount, name='apply_discount'),
    path('discounts/my-discounts/', views_frontend.my_discounts, name='my_discounts'),
    
    path('loans/', views_frontend.loan_list, name='loan_list'),
    path('loans/create/', views_frontend.loan_create, name='loan_create'),
    path('loans/<int:pk>/', views_frontend.loan_detail, name='loan_detail'),
    path('loans/<int:pk>/pay/', views_frontend.loan_pay, name='loan_pay'),
    path('loans/<int:pk>/statement/', views_frontend.loan_statement, name='loan_statement'),

    # ============================================
    # 🆕 SERVICE MANAGEMENT URLS
    # ============================================
    
    # Services (CRUD)
    path('services/', views_frontend.service_list, name='service_list'),
    path('services/create/', views_frontend.service_create, name='service_create'),
    path('services/<int:pk>/', views_frontend.service_detail, name='service_detail'),
    path('services/<int:pk>/edit/', views_frontend.service_edit, name='service_edit'),
    path('services/<int:pk>/delete/', views_frontend.service_delete, name='service_delete'),

    # Service Requests
    path('service-requests/', views_frontend.service_request_list, name='service_request_list'),
    path('service-requests/create/', views_frontend.service_request_create, name='service_request_create'),
    path('service-requests/<int:pk>/', views_frontend.service_request_detail, name='service_request_detail'),
    path('service-requests/<int:pk>/edit/', views_frontend.service_request_edit, name='service_request_edit'),
    path('service-requests/<int:pk>/status/<str:status>/', views_frontend.service_request_status_update, name='service_request_status_update'),
    path('service-requests/<int:pk>/appointment/', views_frontend.service_request_appointment, name='service_request_appointment'),
    path('service-requests/<int:pk>/feedback/', views_frontend.service_request_feedback, name='service_request_feedback'),
    path('service-requests/<int:pk>/invoice/', views_frontend.service_request_invoice, name='service_request_invoice'),

    # Service Appointments
    path('appointments/', views_frontend.service_appointment_list, name='service_appointment_list'),
    path('appointments/calendar/', views_frontend.service_appointment_calendar, name='service_appointment_calendar'),

    # Service Reports
    path('reports/services/', views_frontend.service_report, name='service_report'),
    path('reports/services/technician/', views_frontend.technician_performance_report, name='technician_performance_report'),

    # Service AJAX Endpoints
    path('ajax/get-service-products/', views_frontend.get_service_products, name='get_service_products'),
    path('ajax/get-technician-schedule/', views_frontend.get_technician_schedule, name='get_technician_schedule'),
    path('ajax/check-appointment-conflict/', views_frontend.check_appointment_conflict, name='check_appointment_conflict'),
    path('services/inventory/', views_frontend.service_inventory_dashboard, name='service_inventory_dashboard'),
    path('services/inventory/items/', views_frontend.service_inventory_list, name='service_inventory_list'),
    path('services/inventory/items/create/', views_frontend.service_inventory_create, name='service_inventory_create'),
    path('services/inventory/items/<int:pk>/', views_frontend.service_inventory_detail, name='service_inventory_detail'),
    path('services/inventory/items/<int:pk>/edit/', views_frontend.service_inventory_edit, name='service_inventory_edit'),
    path('services/inventory/items/<int:pk>/adjust/', views_frontend.service_inventory_adjust, name='service_inventory_adjust'),
    path('services/inventory/items/<int:pk>/transactions/', views_frontend.service_inventory_transactions, name='service_inventory_transactions'),
    path('services/inventory/use/<int:request_id>/', views_frontend.service_inventory_use, name='service_inventory_use'),
    path('services/inventory/po/', views_frontend.service_inventory_po_list, name='service_inventory_po_list'),
    path('services/inventory/po/create/', views_frontend.service_inventory_po_create, name='service_inventory_po_create'),
    path('services/inventory/po/<int:pk>/', views_frontend.service_inventory_po_detail, name='service_inventory_po_detail'),
    path('services/inventory/po/<int:pk>/receive/', views_frontend.service_inventory_po_receive, name='service_inventory_po_receive'),
    path('expenses/', views_frontend.expense_dashboard, name='expense_dashboard'),
    path('expenses/list/', views_frontend.expense_list, name='expense_list'),
    path('expenses/create/', views_frontend.expense_create, name='expense_create'),
    path('expenses/<int:pk>/', views_frontend.expense_detail, name='expense_detail'),
    path('expenses/<int:pk>/edit/', views_frontend.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/submit/', views_frontend.expense_submit, name='expense_submit'),
    path('expenses/<int:pk>/approve/', views_frontend.expense_approve, name='expense_approve'),
    path('expenses/<int:pk>/reject/', views_frontend.expense_reject, name='expense_reject'),
    path('expenses/<int:pk>/pay/', views_frontend.expense_pay, name='expense_pay'),
    path('expenses/<int:pk>/delete/', views_frontend.expense_delete, name='expense_delete'),
    path('expenses/budgets/', views_frontend.expense_budget_list, name='expense_budget_list'),
    path('expenses/budgets/create/', views_frontend.expense_budget_create, name='expense_budget_create'),
    path('expenses/budgets/<int:pk>/', views_frontend.expense_budget_detail, name='expense_budget_detail'),
    path('expenses/claims/', views_frontend.expense_claim_list, name='expense_claim_list'),
    path('expenses/claims/create/', views_frontend.expense_claim_create, name='expense_claim_create'),
    path('expenses/claims/<int:pk>/', views_frontend.expense_claim_detail, name='expense_claim_detail'),
    path('expenses/report/', views_frontend.expense_report, name='expense_report'),
    path('expenses/categories/', views_frontend.expense_category_list, name='expense_category_list'),
    path('expenses/categories/create/', views_frontend.expense_category_create, name='expense_category_create'),
    path('expenses/categories/<int:pk>/edit/', views_frontend.expense_category_edit, name='expense_category_edit'),
    path('expenses/categories/<int:pk>/delete/', views_frontend.expense_category_delete, name='expense_category_delete'),
    path('budgets/', views_frontend.budget_dashboard, name='budget_dashboard'),
    path('budgets/list/', views_frontend.budget_list, name='budget_list'),
    path('budgets/create/', views_frontend.budget_create, name='budget_create'),
    path('budgets/<int:pk>/', views_frontend.budget_detail, name='budget_detail'),
    path('budgets/<int:pk>/edit/', views_frontend.budget_edit, name='budget_edit'),
    path('budgets/<int:pk>/delete/', views_frontend.budget_delete, name='budget_delete'),
    path('budgets/<int:pk>/submit/', views_frontend.budget_submit, name='budget_submit'),
    path('budgets/<int:pk>/approve/', views_frontend.budget_approve, name='budget_approve'),
    path('budgets/<int:pk>/activate/', views_frontend.budget_activate, name='budget_activate'),
    path('budgets/report/', views_frontend.budget_report, name='budget_report'),
    path('shareholder/deposit-request/', views_frontend.shareholder_portal_deposit_request, name='shareholder_portal_deposit_request'),
    path('shareholder/deposit-history/', views_frontend.shareholder_portal_deposit_history, name='shareholder_portal_deposit_history'),
    path('shareholders/deposit-requests/', views_frontend.shareholder_deposit_requests, name='shareholder_deposit_requests'),
    path('shareholders/deposit-requests/<int:pk>/', views_frontend.shareholder_deposit_request_detail, name='shareholder_deposit_request_detail'),
    path('shareholders/deposit-requests/bulk-approve/', views_frontend.shareholder_deposit_request_bulk_approve, name='shareholder_deposit_request_bulk_approve'),
    path('shareholders/deposit-requests/<int:pk>/notify/', views_frontend.shareholder_deposit_request_notification, name='shareholder_deposit_request_notification'),
    path('shareholders/<int:pk>/deposit-requests/', views_frontend.shareholder_deposit_requests_for_shareholder, name='shareholder_deposit_requests_for_shareholder'),
    path('shareholder/withdrawal-request/', views_frontend.shareholder_portal_withdrawal_request, name='shareholder_portal_withdrawal_request'),
    path('shareholder/withdrawal-history/', views_frontend.shareholder_portal_withdrawal_history, name='shareholder_portal_withdrawal_history'),
    path('shareholders/withdrawal-requests/', views_frontend.shareholder_withdrawal_requests, name='shareholder_withdrawal_requests'),
    path('shareholders/withdrawal-requests/<int:pk>/', views_frontend.shareholder_withdrawal_request_detail, name='shareholder_withdrawal_request_detail'),
    path('shareholders/withdrawal-requests/bulk-approve/', views_frontend.shareholder_withdrawal_request_bulk_approve, name='shareholder_withdrawal_request_bulk_approve'),
    path('shareholders/withdrawal-requests/<int:pk>/notify/', views_frontend.shareholder_withdrawal_request_notification, name='shareholder_withdrawal_request_notification'),
    path('shareholders/<int:pk>/withdrawal-requests/', views_frontend.shareholder_withdrawal_requests_for_shareholder, name='shareholder_withdrawal_requests_for_shareholder'),
    path('departments/', views_frontend.department_list, name='department_list'),
    path('departments/create/', views_frontend.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views_frontend.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views_frontend.department_delete, name='department_delete'),
    path('projects/', views_frontend.project_list, name='project_list'),
    path('projects/create/', views_frontend.project_create, name='project_create'),path('projects/<int:pk>/edit/', views_frontend.project_edit, name='project_edit'),
    path('projects/<int:pk>/delete/', views_frontend.project_delete, name='project_delete'),
    path('budgets/<int:pk>/goals/', views_frontend.budget_goals, name='budget_goals'),
    path('budgets/<int:pk>/goals/create/', views_frontend.budget_goal_create, name='budget_goal_create'),
    path('budgets/goals/<int:pk>/', views_frontend.budget_goal_detail, name='budget_goal_detail'),
    path('budgets/goals/<int:pk>/edit/', views_frontend.budget_goal_edit, name='budget_goal_edit'),
    path('budgets/goals/<int:pk>/delete/', views_frontend.budget_goal_delete, name='budget_goal_delete'),
    path('budgets/goals/<int:pk>/update-progress/', views_frontend.budget_goal_update_progress, name='budget_goal_update_progress'),
    path('budgets/goals/<int:pk>/comparison/', views_frontend.budget_goal_comparison, name='budget_goal_comparison'),
    
    
    path('audit/', views_frontend.audit_dashboard, name='audit_dashboard'),
    path('audit/plans/', views_frontend.audit_plan_list, name='audit_plan_list'),
    path('audit/plans/create/', views_frontend.audit_plan_create, name='audit_plan_create'),
    path('audit/plans/<int:pk>/', views_frontend.audit_plan_detail, name='audit_plan_detail'),
    path('audit/plans/<int:pk>/edit/', views_frontend.audit_plan_edit, name='audit_plan_edit'),
    path('audit/plans/<int:pk>/delete/', views_frontend.audit_plan_delete, name='audit_plan_delete'),
    path('audit/plans/<int:pk>/start/', views_frontend.audit_plan_start, name='audit_plan_start'),
    path('audit/plans/<int:pk>/complete/', views_frontend.audit_plan_complete, name='audit_plan_complete'),
    path('audit/plans/<int:pk>/findings/', views_frontend.audit_findings, name='audit_findings'),
    path('audit/findings/<int:pk>/', views_frontend.audit_finding_detail, name='audit_finding_detail'),
    path('audit/findings/<int:pk>/resolve/', views_frontend.audit_finding_resolve, name='audit_finding_resolve'),
    path('audit/reports/<int:pk>/', views_frontend.audit_report_view, name='audit_report_view'),
    path('audit/reports/<int:pk>/pdf/', views_frontend.audit_report_pdf, name='audit_report_pdf'),
    path('audit/controls/', views_frontend.internal_controls, name='internal_controls'),
    path('audit/controls/create/', views_frontend.internal_control_create, name='internal_control_create'),
    path('audit/trails/', views_frontend.audit_trails, name='audit_trails'),
    path('supply-chain/', views_frontend.supply_chain_dashboard, name='supply_chain_dashboard'),
    path('supply-chain/suppliers/', views_frontend.supplier_list, name='supplier_list'),
    path('supply-chain/suppliers/create/', views_frontend.supplier_create, name='supplier_create'),
    path('supply-chain/suppliers/<int:pk>/', views_frontend.supplier_detail, name='supplier_detail'),
    path('supply-chain/suppliers/<int:pk>/edit/', views_frontend.supplier_edit, name='supplier_edit'),
    path('supply-chain/forecast/', views_frontend.supply_forecast, name='supply_forecast'),
    path('supply-chain/forecast/create/', views_frontend.supply_forecast_create, name='supply_forecast_create'),
    path('supply-chain/deliveries/', views_frontend.delivery_schedule_list, name='delivery_schedule_list'),
    path('supply-chain/deliveries/create/', views_frontend.delivery_schedule_create, name='delivery_schedule_create'),
    path('supply-chain/deliveries/<int:pk>/', views_frontend.delivery_schedule_detail, name='delivery_schedule_detail'),
    path('supply-chain/tracking/<int:pk>/', views_frontend.logistics_tracking, name='logistics_tracking'),
    path('supply-chain/analytics/', views_frontend.supply_chain_analytics, name='supply_chain_analytics'),
    path('security/', views_security.security_dashboard, name='security_dashboard'),
    path('security/settings/', views_security.security_settings_view, name='security_settings'),
    path('security/two-factor/', views_security.two_factor_setup, name='two_factor_setup'),
    path('security/two-factor/verify/', views_security.two_factor_verify, name='two_factor_verify'),
    path('security/ip-whitelist/', views_security.ip_whitelist_view, name='ip_whitelist'),
    path('security/ip-blacklist/', views_security.ip_blacklist_view, name='ip_blacklist'),
    path('security/logs/', views_security.security_logs, name='security_logs'),
    path('security/alerts/', views_security.security_alerts_view, name='security_alerts'),
    path('security/api-keys/', views_security.api_key_management, name='api_key_management'),
    path('security/change-password/', views_security.change_password_security, name='change_password_security'),
    path('bi/', views_bi.bi_dashboard, name='bi_dashboard'),
    path('bi/dashboards/', views_bi.bi_dashboards_list, name='bi_dashboards_list'),
    path('bi/dashboards/create/', views_bi.bi_dashboard_create, name='bi_dashboard_create'),
    path('bi/dashboards/<int:pk>/edit/', views_bi.bi_dashboard_edit, name='bi_dashboard_edit'),
    path('bi/dashboards/<int:dashboard_id>/widget/create/', views_bi.bi_widget_create, name='bi_widget_create'),
    path('bi/kpi/', views_bi.bi_kpi_dashboard, name='bi_kpi_dashboard'),
    path('bi/kpi/create/', views_bi.bi_kpi_create, name='bi_kpi_create'),
    path('bi/reports/', views_bi.bi_reports, name='bi_reports'),
    path('bi/reports/<int:pk>/generate/', views_bi.bi_report_generate, name='bi_report_generate'),
    path('bi/api/', views_bi.bi_analytics_api, name='bi_analytics_api'),
    path('bi/insights/', views_bi.bi_insights, name='bi_insights'),
    path('bi/forecast/', views_bi.bi_forecast, name='bi_forecast'),
    path('testing/', views_testing.test_dashboard, name='test_dashboard'),
    path('testing/projects/', views_testing.test_project_list, name='test_project_list'),
    path('testing/projects/create/', views_testing.test_project_create, name='test_project_create'),
    path('testing/suites/create/<int:project_id>/', views_testing.test_suite_create, name='test_suite_create'),
    path('testing/cases/', views_testing.test_case_list, name='test_case_list'),
    path('testing/cases/<int:suite_id>/', views_testing.test_case_list, name='test_case_list'),
    path('testing/cases/create/<int:suite_id>/', views_testing.test_case_create, name='test_case_create'),
    path('testing/cases/execute/<int:pk>/', views_testing.test_case_execute, name='test_case_execute'),
    path('testing/bugs/', views_testing.bug_list, name='bug_list'),
    path('testing/bugs/create/', views_testing.bug_create, name='bug_create'),
    path('testing/bugs/<int:pk>/update/', views_testing.bug_update_status, name='bug_update_status'),
    path('testing/reports/generate/', views_testing.test_report_generate, name='test_report_generate'),
    path('testing/reports/<int:pk>/', views_testing.test_report_view, name='test_report_view'),
    path('testing/plans/', views_testing.test_plan_list, name='test_plan_list'),
    path('testing/plans/create/', views_testing.test_plan_create, name='test_plan_create'),
    path('testing/plans/<int:pk>/', views_testing.test_plan_detail, name='test_plan_detail'),
    
   
    
    path('documents/', views_document.document_dashboard, name='document_dashboard'),
    path('documents/list/', views_document.document_list, name='document_list'),
    path('documents/upload/', views_document.document_upload, name='document_upload'),
    path('documents/<int:pk>/', views_document.document_detail, name='document_detail'),
    path('documents/<int:pk>/download/', views_document.document_download, name='document_download'),
    path('documents/<int:pk>/preview/', views_document.document_preview, name='document_preview'),
    path('documents/<int:pk>/delete/', views_document.document_delete, name='document_delete'),
    path('purchases/<int:pk>/', views_frontend.purchase_detail, name='purchase_detail'),
    path('profile/', views_frontend.profile_view, name='profile'),
    path('change-password/', 
     auth_views.PasswordChangeView.as_view(
         template_name='change_password.html',
         success_url='/change-password/done/'
     ), 
     name='change_password'),
     path('change-password/done/', 
     auth_views.PasswordChangeDoneView.as_view(
         template_name='change_password_done.html'
     ), 
     name='password_change_done'),
     path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
     path('purchases/<int:pk>/', views_frontend.purchase_detail, name='purchase_detail'),
     path('', views_frontend.dashboard_view, name='dashboard'),
     path('sales/<int:pk>/convert-to-expense/', views_frontend.convert_sale_to_expense, name='convert_sale_to_expense'),
    path('reports/self-expense/', views_frontend.self_expense_report, name='self_expense_report'),
    path('reports/self-expense/pdf/', views_frontend.self_expense_report_pdf, name='self_expense_report_pdf'),
    path('reports/self-expense/export/', views_frontend.self_expense_export, name='self_expense_export'),
    path('sales/bulk-convert-to-expense/', views_frontend.bulk_convert_to_expense, name='bulk_convert_to_expense'),
    path('ajax/get-product-by-name/', views_frontend.get_product_by_name, name='get_product_by_name'),
    path('dividend-allocation/<int:pk>/pay/', views_frontend.mark_allocation_paid, name='mark_allocation_paid'),
    path('dividends/<int:pk>/edit/', views_frontend.dividend_edit, name='dividend_edit'),
    
    # ✅ Process deduction for a purchase
    path('purchases/<int:pk>/process-deduction/', 
         views_frontend.process_purchase_deduction, 
         name='process_purchase_deduction'),
    
    # ✅ View deduction details for a purchase
    path('purchases/<int:pk>/deduction-details/', 
         views_frontend.purchase_deduction_details, 
         name='purchase_deduction_details'),
    
    # ✅ Toggle deduction feature
    path('settings/toggle-deduction/', 
         views_frontend.toggle_shareholder_deduction, 
         name='toggle_shareholder_deduction'),
    
    # ✅ Change deduction type (equal/proportional)
    path('settings/deduction-type/', 
         views_frontend.change_deduction_type, 
         name='change_deduction_type'),
    
    # ✅ Shareholder Deduction Report
    path('reports/shareholder-deduction/', 
         views_frontend.shareholder_deduction_report, 
         name='shareholder_deduction_report'),
    
    # ✅ Shareholder Deduction Report (PDF)
    path('reports/shareholder-deduction/pdf/', 
         views_frontend.shareholder_deduction_report_pdf, 
         name='shareholder_deduction_report_pdf'),
    
    # ✅ Shareholder Deduction Report (Excel)
    path('reports/shareholder-deduction/export/', 
         views_frontend.shareholder_deduction_report_export, 
         name='shareholder_deduction_report_export'),
    
    # ✅ Bulk process deductions
    path('purchases/bulk-process-deductions/', 
         views_frontend.bulk_process_deductions, 
         name='bulk_process_deductions'),
    
    # ✅ Shareholder balance summary with deductions
    path('shareholders/balance-summary/', 
         views_frontend.shareholder_balance_summary, 
         name='shareholder_balance_summary'),
    
    # ✅ Purchase deduction history for a shareholder
    path('shareholders/<int:pk>/deduction-history/', 
         views_frontend.shareholder_deduction_history, 
         name='shareholder_deduction_history'),
         # urls.py
    path('balance-dividend/create/', views_frontend.balance_dividend_create, name='balance_dividend_create'),
    path('balance-dividend/<int:pk>/', views_frontend.balance_dividend_detail, name='balance_dividend_detail'),
    path('balance-dividend/<int:pk>/generate/', views_frontend.balance_dividend_generate, name='balance_dividend_generate'),
    path('balance-dividend/<int:pk>/distribute/', views_frontend.balance_dividend_distribute, name='balance_dividend_distribute'),
    path('balance-dividend/payment/<int:pk>/pay/', views_frontend.balance_dividend_pay, name='balance_dividend_pay'),
    path('balance-dividend/list/', views_frontend.balance_dividend_list, name='balance_dividend_list'),
    path('balance-dividend/report/', views_frontend.balance_dividend_report, name='balance_dividend_report'),
    path('balance-dividend/<int:pk>/delete/', views_frontend.balance_dividend_delete, name='balance_dividend_delete'),
    path('balance-dividend/<int:pk>/edit/', views_frontend.balance_dividend_edit, name='balance_dividend_edit'),
    
    # API Endpoints
    path('api/eligible-shareholders/', views_frontend.eligible_shareholders_api, name='eligible_shareholders_api'),
    path('api/balance-dividend-preview/', views_frontend.balance_dividend_preview_api, name='balance_dividend_preview_api'),
    path('api/dividend-profit/', views_frontend.dividend_profit_api, name='dividend_profit_api'),
    path('api/eligible-shareholders/', views_frontend.eligible_shareholders_api, name='eligible_shareholders_api'),
    path('api/balance-dividend-preview/', views_frontend.balance_dividend_preview_api, name='balance_dividend_preview_api'),
    path('shareholders/<int:pk>/withdraw-from-balance/', 
         views_frontend.shareholder_withdraw_from_balance, name='shareholder_withdraw_from_balance'),
    
    path('backup/fast/', views_frontend.create_fast_backup_with_progress, name='fast_backup'),
    path('backup/background/', views_frontend.backup_in_background, name='backup_background'),
    path('backup/progress/', views_frontend.get_backup_progress, name='backup_progress'),
    path('backup/files/', views_frontend.get_backup_files_api, name='backup_files_api'),
    path('backup/stats/', views_frontend.get_backup_stats, name='backup_stats'),
    path('backup/cloud-files/', views_frontend.get_cloud_files, name='get_cloud_files'),
    re_path(r'^backup/download/(?P<filename>.+)/$', views_frontend.download_backup, name='download_backup'),
    re_path(r'^backup/delete/(?P<filename>.+)/$', views_frontend.delete_backup_file, name='delete_backup_file'),
    re_path(r'^backup/restore/(?P<filename>.+)/$', views_frontend.restore_from_cloud, name='restore_from_cloud'),
    re_path(r'^backup/restore-local/(?P<filename>.+)/$', views_frontend.restore_local_backup, name='restore_local_backup'),
    path('backup/upload/', views_frontend.upload_backup_file, name='upload_backup_file'),
    path('vendors/<int:pk>/delete/', views_frontend.vendor_delete, name='vendor_delete'),
    
    
    path('ajax/search-products/', views_frontend.search_products_ajax, name='search_products_ajax'),
    # ✅ SAHI - Vendor Pricing Report (Matrix view)
    path('vendors/pricing-report/', views_frontend.vendor_pricing_report, name='vendor_pricing_report'),
    path('vendors/pricing-report/export/', views_frontend.vendor_pricing_report_export, name='vendor_pricing_report_export'),
    path('products/import-export/', views_frontend.product_import_export, name='product_import_export'),
    path('products/import/', views_frontend.product_import, name='product_import'),
    path('products/export/csv/', views_frontend.product_export_csv, name='product_export_csv'),
    path('products/export/excel/', views_frontend.product_export_excel, name='product_export_excel'),
    path('products/export/all/', views_frontend.product_export_all, name='product_export_all'),
    path('products/export/template/', views_frontend.product_export_template, name='product_export_template'),
    path('api/product/create/', views_frontend.api_create_product, name='api_create_product'),
    
    # Dashboard
    path('accounts/', views_frontend.accounts_dashboard, name='accounts_dashboard'),
    
    # Chart of Accounts
    path('accounts/chart/', views_frontend.chart_of_accounts, name='chart_of_accounts'),
    path('accounts/chart/create/', views_frontend.account_create, name='account_create'),
    path('accounts/chart/<int:pk>/edit/', views_frontend.account_edit, name='account_edit'),
    path('accounts/chart/<int:pk>/delete/', views_frontend.account_delete, name='account_delete'),
    
    # Journal Entries
    path('accounts/journal/', views_frontend.journal_entry_list, name='journal_entry_list'),
    path('accounts/journal/create/', views_frontend.journal_entry_create, name='journal_entry_create'),
    path('accounts/journal/<int:pk>/', views_frontend.journal_entry_detail, name='journal_entry_detail'),
    path('accounts/journal/<int:pk>/post/', views_frontend.journal_entry_post, name='journal_entry_post'),
    path('accounts/journal/<int:pk>/reverse/', views_frontend.journal_entry_reverse, name='journal_entry_reverse'),
    path('accounts/journal/<int:pk>/delete/', views_frontend.journal_entry_delete, name='journal_entry_delete'),
    
    # General Ledger
    path('accounts/ledger/', views_frontend.general_ledger, name='general_ledger'),
    path('accounts/ledger/<int:account_id>/', views_frontend.account_ledger, name='account_ledger'),
    
    # Trial Balance
    path('accounts/trial-balance/', views_frontend.trial_balance, name='trial_balance'),
    path('accounts/trial-balance/generate/', views_frontend.generate_trial_balance, name='generate_trial_balance'),
    
    # Financial Statements
    path('accounts/balance-sheet/', views_frontend.balance_sheet, name='balance_sheet'),
    path('accounts/profit-loss/', views_frontend.profit_loss_statement, name='profit_loss_statement'),
    path('accounts/cash-flow/', views_frontend.cash_flow_statement, name='cash_flow_statement'),
    
    # Periods
    path('accounts/periods/', views_frontend.financial_periods, name='financial_periods'),
    path('accounts/periods/create/', views_frontend.financial_period_create, name='financial_period_create'),
    path('accounts/periods/<int:pk>/close/', views_frontend.financial_period_close, name='financial_period_close'),
    
    # Reports
    path('accounts/reports/', views_frontend.accounts_reports, name='accounts_reports'),
    path('accounts/reports/export/', views_frontend.export_accounts_report, name='export_accounts_report'),
    path('api/users/bulk-action/', views_frontend.bulk_user_action, name='bulk_user_action'),
    path('api/users/<int:user_id>/quick-view/', views_frontend.quick_view_user, name='quick_view_user'),
    path('api/users/activity-stats/', views_frontend.user_activity_stats, name='user_activity_stats'),
    path('users/export/', views_frontend.export_users, name='export_users'),
    path('permission-matrix/', views_frontend.permission_matrix, name='permission_matrix'),
    path('api/permission-matrix/', views_frontend.permission_matrix_api, name='permission_matrix_api'),
    path('api/permission-matrix/save/', views_frontend.permission_matrix_save, name='permission_matrix_save'),
    path('vendors/<int:pk>/ledger-report/', views_frontend.vendor_ledger_report, name='vendor_ledger_report'),
    path('vendors/<int:pk>/ledger-export/', views_frontend.vendor_ledger_export, name='vendor_ledger_export'),
    path('vendors/<int:pk>/ledger-pdf/', views_frontend.vendor_ledger_pdf, name='vendor_ledger_pdf'),
    path('vendors/purchase-product-report/', views_frontend.vendor_purchase_product_report, name='vendor_purchase_product_report'),
    path('vendors/purchase-product-export/', views_frontend.vendor_purchase_product_export, name='vendor_purchase_product_export'),
    path('vendors/purchase-product-pdf/', views_frontend.vendor_purchase_product_pdf, name='vendor_purchase_product_pdf'),
    path('ajax/search-products-purchase/', views_frontend.search_products_purchase, name='search_products_purchase'),
    path('ajax/search-products/', views_frontend.search_products_ajax, name='search_products_ajax'),
    path('loan-returns/', views_frontend.loan_return_list, name='loan_return_list'),
    path('loan-returns/create/', views_frontend.loan_return_create, name='loan_return_create'),
    path('loan-returns/<int:pk>/', views_frontend.loan_return_detail, name='loan_return_detail'),
    path('loan-returns/<int:pk>/pay/', views_frontend.loan_return_pay, name='loan_return_pay'),
    path('loan-returns/<int:pk>/delete/', views_frontend.loan_return_delete, name='loan_return_delete'),
    path('loans/', views_frontend.loan_list, name='loan_list'),
    path('loans/create/', views_frontend.loan_create, name='loan_create'),
    path('loans/<int:pk>/', views_frontend.loan_detail, name='loan_detail'),
    path('loans/<int:pk>/delete/', views_frontend.loan_delete, name='loan_delete'),
    path('loans/dashboard/', views_frontend.loan_dashboard, name='loan_dashboard'),
    path('loans/export/excel/', views_frontend.loan_export_report, name='loan_export_report'),
    path('loans/export/pdf/', views_frontend.loan_export_pdf, name='loan_export_pdf'),
    path('loans-given/dashboard/', views_frontend.loan_given_dashboard, name='loan_given_dashboard'),
    path('loans-given/', views_frontend.loan_given_list, name='loan_given_list'),
    path('loans-given/create/', views_frontend.loan_given_create, name='loan_given_create'),
    path('loans-given/<int:pk>/', views_frontend.loan_given_detail, name='loan_given_detail'),
    path('loans-given/<int:pk>/pay/', views_frontend.loan_given_pay, name='loan_given_pay'),
    path('loans-given/<int:pk>/delete/', views_frontend.loan_given_delete, name='loan_given_delete'),
    path('returns/purchase/<int:pk>/delete/', views_frontend.purchase_return_delete, name='purchase_return_delete'),
    path('ajax/get-purchase-return-history/', views_frontend.get_purchase_return_history, name='get_purchase_return_history'),
    
]