"""Frontend views: warehouses."""
from ..models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from ..models import Location, CompanyInfo, Sale


@login_required
def warehouse_performance_report(request):
    """Warehouse performance report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    warehouses = Warehouse.objects.all()
    warehouse_data = []
    
    for warehouse in warehouses:
        sales = Sale.objects.filter(
            warehouse=warehouse,
            sale_date__date__gte=from_date_obj,
            sale_date__date__lte=to_date_obj
        )
        
        total_sales = sum(s.total_amount() for s in sales)
        sale_count = sales.count()
        
        inventory_items = Inventory.objects.filter(warehouse=warehouse)
        stock_value = sum(inv.stock_value() for inv in inventory_items)
        product_count = inventory_items.count()
        
        warehouse_data.append({
            'name': warehouse.name,
            'total_sales': total_sales,
            'sale_count': sale_count,
            'stock_value': stock_value,
            'product_count': product_count,
        })
    
    warehouse_data.sort(key=lambda x: x['total_sales'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouse_data': warehouse_data,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/warehouse_performance.html', context)


@login_required
def warehouse_list(request):
    """List all warehouses with stats"""
    warehouses = Warehouse.objects.select_related('location').all()
    
    search = request.GET.get('search', '')
    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) |
            Q(location__name__icontains=search)
        )
    
    # Calculate stats for each warehouse
    total_stock_value = 0
    total_products = 0
    low_stock_count = 0
    
    for wh in warehouses:
        inventory_items = Inventory.objects.filter(warehouse=wh)
        wh.product_count = inventory_items.count()
        wh.stock_value = sum(inv.stock_value() for inv in inventory_items)
        total_stock_value += wh.stock_value
        total_products += wh.product_count
        low_stock_count += sum(1 for inv in inventory_items if inv.check_low_stock())
    
    paginator = Paginator(warehouses, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'total_warehouses': warehouses.count(),
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'low_stock_count': low_stock_count,
    }
    return render(request, 'warehouses/list.html', context)


@login_required
def warehouse_create(request):
    """Create new warehouse"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        location_id = request.POST.get('location') or None
        description = request.POST.get('description', '')
        
        if not name:
            messages.error(request, 'Warehouse name is required!')
            return redirect('warehouse_create')
        
        if Warehouse.objects.filter(name__iexact=name).exists():
            messages.error(request, f'Warehouse "{name}" already exists!')
            return redirect('warehouse_create')
        
        warehouse = Warehouse.objects.create(
            name=name,
            location_id=location_id,
            description=description
        )
        
        messages.success(request, f'✅ Warehouse "{warehouse.name}" created successfully!')
        return redirect('warehouse_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'locations': Location.objects.all(),
    }
    return render(request, 'warehouses/create.html', context)


@login_required
def warehouse_update(request, pk):
    """Update warehouse"""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        location_id = request.POST.get('location') or None
        description = request.POST.get('description', '')
        
        if not name:
            messages.error(request, 'Warehouse name is required!')
            return redirect('warehouse_update', pk=pk)
        
        if Warehouse.objects.filter(name__iexact=name).exclude(pk=pk).exists():
            messages.error(request, f'Warehouse "{name}" already exists!')
            return redirect('warehouse_update', pk=pk)
        
        warehouse.name = name
        warehouse.location_id = location_id
        warehouse.description = description
        warehouse.save()
        
        messages.success(request, f'✅ Warehouse "{warehouse.name}" updated successfully!')
        return redirect('warehouse_list')
    
    # Get warehouse stats
    inventory_items = Inventory.objects.filter(warehouse=warehouse)
    product_count = inventory_items.count()
    stock_value = sum(inv.stock_value() for inv in inventory_items)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouse': warehouse,
        'locations': Location.objects.all(),
        'product_count': product_count,
        'stock_value': stock_value,
    }
    return render(request, 'warehouses/update.html', context)


@login_required
def warehouse_inventory(request, pk):
    """View inventory items in a warehouse"""
    from decimal import Decimal  # ✅ Ensure Decimal is imported
    
    warehouse = get_object_or_404(Warehouse, pk=pk)
    inventory_items = Inventory.objects.filter(warehouse=warehouse).select_related('product', 'product__unit')
    
    total_products = inventory_items.count()
    total_stock_value = sum(inv.stock_value() for inv in inventory_items)
    low_stock_count = sum(1 for inv in inventory_items if inv.check_low_stock())
    
    # Add calculated fields
    for inv in inventory_items:
        inv.stock_value = inv.stock_value()
        
        # ✅ FIX: Decimal division
        if inv.stock > 0:
            inv.avg_price = inv.stock_value / Decimal(str(inv.stock))
        else:
            inv.avg_price = Decimal('0.00')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouse': warehouse,
        'inventory_items': inventory_items,
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'low_stock_count': low_stock_count,
    }
    return render(request, 'warehouses/inventory.html', context)


# ============================================
# WAREHOUSE CREATE (FRONTEND)
# ============================================
@login_required
def warehouse_create_frontend(request):
    """Frontend warehouse creation view"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            location_id = request.POST.get('location') or None
            description = request.POST.get('description', '')
            
            if not name:
                messages.error(request, 'Warehouse name is required!')
                return redirect('warehouse_create_frontend')
            
            # Check for duplicate warehouse name
            if Warehouse.objects.filter(name__iexact=name).exists():
                messages.error(request, f'Warehouse "{name}" already exists!')
                return redirect('warehouse_create_frontend')
            
            warehouse = Warehouse(
                name=name,
                location_id=location_id,
                description=description
            )
            warehouse.save()
            
            messages.success(request, f'✅ Warehouse "{warehouse.name}" created successfully!')
            return redirect('warehouse_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('warehouse_create_frontend')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'locations': Location.objects.all(),
    }
    return render(request, 'warehouses/create.html', context)


# ============================================
# WAREHOUSE LIST (FRONTEND)
# ============================================
@login_required
def warehouse_list_frontend(request):
    """List all warehouses"""
    warehouses = Warehouse.objects.select_related('location').all().order_by('name')
    
    search = request.GET.get('search', '')
    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) |
            Q(location__name__icontains=search)
        )
    
    # Calculate stats
    total_warehouses = warehouses.count()
    total_stock_value = 0
    for warehouse in warehouses:
        stock_value = sum(inv.stock_value() for inv in Inventory.objects.filter(warehouse=warehouse))
        warehouse.stock_value = stock_value
        total_stock_value += stock_value
        warehouse.product_count = Inventory.objects.filter(warehouse=warehouse).count()
    
    paginator = Paginator(warehouses, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'total_warehouses': total_warehouses,
        'total_stock_value': total_stock_value,
    }
    return render(request, 'warehouses/list.html', context)


# ============================================
# WAREHOUSE UPDATE (FRONTEND)
# ============================================
@login_required
def warehouse_update_frontend(request, pk):
    """Update warehouse"""
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    if request.method == 'POST':
        try:
            warehouse.name = request.POST.get('name', '').strip()
            warehouse.location_id = request.POST.get('location') or None
            warehouse.description = request.POST.get('description', '')
            
            if not warehouse.name:
                messages.error(request, 'Warehouse name is required!')
                return redirect('warehouse_update', pk=pk)
            
            # Check for duplicate (excluding self)
            if Warehouse.objects.filter(name__iexact=warehouse.name).exclude(pk=pk).exists():
                messages.error(request, f'Warehouse "{warehouse.name}" already exists!')
                return redirect('warehouse_update', pk=pk)
            
            warehouse.save()
            messages.success(request, f'✅ Warehouse "{warehouse.name}" updated!')
            return redirect('warehouse_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('warehouse_update', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouse': warehouse,
        'locations': Location.objects.all(),
    }
    return render(request, 'warehouses/update.html', context)
