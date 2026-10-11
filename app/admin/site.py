"""CustomAdminSite and the replacement of `admin.site`."""
import shutil
from django.conf import settings
from ..models import *
import os
import subprocess
import io
from django.contrib import admin, messages
from django.utils.timezone import now
from django.contrib.auth.models import User
from django.db.models import Sum, F
from datetime import datetime, timedelta
from django.http import HttpResponse, HttpResponseForbidden
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from django.contrib.admin.models import LogEntry
from django.urls import path
from django.shortcuts import render, redirect, get_object_or_404
from django.template.response import TemplateResponse
from .helpers import generate_invoice_pdf


class CustomAdminSite(admin.AdminSite):
    """Custom Admin Site for Adding Backup/Restore/Delete View"""

    index_template = "admin/custom_index.html"

    def get_default_backup_dir(self):
        """Get default backup directory based on platform"""
        import platform
        
        if platform.system() == 'Linux' and os.path.exists('/storage/emulated/0/'):
            return '/storage/emulated/0/Download/Backups/'
        elif platform.system() == 'Windows':
            return os.path.join(os.path.expanduser('~'), 'Documents', 'Backups')
        else:
            return os.path.join(os.path.expanduser('~'), 'Backups')

    def get_active_backup_dir(self, request):
        """Get current backup directory (session ya default)"""
        session_path = request.session.get('backup_dir', '')
        if session_path and os.path.exists(session_path):
            return session_path
        
        default = self.get_default_backup_dir()
        os.makedirs(default, exist_ok=True)
        return default

    # ============================================
    # URLS
    # ============================================
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # Database Backup/Restore
            path('database-backup/', self.admin_view(self.database_backup_view), name='database-backup'),
            path('backup-db/', self.admin_view(self.backup_database), name='backup-db'),
            path('restore-db/', self.admin_view(self.restore_database), name='restore-db'),
            path('delete-backup/<str:filename>/', self.admin_view(self.delete_backup), name='delete-backup'),
            path('set-backup-dir/', self.admin_view(self.set_backup_dir), name='set-backup-dir'),
            
            # Invoice & Documents
            path('invoice/<int:sale_id>/', self.admin_view(self.invoice_view), name='generate_invoice'),
            path('challan-pdf/<int:challan_id>/', self.admin_view(self.challan_pdf_view), name='generate_challan_pdf'),
            path('grn-pdf/<int:grn_id>/', self.admin_view(self.grn_pdf_view), name='generate_grn_pdf'),
            path('audit-pdf/<int:audit_id>/', self.admin_view(self.audit_pdf_view), name='generate_audit_pdf'),
            
            # Barcode & Search
            path('find-product-by-barcode/', self.admin_view(self.find_product_by_barcode_view), name='find_product_by_barcode'),
            path('find-product-by-serial/', self.admin_view(self.find_product_by_serial_view), name='find_product_by_serial'),
            path('get-product-price/', self.admin_view(self.get_product_price_view), name='get_product_price'),
            path('get-batch-selling-price/', self.admin_view(self.get_batch_selling_price_view), name='get_batch_selling_price'),
            path('get-next-bill-no/', self.admin_view(self.get_next_bill_no), name='get-next-bill-no'),
            path('app/product/supplier-barcode/', self.admin_view(self.supplier_barcode_view), name='supplier_barcode'),
            path('set-supplier-barcode/', self.admin_view(self.set_supplier_barcode), name='set_supplier_barcode'),
            
            # Status Updates
            path('app/saleorder/update-status/', self.admin_view(self.update_order_status_view), name='update_order_status'),
            path('app/purchaseorder/update-status/', self.admin_view(self.update_po_status_view), name='update_po_status'),
            
            # Dashboard
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
            path('dashboard/sales-forecast/', self.admin_view(self.sales_forecast_view), name='sales_forecast'),
            
            # System Health
            path('system-health/', self.admin_view(self.system_health_view), name='system-health'),
            
            # Range Reports
            path('reports/range/', self.admin_view(self.range_report_view), name='range_report'),
            path('reports/range/pdf/', self.admin_view(self.range_report_pdf), name='range_report_pdf'),
            
            # WhatsApp
            path('whatsapp/send/', self.admin_view(self.whatsapp_view), name='whatsapp_send'),
            path('whatsapp/reminders/', self.admin_view(self.whatsapp_reminders_view), name='whatsapp_reminders'),
            path('whatsapp/daily-summary/', self.admin_view(self.whatsapp_daily_summary_view), name='whatsapp_daily'),
        ]
        return custom_urls + urls

    # ============================================
    # BACKUP METHODS
    # ============================================
    
    def get_backup_files(self, request):
        """Get list of backup files from active backup directory"""
        try:
            backup_path = self.get_active_backup_dir(request)
            if not os.path.exists(backup_path):
                return []
            files = os.listdir(backup_path)
            files = [f for f in files if f.endswith(('.dump', '.sql', '.json', '.gz', '.sqlite'))]
            files = sorted(files, key=lambda x: os.path.getmtime(os.path.join(backup_path, x)), reverse=True)
            return files
        except Exception:
            return []

    def set_backup_dir(self, request):
        """AJAX: User se folder path lo aur session mein save karo"""
        from django.http import JsonResponse
        import json
        
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                backup_path = data.get('path', '').strip()
            except:
                backup_path = request.POST.get('path', '').strip()
            
            if backup_path:
                try:
                    os.makedirs(backup_path, exist_ok=True)
                except OSError as e:
                    return JsonResponse({'success': False, 'message': f'❌ Cannot create folder: {e}'})
                
                request.session['backup_dir'] = backup_path
                request.session.modified = True
                
                return JsonResponse({
                    'success': True, 
                    'message': f'✅ Backup folder set: {backup_path}',
                    'path': backup_path
                })
            else:
                return JsonResponse({'success': False, 'message': '❌ Please enter a valid path'})
        
        return JsonResponse({'success': False, 'message': 'Invalid request'})

    def database_backup_view(self, request):
        """Backup page view"""
        if not request.user.is_superuser:
            return HttpResponseForbidden("You are not allowed to access this page.")
        
        backup_path = self.get_active_backup_dir(request)
        backup_files = self.get_backup_files(request)
        
        import platform
        is_android = platform.system() == 'Linux' and os.path.exists('/storage/emulated/0/')
        is_windows = platform.system() == 'Windows'
        
        context = {
            **self.each_context(request),
            "title": "Database Backup & Restore",
            "backup_files": backup_files,
            "backup_dir": backup_path,
            "is_android": is_android,
            "is_windows": is_windows,
        }
        return TemplateResponse(request, "admin/database_backup.html", context)

    def backup_database(self, request):
        """Create backup"""
        backup_path = self.get_active_backup_dir(request)
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_path, f'db_backup_{timestamp}.json')
            
            result = subprocess.run(
                ['python', 'manage.py', 'dumpdata', '--exclude', 'auth.permission', 
                 '--exclude', 'contenttypes', '--indent', '2', '--output', backup_file],
                check=True, capture_output=True, text=True
            )
            
            success_msg = f"✅ Database backup created!\n📁 {backup_file}"
            
            if 'sqlite' in settings.DATABASES['default']['ENGINE']:
                db_path = settings.DATABASES['default']['NAME']
                if os.path.exists(db_path):
                    sqlite_backup = os.path.join(backup_path, f'db_backup_{timestamp}.sqlite')
                    shutil.copy2(db_path, sqlite_backup)
                    success_msg += f"\n📁 {sqlite_backup}"
            
            messages.success(request, success_msg)
        except subprocess.CalledProcessError as e:
            messages.error(request, f"❌ Error while creating backup: {e.stderr}")
        except Exception as e:
            messages.error(request, f"❌ Error: {str(e)}")
        
        return redirect("admin:database-backup")

    def restore_database(self, request):
        """Restore database from backup"""
        if request.method == 'POST':
            backup_file = request.POST.get('backup_file', '')
            backup_path = self.get_active_backup_dir(request)
            full_path = os.path.join(backup_path, backup_file)
            
            if '..' in backup_file or '/' in backup_file or '\\' in backup_file:
                messages.error(request, "❌ Invalid filename")
                return redirect("admin:database-backup")
            
            if not backup_file or not os.path.exists(full_path):
                messages.error(request, f"❌ Backup file not found: {backup_file}")
                return redirect("admin:database-backup")
            
            try:
                if backup_file.endswith('.json'):
                    result = subprocess.run(
                        ['python', 'manage.py', 'loaddata', full_path],
                        check=True, capture_output=True, text=True
                    )
                    messages.success(request, f"✅ Database restored from {backup_file}")
                
                elif backup_file.endswith('.sqlite'):
                    if 'sqlite' in settings.DATABASES['default']['ENGINE']:
                        db_path = settings.DATABASES['default']['NAME']
                        safety_backup = db_path + '.before_restore'
                        shutil.copy2(db_path, safety_backup)
                        shutil.copy2(full_path, db_path)
                        messages.success(request, f"✅ SQLite database restored!\n⚠ Old DB saved as .before_restore")
                    else:
                        messages.error(request, "❌ Not a SQLite database")
                
                else:
                    messages.error(request, f"❌ Unsupported format: {backup_file}")
                    
            except subprocess.CalledProcessError as e:
                messages.error(request, f"❌ Error: {e.stderr}")
            except Exception as e:
                messages.error(request, f"❌ Error: {str(e)}")
        
        return redirect("admin:database-backup")

    def delete_backup(self, request, filename):
        """Delete a backup file"""
        backup_path = self.get_active_backup_dir(request)
        
        if '..' in filename or '/' in filename or '\\' in filename:
            messages.error(request, "❌ Invalid filename")
            return redirect("admin:database-backup")
        
        file_path = os.path.join(backup_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            messages.success(request, f"🗑️ Backup file '{filename}' deleted!")
        else:
            messages.error(request, f"❌ File not found: '{filename}'")
        return redirect("admin:database-backup")

    # ============================================
    # GET NEXT BILL NUMBER
    # ============================================
    def get_next_bill_no(self, request):
        from django.http import JsonResponse
        
        prefix = request.GET.get('prefix', '')
        today = datetime.now().strftime('%Y%m%d')
        
        if not prefix:
            prefix = f'INV-{today}'
        
        try:
            last_sale = Sale.objects.filter(
                bill_no__startswith=prefix
            ).order_by('-bill_no').first()
            
            if last_sale:
                try:
                    last_num = int(last_sale.bill_no.split('-')[-1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            
            bill_no = f'{prefix}-{new_num}'
            return JsonResponse({'success': True, 'bill_no': bill_no})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    # ============================================
    # DOCUMENT VIEWS
    # ============================================
    def invoice_view(self, request, sale_id):
        sale = get_object_or_404(Sale, pk=sale_id)
        pdf_buffer = generate_invoice_pdf(sale)
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Invoice_{sale.bill_no}.pdf"'
        return response

    def challan_pdf_view(self, request, challan_id):
        challan = get_object_or_404(DeliveryChallan, pk=challan_id)
        admin_obj = DeliveryChallanAdmin(DeliveryChallan, self)
        return admin_obj.generate_challan_pdf(request, DeliveryChallan.objects.filter(pk=challan_id))

    def grn_pdf_view(self, request, grn_id):
        grn = get_object_or_404(GoodsReceivedNote, pk=grn_id)
        admin_obj = GoodsReceivedNoteAdmin(GoodsReceivedNote, self)
        return admin_obj.generate_grn_pdf(request, GoodsReceivedNote.objects.filter(pk=grn_id))

    def audit_pdf_view(self, request, audit_id):
        audit = get_object_or_404(StockAudit, pk=audit_id)
        admin_obj = StockAuditAdmin(StockAudit, self)
        return admin_obj.generate_audit_pdf(request, StockAudit.objects.filter(pk=audit_id))

    # ============================================
    # BARCODE & SERIAL SEARCH
    # ============================================
    def find_product_by_barcode_view(self, request):
        from django.http import JsonResponse
        import re
        
        barcode = request.GET.get('barcode', '').strip()
        barcode = re.sub(r'[^0-9]', '', barcode)
        
        if not barcode:
            return JsonResponse({'success': False, 'message': 'No barcode provided'})
        
        try:
            product = Product.objects.get(barcode=barcode)
            return JsonResponse({
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'barcode': product.barcode,
                    'serial_no': product.serial_no or '',
                    'price': str(product.price)
                }
            })
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'})

    def find_product_by_serial_view(self, request):
        """AJAX view to find product by serial number"""
        from django.http import JsonResponse
        
        serial = request.GET.get('serial', '').strip()
        
        if not serial:
            return JsonResponse({'success': False, 'message': 'No serial number provided'})
        
        try:
            product = Product.objects.get(serial_no__iexact=serial)
            return JsonResponse({
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'serial_no': product.serial_no,
                    'barcode': product.barcode or '',
                    'price': str(product.price)
                }
            })
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found with this serial number'})

    def get_product_price_view(self, request):
        from django.http import JsonResponse
        
        product_id = request.GET.get('product_id')
        if product_id:
            try:
                product = Product.objects.get(pk=product_id)
                return JsonResponse({
                    'success': True,
                    'price': str(product.price),
                    'name': product.name
                })
            except Product.DoesNotExist:
                pass
        return JsonResponse({'success': False})

    # ============================================
    # ✅ BATCH SELLING PRICE API (NEW!)
    # ============================================
    def get_batch_selling_price_view(self, request):
        """Get batch selling price for a product"""
        from django.http import JsonResponse
        
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        
        if not product_id:
            return JsonResponse({'success': False, 'message': 'Product ID required'})
        
        try:
            product = Product.objects.get(pk=product_id)
            
            # ✅ Latest batch dhundo jisme selling price set hai
            batch = None
            if warehouse_id:
                batch = StockBatch.objects.filter(
                    product=product,
                    warehouse_id=warehouse_id,
                    remaining_qty__gt=0,
                    selling_price__gt=0
                ).order_by('id').first()
            else:
                batch = StockBatch.objects.filter(
                    product=product,
                    remaining_qty__gt=0,
                    selling_price__gt=0
                ).order_by('id').first()
            
            default_price = str(product.price)
            
            if batch and batch.selling_price > 0:
                return JsonResponse({
                    'success': True,
                    'price': str(batch.selling_price),
                    'purchase_price': str(batch.price),
                    'batch_selling_price': str(batch.selling_price),
                    'name': product.name,
                    'has_batch_price': True
                })
            else:
                return JsonResponse({
                    'success': True,
                    'price': default_price,
                    'name': product.name,
                    'has_batch_price': False
                })
                
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'})

    def supplier_barcode_view(self, request):
        ids_str = request.GET.get('ids', '')
        product_ids = [int(id) for id in ids_str.split(',') if id]
        products = Product.objects.filter(id__in=product_ids)
        return render(request, "admin/supplier_barcode.html", {
            **self.each_context(request),
            "title": "Set Supplier Barcode",
            "products": products
        })

    def set_supplier_barcode(self, request):
        from django.http import JsonResponse
        import re
        
        product_id = request.POST.get('product_id')
        barcode = request.POST.get('barcode', '').strip()
        
        if not product_id or not barcode:
            return JsonResponse({'success': False, 'message': 'Missing data'})
        
        barcode = re.sub(r'[^0-9]', '', barcode)
        if not barcode:
            return JsonResponse({'success': False, 'message': 'Invalid barcode'})
        
        try:
            product = Product.objects.get(pk=product_id)
            if Product.objects.filter(barcode=barcode).exclude(pk=product_id).exists():
                return JsonResponse({'success': False, 'message': '❌ Already used by another product'})
            
            product.barcode = barcode
            product.use_custom_barcode = True
            product.save()
            return JsonResponse({
                'success': True,
                'message': f'✅ Barcode set for {product.name}',
                'barcode': barcode
            })
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'})

    # ============================================
    # STATUS UPDATE VIEWS
    # ============================================
    def update_order_status_view(self, request):
        ids_str = request.GET.get('ids', '')
        order_ids = [int(id) for id in ids_str.split(',') if id]
        orders = SaleOrder.objects.filter(id__in=order_ids)
        
        if request.method == 'POST':
            new_status = request.POST.get('status')
            if new_status:
                orders.update(status=new_status)
                messages.success(request, f"✅ Updated {orders.count()} orders")
                return redirect("admin:app_saleorder_changelist")
        
        return render(request, "admin/update_order_status.html", {
            **self.each_context(request),
            "title": "Update Order Status",
            "orders": orders,
            "status_choices": SaleOrder.ORDER_STATUS
        })

    def update_po_status_view(self, request):
        ids_str = request.GET.get('ids', '')
        po_ids = [int(id) for id in ids_str.split(',') if id]
        orders = PurchaseOrder.objects.filter(id__in=po_ids)
        
        if request.method == 'POST':
            new_status = request.POST.get('status')
            if new_status:
                orders.update(status=new_status)
                messages.success(request, f"✅ Updated {orders.count()} POs")
                return redirect("admin:app_purchaseorder_changelist")
        
        return render(request, "admin/update_po_status.html", {
            **self.each_context(request),
            "title": "Update PO Status",
            "orders": orders,
            "status_choices": PurchaseOrder.ORDER_STATUS
        })

    # ============================================
    # DASHBOARD
    # ============================================
    def dashboard_view(self, request):
        from datetime import timedelta, date
        import json
        
        today = date.today()
        month_ago = today - timedelta(days=30)
        
        daily_sales = []
        for i in range(30):
            d = today - timedelta(days=29-i)
            total = Sale.objects.filter(sale_date__date=d).aggregate(
                t=Sum('saleitem__total_amt')
            )['t'] or 0
            daily_sales.append({'date': d.strftime('%d %b'), 'amount': float(total)})
        
        top_products = SaleItem.objects.filter(
            sale__sale_date__gte=month_ago
        ).values('product__name').annotate(
            total_qty=Sum('qty'), total_sales=Sum('total_amt')
        ).order_by('-total_sales')[:10]
        
        slow_moving = []
        for inv in Inventory.objects.filter(stock__gt=0):
            sales_30d = SaleItem.objects.filter(
                product=inv.product, sale__sale_date__gte=month_ago
            ).aggregate(t=Sum('qty'))['t'] or 0
            if sales_30d == 0 or (inv.stock > 0 and (sales_30d / inv.stock) < 0.1):
                slow_moving.append({
                    'name': inv.product.name,
                    'stock': inv.stock,
                    'sales_30d': sales_30d,
                    'warehouse': inv.warehouse.name
                })
        
        context = {
            **self.each_context(request),
            "title": "Dashboard",
            "daily_sales": json.dumps(daily_sales),
            "top_products": list(top_products),
            "slow_moving": slow_moving[:10],
            "total_customers": Customer.objects.count(),
            "total_products": Product.objects.count(),
            "total_sales_today": Sale.objects.filter(sale_date__date=today).count(),
            "total_purchase_today": Purchase.objects.filter(pur_date__date=today).count(),
            "low_stock_count": Inventory.objects.filter(stock__lt=F('product__low_stock_threshold')).count(),
        }
        return TemplateResponse(request, "admin/dashboard.html", context)

    def sales_forecast_view(self, request):
        from datetime import date, timedelta
        
        today = date.today()
        daily_data = []
        for i in range(90):
            d = today - timedelta(days=89-i)
            total = Sale.objects.filter(sale_date__date=d).aggregate(
                t=Sum('saleitem__total_amt')
            )['t'] or 0
            daily_data.append(float(total))
        
        forecast = []
        if len(daily_data) >= 7:
            for i in range(7):
                avg = sum(daily_data[-7:]) / 7
                next_date = today + timedelta(days=i+1)
                forecast.append({'date': next_date.strftime('%d %b'), 'amount': round(avg, 2)})
                daily_data.append(avg)
        
        return TemplateResponse(request, "admin/sales_forecast.html", {
            **self.each_context(request),
            "title": "Sales Forecast",
            "forecast": forecast
        })

    # ============================================
    # SYSTEM HEALTH
    # ============================================
    def system_health_view(self, request):
        cpu_percent = 0
        cpu_count = 0
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpu_count = sum(1 for line in f if line.startswith('processor'))
            with open('/proc/stat', 'r') as f:
                cpu_line = f.readline()
                cpu_values = [int(x) for x in cpu_line.split()[1:8]]
                idle = cpu_values[3]
                total = sum(cpu_values)
                if total > 0:
                    cpu_percent = round(100 - (idle / total * 100), 1)
        except:
            pass
        
        ram_total_gb = 0
        ram_used_gb = 0
        ram_percent = 0
        try:
            mem_info = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        mem_info[parts[0].strip()] = int(parts[1].strip().split()[0])
            total_kb = mem_info.get('MemTotal', 0)
            free_kb = mem_info.get('MemFree', 0)
            buffers_kb = mem_info.get('Buffers', 0)
            cached_kb = mem_info.get('Cached', 0)
            used_kb = total_kb - free_kb - buffers_kb - cached_kb
            ram_total_gb = round(total_kb / (1024**2), 2)
            ram_used_gb = round(used_kb / (1024**2), 2)
            if total_kb > 0:
                ram_percent = round((used_kb / total_kb) * 100, 1)
        except:
            pass
        
        disk_total_gb = 0
        disk_used_gb = 0
        disk_percent = 0
        try:
            stat = os.statvfs('/storage/emulated/0/')
            total_bytes = stat.f_frsize * stat.f_blocks
            free_bytes = stat.f_frsize * stat.f_bfree
            used_bytes = total_bytes - free_bytes
            disk_total_gb = round(total_bytes / (1024**3), 1)
            disk_used_gb = round(used_bytes / (1024**3), 1)
            if total_bytes > 0:
                disk_percent = round((used_bytes / total_bytes) * 100, 1)
        except:
            pass
        
        db_size_mb = 0
        try:
            if 'sqlite' in settings.DATABASES['default']['ENGINE']:
                db_path = settings.DATABASES['default']['NAME']
                if os.path.exists(db_path):
                    db_size_mb = round(os.path.getsize(db_path) / (1024**2), 2)
        except:
            pass
        
        model_counts = {
            'Products': Product.objects.count(),
            'Customers': Customer.objects.count(),
            'Vendors': Vendor.objects.count(),
            'Sales': Sale.objects.count(),
            'Purchases': Purchase.objects.count(),
            'Sale Orders': SaleOrder.objects.count(),
            'Purchase Orders': PurchaseOrder.objects.count(),
            'Challans': DeliveryChallan.objects.count(),
            'GRNs': GoodsReceivedNote.objects.count(),
            'Inventory Items': Inventory.objects.count(),
            'Users': User.objects.count(),
        }
        total_records = sum(model_counts.values())
        
        yesterday = now() - timedelta(hours=24)
        recent_sales = Sale.objects.filter(sale_date__gte=yesterday).count()
        recent_purchases = Purchase.objects.filter(pur_date__gte=yesterday).count()
        recent_orders = SaleOrder.objects.filter(order_date__gte=yesterday).count()
        recent_pos = PurchaseOrder.objects.filter(order_date__gte=yesterday).count()
        recent_challans = DeliveryChallan.objects.filter(challan_date__gte=yesterday).count()
        recent_grns = GoodsReceivedNote.objects.filter(grn_date__gte=yesterday).count()
        recent_logs = LogEntry.objects.select_related('user').order_by('-action_time')[:10]
        
        last_backup = None
        try:
            backup_files = self.get_backup_files(request)
            if backup_files:
                last_backup = backup_files[0]
        except:
            pass
        
        license_valid = License.objects.filter(
            expiry_date__gte=now().date(), is_active=True
        ).exists()
        
        import django, sys
        context = {
            **self.each_context(request),
            "title": "System Health",
            "cpu_percent": cpu_percent,
            "cpu_count": cpu_count,
            "ram_total_gb": ram_total_gb,
            "ram_used_gb": ram_used_gb,
            "ram_percent": ram_percent,
            "disk_total_gb": disk_total_gb,
            "disk_used_gb": disk_used_gb,
            "disk_percent": disk_percent,
            "db_size_mb": db_size_mb,
            "total_records": total_records,
            "model_counts": model_counts,
            "recent_sales": recent_sales,
            "recent_purchases": recent_purchases,
            "recent_orders": recent_orders,
            "recent_pos": recent_pos,
            "recent_challans": recent_challans,
            "recent_grns": recent_grns,
            "recent_logs": recent_logs,
            "last_backup": last_backup,
            "license_valid": license_valid,
            "django_version": django.get_version(),
            "python_version": sys.version.split()[0],
            "uptime_str": "N/A",
        }
        return TemplateResponse(request, "admin/system_health.html", context)

    # ============================================
    # RANGE REPORTING VIEWS
    # ============================================
    def range_report_view(self, request):
        """Range report page with date filters"""
        from datetime import date, timedelta
        
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
        report_type = request.GET.get('report_type', 'sales')
        
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        context = {
            **self.each_context(request),
            "title": "📊 Range Reports",
            "from_date": from_date,
            "to_date": to_date,
            "report_type": report_type,
        }
        
        if report_type == 'sales':
            data = ReportManager.get_sales_by_date_range(from_date_obj, to_date_obj)
            context['sales_data'] = data
            context['top_products'] = ReportManager.get_top_products_by_date_range(from_date_obj, to_date_obj)
        elif report_type == 'purchases':
            data = ReportManager.get_purchases_by_date_range(from_date_obj, to_date_obj)
            context['purchase_data'] = data
        elif report_type == 'daily':
            context['daily_data'] = ReportManager.get_daily_summary(from_date_obj, to_date_obj)
        
        return TemplateResponse(request, "admin/range_report.html", context)

    def range_report_pdf(self, request):
        """Generate PDF for range report"""
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        report_type = request.GET.get('report_type', 'sales')
        
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "YOUR COMPANY"
        story.append(Paragraph(company_name, styles['Heading1']))
        story.append(Paragraph(f"Report: {from_date} to {to_date}", styles['Heading2']))
        
        if report_type == 'sales':
            data = ReportManager.get_sales_by_date_range(from_date_obj, to_date_obj)
            story.append(Paragraph(f"Total Sales: {data['count']}"))
            story.append(Paragraph(f"Total Amount: Rs. {data['total_amount']:,.2f}"))
            story.append(Paragraph(f"Total Profit: Rs. {data['total_profit']:,.2f}"))
        
        doc.build(story)
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')

    # ============================================
    # WHATSAPP VIEWS
    # ============================================
    def whatsapp_view(self, request):
        customers = Customer.objects.exclude(contact_number__isnull=True).exclude(contact_number='')
        return TemplateResponse(request, "admin/whatsapp_send.html", {
            **self.each_context(request), "title": "📱 WhatsApp Messages", "customers": customers,
        })

    def whatsapp_reminders_view(self, request):
        from ..whatsapp_utils import WhatsAppBulkSender
        if request.method == 'POST':
            customer_id = request.POST.get('customer_id')
            if customer_id:
                from ..whatsapp_utils import WhatsAppSender
                customer = Customer.objects.get(id=customer_id)
                WhatsAppSender.send_direct_message(customer.contact_number, request.POST.get('message', 'Payment reminder'))
                messages.success(request, "✅ Link generated!")
        return TemplateResponse(request, "admin/whatsapp_reminders.html", {
            **self.each_context(request), "title": "💰 Payment Reminders",
            "customers": WhatsAppBulkSender.generate_reminder_links(),
        })

    def whatsapp_daily_summary_view(self, request):
        from ..whatsapp_utils import WhatsAppSender
        if request.method == 'POST':
            phone = request.POST.get('phone', '')
            if phone:
                result = WhatsAppSender.send_daily_summary(phone)
                if result['success']:
                    messages.success(request, "✅ Daily summary link generated!")
                    return TemplateResponse(request, "admin/whatsapp_daily_summary.html", {
                        **self.each_context(request), "title": "📊 Daily Summary", "result": result,
                    })
        return TemplateResponse(request, "admin/whatsapp_daily_summary.html", {
            **self.each_context(request), "title": "📊 Daily Summary on WhatsApp",
        })


# Default Admin Site کو CustomAdminSite سے Replace کریں
admin.site = CustomAdminSite()


admin.site.site_header = "Welcome"


admin.site.site_title = "Web App"


admin.site.index_title = "Admin Dashboard"
