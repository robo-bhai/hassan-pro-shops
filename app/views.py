from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from django.shortcuts import get_object_or_404, render, redirect
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import models
from decimal import Decimal
from io import BytesIO
import json
import re

# Models import
from .models import (
    Sale, SaleItem, CompanyInfo, Product, Purchase, 
    PurchaseItem, Warehouse, Vendor, License, Customer,
    Inventory, StockBatch
)

# ============================================
# HOME & BASIC VIEWS
# ============================================

@login_required
def home_view(request):
    """
    Main dashboard view for the empty root path.
    """
    return render(request, 'home.html')


@login_required
def add_purchase_view(request):
    if request.method == 'POST':
        vendor_id = request.POST.get('vendor')
        warehouse_id = request.POST.get('warehouse')
        paid = request.POST.get('paid', '0')
        bill_no = request.POST.get('bill_no', '')

        try:
            purchase = Purchase.objects.create(
                vendor=Vendor.objects.get(id=vendor_id),
                warehouse=Warehouse.objects.get(id=warehouse_id),
                paid=Decimal(paid),
                bill_no=bill_no,
                pur_date=now(),
                created_by=request.user,
            )

            product_ids = request.POST.getlist('product')
            qtys = request.POST.getlist('qty')
            prices = request.POST.getlist('price')

            for i in range(len(product_ids)):
                product = Product.objects.get(id=product_ids[i])
                qty = Decimal(qtys[i])
                price = Decimal(prices[i])
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product=product,
                    qty=qty,
                    price=price,
                )
            
            messages.success(request, "Purchase added successfully.")
            return redirect('home')
        except Exception as e:
            messages.error(request, f"Error: {e}")

    products = Product.objects.all()
    vendors = Vendor.objects.all()
    warehouses = Warehouse.objects.all()
    return render(request, 'add_purchase.html', {
        'products': products,
        'vendors': vendors,
        'warehouses': warehouses
    })


def generate_invoice_pdf(request, sale_id):
    company = CompanyInfo.objects.first()
    sale = get_object_or_404(Sale, pk=sale_id)
    sale_items = sale.saleitem_set.all()
    
    total_without_discount = sum(item.total_amt for item in sale_items)
    total_amount = total_without_discount
    previous_balance = sale.previous_balance
    outstanding_balance = sale.outstanding_balance()
    total_outstanding = previous_balance + outstanding_balance
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#333333'),
        spaceAfter=30,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#666666'),
        spaceAfter=10
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=5
    )
    
    story = []
    
    if company:
        company_name = Paragraph(company.name or "Company Name", title_style)
        story.append(company_name)
        
        if company.address:
            story.append(Paragraph(company.address, normal_style))
        if company.contact_number:
            story.append(Paragraph(f"Phone: {company.contact_number}", normal_style))
        if company.email:
            story.append(Paragraph(f"Email: {company.email}", normal_style))
        
        story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    invoice_details = [
        ["Bill No:", str(sale.bill_no)],
        ["Invoice Date:", sale.sale_date.strftime("%d-%m-%Y")],
        ["Customer Name:", sale.customer.name],
        ["Contact Number:", sale.customer.contact_number or "N/A"],
        ["Address:", sale.customer.address or "N/A"],
    ]
    
    details_table = Table(invoice_details, colWidths=[2*inch, 4*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#333333')),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#999999')),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 0.2*inch))
    
    product_data = [['S.No', 'Product Name', 'Quantity', 'Price', 'Total Amount']]
    
    for idx, item in enumerate(sale_items, 1):
        product_data.append([
            str(idx),
            item.product.name,
            str(item.qty),
            f"₹{item.price:,.2f}",
            f"₹{item.total_amt:,.2f}"
        ])
    
    product_data.append(['', '', '', 'Total:', f"₹{total_amount:,.2f}"])
    
    product_table = Table(product_data, colWidths=[0.5*inch, 2.5*inch, 1*inch, 1.5*inch, 1.5*inch])
    product_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -2), 'LEFT'),
        ('ALIGN', (4, 1), (4, -2), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('BACKGROUND', (3, -1), (4, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (3, -1), (4, -1), 'Helvetica-Bold'),
        ('SPAN', (0, -1), (2, -1)),
    ]))
    story.append(product_table)
    story.append(Spacer(1, 0.2*inch))
    
    payment_data = [
        ["Previous Balance:", f"₹{previous_balance:,.2f}"],
        ["Total Amount:", f"₹{total_amount:,.2f}"],
        ["Paid Amount:", f"₹{sale.paid:,.2f}"],
        ["Outstanding Balance:", f"₹{outstanding_balance:,.2f}"],
        ["Total Outstanding:", f"₹{total_outstanding:,.2f}"],
    ]
    
    payment_table = Table(payment_data, colWidths=[2*inch, 2*inch])
    payment_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9f9f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(payment_table)
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("Terms & Conditions:", heading_style))
    story.append(Paragraph("1. Goods once sold will not be taken back.", normal_style))
    story.append(Paragraph("2. Payment is due within 15 days.", normal_style))
    
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated on: {now().strftime('%d-%m-%Y %H:%M:%S')}", normal_style))
    story.append(Paragraph("Thank you for your business!", normal_style))
    
    doc.build(story)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{sale.pk}.pdf"'
    response.write(pdf)
    
    return response


def some_default_view(request):
    return HttpResponse("Sale ID is required to generate an invoice.")


def license_expired_view(request):
    msg = request.GET.get('msg', 'License Issue')
    return render(request, 'license_expired.html', {'message': msg})


# ============================================
# BARCODE SEARCH (AJAX)
# ============================================

from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def find_product_by_barcode(request):
    """AJAX view to find product by barcode"""
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
                'price': str(product.price)
            }
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product not found'})


# ============================================
# POS VIEWS
# ============================================

@login_required
def pos_view(request):
    """Main POS Interface"""
    warehouses = Warehouse.objects.all()
    customers = Customer.objects.all()
    products = Product.objects.filter(inventory__stock__gt=0).distinct()[:50]
    
    # Default customer (Cash Customer)
    default_customer = Customer.objects.filter(name__icontains='cash').first()
    if not default_customer:
        default_customer = Customer.objects.first()
    
    context = {
        'warehouses': warehouses,
        'customers': customers,
        'products': products,
        'default_customer': default_customer,
        'default_warehouse': Warehouse.objects.first(),
    }
    return render(request, 'pos/pos_interface.html', context)


def pos_get_products(request):
    """Get all products for POS grid"""
    warehouse_id = request.GET.get('warehouse')
    products = Product.objects.filter(inventory__stock__gt=0).distinct()
    
    if warehouse_id:
        products = products.filter(inventory__warehouse_id=warehouse_id, inventory__stock__gt=0)
    
    product_list = []
    for p in products[:50]:
        stock = Inventory.get_stock(p, warehouse_id) if warehouse_id else 0
        product_list.append({
            'id': p.id,
            'name': p.name,
            'barcode': p.barcode or '',
            'price': str(p.price),
            'stock': stock,
            'unit': p.unit.name if p.unit else 'pcs',
        })
    
    return JsonResponse({'products': product_list})


def pos_search_product(request):
    """Search product by name or barcode"""
    query = request.GET.get('q', '').strip()
    warehouse_id = request.GET.get('warehouse')
    
    if not query:
        return JsonResponse({'products': []})
    
    products = Product.objects.filter(
        models.Q(name__icontains=query) | 
        models.Q(barcode__icontains=query) |
        models.Q(serial_no__icontains=query)
    ).filter(inventory__stock__gt=0).distinct()[:20]
    
    if warehouse_id:
        products = products.filter(inventory__warehouse_id=warehouse_id, inventory__stock__gt=0)
    
    product_list = []
    for p in products:
        stock = Inventory.get_stock(p, warehouse_id) if warehouse_id else 0
        product_list.append({
            'id': p.id,
            'name': p.name,
            'barcode': p.barcode or '',
            'price': str(p.price),
            'stock': stock,
            'unit': p.unit.name if p.unit else 'pcs',
        })
    
    return JsonResponse({'products': product_list})


@require_POST
@csrf_exempt
def pos_quick_add(request):
    """Quick add product to cart by barcode"""
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    barcode = re.sub(r'[^0-9]', '', barcode)
    warehouse_id = data.get('warehouse')
    
    if not barcode:
        return JsonResponse({'success': False, 'message': 'No barcode provided'})
    
    try:
        product = Product.objects.get(barcode=barcode)
        
        # Check stock
        stock = Inventory.get_stock(product, warehouse_id)
        if stock <= 0:
            return JsonResponse({'success': False, 'message': f'Out of stock: {product.name}'})
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'price': str(product.price),
                'stock': stock,
                'unit': product.unit.name if product.unit else 'pcs',
            }
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product not found'})


@require_POST
@csrf_exempt
def pos_complete_sale(request):
    """Complete POS sale"""
    data = json.loads(request.body)
    
    customer_id = data.get('customer_id')
    warehouse_id = data.get('warehouse_id')
    items = data.get('items', [])
    payment_method = data.get('payment_method', 'cash')
    paid_amount = Decimal(str(data.get('paid_amount', 0)))
    discount = Decimal(str(data.get('discount', 0)))
    
    if not items:
        return JsonResponse({'success': False, 'message': 'Cart is empty'})
    
    try:
        customer = Customer.objects.get(id=customer_id)
        warehouse = Warehouse.objects.get(id=warehouse_id)
        
        # Generate bill number
        last_sale = Sale.objects.order_by('-id').first()
        next_id = (last_sale.id + 1) if last_sale else 1
        bill_no = f"POS-{now().strftime('%Y%m%d')}-{next_id:04d}"
        
        # Create sale
        sale = Sale.objects.create(
            warehouse=warehouse,
            bill_no=bill_no,
            customer=customer,
            sale_date=now(),
            paid=paid_amount,
            discount_value=discount,
            created_by=request.user,
        )
        
        total_amount = Decimal('0.0')
        
        for item in items:
            product = Product.objects.get(id=item['id'])
            qty = Decimal(str(item['qty']))
            price = Decimal(str(item['price']))
            
            sale_item = SaleItem.objects.create(
                sale=sale,
                product=product,
                qty=qty,
                price=price,
            )
            total_amount += sale_item.total_amt
        
        # Calculate change
        total_after_discount = total_amount - discount
        change = paid_amount - total_after_discount
        if change < 0:
            change = Decimal('0.0')
        
        return JsonResponse({
            'success': True,
            'sale_id': sale.id,
            'bill_no': bill_no,
            'total': str(total_after_discount),
            'discount': str(discount),
            'paid': str(paid_amount),
            'change': str(change),
            'message': 'Sale completed successfully!'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@require_POST
@csrf_exempt
def pos_hold_sale(request):
    """Hold sale for later (save to session)"""
    data = json.loads(request.body)
    request.session['held_sale'] = data
    return JsonResponse({'success': True, 'message': 'Sale held'})


def pos_get_cart(request):
    """Get held sale from session"""
    held_sale = request.session.get('held_sale', {})
    return JsonResponse(held_sale)


def pos_print_receipt(request, sale_id):
    """Generate thermal receipt for POS"""
    sale = get_object_or_404(Sale, id=sale_id)
    company = CompanyInfo.objects.first()
    
    context = {
        'sale': sale,
        'company': company,
        'items': sale.saleitem_set.all(),
        'date': now(),
    }
    
    return render(request, 'pos/receipt.html', context)


# ============================================
# SALE RETURN (Optional)
# ============================================

@login_required
def process_sale_return(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    data = request.POST

    try:
        from .models import SaleRetrn, SaleRetrnItem
        sale_return = SaleRetrn.objects.create(sale=sale, return_reason=data.get('note', ''))

        for item in data.getlist('items'):
            product = get_object_or_404(Product, id=item['product_id'])
            SaleRetrnItem.objects.create(
                sale_return=sale_return,
                product=product,
                qty=item['qty'],
                price=item['price']
            )

        return JsonResponse({"status": "success", "refund": str(sale_return.total_amt)})
    except ImportError:
        return JsonResponse({"status": "error", "message": "Return models not found."}, status=500)
        
        
# ============================================
# DATABASE BACKUP & RCLONE CLOUD MANAGEMENT
# ============================================
import json
import os
import subprocess
import shutil
import time

# Configurations (Termux paths and Rclone settings)
BACKUP_DIR = "/storage/emulated/0/Download/Backups"
REMOTE_NAME = "gdrive"
REMOTE_DIR = "TermuxBackups"


def run_rclone_cmd(cmd):
    """Utility to execute shell commands securely."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode == 0, result.stderr


def get_remote_backups():
    """Fetches live remote files from Google Drive using lsjson, sorted newest first."""
    cmd = ["rclone", "lsjson", f"{REMOTE_NAME}:{REMOTE_DIR}"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and result.stdout:
        try:
            files_data = json.loads(result.stdout)
            # Filter directories, keep only real files
            files_only = [f for f in files_data if not f.get("IsDir")]
            # Sort chronologically (Newest first)
            files_only.sort(key=lambda x: x.get("ModTime", ""), reverse=True)
            return files_only
        except Exception:
            return []
    return []


@login_required
def database_backup_view(request):
    """
    Handles local backup generation, rclone cloud uploads, 
    rolling 3-file retention, and interactive database restoration.
    """
    restore_file = request.GET.get("restore")
    delete_file = request.GET.get("delete")

    # ---- 1. CLOUD RESTORE LOGIC ----
    if restore_file:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        local_path = os.path.join(BACKUP_DIR, restore_file)

        # Download the file from Google Drive to local Backups folder
        success, err = run_rclone_cmd([
            "rclone", "copyto", 
            f"{REMOTE_NAME}:{REMOTE_DIR}/{restore_file}", 
            local_path
        ])

        if success:
            # Check if it's an SQLite backup and replace current database file
            if restore_file.endswith(".sqlite3") and os.path.exists(local_path):
                try:
                    # Closing any active connections before database replacement is ideal
                    shutil.copy(local_path, "db.sqlite3")
                    messages.success(request, f"🎉 '{restore_file}' successfully downloaded and database restored!")
                except Exception as db_err:
                    messages.error(request, f"❌ Local replacement failed: {db_err}")
            else:
                messages.success(request, f"📥 File '{restore_file}' downloaded safely to {BACKUP_DIR}. (Process JSON restore manually if needed).")
        else:
            messages.error(request, f"❌ Cloud restore download failed: {err}")
        return redirect("database_backup")

    # ---- 2. CLOUD DELETE LOGIC ----
    if delete_file:
        success, err = run_rclone_cmd([
            "rclone", "deletefile", 
            f"{REMOTE_NAME}:{REMOTE_DIR}/{delete_file}"
        ])
        if success:
            messages.success(request, f"🗑️ '{delete_file}' deleted permanently from Google Drive.")
        else:
            messages.error(request, f"❌ Cloud delete failed: {err}")
        return redirect("database_backup")

    # ---- 3. CREATE BACKUP AND SYNC LOGIC (POST) ----
    if request.method == "POST":
        action = request.POST.get("action")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        timestamp = int(time.time())
        filename = ""

        if action == "json_backup":
            filename = f"backup_full_{timestamp}.json"
            local_path = os.path.join(BACKUP_DIR, filename)
            # Execute Django standard dumpdata
            subprocess.run(f"python manage.py dumpdata > {local_path}", shell=True)

        elif action == "sqlite_backup":
            filename = f"backup_{timestamp}.sqlite3"
            local_path = os.path.join(BACKUP_DIR, filename)
            # Direct binary copy of db.sqlite3
            if os.path.exists("db.sqlite3"):
                shutil.copy("db.sqlite3", local_path)
            else:
                messages.error(request, "❌ Central db.sqlite3 file not found.")
                return redirect("database_backup")

        # Sync/Copy the updated local backups folder to Google Drive
        success, err = run_rclone_cmd(["rclone", "copy", BACKUP_DIR, f"{REMOTE_NAME}:{REMOTE_DIR}"])

        if success:
            # Active 3-files maximum retention enforcement rules
            remote_files = get_remote_backups()
            if len(remote_files) > 3:
                # Target files older than the top 3 index
                for old_file in remote_files[3:]:
                    old_name = old_file["Name"]
                    run_rclone_cmd(["rclone", "deletefile", f"{REMOTE_NAME}:{REMOTE_DIR}/{old_name}"])

            messages.success(request, f"🚀 Backup '{filename}' created and safely synced to Google Drive!")
        else:
            messages.error(request, f"❌ Cloud backup sync failed: {err}")

        return redirect("database_backup")

    # ---- 4. RENDER DATA PROCESSING ----
    cloud_files = get_remote_backups()
    
    backup_files = [f["Name"] for f in cloud_files]
    file_sizes = {f["Name"]: f"{round(f['Size'] / 1024, 2)} KB" for f in cloud_files}
    file_dates = {f["Name"]: f["ModTime"][:19].replace("T", " ") for f in cloud_files}

    context = {
        "backup_dir": f"{REMOTE_NAME}:{REMOTE_DIR} (Cloud Link)",
        "backup_files": backup_files,
        "file_sizes": file_sizes,
        "file_dates": file_dates,
    }
    return render(request, "database_backup.html", context)
        
        