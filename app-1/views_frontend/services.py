"""Frontend views: services."""
from ..models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F, Avg
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ..models import Unit, CompanyInfo, Sale, Employee, SaleItem, Product


@login_required
def service_list(request):
    """List all services"""
    services = Service.objects.select_related('category').all().order_by('name')
    
    search = request.GET.get('search', '')
    if search:
        services = services.filter(
            Q(name__icontains=search) |
            Q(service_code__icontains=search) |
            Q(description__icontains=search)
        )
    
    service_type = request.GET.get('type', '')
    if service_type:
        services = services.filter(service_type=service_type)
    
    category = request.GET.get('category', '')
    if category:
        services = services.filter(category_id=category)
    
    is_active = request.GET.get('is_active', '')
    if is_active == 'active':
        services = services.filter(is_active=True)
    elif is_active == 'inactive':
        services = services.filter(is_active=False)
    
    paginator = Paginator(services, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'service_type': service_type,
        'category': category,
        'is_active': is_active,
        'categories': ServiceCategory.objects.filter(is_active=True),
        'service_types': Service.SERVICE_TYPES,
        'total_services': services.count(),
        'active_services': services.filter(is_active=True).count(),
    }
    return render(request, 'services/list.html', context)


@login_required
def service_create(request):
    """Create new service"""
    if request.method == 'POST':
        try:
            service = Service.objects.create(
                name=request.POST.get('name'),
                service_type=request.POST.get('service_type'),
                category_id=request.POST.get('category') or None,
                description=request.POST.get('description', ''),
                pricing_type=request.POST.get('pricing_type'),
                price=Decimal(request.POST.get('price', 0)),
                estimated_hours=Decimal(request.POST.get('estimated_hours', 0)),
                min_charge=Decimal(request.POST.get('min_charge', 0)),
                max_charge=Decimal(request.POST.get('max_charge', 0)) or None,
                requires_technician=request.POST.get('requires_technician') == 'on',
                default_technician_id=request.POST.get('default_technician') or None,
                needs_appointment=request.POST.get('needs_appointment') == 'on',
                warranty_months=int(request.POST.get('warranty_months', 0)),
                is_active=request.POST.get('is_active') == 'on',
                created_by=request.user
            )
            
            # Add product requirements
            product_ids = request.POST.getlist('product_ids[]')
            quantities = request.POST.getlist('quantities[]')
            is_optionals = request.POST.getlist('is_optional[]')
            
            for i in range(len(product_ids)):
                if product_ids[i]:
                    ServiceProductRequirement.objects.create(
                        service=service,
                        product_id=product_ids[i],
                        quantity=float(quantities[i] if i < len(quantities) else 1),
                        is_optional=i < len(is_optionals) and is_optionals[i] == 'on'
                    )
            
            messages.success(request, f'✅ Service "{service.name}" created successfully!')
            return redirect('service_detail', pk=service.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': ServiceCategory.objects.filter(is_active=True),
        'service_types': Service.SERVICE_TYPES,
        'pricing_types': Service.PRICING_TYPES,
        'employees': Employee.objects.filter(status='active', department='sales'),
        'products': Product.objects.all().order_by('name')[:100],
    }
    return render(request, 'services/create.html', context)


@login_required
def service_detail(request, pk):
    """Service detail view"""
    service = get_object_or_404(Service, pk=pk)
    requirements = service.product_requirements.all()
    
    # Get recent service requests
    recent_requests = ServiceRequest.objects.filter(service=service).order_by('-created_at')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'service': service,
        'requirements': requirements,
        'recent_requests': recent_requests,
        'total_requests': ServiceRequest.objects.filter(service=service).count(),
        'completed_requests': ServiceRequest.objects.filter(service=service, status='completed').count(),
    }
    return render(request, 'services/detail.html', context)


@login_required
def service_edit(request, pk):
    """Edit service"""
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        try:
            service.name = request.POST.get('name')
            service.service_type = request.POST.get('service_type')
            service.category_id = request.POST.get('category') or None
            service.description = request.POST.get('description', '')
            service.pricing_type = request.POST.get('pricing_type')
            service.price = Decimal(request.POST.get('price', 0))
            service.estimated_hours = Decimal(request.POST.get('estimated_hours', 0))
            service.min_charge = Decimal(request.POST.get('min_charge', 0))
            service.max_charge = Decimal(request.POST.get('max_charge', 0)) or None
            service.requires_technician = request.POST.get('requires_technician') == 'on'
            service.default_technician_id = request.POST.get('default_technician') or None
            service.needs_appointment = request.POST.get('needs_appointment') == 'on'
            service.warranty_months = int(request.POST.get('warranty_months', 0))
            service.is_active = request.POST.get('is_active') == 'on'
            service.save()
            
            # Update requirements (delete old, add new)
            service.product_requirements.all().delete()
            
            product_ids = request.POST.getlist('product_ids[]')
            quantities = request.POST.getlist('quantities[]')
            is_optionals = request.POST.getlist('is_optional[]')
            
            for i in range(len(product_ids)):
                if product_ids[i]:
                    ServiceProductRequirement.objects.create(
                        service=service,
                        product_id=product_ids[i],
                        quantity=float(quantities[i] if i < len(quantities) else 1),
                        is_optional=i < len(is_optionals) and is_optionals[i] == 'on'
                    )
            
            messages.success(request, f'✅ Service "{service.name}" updated!')
            return redirect('service_detail', pk=service.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'service': service,
        'categories': ServiceCategory.objects.filter(is_active=True),
        'service_types': Service.SERVICE_TYPES,
        'pricing_types': Service.PRICING_TYPES,
        'employees': Employee.objects.filter(status='active', department='sales'),
        'products': Product.objects.all().order_by('name')[:100],
    }
    return render(request, 'services/edit.html', context)


@login_required
def service_delete(request, pk):
    """Delete service"""
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        name = service.name
        service.delete()
        messages.success(request, f'🗑️ Service "{name}" deleted!')
        return redirect('service_list')
    
    return redirect('service_detail', pk=pk)


@login_required
def service_request_list(request):
    """List all service requests"""
    requests = ServiceRequest.objects.select_related(
        'customer', 'service', 'technician'
    ).all().order_by('-created_at')
    
    # Filters
    search = request.GET.get('search', '')
    if search:
        requests = requests.filter(
            Q(request_no__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(service__name__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        requests = requests.filter(status=status)
    
    priority = request.GET.get('priority', '')
    if priority:
        requests = requests.filter(priority=priority)
    
    service_type = request.GET.get('service_type', '')
    if service_type:
        requests = requests.filter(service__service_type=service_type)
    
    technician = request.GET.get('technician', '')
    if technician:
        requests = requests.filter(technician_id=technician)
    
    # Date range
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        requests = requests.filter(created_at__date__gte=from_date)
    if to_date:
        requests = requests.filter(created_at__date__lte=to_date)
    
    # Stats
    total_requests = requests.count()
    pending = requests.filter(status='pending').count()
    in_progress = requests.filter(status='in_progress').count()
    completed = requests.filter(status='completed').count()
    overdue = sum(1 for r in requests if r.is_overdue())
    
    paginator = Paginator(requests, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'status': status,
        'priority': priority,
        'service_type': service_type,
        'technician': technician,
        'from_date': from_date,
        'to_date': to_date,
        'total_requests': total_requests,
        'pending': pending,
        'in_progress': in_progress,
        'completed': completed,
        'overdue': overdue,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'priority_choices': ServiceRequest.PRIORITY_CHOICES,
        'service_types': Service.SERVICE_TYPES,
        'technicians': Employee.objects.filter(status='active', department='sales'),
    }
    return render(request, 'services/request_list.html', context)


@login_required
def service_request_create(request):
    """Create new service request"""
    if request.method == 'POST':
        try:
            customer_id = request.POST.get('customer')
            service_id = request.POST.get('service')
            
            if not customer_id or not service_id:
                messages.error(request, 'Customer and Service are required!')
                return redirect('service_request_create')
            
            service_request = ServiceRequest.objects.create(
                customer_id=customer_id,
                service_id=service_id,
                description=request.POST.get('description', ''),
                priority=request.POST.get('priority', 'medium'),
                requested_date=request.POST.get('requested_date'),
                scheduled_date=request.POST.get('scheduled_date') or None,
                appointment_time=request.POST.get('appointment_time') or None,
                service_address=request.POST.get('service_address', ''),
                contact_person=request.POST.get('contact_person', ''),
                contact_phone=request.POST.get('contact_phone', ''),
                quoted_price=Decimal(request.POST.get('quoted_price', 0)),
                technician_id=request.POST.get('technician') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='pending'
            )
            
            # If technician assigned, mark as assigned
            if service_request.technician:
                service_request.status = 'assigned'
                service_request.assigned_at = now()
                service_request.save()
            
            messages.success(request, f'✅ Service Request #{service_request.request_no} created!')
            return redirect('service_request_detail', pk=service_request.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_request_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'customers': Customer.objects.all().order_by('name'),
        'services': Service.objects.filter(is_active=True).order_by('name'),
        'technicians': Employee.objects.filter(status='active', department='sales'),
        'priority_choices': ServiceRequest.PRIORITY_CHOICES,
    }
    return render(request, 'services/request_create.html', context)


@login_required
def service_request_detail(request, pk):
    """Service request detail view"""
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related('customer', 'service', 'technician', 'invoice'),
        pk=pk
    )
    
    used_products = service_request.used_products.all()
    appointments = service_request.appointments.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request': service_request,
        'used_products': used_products,
        'appointments': appointments,
        'feedback': getattr(service_request, 'feedback', None),
        'can_edit': service_request.status not in ['completed', 'cancelled'],
        'can_invoice': service_request.status == 'completed' and not service_request.invoice,
    }
    return render(request, 'services/request_detail.html', context)


@login_required
def service_request_edit(request, pk):
    """Edit service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    if service_request.status in ['completed', 'cancelled']:
        messages.error(request, '❌ Cannot edit completed or cancelled requests!')
        return redirect('service_request_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            service_request.customer_id = request.POST.get('customer')
            service_request.service_id = request.POST.get('service')
            service_request.description = request.POST.get('description', '')
            service_request.priority = request.POST.get('priority', 'medium')
            service_request.requested_date = request.POST.get('requested_date')
            service_request.scheduled_date = request.POST.get('scheduled_date') or None
            service_request.appointment_time = request.POST.get('appointment_time') or None
            service_request.service_address = request.POST.get('service_address', '')
            service_request.contact_person = request.POST.get('contact_person', '')
            service_request.contact_phone = request.POST.get('contact_phone', '')
            service_request.quoted_price = Decimal(request.POST.get('quoted_price', 0))
            service_request.technician_id = request.POST.get('technician') or None
            service_request.notes = request.POST.get('notes', '')
            service_request.save()
            
            # If technician assigned and status is pending, update to assigned
            if service_request.technician and service_request.status == 'pending':
                service_request.status = 'assigned'
                service_request.assigned_at = now()
                service_request.save()
            
            messages.success(request, f'✅ Service Request #{service_request.request_no} updated!')
            return redirect('service_request_detail', pk=service_request.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_request_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request': service_request,
        'customers': Customer.objects.all().order_by('name'),
        'services': Service.objects.filter(is_active=True).order_by('name'),
        'technicians': Employee.objects.filter(status='active', department='sales'),
        'priority_choices': ServiceRequest.PRIORITY_CHOICES,
    }
    return render(request, 'services/request_edit.html', context)


@login_required
def service_request_status_update(request, pk, status):
    """Quick status update for service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    valid_statuses = ['pending', 'confirmed', 'assigned', 'in_progress', 'completed', 'cancelled']
    
    if status in valid_statuses:
        if status == 'assigned':
            service_request.assigned_at = now()
        elif status == 'completed':
            service_request.completed_date = now().date()
            # Auto complete all appointments
            service_request.appointments.update(status='completed')
        
        service_request.status = status
        service_request.save()
        
        messages.success(request, f'✅ Request #{service_request.request_no} → {service_request.get_status_display()}')
    else:
        messages.error(request, '❌ Invalid status!')
    
    return redirect('service_request_detail', pk=service_request.pk)


@login_required
def service_request_appointment(request, pk):
    """Schedule appointment for service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    if request.method == 'POST':
        try:
            technician_id = request.POST.get('technician')
            appointment_date = request.POST.get('appointment_date')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            notes = request.POST.get('notes', '')
            
            # Check for conflicts
            if technician_id and appointment_date and start_time:
                technician = Employee.objects.get(id=technician_id)
                
                # Check if technician already has appointment at this time
                conflicting = ServiceAppointment.objects.filter(
                    technician=technician,
                    appointment_date=appointment_date,
                    status__in=['scheduled', 'arrived', 'in_progress']
                )
                
                if start_time:
                    # Check time overlap (simplified)
                    for existing in conflicting:
                        if existing.start_time <= start_time <= existing.end_time:
                            messages.error(request, f'⚠️ {technician.name} is already booked at this time!')
                            return redirect('service_request_appointment', pk=pk)
                
                appointment = ServiceAppointment.objects.create(
                    service_request=service_request,
                    technician_id=technician_id,
                    appointment_date=appointment_date,
                    start_time=start_time,
                    end_time=end_time or None,
                    duration_hours=Decimal(request.POST.get('duration_hours', 0)),
                    notes=notes,
                    status='scheduled'
                )
                
                # Update service request
                service_request.scheduled_date = appointment_date
                service_request.technician_id = technician_id
                if service_request.status == 'pending':
                    service_request.status = 'confirmed'
                service_request.save()
                
                messages.success(request, f'✅ Appointment scheduled for {appointment_date}!')
                return redirect('service_request_detail', pk=service_request.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_request_appointment', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request': service_request,
        'technicians': Employee.objects.filter(status='active', department='sales'),
    }
    return render(request, 'services/request_appointment.html', context)


@login_required
def service_request_feedback(request, pk):
    """Submit feedback for completed service"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    if service_request.status != 'completed':
        messages.error(request, '❌ Feedback only for completed services!')
        return redirect('service_request_detail', pk=pk)
    
    if hasattr(service_request, 'feedback'):
        messages.warning(request, '⚠️ Feedback already submitted!')
        return redirect('service_request_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            feedback = ServiceFeedback.objects.create(
                service_request=service_request,
                rating=int(request.POST.get('rating', 5)),
                comment=request.POST.get('comment', ''),
                technician_rating=int(request.POST.get('technician_rating', 5)),
                timeliness_rating=int(request.POST.get('timeliness_rating', 5)),
                quality_rating=int(request.POST.get('quality_rating', 5)),
                would_recommend=request.POST.get('would_recommend') == 'on'
            )
            
            service_request.feedback_rating = feedback.rating
            service_request.feedback_comment = feedback.comment
            service_request.save()
            
            messages.success(request, f'✅ Thank you for your feedback!')
            return redirect('service_request_detail', pk=service_request.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request': service_request,
    }
    return render(request, 'services/request_feedback.html', context)


@login_required
def service_request_invoice(request, pk):
    """Generate invoice for service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    if service_request.status != 'completed':
        messages.error(request, '❌ Invoice only for completed services!')
        return redirect('service_request_detail', pk=pk)
    
    if service_request.invoice:
        messages.warning(request, '⚠️ Invoice already generated!')
        return redirect('service_request_detail', pk=pk)
    
    try:
        with transaction.atomic():
            # Get default warehouse
            default_warehouse = Warehouse.objects.first()
            if not default_warehouse:
                messages.error(request, '❌ No warehouse found! Please create a warehouse first.')
                return redirect('service_request_detail', pk=pk)
            
            # Create sale
            sale = Sale.objects.create(
                customer=service_request.customer,
                bill_no=f"SVC-{service_request.request_no}",
                sale_date=now(),
                paid=0,
                discount_value=service_request.discount,
                created_by=request.user,
                warehouse=default_warehouse
            )
            
            # Add service item
            SaleItem.objects.create(
                sale=sale,
                product=None,  # Service
                qty=1,
                price=service_request.total_amount(),
                total_amt=service_request.total_amount(),
                profit=0,
                discount=0
            )
            
            # Add any products used
            for used_product in service_request.used_products.all():
                SaleItem.objects.create(
                    sale=sale,
                    product=used_product.product,
                    qty=used_product.quantity,
                    price=used_product.price,
                    total_amt=used_product.total,
                    profit=0,
                    discount=0
                )
            
            service_request.invoice = sale
            service_request.save()
            
            messages.success(request, f'✅ Invoice #{sale.bill_no} generated successfully!')
            return redirect('sale_detail', pk=sale.pk)
            
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
        return redirect('service_request_detail', pk=pk)


@login_required
def service_appointment_list(request):
    """List all service appointments"""
    appointments = ServiceAppointment.objects.select_related(
        'service_request', 'technician'
    ).all().order_by('appointment_date', 'start_time')
    
    status = request.GET.get('status', '')
    if status:
        appointments = appointments.filter(status=status)
    
    technician = request.GET.get('technician', '')
    if technician:
        appointments = appointments.filter(technician_id=technician)
    
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        appointments = appointments.filter(appointment_date__gte=date_from)
    if date_to:
        appointments = appointments.filter(appointment_date__lte=date_to)
    
    paginator = Paginator(appointments, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'technician': technician,
        'date_from': date_from,
        'date_to': date_to,
        'technicians': Employee.objects.filter(status='active', department='sales'),
        'status_choices': ServiceAppointment.STATUS_CHOICES,
        'total_appointments': appointments.count(),
        'scheduled': appointments.filter(status='scheduled').count(),
        'completed': appointments.filter(status='completed').count(),
    }
    return render(request, 'services/appointment_list.html', context)


@login_required
def service_appointment_calendar(request):
    """Calendar view for appointments"""
    # Get appointments for current month
    month = request.GET.get('month', date.today().month)
    year = request.GET.get('year', date.today().year)
    
    start_date = date(int(year), int(month), 1)
    if int(month) == 12:
        end_date = date(int(year) + 1, 1, 1)
    else:
        end_date = date(int(year), int(month) + 1, 1)
    
    appointments = ServiceAppointment.objects.filter(
        appointment_date__gte=start_date,
        appointment_date__lt=end_date
    ).select_related('service_request', 'technician')
    
    # Group by date
    calendar_data = {}
    for app in appointments:
        date_str = app.appointment_date.strftime('%Y-%m-%d')
        if date_str not in calendar_data:
            calendar_data[date_str] = []
        calendar_data[date_str].append({
            'id': app.id,
            'time': app.start_time.strftime('%H:%M') if app.start_time else 'TBD',
            'technician': app.technician.name,
            'customer': app.service_request.customer.name,
            'service': app.service_request.service.name,
            'status': app.status,
            'status_badge': app.get_status_display(),
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'calendar_data': calendar_data,
        'month': month,
        'year': year,
        'month_name': start_date.strftime('%B'),
        'prev_month': start_date - timedelta(days=1),
        'next_month': end_date,
        'total_appointments': appointments.count(),
    }
    return render(request, 'services/appointment_calendar.html', context)


@login_required
def service_report(request):
    """Service reports dashboard"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Get service requests in range
    requests = ServiceRequest.objects.filter(
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    )
    
    total_requests = requests.count()
    total_revenue = sum(r.total_amount() for r in requests if r.status == 'completed')
    completed_count = requests.filter(status='completed').count()
    avg_rating = ServiceFeedback.objects.filter(
        service_request__in=requests
    ).aggregate(avg=Avg('rating'))['avg'] or 0
    
    # Service type breakdown
    type_breakdown = {}
    for r in requests:
        service_type = r.service.get_service_type_display()
        type_breakdown[service_type] = type_breakdown.get(service_type, 0) + 1
    
    # Technician performance
    technician_performance = []
    for emp in Employee.objects.filter(status='active', department='sales'):
        emp_requests = requests.filter(technician=emp)
        completed = emp_requests.filter(status='completed').count()
        if completed > 0:
            avg_time = 0  # Could calculate from appointment durations
            technician_performance.append({
                'name': emp.name,
                'total': emp_requests.count(),
                'completed': completed,
                'avg_rating': ServiceFeedback.objects.filter(
                    service_request__technician=emp
                ).aggregate(avg=Avg('technician_rating'))['avg'] or 0,
            })
    
    technician_performance.sort(key=lambda x: x['completed'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_requests': total_requests,
        'total_revenue': total_revenue,
        'completed_count': completed_count,
        'avg_rating': avg_rating,
        'type_breakdown': type_breakdown,
        'technician_performance': technician_performance,
    }
    return render(request, 'services/report.html', context)


@login_required
def technician_performance_report(request):
    """Detailed technician performance report"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    technicians = Employee.objects.filter(status='active', department='sales')
    tech_data = []
    
    for tech in technicians:
        appointments = ServiceAppointment.objects.filter(
            technician=tech,
            appointment_date__gte=from_date_obj,
            appointment_date__lte=to_date_obj
        )
        
        completed = appointments.filter(status='completed').count()
        scheduled = appointments.filter(status='scheduled').count()
        no_show = appointments.filter(status='no_show').count()
        cancelled = appointments.filter(status='cancelled').count()
        
        # Ratings for this technician
        ratings = ServiceFeedback.objects.filter(
            service_request__technician=tech
        ).aggregate(
            avg_tech=Avg('technician_rating'),
            avg_timeliness=Avg('timeliness_rating'),
            avg_quality=Avg('quality_rating')
        )
        
        tech_data.append({
            'technician': tech,
            'total': appointments.count(),
            'completed': completed,
            'scheduled': scheduled,
            'no_show': no_show,
            'cancelled': cancelled,
            'avg_tech_rating': ratings['avg_tech'] or 0,
            'avg_timeliness': ratings['avg_timeliness'] or 0,
            'avg_quality': ratings['avg_quality'] or 0,
            'completion_rate': round((completed / appointments.count() * 100) if appointments.count() > 0 else 0, 1),
        })
    
    tech_data.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'technician_data': tech_data,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'services/technician_report.html', context)


@login_required
def get_service_products(request):
    """AJAX: Get products required for a service"""
    service_id = request.GET.get('service_id')
    
    if not service_id:
        return JsonResponse({'success': False, 'message': 'Service ID required'})
    
    try:
        service = Service.objects.get(id=service_id)
        requirements = service.product_requirements.all()
        
        products = []
        for req in requirements:
            products.append({
                'id': req.product.id,
                'name': req.product.name,
                'quantity': req.quantity,
                'is_optional': req.is_optional,
                'price': str(req.product.price),
                'unit': req.product.unit.name if req.product.unit else '',
            })
        
        return JsonResponse({
            'success': True,
            'service_name': service.name,
            'service_price': str(service.price),
            'estimated_hours': str(service.estimated_hours),
            'requires_technician': service.requires_technician,
            'products': products,
        })
    except Service.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Service not found'})


@login_required
def get_technician_schedule(request):
    """AJAX: Get technician schedule for a date"""
    technician_id = request.GET.get('technician_id')
    date = request.GET.get('date')
    
    if not technician_id or not date:
        return JsonResponse({'success': False, 'message': 'Technician and date required'})
    
    try:
        appointments = ServiceAppointment.objects.filter(
            technician_id=technician_id,
            appointment_date=date,
            status__in=['scheduled', 'arrived', 'in_progress']
        )
        
        schedule = []
        for app in appointments:
            schedule.append({
                'id': app.id,
                'request_no': app.service_request.request_no,
                'customer': app.service_request.customer.name,
                'service': app.service_request.service.name,
                'start_time': app.start_time.strftime('%H:%M') if app.start_time else 'TBD',
                'end_time': app.end_time.strftime('%H:%M') if app.end_time else 'TBD',
                'status': app.status,
            })
        
        return JsonResponse({
            'success': True,
            'schedule': schedule,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def check_appointment_conflict(request):
    """AJAX: Check if appointment time conflicts"""
    technician_id = request.GET.get('technician_id')
    date = request.GET.get('date')
    start_time = request.GET.get('start_time')
    
    if not all([technician_id, date, start_time]):
        return JsonResponse({'success': False, 'message': 'Missing parameters'})
    
    try:
        # Check for conflicts
        conflicting = ServiceAppointment.objects.filter(
            technician_id=technician_id,
            appointment_date=date,
            start_time__lte=start_time,
            end_time__gte=start_time,
            status__in=['scheduled', 'arrived', 'in_progress']
        ).exists()
        
        return JsonResponse({
            'success': True,
            'has_conflict': conflicting,
            'message': '❌ Time slot not available' if conflicting else '✅ Time slot available',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def service_inventory_dashboard(request):
    """Service Inventory Dashboard"""
    
    items = ServiceInventory.objects.filter(is_active=True)
    
    total_items = items.count()
    low_stock_items = items.filter(current_stock__lte=F('reorder_level')).count()
    critical_stock = items.filter(current_stock__lte=F('min_stock')).count()
    total_value = sum(item.stock_value() for item in items)
    
    # Recent transactions
    recent_transactions = ServiceInventoryTransaction.objects.select_related(
        'inventory_item'
    ).order_by('-created_at')[:10]
    
    # Top used items
    top_used = ServicePartUsage.objects.values(
        'inventory_item__name', 'inventory_item__item_code'
    ).annotate(
        total_used=Sum('quantity')
    ).order_by('-total_used')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_items': total_items,
        'low_stock_items': low_stock_items,
        'critical_stock': critical_stock,
        'total_value': total_value,
        'recent_transactions': recent_transactions,
        'top_used': top_used,
    }
    return render(request, 'services/inventory/dashboard.html', context)


@login_required
def service_inventory_list(request):
    """List all service inventory items"""
    
    items = ServiceInventory.objects.select_related('category', 'unit', 'warehouse').all()
    
    search = request.GET.get('search', '')
    if search:
        items = items.filter(
            Q(name__icontains=search) |
            Q(item_code__icontains=search) |
            Q(description__icontains=search)
        )
    
    item_type = request.GET.get('type', '')
    if item_type:
        items = items.filter(item_type=item_type)
    
    category = request.GET.get('category', '')
    if category:
        items = items.filter(category_id=category)
    
    stock_status = request.GET.get('stock_status', '')
    if stock_status == 'low':
        items = items.filter(current_stock__lte=F('reorder_level'), current_stock__gt=0)
    elif stock_status == 'critical':
        items = items.filter(current_stock__lte=F('min_stock'))
    elif stock_status == 'out':
        items = items.filter(current_stock__lte=0)
    elif stock_status == 'ok':
        items = items.filter(current_stock__gt=F('reorder_level'))
    
    paginator = Paginator(items, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'item_type': item_type,
        'category': category,
        'stock_status': stock_status,
        'categories': ServiceInventoryCategory.objects.filter(is_active=True),
        'item_types': ServiceInventory.INVENTORY_TYPES,
        'total_items': items.count(),
        'low_stock_count': items.filter(current_stock__lte=F('reorder_level')).count(),
        'critical_count': items.filter(current_stock__lte=F('min_stock')).count(),
    }
    return render(request, 'services/inventory/list.html', context)


@login_required
def service_inventory_create(request):
    """Create new service inventory item"""
    
    if request.method == 'POST':
        try:
            item = ServiceInventory.objects.create(
                name=request.POST.get('name'),
                description=request.POST.get('description', ''),
                item_type=request.POST.get('item_type'),
                category_id=request.POST.get('category') or None,
                product_id=request.POST.get('product') or None,
                current_stock=float(request.POST.get('current_stock', 0)),
                min_stock=float(request.POST.get('min_stock', 5)),
                reorder_level=float(request.POST.get('reorder_level', 10)),
                reorder_quantity=float(request.POST.get('reorder_quantity', 20)),
                unit_cost=Decimal(request.POST.get('unit_cost', 0)),
                selling_price=Decimal(request.POST.get('selling_price', 0)),
                markup_percent=Decimal(request.POST.get('markup_percent', 20)),
                unit_id=request.POST.get('unit') or None,
                preferred_supplier_id=request.POST.get('supplier') or None,
                warehouse_id=request.POST.get('warehouse') or None,
                shelf_location=request.POST.get('shelf_location', ''),
                barcode=request.POST.get('barcode', '') or None,
                is_active=request.POST.get('is_active') == 'on',
                is_consumable=request.POST.get('is_consumable') == 'on',
                is_serialized=request.POST.get('is_serialized') == 'on',
                created_by=request.user
            )
            
            # Create opening balance transaction
            if item.current_stock > 0:
                ServiceInventoryTransaction.objects.create(
                    inventory_item=item,
                    transaction_type='opening',
                    quantity=item.current_stock,
                    balance_after=item.current_stock,
                    unit_cost=item.unit_cost,
                    notes="Opening balance",
                    created_by=request.user
                )
            
            messages.success(request, f'✅ Inventory item "{item.name}" created!')
            return redirect('service_inventory_detail', pk=item.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': ServiceInventoryCategory.objects.filter(is_active=True),
        'item_types': ServiceInventory.INVENTORY_TYPES,
        'units': Unit.objects.all(),
        'suppliers': Vendor.objects.all(),
        'warehouses': Warehouse.objects.all(),
        'products': Product.objects.all(),
    }
    return render(request, 'services/inventory/create.html', context)


@login_required
def service_inventory_detail(request, pk):
    """Inventory item detail view"""
    
    item = get_object_or_404(ServiceInventory, pk=pk)
    transactions = item.transactions.all().order_by('-created_at')[:20]
    usage = item.usage_records.all().order_by('-used_at')[:20]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'item': item,
        'transactions': transactions,
        'usage': usage,
        'stock_value': item.stock_value(),
        'is_low': item.is_low_stock(),
        'is_critical': item.is_critical_stock(),
        'stock_percent': min((item.current_stock / item.reorder_level) * 100, 100) if item.reorder_level > 0 else 0,
    }
    return render(request, 'services/inventory/detail.html', context)


@login_required
def service_inventory_edit(request, pk):
    """Edit inventory item"""
    
    item = get_object_or_404(ServiceInventory, pk=pk)
    
    if request.method == 'POST':
        try:
            item.name = request.POST.get('name')
            item.description = request.POST.get('description', '')
            item.item_type = request.POST.get('item_type')
            item.category_id = request.POST.get('category') or None
            item.product_id = request.POST.get('product') or None
            item.min_stock = float(request.POST.get('min_stock', 5))
            item.reorder_level = float(request.POST.get('reorder_level', 10))
            item.reorder_quantity = float(request.POST.get('reorder_quantity', 20))
            item.unit_cost = Decimal(request.POST.get('unit_cost', 0))
            item.selling_price = Decimal(request.POST.get('selling_price', 0))
            item.markup_percent = Decimal(request.POST.get('markup_percent', 20))
            item.unit_id = request.POST.get('unit') or None
            item.preferred_supplier_id = request.POST.get('supplier') or None
            item.warehouse_id = request.POST.get('warehouse') or None
            item.shelf_location = request.POST.get('shelf_location', '')
            item.barcode = request.POST.get('barcode', '') or None
            item.is_active = request.POST.get('is_active') == 'on'
            item.is_consumable = request.POST.get('is_consumable') == 'on'
            item.is_serialized = request.POST.get('is_serialized') == 'on'
            item.save()
            
            messages.success(request, f'✅ Item "{item.name}" updated!')
            return redirect('service_inventory_detail', pk=item.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'item': item,
        'categories': ServiceInventoryCategory.objects.filter(is_active=True),
        'item_types': ServiceInventory.INVENTORY_TYPES,
        'units': Unit.objects.all(),
        'suppliers': Vendor.objects.all(),
        'warehouses': Warehouse.objects.all(),
        'products': Product.objects.all(),
    }
    return render(request, 'services/inventory/edit.html', context)


@login_required
def service_inventory_adjust(request, pk):
    """Adjust inventory stock"""
    
    item = get_object_or_404(ServiceInventory, pk=pk)
    
    if request.method == 'POST':
        try:
            adjustment_type = request.POST.get('adjustment_type')
            quantity = float(request.POST.get('quantity', 0))
            reason = request.POST.get('reason', '')
            
            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero!')
                return redirect('service_inventory_adjust', pk=pk)
            
            if adjustment_type == 'decrease' and not item.can_fulfill(quantity):
                messages.error(request, f'Insufficient stock! Available: {item.current_stock}')
                return redirect('service_inventory_adjust', pk=pk)
            
            # Create adjustment record
            adjustment = ServiceInventoryStockAdjustment.objects.create(
                inventory_item=item,
                adjustment_type=adjustment_type,
                quantity=quantity,
                reason=reason,
                performed_by=request.user
            )
            
            # Update stock
            if adjustment_type == 'increase':
                item.increase_stock(quantity, request.user, reason)
            else:
                item.reduce_stock(quantity, request.user, reason)
            
            messages.success(request, f'✅ Stock adjusted successfully! New stock: {item.current_stock}')
            return redirect('service_inventory_detail', pk=item.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_adjust', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'item': item,
    }
    return render(request, 'services/inventory/adjust.html', context)


@login_required
def service_inventory_transactions(request, pk):
    """View all transactions for an item"""
    
    item = get_object_or_404(ServiceInventory, pk=pk)
    transactions = item.transactions.all().order_by('-created_at')
    
    paginator = Paginator(transactions, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'item': item,
        'page_obj': page_obj,
        'transactions': page_obj,
    }
    return render(request, 'services/inventory/transactions.html', context)


@login_required
def service_inventory_use(request, request_id):
    """Use inventory items in service request"""
    
    service_request = get_object_or_404(ServiceRequest, pk=request_id)
    
    if request.method == 'POST':
        try:
            inventory_item_id = request.POST.get('inventory_item')
            quantity = float(request.POST.get('quantity', 0))
            charged_to_customer = request.POST.get('charged_to_customer') == 'on'
            notes = request.POST.get('notes', '')
            
            if not inventory_item_id:
                messages.error(request, 'Please select an item!')
                return redirect('service_inventory_use', request_id=request_id)
            
            item = get_object_or_404(ServiceInventory, pk=inventory_item_id)
            
            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero!')
                return redirect('service_inventory_use', request_id=request_id)
            
            if not item.can_fulfill(quantity):
                messages.error(request, f'Insufficient stock! Available: {item.current_stock}')
                return redirect('service_inventory_use', request_id=request_id)
            
            # Create part usage record
            part_usage = ServicePartUsage.objects.create(
                service_request=service_request,
                inventory_item=item,
                quantity=quantity,
                unit_cost=item.unit_cost,
                charged_to_customer=charged_to_customer,
                markup_percent=item.markup_percent,
                used_by=request.user,
                notes=notes
            )
            
            messages.success(request, f'✅ {item.name} x{quantity} used in service request!')
            return redirect('service_request_detail', pk=request_id)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_use', request_id=request_id)
    
    items = ServiceInventory.objects.filter(is_active=True, current_stock__gt=0)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'service_request': service_request,
        'items': items,
        'existing_usage': service_request.parts_used.all(),
    }
    return render(request, 'services/inventory/use.html', context)


@login_required
def service_inventory_po_create(request):
    """Create purchase order for service inventory"""
    
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            expected_delivery = request.POST.get('expected_delivery')
            discount = Decimal(request.POST.get('discount', 0))
            notes = request.POST.get('notes', '')
            
            po = ServiceInventoryPurchaseOrder.objects.create(
                supplier_id=supplier_id,
                expected_delivery=expected_delivery or None,
                discount=discount,
                notes=notes,
                created_by=request.user,
                status='draft'
            )
            
            item_ids = request.POST.getlist('item_ids[]')
            quantities = request.POST.getlist('quantities[]')
            prices = request.POST.getlist('prices[]')
            
            for i in range(len(item_ids)):
                if item_ids[i] and float(quantities[i]) > 0:
                    ServiceInventoryPODetail.objects.create(
                        po=po,
                        inventory_item_id=item_ids[i],
                        quantity=float(quantities[i]),
                        unit_price=Decimal(prices[i])
                    )
            
            messages.success(request, f'✅ PO #{po.po_no} created!')
            return redirect('service_inventory_po_detail', pk=po.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_po_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suppliers': Vendor.objects.all(),
        'items': ServiceInventory.objects.filter(is_active=True),
    }
    return render(request, 'services/inventory/po_create.html', context)


@login_required
def service_inventory_po_list(request):
    """List all inventory purchase orders"""
    
    pos = ServiceInventoryPurchaseOrder.objects.all().order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        pos = pos.filter(status=status)
    
    paginator = Paginator(pos, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'status_choices': ServiceInventoryPurchaseOrder.STATUS_CHOICES,
        'total_pos': pos.count(),
        'pending_count': pos.filter(status__in=['pending', 'approved', 'ordered']).count(),
        'received_count': pos.filter(status='received').count(),
    }
    return render(request, 'services/inventory/po_list.html', context)


@login_required
def service_inventory_po_detail(request, pk):
    """View PO detail"""
    
    po = get_object_or_404(ServiceInventoryPurchaseOrder, pk=pk)
    details = po.po_details.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'po': po,
        'details': details,
        'can_receive': po.status in ['ordered', 'partial'],
        'can_edit': po.status in ['draft', 'pending'],
    }
    return render(request, 'services/inventory/po_detail.html', context)


@login_required
def service_inventory_po_receive(request, pk):
    """Receive PO items"""
    
    po = get_object_or_404(ServiceInventoryPurchaseOrder, pk=pk)
    
    if po.status not in ['ordered', 'partial']:
        messages.error(request, '❌ PO cannot be received!')
        return redirect('service_inventory_po_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            detail_ids = request.POST.getlist('detail_ids[]')
            received_qty = request.POST.getlist('received_qty[]')
            
            for i, detail_id in enumerate(detail_ids):
                if detail_id and float(received_qty[i]) > 0:
                    detail = ServiceInventoryPODetail.objects.get(id=detail_id, po=po)
                    qty = float(received_qty[i])
                    
                    if qty > detail.quantity - detail.received_quantity:
                        messages.error(request, f'Quantity exceeds pending for {detail.inventory_item.name}!')
                        return redirect('service_inventory_po_receive', pk=pk)
                    
                    # Update stock
                    detail.inventory_item.increase_stock(
                        quantity=qty,
                        user=request.user,
                        reason=f"Received via PO {po.po_no}"
                    )
                    
                    detail.received_quantity += qty
                    detail.save()
            
            # Check if fully received
            all_received = all(d.received_quantity >= d.quantity for d in po.po_details.all())
            if all_received:
                po.status = 'received'
                po.received_date = date.today()
                po.save()
            else:
                po.status = 'partial'
                po.save()
            
            messages.success(request, f'✅ PO #{po.po_no} items received!')
            return redirect('service_inventory_po_detail', pk=po.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('service_inventory_po_receive', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'po': po,
    }
    return render(request, 'services/inventory/po_receive.html', context)
