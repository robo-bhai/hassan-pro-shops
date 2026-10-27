"""Frontend views: production."""
from ...security.permissions import perm_required
from ...models import *
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ...models import ProductionOrder, ProductionBOM, ProductionOperation, ProductionStockUpdate, TransferOrder, ProductionReport, CompanyInfo, Employee, Product
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


# ✅ NEW CODE
@login_required
@perm_required('view_production')
def production_order_list(request):
    orders = ProductionOrder.objects.select_related(
        'product',
        'source_warehouse',
        'target_warehouse',
        'created_by'
    ).prefetch_related(
        'bom_items__raw_material',
        'bom_items__raw_material__unit',
        'operations',
        'stock_updates'
    ).order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        orders = orders.filter(status=status)
    
    search = request.GET.get('search', '')
    if search:
        orders = orders.filter(order_no__icontains=search) | orders.filter(product__name__icontains=search)
    
    # Statistics
    total_orders = orders.count()
    pending_orders = orders.filter(status__in=['draft', 'planned', 'approved']).count()
    in_progress = orders.filter(status='in_progress').count()
    completed = orders.filter(status='completed').count()
    total_quantity = sum(o.quantity for o in orders)
    
    paginator = Paginator(orders, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'search': search,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'in_progress': in_progress,
        'completed': completed,
        'total_quantity': total_quantity,
    }
    return render(request, 'production/order_list.html', context)


@login_required
@perm_required('manage_production')
def production_order_create(request):
    """Create new production order"""
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product')
            quantity = Decimal(request.POST.get('quantity'))
            planned_start_date = request.POST.get('planned_start_date')
            planned_end_date = request.POST.get('planned_end_date')
            source_warehouse_id = request.POST.get('source_warehouse')
            target_warehouse_id = request.POST.get('target_warehouse')
            notes = request.POST.get('notes', '')
            
            product = get_object_or_404(Product, pk=product_id)
            
            # Check if product has BOM template
            # (You can create a ProductBOMTemplate model for reusability)
            
            order = ProductionOrder.objects.create(
                product=product,
                quantity=quantity,
                planned_start_date=planned_start_date,
                planned_end_date=planned_end_date,
                source_warehouse_id=source_warehouse_id,
                target_warehouse_id=target_warehouse_id,
                notes=notes,
                created_by=request.user,
                status='draft'
            )
            
            messages.success(request, f'✅ Production Order #{order.order_no} created!')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_order_create')
    
    warehouses = Warehouse.objects.all()
    products = Product.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouses': warehouses,
        'products': products,
    }
    return render(request, 'production/order_create.html', context)


@login_required
@perm_required('view_production')
def production_order_detail(request, pk):
    """View production order details"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    bom_items = order.bom_items.all()
    operations = order.operations.all()
    stock_updates = order.stock_updates.all()
    transfers = order.transfers.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'bom_items': bom_items,
        'operations': operations,
        'stock_updates': stock_updates,
        'transfers': transfers,
        'progress': order.progress_percent(),
    }
    return render(request, 'production/order_detail.html', context)


@login_required
@perm_required('manage_production')
def production_order_edit(request, pk):
    """Edit production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if order.status not in ['draft', 'planned']:
        messages.error(request, 'Cannot edit order that is already in progress!')
        return redirect('production_order_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            order.quantity = Decimal(request.POST.get('quantity'))
            order.planned_start_date = request.POST.get('planned_start_date')
            order.planned_end_date = request.POST.get('planned_end_date')
            order.source_warehouse_id = request.POST.get('source_warehouse')
            order.target_warehouse_id = request.POST.get('target_warehouse')
            order.notes = request.POST.get('notes', '')
            order.save()
            
            messages.success(request, f'✅ Production Order #{order.order_no} updated!')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_order_edit', pk=pk)
    
    warehouses = Warehouse.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'warehouses': warehouses,
    }
    return render(request, 'production/order_edit.html', context)


@login_required
@perm_required('manage_production')
def production_order_delete(request, pk):
    """Delete production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if order.status not in ['draft', 'cancelled']:
        messages.error(request, 'Cannot delete order that is in progress or completed!')
        return redirect('production_order_detail', pk=pk)
    
    if request.method == 'POST':
        order_no = order.order_no
        order.delete()
        messages.success(request, f'🗑️ Production Order #{order_no} deleted!')
        return redirect('production_order_list')
    
    return redirect('production_order_list')


@login_required
@perm_required('manage_production')
@transaction.atomic
def production_order_start(request, pk):
    """Start production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if order.status != 'approved':
        messages.error(request, 'Order must be approved before starting!')
        return redirect('production_order_detail', pk=pk)
    
    order.status = 'in_progress'
    order.actual_start_date = date.today()
    order.save()
    
    messages.success(request, f'✅ Production Order #{order.order_no} started!')
    return redirect('production_order_detail', pk=pk)


@login_required
@perm_required('manage_production')
@transaction.atomic
def production_order_complete(request, pk):
    """Complete production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if order.status != 'in_progress':
        messages.error(request, 'Order must be in progress to complete!')
        return redirect('production_order_detail', pk=pk)
    
    if order.produced_quantity < order.quantity:
        messages.warning(request, f'Only {order.produced_quantity}/{order.quantity} produced!')
    
    order.status = 'completed'
    order.actual_end_date = date.today()
    order.completed_at = now()
    order.save()
    
    # Create production report
    ProductionReport.objects.create(
        production_order=order,
        planned_quantity=order.quantity,
        produced_quantity=order.produced_quantity,
        planned_hours=sum(op.estimated_hours for op in order.operations.all()),
        actual_hours=sum(op.actual_hours for op in order.operations.all()),
        planned_cost=order.total_production_cost,
        actual_cost=order.total_production_cost
    )
    
    messages.success(request, f'✅ Production Order #{order.order_no} completed!')
    return redirect('production_order_detail', pk=pk)


@login_required
@perm_required('manage_production')
def production_bom_add(request, pk):
    """Add BOM item to production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if request.method == 'POST':
        try:
            raw_material_id = request.POST.get('raw_material')
            quantity_required = Decimal(request.POST.get('quantity_required'))
            cost_per_unit = Decimal(request.POST.get('cost_per_unit', 0))
            waste_percentage = Decimal(request.POST.get('waste_percentage', 0))
            
            bom = ProductionBOM.objects.create(
                production_order=order,
                raw_material_id=raw_material_id,
                quantity_required=quantity_required,
                cost_per_unit=cost_per_unit,
                waste_percentage=waste_percentage
            )
            
            messages.success(request, f'✅ BOM item added: {bom.raw_material.name}')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_bom_add', pk=pk)
    
    products = Product.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'products': products,
    }
    return render(request, 'production/bom_add.html', context)


@login_required
@perm_required('manage_production')
def production_bom_edit(request, pk):
    """Edit BOM item"""
    bom = get_object_or_404(ProductionBOM, pk=pk)
    order = bom.production_order
    
    if request.method == 'POST':
        try:
            bom.quantity_required = Decimal(request.POST.get('quantity_required'))
            bom.cost_per_unit = Decimal(request.POST.get('cost_per_unit', 0))
            bom.waste_percentage = Decimal(request.POST.get('waste_percentage', 0))
            bom.save()
            
            messages.success(request, f'✅ BOM item updated!')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_bom_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'bom': bom,
        'order': order,
    }
    return render(request, 'production/bom_edit.html', context)


@login_required
@perm_required('manage_production')
def production_bom_delete(request, pk):
    """Delete BOM item"""
    bom = get_object_or_404(ProductionBOM, pk=pk)
    order = bom.production_order
    
    if request.method == 'POST':
        material_name = bom.raw_material.name
        bom.delete()
        messages.success(request, f'🗑️ BOM item "{material_name}" removed!')
        return redirect('production_order_detail', pk=order.pk)
    
    return redirect('production_order_detail', pk=order.pk)


@login_required
@perm_required('manage_production')
def production_operation_add(request, pk):
    """Add operation to production order"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if request.method == 'POST':
        try:
            operation_type = request.POST.get('operation_type')
            operation_name = request.POST.get('operation_name')
            sequence = int(request.POST.get('sequence', 0))
            estimated_hours = Decimal(request.POST.get('estimated_hours', 0))
            assigned_to_id = request.POST.get('assigned_to') or None
            labor_cost = Decimal(request.POST.get('labor_cost', 0))
            overhead_cost = Decimal(request.POST.get('overhead_cost', 0))
            
            operation = ProductionOperation.objects.create(
                production_order=order,
                operation_type=operation_type,
                operation_name=operation_name,
                sequence=sequence,
                estimated_hours=estimated_hours,
                assigned_to_id=assigned_to_id,
                labor_cost=labor_cost,
                overhead_cost=overhead_cost
            )
            
            messages.success(request, f'✅ Operation "{operation.operation_name}" added!')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_operation_add', pk=pk)
    
    employees = Employee.objects.filter(status='active')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'employees': employees,
        'operation_types': ProductionOperation.OPERATION_TYPES,
    }
    return render(request, 'production/operation_add.html', context)


@login_required
@perm_required('manage_production')
def production_operation_start(request, pk):
    """Start an operation"""
    operation = get_object_or_404(ProductionOperation, pk=pk)
    operation.mark_start()
    
    messages.success(request, f'✅ Operation "{operation.operation_name}" started!')
    return redirect('production_order_detail', pk=operation.production_order.pk)


@login_required
@perm_required('manage_production')
def production_operation_complete(request, pk):
    """Complete an operation"""
    operation = get_object_or_404(ProductionOperation, pk=pk)
    
    if request.method == 'POST':
        actual_hours = Decimal(request.POST.get('actual_hours', 0))
        operation.actual_hours = actual_hours
        operation.mark_complete()
        
        messages.success(request, f'✅ Operation "{operation.operation_name}" completed!')
        return redirect('production_order_detail', pk=operation.production_order.pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'operation': operation,
    }
    return render(request, 'production/operation_complete.html', context)


@login_required
@perm_required('view_production', post='manage_production')
@transaction.atomic
def production_consume_stock(request, pk):
    """Consume raw materials from warehouse with stock validation"""
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    # Check if order is in correct status
    if order.status not in ['approved', 'in_progress']:
        messages.error(request, '❌ Order must be Approved or In Progress to consume stock!')
        return redirect('production_order_detail', pk=order.pk)
    
    if request.method == 'POST':
        # ... POST handling with stock validation ...
        pass
    
    # GET request - Show stock summary
    source_warehouse = order.source_warehouse
    stock_summary = []
    all_available = True
    
    for bom in order.bom_items.all():
        required_qty = bom.calculate_required_for_quantity(order.quantity)
        current_stock = Inventory.get_stock(bom.raw_material, source_warehouse) if source_warehouse else 0
        
        stock_summary.append({
            'raw_material': bom.raw_material.name,
            'required': required_qty,
            'available': current_stock,
            'status': '✅ Available' if current_stock >= required_qty else f'❌ Shortage of {required_qty - current_stock:.2f}',
            'is_available': current_stock >= required_qty
        })
        
        if current_stock < required_qty:
            all_available = False
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'stock_summary': stock_summary,
        'all_available': all_available,
        'source_warehouse': source_warehouse,
    }
    return render(request, 'production/consume_stock.html', context)


@login_required
@perm_required('view_production', post='manage_production')
@transaction.atomic
def production_produce_stock(request, pk):
    """Add finished goods to warehouse"""
    from decimal import Decimal
    
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    if request.method == 'POST':
        try:
            produced_qty = Decimal(request.POST.get('produced_quantity', order.quantity))
            unit_price = Decimal(request.POST.get('unit_price', order.product.price))
            
            if produced_qty <= 0:
                messages.error(request, 'Quantity must be greater than zero!')
                return redirect('production_order_detail', pk=order.pk)
            
            target_warehouse = order.target_warehouse or order.source_warehouse
            
            # FIX: convert produced_qty to float
            produced_qty_float = float(produced_qty)
            
            # Update stock in target warehouse
            Inventory.update_stock(order.product, produced_qty_float, target_warehouse)
            
            # Create batch
            batch = StockBatch.objects.create(
                product=order.product,
                warehouse=target_warehouse,
                qty=produced_qty_float,
                remaining_qty=produced_qty_float,
                price=unit_price,
                selling_price=unit_price * Decimal('1.2')
            )
            
            # FIX: produced_qty_float use karo
            order.produced_quantity = order.produced_quantity + produced_qty_float
            order.save()
            
            # Create stock update record
            ProductionStockUpdate.objects.create(
                production_order=order,
                product=order.product,
                update_type='produce',
                quantity=produced_qty_float,
                unit_cost=unit_price,
                batch=batch,
                warehouse=target_warehouse,
                created_by=request.user,
                notes=f"Produced from order {order.order_no}"
            )
            
            messages.success(request, f'✅ {produced_qty_float:,.0f} units of {order.product.name} produced!')
            return redirect('production_order_detail', pk=order.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('production_order_detail', pk=order.pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
    }
    return render(request, 'production/produce_stock.html', context)


@login_required
@perm_required('view_production')
def transfer_order_list(request):
    """List all transfer orders"""
    transfers = TransferOrder.objects.select_related('product', 'from_warehouse', 'to_warehouse').order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        transfers = transfers.filter(status=status)
    
    transfer_type = request.GET.get('type', '')
    if transfer_type:
        transfers = transfers.filter(transfer_type=transfer_type)
    
    paginator = Paginator(transfers, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'transfer_type': transfer_type,
    }
    return render(request, 'production/transfer_list.html', context)


@login_required
@perm_required('manage_production')
def transfer_order_create(request):
    """Create new transfer order"""
    if request.method == 'POST':
        try:
            transfer_type = request.POST.get('transfer_type')
            from_warehouse_id = request.POST.get('from_warehouse')
            to_warehouse_id = request.POST.get('to_warehouse') or None
            product_id = request.POST.get('product')
            quantity = Decimal(request.POST.get('quantity'))
            price = Decimal(request.POST.get('price', 0))
            vehicle_no = request.POST.get('vehicle_no', '')
            driver_name = request.POST.get('driver_name', '')
            driver_contact = request.POST.get('driver_contact', '')
            expected_delivery_date = request.POST.get('expected_delivery_date') or None
            notes = request.POST.get('notes', '')
            
            # Check stock availability
            current_stock = Inventory.get_stock(Product.objects.get(id=product_id), from_warehouse_id)
            if current_stock < quantity:
                messages.error(request, f'Insufficient stock! Available: {current_stock}')
                return redirect('transfer_order_create')
            
            transfer = TransferOrder.objects.create(
                transfer_type=transfer_type,
                from_warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                product_id=product_id,
                quantity=quantity,
                price=price,
                vehicle_no=vehicle_no,
                driver_name=driver_name,
                driver_contact=driver_contact,
                expected_delivery_date=expected_delivery_date,
                notes=notes,
                created_by=request.user
            )
            
            messages.success(request, f'✅ Transfer Order #{transfer.transfer_no} created!')
            return redirect('transfer_order_detail', pk=transfer.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('transfer_order_create')
    
    warehouses = Warehouse.objects.all()
    products = Product.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouses': warehouses,
        'products': products,
        'transfer_types': TransferOrder.TRANSFER_TYPES,
    }
    return render(request, 'production/transfer_create.html', context)


@login_required
@perm_required('view_production')
def transfer_order_detail(request, pk):
    """View transfer order details"""
    transfer = get_object_or_404(TransferOrder, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'transfer': transfer,
    }
    return render(request, 'production/transfer_detail.html', context)


@login_required
@perm_required('manage_production')
def transfer_order_approve(request, pk):
    """Approve transfer order"""
    transfer = get_object_or_404(TransferOrder, pk=pk)
    transfer.approve(request.user)
    
    messages.success(request, f'✅ Transfer Order #{transfer.transfer_no} approved!')
    return redirect('transfer_order_detail', pk=transfer.pk)


@login_required
@perm_required('manage_production')
@transaction.atomic
def transfer_order_deliver(request, pk):
    """Mark transfer order as delivered"""
    transfer = get_object_or_404(TransferOrder, pk=pk)
    
    if transfer.status != 'approved':
        messages.error(request, 'Order must be approved before delivery!')
        return redirect('transfer_order_detail', pk=transfer.pk)
    
    # Deduct stock from source warehouse
    Inventory.update_stock(transfer.product, -transfer.quantity, transfer.from_warehouse)
    
    transfer.deliver()
    
    messages.success(request, f'✅ Transfer Order #{transfer.transfer_no} delivered!')
    return redirect('transfer_order_detail', pk=transfer.pk)


@login_required
@perm_required('view_production')
def production_report(request):
    """Production reports dashboard"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    orders = ProductionOrder.objects.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date
    )
    
    total_orders = orders.count()
    total_quantity = sum(o.quantity for o in orders)
    completed_orders = orders.filter(status='completed').count()
    total_cost = sum(o.total_production_cost for o in orders)
    
    # Efficiency
    completed_ops = ProductionOperation.objects.filter(
        production_order__in=orders,
        status='completed'
    )
    total_planned_hours = sum(op.estimated_hours for op in completed_ops)
    total_actual_hours = sum(op.actual_hours for op in completed_ops)
    efficiency = (total_planned_hours / total_actual_hours * 100) if total_actual_hours > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_orders': total_orders,
        'total_quantity': total_quantity,
        'completed_orders': completed_orders,
        'total_cost': total_cost,
        'efficiency': efficiency,
        'from_date': from_date,
        'to_date': to_date,
        'orders': orders[:20],
    }
    return render(request, 'production/report.html', context)


def production_report_pdf(request, pk):
    """Generate production report PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from django.http import HttpResponse
    from decimal import Decimal   # ✅ ADD THIS IMPORT
    
    order = get_object_or_404(ProductionOrder, pk=pk)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    story.append(Paragraph(f"<b>{company_name}</b>", styles['Heading1']))
    story.append(Paragraph(f"Production Report - {order.order_no}", styles['Heading2']))
    story.append(Spacer(1, 20))
    
    # Order Info
    data = [
        ['Order No:', order.order_no],
        ['Product:', order.product.name],
        ['Quantity:', f"{order.quantity:,.0f}"],
        ['Status:', order.get_status_display()],
        ['Planned Start:', order.planned_start_date.strftime('%d-%m-%Y') if order.planned_start_date else '-'],
        ['Planned End:', order.planned_end_date.strftime('%d-%m-%Y') if order.planned_end_date else '-'],
    ]
    
    table = Table(data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    
    # BOM Table
    story.append(Paragraph("<b>Bill of Materials</b>", styles['Heading3']))
    bom_data = [['Raw Material', 'Qty Required', 'Cost/Unit', 'Total Cost']]
    for bom in order.bom_items.all():
        bom_data.append([
            bom.raw_material.name,
            f"{bom.quantity_required:,.2f}",
            f"Rs. {bom.cost_per_unit:,.2f}",
            f"Rs. {bom.total_cost:,.2f}"
        ])
    
    if len(bom_data) > 1:
        bom_table = Table(bom_data)
        bom_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        story.append(bom_table)
    else:
        story.append(Paragraph("No BOM items added.", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # ✅ FIX: Cost Summary with Decimal handling
    story.append(Paragraph("<b>Cost Summary</b>", styles['Heading3']))
    
    # Decimal division fix
    if order.quantity > 0:
        cost_per_unit = order.total_production_cost / Decimal(str(order.quantity))
    else:
        cost_per_unit = Decimal('0.00')
    
    cost_data = [
        ['Material Cost:', f"Rs. {order.total_material_cost:,.2f}"],
        ['Labor Cost:', f"Rs. {order.total_labor_cost:,.2f}"],
        ['Overhead Cost:', f"Rs. {order.total_overhead_cost:,.2f}"],
        ['Total Production Cost:', f"Rs. {order.total_production_cost:,.2f}"],
        ['Cost per Unit:', f"Rs. {cost_per_unit:,.2f}" if order.quantity > 0 else "N/A"],
    ]
    
    cost_table = Table(cost_data, colWidths=[2*inch, 2*inch])
    cost_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(cost_table)
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Production_Report_{order.order_no}.pdf"'
    return response


@login_required
@perm_required('view_production')
def get_product_bom_template(request):
    """AJAX: Get BOM template for product"""
    product_id = request.GET.get('product_id')
    
    if not product_id:
        return JsonResponse({'success': False, 'message': 'Product ID required'})
    
    # You can create ProductBOMTemplate model for reusable BOMs
    # For now, return empty
    return JsonResponse({
        'success': True,
        'bom_items': []
    })
