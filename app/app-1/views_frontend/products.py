"""Frontend views: products."""
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper
from ..models import *
import json
import openpyxl
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Value, DecimalField
from decimal import Decimal
from datetime import datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction, models as django_models
from ..models import Category, Brand, Unit, Location, Types, CompanyInfo, Product
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


@login_required
def get_product_stock(request):
    """AJAX: Get product stock in warehouse"""
    product_id = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    
    if not product_id:
        return JsonResponse({'success': False, 'message': 'Product ID required'})
    
    stock = Inventory.get_stock(product_id, warehouse_id) if warehouse_id else 0
    
    return JsonResponse({
        'success': True,
        'stock': float(stock)
    })


@login_required
def products_list_api(request):
    """AJAX: Get all products for text matching"""
    warehouse_id = request.GET.get('warehouse_id')
    
    products = Product.objects.all().values('id', 'name', 'price')
    
    # Add stock info if warehouse provided
    if warehouse_id:
        for product in products:
            inv = Inventory.objects.filter(product_id=product['id'], warehouse_id=warehouse_id).first()
            product['stock'] = inv.stock if inv else 0
    else:
        for product in products:
            product['stock'] = 0
    
    return JsonResponse({
        'success': True,
        'products': list(products),
        'count': len(products)
    })


@login_required
def get_batch_selling_price(request):
    """AJAX: Get batch selling price for a product in a warehouse"""
    product_id = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    
    if not product_id:
        return JsonResponse({'success': False, 'message': 'Product ID required'})
    
    try:
        product = Product.objects.get(pk=product_id)
        
        # Find batch with selling price > 0 in given warehouse
        batch = None
        if warehouse_id:
            batch = StockBatch.objects.filter(
                product=product,
                warehouse_id=warehouse_id,
                remaining_qty__gt=0,
                selling_price__gt=0
            ).order_by('id').first()
        
        default_price = str(product.price)
        
        if batch and batch.selling_price > 0:
            return JsonResponse({
                'success': True,
                'price': str(batch.selling_price),
                'has_batch_price': True,
                'product_id': product.id,
                'product_name': product.name,
            })
        else:
            return JsonResponse({
                'success': True,
                'price': default_price,
                'has_batch_price': False,
                'product_id': product.id,
                'product_name': product.name,
            })
            
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def get_product_by_alias(request):
    """AJAX: Product alias se product search karo"""
    alias = request.GET.get('alias', '').strip().lower()
    
    if not alias:
        return JsonResponse({'success': False, 'message': 'No alias provided'})
    
    try:
        # User ke aliases mein search karo
        product_alias = ProductAlias.objects.filter(alias__iexact=alias).first()
        
        if product_alias:
            product = product_alias.product
        else:
            # Agar alias na mile to normal search
            product = Product.objects.filter(
                Q(name__icontains=alias) |
                Q(barcode__icontains=alias) |
                Q(serial_no__icontains=alias)
            ).first()
        
        if not product:
            return JsonResponse({'success': False, 'message': f'Product "{alias}" not found!'})
        
        warehouse_id = request.GET.get('warehouse_id', '')
        price = Decimal('0.0')
        stock = 0
        has_selling_price = False
        
        # Get unit name
        unit_name = product.unit.name if product.unit else ''
        
        if warehouse_id:
            batch = StockBatch.objects.filter(
                product=product,
                warehouse_id=warehouse_id,
                remaining_qty__gt=0,
                selling_price__gt=0
            ).order_by('id').first()
            
            if batch:
                price = batch.selling_price
                has_selling_price = True
            else:
                price = product.price
                has_selling_price = False
            
            inventory = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first()
            stock = inventory.stock if inventory else 0
        else:
            price = product.price
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode or '',
                'serial_no': product.serial_no or '',
                'price': str(price),
                'stock': stock,
                'unit': unit_name,  # ✅ Unit added
                'has_selling_price': has_selling_price,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def create_product_alias(request):
    """AJAX: User apna product alias create kare"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            alias = data.get('alias', '').strip().lower()
            
            if not product_id or not alias:
                return JsonResponse({'success': False, 'message': 'Product and alias required!'})
            
            product = get_object_or_404(Product, id=product_id)
            
            # Check if alias already exists for this product
            existing = ProductAlias.objects.filter(alias=alias).first()
            if existing:
                return JsonResponse({
                    'success': False, 
                    'message': f'Alias "{alias}" already exists for product "{existing.product.name}"!'
                })
            
            # Create new alias
            product_alias = ProductAlias.objects.create(
                product=product,
                alias=alias,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Alias "{alias}" created for "{product.name}"!',
                'alias': {
                    'id': product_alias.id,
                    'name': alias,
                    'product_id': product.id,
                    'product_name': product.name
                }
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def get_product_aliases(request):
    """AJAX: Get all aliases for a product"""
    product_id = request.GET.get('product_id')
    
    if not product_id:
        return JsonResponse({'success': False, 'message': 'Product ID required'})
    
    aliases = ProductAlias.objects.filter(product_id=product_id).values('id', 'alias')
    
    return JsonResponse({
        'success': True,
        'aliases': list(aliases)
    })


@login_required
def delete_product_alias(request):
    """AJAX: Delete a product alias"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            alias_id = data.get('alias_id')
            
            alias = get_object_or_404(ProductAlias, id=alias_id)
            alias.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Alias deleted successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def batch_list(request):
    """
    Stock batches with stats
    ✅ FIXED: ExpressionWrapper for FloatField * DecimalField
    """
    batches = StockBatch.objects.select_related(
        'product', 'warehouse', 'product__unit',
        'purchase_item', 'purchase_item__purchase',
        'purchase_item__purchase__vendor'
    ).order_by('-id')
    
    search = request.GET.get('search', '')
    if search:
        batches = batches.filter(
            Q(product__name__icontains=search) |
            Q(purchase_item__purchase__bill_no__icontains=search) |
            Q(product__serial_no__icontains=search)
        )
    
    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        batches = batches.filter(warehouse_id=warehouse_id)
    
    stock_status = request.GET.get('stock_status', '')
    if stock_status == 'in_stock':
        batches = batches.filter(remaining_qty__gt=0)
    elif stock_status == 'sold':
        batches = batches.filter(remaining_qty__lte=0)
    elif stock_status == 'has_sp':
        batches = batches.filter(selling_price__gt=0)
    elif stock_status == 'no_sp':
        batches = batches.filter(selling_price=0, remaining_qty__gt=0)
    
    # ✅ FIX: Use ExpressionWrapper
    batches = batches.annotate(
        annotated_stock_value=ExpressionWrapper(
            F('remaining_qty') * F('price'),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        annotated_potential_profit=ExpressionWrapper(
            (F('selling_price') - F('price')) * F('remaining_qty'),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
    )
    
    # ✅ Aggregate with ExpressionWrapper
    stats = batches.aggregate(
        total_batches=Count('id', distinct=True),
        total_stock_value=Coalesce(
            Sum(
                ExpressionWrapper(
                    F('remaining_qty') * F('price'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                ),
                filter=Q(remaining_qty__gt=0)
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_potential_profit=Coalesce(
            Sum(
                ExpressionWrapper(
                    (F('selling_price') - F('price')) * F('remaining_qty'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                ),
                filter=Q(remaining_qty__gt=0, selling_price__gt=0)
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        active_batches=Count('id', filter=Q(remaining_qty__gt=0)),
    )
    
    paginator = Paginator(batches, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'warehouses': Warehouse.objects.all(),
        'selected_warehouse': warehouse_id,
        'stock_status': stock_status,
        'total_batches': stats['total_batches'],
        'total_stock_value': stats['total_stock_value'],
        'total_potential_profit': stats['total_potential_profit'],
        'active_batches': stats['active_batches'],
    }
    return render(request, 'inventory/batches.html', context)


@require_POST
@login_required
def update_batch_selling_price(request):
    """AJAX: Update batch selling price"""
    import json
    data = json.loads(request.body)
    batch_id = data.get('batch_id')
    selling_price = data.get('selling_price')
    
    if not batch_id or not selling_price:
        return JsonResponse({'success': False, 'message': 'Missing data'})
    
    try:
        batch = StockBatch.objects.get(id=batch_id)
        sp = Decimal(str(selling_price))
        
        if sp < batch.price:
            return JsonResponse({
                'success': False, 
                'message': f'Selling price (Rs. {sp:,.2f}) cannot be less than cost price (Rs. {batch.price:,.2f})!'
            })
        
        batch.selling_price = sp
        batch.save()
        
        return JsonResponse({
            'success': True,
            'profit': str(batch.profit_per_unit()),
            'message': f'✅ Selling price updated to Rs. {sp:,.2f}'
        })
    except StockBatch.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Batch not found'})            


@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        try:
            product.name = request.POST.get('name')
            product.serial_no = request.POST.get('serial_no', '') or None
            product.description = request.POST.get('description', '')
            product.used = request.POST.get('used', '')
            product.low_stock_threshold = float(request.POST.get('low_stock_threshold', 10))
            product.unit_id = request.POST.get('unit') or None
            product.category_id = request.POST.get('category') or None
            product.brand_id = request.POST.get('brand') or None
            product.location_id = request.POST.get('location') or None
            product.types_id = request.POST.get('types') or None
            product.is_active = request.POST.get('is_active') == 'on'
            
            new_barcode = request.POST.get('barcode', '').strip()
            if new_barcode:
                product.barcode = new_barcode
                product.use_custom_barcode = True
            
            # ✅ Image upload
            if request.FILES.get('image'):
                product.image = request.FILES['image']
            
            # ✅ Image remove
            if request.POST.get('remove_image') == 'on':
                product.image = None
            
            product.save()
            messages.success(request, f'✅ Product "{product.name}" updated!')
            return redirect('product_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'product': product,
        'units': Unit.objects.all(),
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
        'locations': Location.objects.all(),
        'types': Types.objects.all(),
    }
    return render(request, 'products/update.html', context)


@login_required
def inventory_list(request):
    """
    Inventory list with stock value — OPTIMIZED
    ✅ Cost price based (not sale price)
    """
    from django.db.models import Sum, Count, Q, F, Value, DecimalField, ExpressionWrapper
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    # ✅ Base queryset
    items = Inventory.objects.select_related(
        'product', 'warehouse', 'product__category',
        'product__brand', 'product__unit', 'product__location'
    ).order_by('product__name')
    
    # ✅ Search
    search = request.GET.get('search', '')
    if search:
        items = items.filter(
            Q(product__name__icontains=search) |
            Q(product__serial_no__icontains=search) |
            Q(product__barcode__icontains=search)
        )
    
    # ✅ Warehouse filter
    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        items = items.filter(warehouse_id=warehouse_id)
    
    # ✅ Stock status filter
    stock_status = request.GET.get('stock_status', '')
    if stock_status == 'low':
        items = items.filter(stock__lt=F('product__low_stock_threshold'), stock__gt=0)
    elif stock_status == 'normal':
        items = items.filter(stock__gte=F('product__low_stock_threshold'))
    elif stock_status == 'zero':
        items = items.filter(stock__lte=0)
    
    # ✅ Calculate avg cost from batches (FIFO weighted average)
    total_stock_value = Decimal('0.00')
    items_list = []
    
    for item in items:
        # Get all active batches for this product in this warehouse
        batches = StockBatch.objects.filter(
            product=item.product,
            warehouse=item.warehouse,
            remaining_qty__gt=0
        )
        
        total_cost = Decimal('0.00')
        total_qty = Decimal('0.00')
        
        for batch in batches:
            qty = Decimal(str(batch.remaining_qty))
            price = Decimal(str(batch.price))
            total_cost += qty * price
            total_qty += qty
        
        # ✅ Average cost per unit
        if total_qty > 0:
            item.avg_cost = total_cost / total_qty
        else:
            # Fallback: use product's original_price or 0
            item.avg_cost = item.product.original_price or Decimal('0.00')
        
        # ✅ Stock value based on COST (not sale price)
        item.cost_stock_value = Decimal(str(item.stock)) * item.avg_cost
        
        # ✅ Stock percent for progress bar
        threshold = item.product.low_stock_threshold
        if threshold > 0 and item.stock > 0:
            item.stock_percent = round(min((item.stock / (threshold * 3)) * 100, 100))
        else:
            item.stock_percent = 0
        
        total_stock_value += item.cost_stock_value
        items_list.append(item)
    
    # ✅ Pagination (after processing)
    paginator = Paginator(items_list, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ✅ Statistics
    low_stock_count = sum(1 for item in items_list if item.stock > 0 and item.stock < item.product.low_stock_threshold)
    normal_stock_count = sum(1 for item in items_list if item.stock >= item.product.low_stock_threshold)
    total_items = len(items_list)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'warehouses': Warehouse.objects.all(),
        'selected_warehouse': warehouse_id,
        'stock_status': stock_status,
        'total_items': total_items,
        'total_stock_value': total_stock_value,
        'low_stock_count': low_stock_count,
        'normal_stock_count': normal_stock_count,
        'total_products': Product.objects.count(),
    }
    return render(request, 'inventory/list.html', context)


# ============================================
# AJAX VIEWS
# ============================================
@login_required
def get_product_by_barcode(request):
    """AJAX: Barcode, Serial Number, ya Product Name se product search - SIRF BATCH SELLING PRICE"""
    barcode = request.GET.get('barcode', '').strip()
    serial = request.GET.get('serial', '').strip()
    
    query = barcode or serial
    
    if not query:
        return JsonResponse({'success': False, 'message': 'No query provided'})
    
    product = None
    
    if barcode:
        try:
            product = Product.objects.get(barcode=barcode)
        except Product.DoesNotExist:
            pass
    
    if not product and serial:
        try:
            product = Product.objects.get(serial_no__iexact=serial)
        except Product.DoesNotExist:
            pass
    
    if not product:
        product = Product.objects.filter(name__icontains=query).first()
    
    if not product:
        return JsonResponse({'success': False, 'message': 'Product not found'})
    
    warehouse_id = request.GET.get('warehouse_id', '')
    price = Decimal('0.0')
    stock = 0
    has_selling_price = False
    message = ''
    
    if warehouse_id:
        batch = StockBatch.objects.filter(
            product=product,
            warehouse_id=warehouse_id,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if batch:
            price = batch.selling_price
            has_selling_price = True
        else:
            price = Decimal('0.0')
            has_selling_price = False
        
        inventory = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first()
        stock = inventory.stock if inventory else 0
    else:
        batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).first()
        
        if batch:
            price = batch.selling_price
            has_selling_price = True
        else:
            price = Decimal('0.0')
            has_selling_price = False
        
        stock = sum(inv.stock for inv in Inventory.objects.filter(product=product))
    
    return JsonResponse({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode or '',
            'serial_no': product.serial_no or '',
            'price': str(price),
            'stock': stock,
            'unit': product.unit.name if product.unit else '',
            'has_selling_price': has_selling_price,
            'message': message,
        }
    })


@login_required
def product_create(request):
    if request.method == 'POST':
        try:
            product = Product(
                serial_no=request.POST.get('serial_no', '') or None,
                name=request.POST.get('name'),
                description=request.POST.get('description', ''),
                barcode=request.POST.get('barcode', '') or None,
                used=request.POST.get('used', ''),
                low_stock_threshold=float(request.POST.get('low_stock_threshold', 10)),
                unit_id=request.POST.get('unit') or None,
                category_id=request.POST.get('category') or None,
                brand_id=request.POST.get('brand') or None,
                location_id=request.POST.get('location') or None,
                types_id=request.POST.get('types') or None,
                is_active=request.POST.get('is_active') == 'on',
            )
            
            if request.POST.get('barcode', '').strip():
                product.use_custom_barcode = True
            
            # ✅ Image upload
            if request.FILES.get('image'):
                product.image = request.FILES['image']
            
            product.save()
            messages.success(request, f'✅ Product "{product.name}" created successfully!')
            return redirect('product_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('product_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'units': Unit.objects.all(),
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
        'locations': Location.objects.all(),
        'types': Types.objects.all(),
    }
    return render(request, 'products/create.html', context)


@login_required
def get_product_by_name(request):
    """AJAX: Product name se product search - For Manual/OCR/Voice input"""
    
    name = request.GET.get('name', '').strip()
    warehouse_id = request.GET.get('warehouse_id', '')
    
    if not name:
        return JsonResponse({'success': False, 'message': 'Product name required'})
    
    # Product search by name (partial match)
    products = Product.objects.filter(
        Q(name__icontains=name) |
        Q(barcode__icontains=name) |
        Q(serial_no__icontains=name)
    )
    
    # Check aliases
    alias_products = ProductAlias.objects.filter(alias__icontains=name).values_list('product_id', flat=True)
    products = products | Product.objects.filter(id__in=alias_products)
    
    products = products.distinct()
    
    if not products.exists():
        return JsonResponse({'success': False, 'message': f'Product "{name}" not found!'})
    
    # Get first product
    product = products.first()
    
    # Get price and stock
    price = Decimal('0.0')
    stock = 0
    has_selling_price = False
    
    if warehouse_id:
        batch = StockBatch.objects.filter(
            product=product,
            warehouse_id=warehouse_id,
            remaining_qty__gt=0
        ).order_by('id').first()
        
        if batch:
            price = batch.price
        else:
            price = product.price
        
        inventory = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first()
        stock = inventory.stock if inventory else 0
    else:
        price = product.price
    
    return JsonResponse({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode or '',
            'serial_no': product.serial_no or '',
            'price': str(price),
            'stock': stock,
            'unit': product.unit.name if product.unit else '',
            'has_selling_price': has_selling_price,
        }
    })


@login_required
def search_products_ajax(request):
    """
    AJAX: Live product search for SALE with batch information
    - Shows selling price from latest batch
    - Shows stock
    - Shows batch count and latest batch price
    - Shows batch remaining quantity
    - Warning if no selling price set
    """
    query = request.GET.get('q', '').strip()
    warehouse_id = request.GET.get('warehouse_id', '')
    
    if len(query) < 1:
        return JsonResponse({'success': True, 'products': []})
    
    products = Product.objects.filter(
        Q(name__icontains=query) |
        Q(serial_no__icontains=query) |
        Q(barcode__icontains=query)
    ).distinct()[:15]
    
    result = []
    for product in products:
        stock = 0
        price = 0
        selling_price = 0
        has_selling_price = False
        warning_message = ''
        batch_count = 0
        latest_batch_price = 0
        batch_remaining_qty = 0  # ✅ NEW: Batch remaining quantity
        batch_id = None  # ✅ NEW: Batch ID
        
        if warehouse_id:
            inventory = Inventory.objects.filter(product=product, warehouse_id=warehouse_id).first()
            stock = inventory.stock if inventory else 0
            
            # ✅ Get all batches with remaining stock
            batches = StockBatch.objects.filter(
                product=product,
                warehouse_id=warehouse_id,
                remaining_qty__gt=0
            ).order_by('id')
            
            batch_count = batches.count()
            
            # ✅ Get latest batch (most recent)
            latest_batch = batches.first()
            
            if latest_batch:
                latest_batch_price = float(latest_batch.price)
                selling_price = float(latest_batch.selling_price) if latest_batch.selling_price > 0 else 0
                has_selling_price = selling_price > 0
                batch_remaining_qty = float(latest_batch.remaining_qty)  # ✅ NEW
                batch_id = latest_batch.id  # ✅ NEW
                
                if not has_selling_price and stock > 0:
                    warning_message = '⚠️ No selling price set for this batch!'
            else:
                price = float(product.price)
                warning_message = '⚠️ No stock batch found with selling price!'
        else:
            price = float(product.price)
            # Check any warehouse
            any_batch = StockBatch.objects.filter(
                product=product,
                remaining_qty__gt=0
            ).order_by('id').first()
            
            if any_batch:
                batch_count = StockBatch.objects.filter(
                    product=product,
                    remaining_qty__gt=0
                ).count()
                latest_batch_price = float(any_batch.price)
                selling_price = float(any_batch.selling_price) if any_batch.selling_price > 0 else 0
                has_selling_price = selling_price > 0
                batch_remaining_qty = float(any_batch.remaining_qty)  # ✅ NEW
                batch_id = any_batch.id  # ✅ NEW
            else:
                warning_message = '⚠️ Select a warehouse to check selling price!'
        
        display_price = selling_price if has_selling_price else 0
        
        result.append({
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode or '',
            'serial_no': product.serial_no or '',
            'price': str(display_price),  # Selling price (0 if not set)
            'cost_price': str(latest_batch_price if latest_batch_price > 0 else price),
            'stock': stock,
            'unit': product.unit.name if product.unit else '',
            'has_selling_price': has_selling_price,
            'warning': warning_message,
            'selling_price': str(selling_price) if has_selling_price else '0',
            'batch_count': batch_count,
            'latest_batch_price': str(latest_batch_price) if latest_batch_price > 0 else '0',
            'batch_remaining_qty': str(batch_remaining_qty),  # ✅ NEW
            'batch_id': batch_id,  # ✅ NEW
        })
    
    return JsonResponse({'success': True, 'products': result})


@login_required
def product_import_export(request):
    """Main import/export page with statistics"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can import/export products.')
        return redirect('dashboard')
    
    # Get statistics
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    categories_count = Category.objects.count()
    brands_count = Brand.objects.count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_products': total_products,
        'active_products': active_products,
        'categories_count': categories_count,
        'brands_count': brands_count,
    }
    return render(request, 'products/import_export.html', context)


@login_required
def product_export_template(request):
    """Download CSV template for product import"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="product_import_template.csv"'
    
    writer = csv.writer(response)
    
    # Headers with descriptions
    headers = [
        'Name*', 'Serial No', 'Barcode', 'Description', 
        'Category', 'Brand', 'Unit', 'Location', 'Type',
        'Price', 'Low Stock Threshold', 'Used For', 'Is Active'
    ]
    writer.writerow(headers)
    
    # Add sample rows with explanations
    sample_rows = [
        ['Sample Product 1', 'SN-001', '1234567890', 'High quality electronic device',
         'Electronics', 'Samsung', 'piece', 'Main Warehouse', 'Consumer',
         '100.00', '10', 'Retail', 'True'],
        ['Sample Product 2', 'SN-002', '0987654321', 'Durable household item',
         'Home & Kitchen', 'LG', 'piece', 'Branch A', 'Commercial',
         '250.00', '5', 'Wholesale', 'True'],
        ['Sample Product 3', 'SN-003', '', 'Budget friendly option',
         'Electronics', 'Generic', 'piece', 'Main Warehouse', 'Budget',
         '50.00', '15', 'Retail', 'True'],
    ]
    
    for row in sample_rows:
        writer.writerow(row)
    
    # Add instruction row (commented)
    writer.writerow([])
    writer.writerow(['# INSTRUCTIONS:'])
    writer.writerow(['# * Name is required'])
    writer.writerow(['# Serial No and Barcode should be unique'])
    writer.writerow(['# Category, Brand, Unit, Location, Type will be auto-created if not exist'])
    writer.writerow(['# Is Active: True/False, Yes/No, 1/0, Active/Inactive'])
    writer.writerow(['# Price should be in decimal format (e.g., 100.00)'])
    
    return response


@login_required
def product_export_csv(request):
    """Export products as CSV with selected options"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    products = Product.objects.all().order_by('name')
    
    # Filters
    only_active = request.GET.get('only_active') == 'true'
    if only_active:
        products = products.filter(is_active=True)
    
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="products_export_{timestamp}.csv"'
    
    writer = csv.writer(response)
    
    # Build headers
    headers = ['ID', 'Name', 'Serial No', 'Barcode', 'Description']
    
    if request.GET.get('with_categories') == 'true':
        headers.extend(['Category', 'Brand', 'Unit', 'Location', 'Type'])
    
    if request.GET.get('with_price') == 'true':
        headers.append('Price')
    
    if request.GET.get('with_stock') == 'true':
        headers.append('Stock')
    
    headers.extend(['Low Stock Threshold', 'Used For', 'Is Active', 'Created At', 'Updated At'])
    
    writer.writerow(headers)
    
    for product in products:
        row = [
            product.id,
            product.name,
            product.serial_no or '',
            product.barcode or '',
            product.description or '',
        ]
        
        if request.GET.get('with_categories') == 'true':
            row.extend([
                product.category.name if product.category else '',
                product.brand.name if product.brand else '',
                product.unit.name if product.unit else '',
                product.location.name if product.location else '',
                product.types.name if product.types else '',
            ])
        
        if request.GET.get('with_price') == 'true':
            row.append(str(product.price))
        
        if request.GET.get('with_stock') == 'true':
            # Get total stock across all warehouses
            total_stock = Inventory.objects.filter(product=product).aggregate(
                total=django_models.Sum('stock')
            )['total'] or 0
            row.append(str(total_stock))
        
        row.extend([
            str(product.low_stock_threshold),
            product.used or '',
            'True' if product.is_active else 'False',
            product.created_at.strftime('%Y-%m-%d %H:%M') if product.created_at else '',
            product.updated_at.strftime('%Y-%m-%d %H:%M') if product.updated_at else '',
        ])
        
        writer.writerow(row)
    
    return response


@login_required
def product_export_excel(request):
    """Export products as Excel with selected options"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    products = Product.objects.all().order_by('name')
    
    # Filters
    only_active = request.GET.get('only_active') == 'true'
    if only_active:
        products = products.filter(is_active=True)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    
    # Build headers
    headers = ['ID', 'Name', 'Serial No', 'Barcode', 'Description']
    
    if request.GET.get('with_categories') == 'true':
        headers.extend(['Category', 'Brand', 'Unit', 'Location', 'Type'])
    
    if request.GET.get('with_price') == 'true':
        headers.append('Price')
    
    if request.GET.get('with_stock') == 'true':
        headers.append('Stock')
    
    headers.extend(['Low Stock Threshold', 'Used For', 'Is Active', 'Created At', 'Updated At'])
    
    # Style headers
    header_fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_border = Border(
        bottom=Side(style='medium', color='000000')
    )
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = header_border
    
    # Data
    row_num = 2
    for product in products:
        row = [
            product.id,
            product.name,
            product.serial_no or '',
            product.barcode or '',
            product.description or '',
        ]
        
        if request.GET.get('with_categories') == 'true':
            row.extend([
                product.category.name if product.category else '',
                product.brand.name if product.brand else '',
                product.unit.name if product.unit else '',
                product.location.name if product.location else '',
                product.types.name if product.types else '',
            ])
        
        if request.GET.get('with_price') == 'true':
            row.append(float(product.price))
        
        if request.GET.get('with_stock') == 'true':
            total_stock = Inventory.objects.filter(product=product).aggregate(
                total=django_models.Sum('stock')
            )['total'] or 0
            row.append(float(total_stock))
        
        row.extend([
            product.low_stock_threshold,
            product.used or '',
            'Active' if product.is_active else 'Inactive',
            product.created_at.strftime('%Y-%m-%d %H:%M') if product.created_at else '',
            product.updated_at.strftime('%Y-%m-%d %H:%M') if product.updated_at else '',
        ])
        
        for col, value in enumerate(row, 1):
            cell = ws.cell(row=row_num, column=col, value=value)
            if isinstance(value, (int, float)):
                if col == len(headers) - 2:  # Price column
                    cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
            else:
                cell.alignment = Alignment(horizontal='left')
        
        row_num += 1
    
    # Auto-fit columns
    for col in ws.columns:
        max_length = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    # Add summary sheet
    ws_summary = wb.create_sheet("Summary")
    ws_summary.cell(row=1, column=1, value="Export Summary").font = Font(bold=True, size=14)
    ws_summary.cell(row=3, column=1, value="Total Products:")
    ws_summary.cell(row=3, column=2, value=products.count())
    ws_summary.cell(row=4, column=1, value="Active Products:")
    ws_summary.cell(row=4, column=2, value=products.filter(is_active=True).count())
    ws_summary.cell(row=5, column=1, value="Export Date:")
    ws_summary.cell(row=5, column=2, value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ws_summary.cell(row=6, column=1, value="Exported By:")
    ws_summary.cell(row=6, column=2, value=request.user.username)
    
    ws_summary.column_dimensions['A'].width = 20
    ws_summary.column_dimensions['B'].width = 20
    
    # Response
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="products_export_{timestamp}.xlsx"'
    wb.save(response)
    return response


@login_required
def product_export_all(request):
    """Export all products with all fields (full export)"""
    return product_export_excel(request)


@login_required
def product_import(request):
    """Import products from CSV/Excel file"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method!'})
    
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'success': False, 'message': 'No file uploaded!'})
    
    # Validate file size
    if file.size > 5 * 1024 * 1024:
        return JsonResponse({'success': False, 'message': 'File too large! Maximum size: 5MB'})
    
    try:
        # Parse file
        if file.name.endswith('.csv'):
            data = file.read().decode('utf-8-sig')  # Handle BOM
            rows = list(csv.reader(data.splitlines()))
        else:
            # Excel
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(cell) if cell is not None else '' for cell in row])
        
        if len(rows) < 2:
            return JsonResponse({'success': False, 'message': 'File is empty or invalid!'})
        
        # Get headers
        headers = [h.strip().lower() for h in rows[0] if h]
        
        # Map column indices
        col_map = {}
        for idx, header in enumerate(headers):
            header_lower = header.lower().strip()
            if 'name' in header_lower:
                col_map['name'] = idx
            elif 'serial' in header_lower:
                col_map['serial_no'] = idx
            elif 'barcode' in header_lower:
                col_map['barcode'] = idx
            elif 'description' in header_lower:
                col_map['description'] = idx
            elif 'category' in header_lower:
                col_map['category'] = idx
            elif 'brand' in header_lower:
                col_map['brand'] = idx
            elif 'unit' in header_lower:
                col_map['unit'] = idx
            elif 'location' in header_lower:
                col_map['location'] = idx
            elif 'type' in header_lower:
                col_map['type'] = idx
            elif 'price' in header_lower:
                col_map['price'] = idx
            elif 'stock' in header_lower:
                col_map['stock'] = idx
            elif 'threshold' in header_lower or 'low stock' in header_lower:
                col_map['threshold'] = idx
            elif 'used' in header_lower:
                col_map['used'] = idx
            elif 'active' in header_lower or 'status' in header_lower:
                col_map['active'] = idx
        
        # Required fields
        if 'name' not in col_map:
            return JsonResponse({'success': False, 'message': 'Product Name column is required!'})
        
        # Process rows
        created = 0
        updated = 0
        skipped = 0
        errors = []
        warnings = []
        
        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], 2):
                try:
                    # Skip empty rows
                    if not row or not row[0] or not str(row[0]).strip():
                        skipped += 1
                        continue
                    
                    name = str(row[col_map['name']]).strip()
                    if not name:
                        skipped += 1
                        continue
                    
                    # Get other fields
                    serial_no = str(row[col_map.get('serial_no', -1)]).strip() if col_map.get('serial_no', -1) >= 0 and len(row) > col_map.get('serial_no', -1) else ''
                    barcode = str(row[col_map.get('barcode', -1)]).strip() if col_map.get('barcode', -1) >= 0 and len(row) > col_map.get('barcode', -1) else ''
                    description = str(row[col_map.get('description', -1)]).strip() if col_map.get('description', -1) >= 0 and len(row) > col_map.get('description', -1) else ''
                    
                    # Check if product exists
                    product = None
                    if serial_no:
                        product = Product.objects.filter(serial_no=serial_no).first()
                    if not product and barcode:
                        product = Product.objects.filter(barcode=barcode).first()
                    if not product:
                        product = Product.objects.filter(name__iexact=name).first()
                    
                    # Get or create related objects
                    category = None
                    if col_map.get('category', -1) >= 0 and len(row) > col_map.get('category', -1) and row[col_map['category']]:
                        cat_name = str(row[col_map['category']]).strip()
                        if cat_name:
                            category, _ = Category.objects.get_or_create(name=cat_name)
                    
                    brand = None
                    if col_map.get('brand', -1) >= 0 and len(row) > col_map.get('brand', -1) and row[col_map['brand']]:
                        brand_name = str(row[col_map['brand']]).strip()
                        if brand_name:
                            brand, _ = Brand.objects.get_or_create(name=brand_name)
                    
                    unit = None
                    if col_map.get('unit', -1) >= 0 and len(row) > col_map.get('unit', -1) and row[col_map['unit']]:
                        unit_name = str(row[col_map['unit']]).strip()
                        if unit_name:
                            unit, _ = Unit.objects.get_or_create(name=unit_name)
                    
                    location = None
                    if col_map.get('location', -1) >= 0 and len(row) > col_map.get('location', -1) and row[col_map['location']]:
                        loc_name = str(row[col_map['location']]).strip()
                        if loc_name:
                            location, _ = Location.objects.get_or_create(name=loc_name)
                    
                    types = None
                    if col_map.get('type', -1) >= 0 and len(row) > col_map.get('type', -1) and row[col_map['type']]:
                        type_name = str(row[col_map['type']]).strip()
                        if type_name:
                            types, _ = Types.objects.get_or_create(name=type_name)
                    
                    # Price
                    price = Decimal('0.00')
                    if col_map.get('price', -1) >= 0 and len(row) > col_map.get('price', -1) and row[col_map['price']]:
                        try:
                            price_val = str(row[col_map['price']]).replace(',', '').replace('$', '').replace('Rs.', '').strip()
                            if price_val:
                                price = Decimal(price_val)
                        except:
                            warnings.append(f"Row {row_num}: Invalid price format, using 0.00")
                    
                    # Threshold
                    threshold = 10
                    if col_map.get('threshold', -1) >= 0 and len(row) > col_map.get('threshold', -1) and row[col_map['threshold']]:
                        try:
                            threshold_val = str(row[col_map['threshold']]).replace(',', '').strip()
                            if threshold_val:
                                threshold = int(float(threshold_val))
                        except:
                            warnings.append(f"Row {row_num}: Invalid threshold, using 10")
                    
                    # Active
                    is_active = True
                    if col_map.get('active', -1) >= 0 and len(row) > col_map.get('active', -1) and row[col_map['active']]:
                        active_val = str(row[col_map['active']]).strip().lower()
                        is_active = active_val in ['true', 'yes', '1', 'active', 't', 'y', 'enabled', 'on']
                    
                    # Used for
                    used = ''
                    if col_map.get('used', -1) >= 0 and len(row) > col_map.get('used', -1):
                        used = str(row[col_map['used']]).strip()
                    
                    # Create or update
                    if product:
                        # Update
                        product.name = name
                        if serial_no:
                            product.serial_no = serial_no
                        if barcode:
                            product.barcode = barcode
                        if description:
                            product.description = description
                        product.category = category
                        product.brand = brand
                        product.unit = unit
                        product.location = location
                        product.types = types
                        product.price = price
                        product.low_stock_threshold = threshold
                        product.used = used
                        product.is_active = is_active
                        product.save()
                        updated += 1
                    else:
                        # Create
                        product = Product.objects.create(
                            name=name,
                            serial_no=serial_no if serial_no else None,
                            barcode=barcode if barcode else None,
                            description=description,
                            category=category,
                            brand=brand,
                            unit=unit,
                            location=location,
                            types=types,
                            price=price,
                            low_stock_threshold=threshold,
                            used=used,
                            is_active=is_active,
                            created_by=request.user
                        )
                        created += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'message': f'Import completed!',
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'errors': errors[:10],
            'warnings': warnings[:10],
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
            'errors': [str(e)]
        })


@login_required
def product_list(request):
    products = Product.objects.select_related('unit', 'category', 'brand', 'location', 'types').order_by('serial_no')
    
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(serial_no__icontains=search) |
            Q(barcode__icontains=search) |
            Q(description__icontains=search)
        )
    
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)
    
    brand_id = request.GET.get('brand', '')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    location_id = request.GET.get('location', '')
    if location_id:
        products = products.filter(location_id=location_id)
    
    paginator = Paginator(products, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ✅ NEW: Quick Stats
    active_count = Product.objects.filter(is_active=True).count()
    
    # Total stock and value
    total_stock = 0
    total_value = Decimal('0.00')
    inventory_items = Inventory.objects.select_related('product')
    for inv in inventory_items:
        total_stock += inv.stock
        total_value += inv.stock_value()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
        'locations': Location.objects.all(),
        'selected_category': category_id,
        'selected_brand': brand_id,
        'selected_location': location_id,
        'active_count': active_count,  # ✅ NEW
        'total_stock': total_stock,    # ✅ NEW
        'total_value': total_value,    # ✅ NEW
    }
    return render(request, 'products/list.html', context)


@login_required
def api_create_product(request):
    """API to create new product from manual entry"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method!'})
    
    try:
        data = json.loads(request.body)
        
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'message': 'Product name is required!'})
        
        # Create product
        product = Product.objects.create(
            name=name,
            serial_no=data.get('serial_no') or None,
            barcode=data.get('barcode') or None,
            description=data.get('description', ''),
            used='',
            low_stock_threshold=float(data.get('low_stock_threshold', 10)),
            unit_id=data.get('unit_id') or None,
            category_id=data.get('category_id') or None,
            brand_id=data.get('brand_id') or None,
            location_id=data.get('location_id') or None,
            types_id=data.get('types_id') or None,
            is_active=True,
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Product "{product.name}" created successfully!',
            'product': {
                'id': product.id,
                'name': product.name,
                'price': str(product.price),
                'stock': 0,
                'unit': product.unit.name if product.unit else '',
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


def product_set_discount(request, pk):
    """
    Product par discount set karein (batch price se auto-calculate)

    - Batch ki selling price = Original price
    - Discount % set karein
    - New price auto-calculate hoga
    - ✅ Save hone ke baad products list par redirect hoga
    """
    from decimal import Decimal

    product = get_object_or_404(Product, pk=pk)

    # ✅ Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('product_list')

    # ✅ Batch se current price lo
    batch = StockBatch.objects.filter(
        product=product,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).order_by('id').first()

    if batch:
        batch_price = batch.selling_price
    else:
        batch_price = product.price or Decimal('0.00')

    if request.method == 'POST':
        try:
            discount_percentage = request.POST.get('discount_percentage', '0').strip()

            try:
                discount_percentage = Decimal(discount_percentage)
            except:
                discount_percentage = Decimal('0')

            if discount_percentage < 0 or discount_percentage > 100:
                messages.error(request, '❌ Discount 0-100 ke darmiyan honi chahiye!')
                return redirect('product_list')  # ✅ YAHAN CHANGE

            # ✅ Original price = batch price
            product.original_price = batch_price
            product.discount_percentage = discount_percentage

            # ✅ New price calculate karo
            if discount_percentage > 0:
                new_price = batch_price * (1 - discount_percentage / 100)
                product.price = new_price
            else:
                product.price = batch_price

            product.save()

            messages.success(
                request,
                f'✅ Discount set!\n'
                f'Original: Rs. {batch_price:,.2f}\n'
                f'Discount: {discount_percentage}%\n'
                f'New Price: Rs. {product.price:,.2f}'
            )

            return redirect('product_list')  # ✅ YAHAN CHANGE

        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('product_list')  # ✅ YAHAN CHANGE

    # GET request
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'product': product,
        'batch_price': batch_price,
    }
    return render(request, 'products/set_discount.html', context)
