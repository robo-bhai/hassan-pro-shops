"""Frontend views: supply chain."""
from ..models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from decimal import Decimal
from datetime import date
from django.core.paginator import Paginator
from django.contrib import messages
from ..models import CompanyInfo, Purchase, Product, Supplier, SupplierCategory, SupplyChainForecast, DeliverySchedule, LogisticsTracking, SupplyChainAnalytics


@login_required
def supply_chain_dashboard(request):
    """Supply chain dashboard"""
    total_suppliers = Supplier.objects.filter(is_active=True).count()
    total_forecasts = SupplyChainForecast.objects.count()
    total_deliveries = DeliverySchedule.objects.count()
    pending_deliveries = DeliverySchedule.objects.filter(status__in=['scheduled', 'in_transit']).count()
    
    # Recent deliveries
    recent_deliveries = DeliverySchedule.objects.order_by('-created_at')[:5]
    
    # Supplier rating distribution
    suppliers = Supplier.objects.filter(is_active=True)
    rating_distribution = {
        'excellent': suppliers.filter(rating__gte=4.5).count(),
        'good': suppliers.filter(rating__gte=4.0, rating__lt=4.5).count(),
        'average': suppliers.filter(rating__gte=3.0, rating__lt=4.0).count(),
        'poor': suppliers.filter(rating__gte=2.0, rating__lt=3.0).count(),
        'needs_improvement': suppliers.filter(rating__lt=2.0).count(),
    }
    
    # Latest analytics
    latest_analytics = SupplyChainAnalytics.objects.order_by('-report_date').first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_suppliers': total_suppliers,
        'total_forecasts': total_forecasts,
        'total_deliveries': total_deliveries,
        'pending_deliveries': pending_deliveries,
        'recent_deliveries': recent_deliveries,
        'rating_distribution': rating_distribution,
        'latest_analytics': latest_analytics,
    }
    return render(request, 'supply_chain/dashboard.html', context)


@login_required
def supplier_list(request):
    """List all suppliers"""
    suppliers = Supplier.objects.select_related('category').all()
    
    search = request.GET.get('search', '')
    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) |
            Q(supplier_code__icontains=search) |
            Q(contact_person__icontains=search) |
            Q(email__icontains=search)
        )
    
    supplier_type = request.GET.get('type', '')
    if supplier_type:
        suppliers = suppliers.filter(supplier_type=supplier_type)
    
    is_active = request.GET.get('is_active', '')
    if is_active:
        suppliers = suppliers.filter(is_active=is_active == 'active')
    
    paginator = Paginator(suppliers, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'supplier_type': supplier_type,
        'is_active': is_active,
        'supplier_types': Supplier.SUPPLIER_TYPES,
        'total_suppliers': suppliers.count(),
    }
    return render(request, 'supply_chain/supplier_list.html', context)


@login_required
def supplier_create(request):
    """Create new supplier"""
    if request.method == 'POST':
        try:
            supplier = Supplier.objects.create(
                name=request.POST.get('name'),
                supplier_type=request.POST.get('supplier_type'),
                category_id=request.POST.get('category') or None,
                contact_person=request.POST.get('contact_person'),
                email=request.POST.get('email'),
                phone=request.POST.get('phone'),
                address=request.POST.get('address'),
                website=request.POST.get('website', ''),
                lead_time=int(request.POST.get('lead_time', 7)),
                payment_terms=request.POST.get('payment_terms', '30 days'),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                is_active=request.POST.get('is_active') == 'on'
            )
            
            messages.success(request, f'✅ Supplier "{supplier.name}" created successfully!')
            return redirect('supplier_detail', pk=supplier.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    categories = SupplierCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': categories,
        'supplier_types': Supplier.SUPPLIER_TYPES,
    }
    return render(request, 'supply_chain/supplier_create.html', context)


@login_required
def supplier_detail(request, pk):
    """Supplier detail view"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    # Get purchase orders from this supplier
    purchases = Purchase.objects.filter(vendor__name=supplier.name).order_by('-pur_date')[:10]
    
    # Calculate supplier performance
    total_orders = purchases.count()
    on_time = purchases.filter(pur_date__lte=date.today()).count()
    on_time_rate = (on_time / total_orders * 100) if total_orders > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'supplier': supplier,
        'purchases': purchases,
        'rating_display': supplier.get_rating_display(),
        'total_orders': total_orders,
        'on_time_rate': on_time_rate,
    }
    return render(request, 'supply_chain/supplier_detail.html', context)


@login_required
def supplier_edit(request, pk):
    """Edit supplier"""
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        try:
            supplier.name = request.POST.get('name')
            supplier.supplier_type = request.POST.get('supplier_type')
            supplier.category_id = request.POST.get('category') or None
            supplier.contact_person = request.POST.get('contact_person')
            supplier.email = request.POST.get('email')
            supplier.phone = request.POST.get('phone')
            supplier.address = request.POST.get('address')
            supplier.website = request.POST.get('website', '')
            supplier.lead_time = int(request.POST.get('lead_time', 7))
            supplier.payment_terms = request.POST.get('payment_terms', '30 days')
            supplier.rating = Decimal(request.POST.get('rating', 0))
            supplier.on_time_delivery_rate = Decimal(request.POST.get('on_time_delivery_rate', 0))
            supplier.quality_score = Decimal(request.POST.get('quality_score', 0))
            supplier.price_competitiveness = Decimal(request.POST.get('price_competitiveness', 0))
            supplier.notes = request.POST.get('notes', '')
            supplier.is_active = request.POST.get('is_active') == 'on'
            supplier.save()
            
            messages.success(request, f'✅ Supplier "{supplier.name}" updated successfully!')
            return redirect('supplier_detail', pk=supplier.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    categories = SupplierCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'supplier': supplier,
        'categories': categories,
        'supplier_types': Supplier.SUPPLIER_TYPES,
    }
    return render(request, 'supply_chain/supplier_edit.html', context)


@login_required
def supply_forecast(request):
    """View supply chain forecasts"""
    forecasts = SupplyChainForecast.objects.select_related('product', 'created_by').all()
    
    forecast_type = request.GET.get('type', '')
    if forecast_type:
        forecasts = forecasts.filter(forecast_type=forecast_type)
    
    product_id = request.GET.get('product', '')
    if product_id:
        forecasts = forecasts.filter(product_id=product_id)
    
    paginator = Paginator(forecasts, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'forecast_type': forecast_type,
        'product_id': product_id,
        'products': Product.objects.all(),
        'forecast_types': SupplyChainForecast.FORECAST_TYPES,
        'methodology_choices': SupplyChainForecast.METHODOLOGY_CHOICES,
    }
    return render(request, 'supply_chain/forecast_list.html', context)


@login_required
def supply_forecast_create(request):
    """Create new supply chain forecast"""
    if request.method == 'POST':
        try:
            forecast = SupplyChainForecast.objects.create(
                product_id=request.POST.get('product'),
                forecast_type=request.POST.get('forecast_type'),
                period_start=request.POST.get('period_start'),
                period_end=request.POST.get('period_end'),
                forecasted_quantity=float(request.POST.get('forecasted_quantity', 0)),
                methodology=request.POST.get('methodology', 'moving_average'),
                confidence_level=Decimal(request.POST.get('confidence_level', 80)),
                created_by=request.user
            )
            
            messages.success(request, f'✅ Forecast created for {forecast.product.name}')
            return redirect('supply_forecast')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    products = Product.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'products': products,
        'forecast_types': SupplyChainForecast.FORECAST_TYPES,
        'methodology_choices': SupplyChainForecast.METHODOLOGY_CHOICES,
    }
    return render(request, 'supply_chain/forecast_create.html', context)


@login_required
def delivery_schedule_list(request):
    """List all delivery schedules"""
    deliveries = DeliverySchedule.objects.select_related('product', 'from_warehouse', 'to_warehouse').all()
    
    status = request.GET.get('status', '')
    if status:
        deliveries = deliveries.filter(status=status)
    
    delivery_type = request.GET.get('type', '')
    if delivery_type:
        deliveries = deliveries.filter(delivery_type=delivery_type)
    
    search = request.GET.get('search', '')
    if search:
        deliveries = deliveries.filter(
            Q(schedule_no__icontains=search) |
            Q(product__name__icontains=search) |
            Q(driver_name__icontains=search)
        )
    
    paginator = Paginator(deliveries, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'delivery_type': delivery_type,
        'search': search,
        'status_choices': DeliverySchedule.DELIVERY_STATUS,
        'delivery_types': DeliverySchedule.DELIVERY_TYPES,
    }
    return render(request, 'supply_chain/delivery_list.html', context)


@login_required
def delivery_schedule_create(request):
    """Create new delivery schedule"""
    if request.method == 'POST':
        try:
            delivery = DeliverySchedule.objects.create(
                delivery_type=request.POST.get('delivery_type'),
                from_location=request.POST.get('from_location'),
                to_location=request.POST.get('to_location'),
                from_warehouse_id=request.POST.get('from_warehouse') or None,
                to_warehouse_id=request.POST.get('to_warehouse') or None,
                product_id=request.POST.get('product'),
                quantity=float(request.POST.get('quantity', 0)),
                unit=request.POST.get('unit', ''),
                scheduled_date=request.POST.get('scheduled_date'),
                vehicle_no=request.POST.get('vehicle_no', ''),
                driver_name=request.POST.get('driver_name', ''),
                driver_phone=request.POST.get('driver_phone', ''),
                transport_company=request.POST.get('transport_company', ''),
                tracking_number=request.POST.get('tracking_number', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            messages.success(request, f'✅ Delivery Schedule "{delivery.schedule_no}" created!')
            return redirect('delivery_schedule_detail', pk=delivery.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    warehouses = Warehouse.objects.all()
    products = Product.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'warehouses': warehouses,
        'products': products,
        'delivery_types': DeliverySchedule.DELIVERY_TYPES,
        'status_choices': DeliverySchedule.DELIVERY_STATUS,
    }
    return render(request, 'supply_chain/delivery_create.html', context)


@login_required
def delivery_schedule_detail(request, pk):
    """Delivery schedule detail"""
    delivery = get_object_or_404(DeliverySchedule, pk=pk)
    tracking = delivery.tracking.all().order_by('-timestamp')
    
    # Check if delayed
    is_delayed = delivery.is_delayed()
    
    # Calculate days since scheduled
    days_since_scheduled = (date.today() - delivery.scheduled_date).days if delivery.scheduled_date else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'delivery': delivery,
        'tracking': tracking,
        'is_delayed': is_delayed,
        'days_since_scheduled': days_since_scheduled,
    }
    return render(request, 'supply_chain/delivery_detail.html', context)


@login_required
def logistics_tracking(request, pk):
    """Add logistics tracking update"""
    delivery = get_object_or_404(DeliverySchedule, pk=pk)
    
    if request.method == 'POST':
        try:
            tracking = LogisticsTracking.objects.create(
                delivery=delivery,
                location=request.POST.get('location'),
                status=request.POST.get('status'),
                remarks=request.POST.get('remarks', ''),
                latitude=request.POST.get('latitude') or None,
                longitude=request.POST.get('longitude') or None,
            )
            
            # Update delivery status if delivered
            if request.POST.get('status') == 'delivered':
                delivery.status = 'delivered'
                delivery.actual_delivery_date = date.today()
                delivery.save()
            elif request.POST.get('status') == 'in_transit' and delivery.status == 'scheduled':
                delivery.status = 'in_transit'
                delivery.save()
            
            messages.success(request, f'✅ Tracking update added for {delivery.schedule_no}')
            return redirect('delivery_schedule_detail', pk=delivery.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'delivery': delivery,
        'tracking_statuses': ['scheduled', 'in_transit', 'delivered', 'delayed', 'cancelled'],
    }
    return render(request, 'supply_chain/tracking_add.html', context)


@login_required
def supply_chain_analytics(request):
    """Supply chain analytics"""
    analytics = SupplyChainAnalytics.objects.order_by('-report_date')[:30]
    
    if analytics.exists():
        latest = analytics.first()
    else:
        latest = None
    
    # Calculate trends
    if analytics.count() >= 2:
        current = analytics[0]
        previous = analytics[1]
        trend = {
            'on_time_delivery': current.on_time_delivery_rate - previous.on_time_delivery_rate,
            'inventory_turnover': current.inventory_turnover - previous.inventory_turnover,
        }
    else:
        trend = None
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'analytics': analytics,
        'latest': latest,
        'trend': trend,
    }
    return render(request, 'supply_chain/analytics.html', context)
