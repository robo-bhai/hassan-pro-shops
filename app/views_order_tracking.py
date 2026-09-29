# app/views_order_tracking.py
"""
Order Tracking Views - Complete Professional System
====================================================
✅ Admin Tracking Panel
✅ Assign Rider (Local)
✅ Customer Pickup
✅ Status Updates with Timeline
✅ WhatsApp Auto-Notifications
✅ Delivery Proof Photo
✅ Public Tracking Page
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now as tz_now
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
import logging
import json

from .models import (
    DeliveryInfo, OrderTracking, DeliveryFeedback,
    SaleOrder, CustomerOrder, CompanyInfo,
)

logger = logging.getLogger(__name__)


# ============================================
# HELPER FUNCTIONS
# ============================================

def _get_whatsapp_sender():
    """Lazy import WhatsApp sender"""
    try:
        from .whatsapp_utils import WhatsAppSender
        return WhatsAppSender
    except ImportError:
        logger.warning("WhatsAppSender not found")
        return None


def _is_admin(user):
    """Check if user is admin/staff"""
    return user.is_superuser or user.is_staff


# ============================================
# ADMIN: TRACKING PANEL (LIST)
# ============================================

@login_required
def order_tracking_panel(request):
    """Admin: All orders tracking panel"""
    
    if not _is_admin(request.user):
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    status_filter = request.GET.get('status', 'active')
    search = request.GET.get('search', '').strip()
    delivery_filter = request.GET.get('delivery', '')
    
    # Get orders
    orders = SaleOrder.objects.select_related(
        'customer', 'warehouse'
    ).prefetch_related('tracking_history').order_by('-order_date')
    
    # Status filter
    if status_filter == 'active':
        orders = orders.exclude(status__in=['delivered', 'cancelled'])
    elif status_filter == 'delivered':
        orders = orders.filter(status='delivered')
    elif status_filter == 'cancelled':
        orders = orders.filter(status='cancelled')
    
    # Search
    if search:
        orders = orders.filter(
            Q(order_no__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__contact_number__icontains=search)
        )
    
    # Delivery type filter
    if delivery_filter == 'local_rider':
        delivery_ids = DeliveryInfo.objects.filter(
            delivery_type='local_rider'
        ).values_list('sale_order_id', flat=True)
        orders = orders.filter(id__in=delivery_ids)
    elif delivery_filter == 'customer_pickup':
        delivery_ids = DeliveryInfo.objects.filter(
            delivery_type='customer_pickup'
        ).values_list('sale_order_id', flat=True)
        orders = orders.filter(id__in=delivery_ids)
    elif delivery_filter == 'no_delivery':
        delivery_ids = DeliveryInfo.objects.values_list('sale_order_id', flat=True)
        orders = orders.exclude(id__in=delivery_ids)
    
    # Stats
    stats = {
        'total': SaleOrder.objects.count(),
        'active': SaleOrder.objects.exclude(status__in=['delivered', 'cancelled']).count(),
        'delivered': SaleOrder.objects.filter(status='delivered').count(),
        'out_for_delivery': DeliveryInfo.objects.filter(status='in_transit').count(),
    }
    
    # Pagination
    paginator = Paginator(orders, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'orders': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'search': search,
        'delivery_filter': delivery_filter,
    }
    return render(request, 'order_tracking/admin_panel.html', context)


# ============================================
# ADMIN: DETAIL PAGE
# ============================================

@login_required
def order_tracking_detail(request, order_id):
    """Admin: Order detail with tracking timeline"""
    
    if not _is_admin(request.user):
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    order = get_object_or_404(SaleOrder, pk=order_id)
    
    # Get or create delivery info
    delivery_info, created = DeliveryInfo.objects.get_or_create(
        sale_order=order,
        defaults={'status': 'pending'}
    )
    
    # Get tracking history
    tracking_history = order.tracking_history.all().order_by('-timestamp')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'order': order,
        'delivery_info': delivery_info,
        'tracking_history': tracking_history,
    }
    return render(request, 'order_tracking/admin_detail.html', context)


# ============================================
# ADMIN: SET DELIVERY TYPE
# ============================================

@login_required
@require_POST
def order_set_delivery_type(request, order_id):
    """Admin: Set delivery type (Local Rider / Customer Pickup)"""
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        order = get_object_or_404(SaleOrder, pk=order_id)
        delivery_info, _ = DeliveryInfo.objects.get_or_create(sale_order=order)
        
        delivery_type = request.POST.get('delivery_type')
        
        if delivery_type not in ['local_rider', 'customer_pickup']:
            return JsonResponse({'success': False, 'message': 'Invalid delivery type'})
        
        delivery_info.delivery_type = delivery_type
        delivery_info.created_by = request.user
        delivery_info.save()
        
        customer = order.customer
        whatsapp_url = None
        WhatsAppSender = _get_whatsapp_sender()
        
        if delivery_type == 'customer_pickup' and WhatsAppSender:
            company = CompanyInfo.objects.first()
            pickup_address = company.address if company else "Our Store"
            
            whatsapp_url = WhatsAppSender.send_ready_for_pickup(
                customer_phone=customer.contact_number,
                customer_name=customer.name,
                order_no=order.order_no,
                pickup_address=pickup_address,
            )
            
            # Create tracking entry
            OrderTracking.objects.create(
                sale_order=order,
                status='ready_for_pickup',
                title='Ready for Pickup',
                description=f'Order ready at {pickup_address}',
                updated_by=request.user,
                whatsapp_sent=bool(whatsapp_url),
                whatsapp_sent_at=tz_now() if whatsapp_url else None,
            )
            
            delivery_info.pickup_location = pickup_address
            delivery_info.pickup_ready_at = tz_now()
            delivery_info.status = 'assigned'
            delivery_info.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Delivery type: {delivery_info.get_delivery_type_display()}',
            'whatsapp_url': whatsapp_url,
            'delivery_type': delivery_type,
        })
        
    except Exception as e:
        logger.error(f"Set delivery type error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# ADMIN: ASSIGN RIDER
# ============================================

@login_required
@require_POST
def order_assign_rider(request, order_id):
    """Admin: Assign rider to order"""
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        order = get_object_or_404(SaleOrder, pk=order_id)
        delivery_info, _ = DeliveryInfo.objects.get_or_create(sale_order=order)
        
        rider_name = request.POST.get('rider_name', '').strip()
        rider_contact = request.POST.get('rider_contact', '').strip()
        rider_vehicle = request.POST.get('rider_vehicle', '').strip()
        expected_time = request.POST.get('expected_time', '').strip()
        
        if not rider_name or not rider_contact:
            return JsonResponse({
                'success': False,
                'message': 'Rider name aur contact zaroori hai!'
            })
        
        delivery_info.delivery_type = 'local_rider'
        delivery_info.rider_name = rider_name
        delivery_info.rider_contact = rider_contact
        delivery_info.rider_vehicle = rider_vehicle
        delivery_info.status = 'assigned'
        delivery_info.assigned_at = tz_now()
        delivery_info.created_by = request.user
        delivery_info.save()
        
        # Create tracking entry
        tracking = OrderTracking.objects.create(
            sale_order=order,
            status='rider_assigned',
            title='Rider Assigned',
            description=f'Rider: {rider_name} ({rider_contact})',
            rider_name=rider_name,
            rider_contact=rider_contact,
            updated_by=request.user,
        )
        
        # Send WhatsApp
        WhatsAppSender = _get_whatsapp_sender()
        whatsapp_url = None
        
        if WhatsAppSender:
            whatsapp_url = WhatsAppSender.send_rider_assigned(
                customer_phone=order.customer.contact_number,
                customer_name=order.customer.name,
                order_no=order.order_no,
                rider_name=rider_name,
                rider_contact=rider_contact,
                rider_vehicle=rider_vehicle,
                expected_time=expected_time,
            )
            
            if whatsapp_url:
                tracking.whatsapp_sent = True
                tracking.whatsapp_sent_at = tz_now()
                tracking.save()
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Rider {rider_name} assigned!',
            'whatsapp_url': whatsapp_url,
        })
        
    except Exception as e:
        logger.error(f"Assign rider error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# ADMIN: UPDATE STATUS
# ============================================

@login_required
@require_POST
def order_update_status(request, order_id):
    """Admin: Update order status with timeline + WhatsApp"""
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        order = get_object_or_404(SaleOrder, pk=order_id)
        delivery_info, _ = DeliveryInfo.objects.get_or_create(sale_order=order)
        
        new_status = request.POST.get('status')
        location = request.POST.get('location', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        if not new_status:
            return JsonResponse({'success': False, 'message': 'Status required'})
        
        # Update order status
        status_mapping = {
            'confirmed': 'confirmed',
            'processing': 'processing',
            'packed': 'ready',
            'out_for_delivery': 'processing',
            'delivered': 'delivered',
            'cancelled': 'cancelled',
        }
        
        if new_status in status_mapping:
            order.status = status_mapping[new_status]
            order.save()
        
        # Update delivery info
        if new_status == 'out_for_delivery':
            delivery_info.status = 'in_transit'
            delivery_info.save()
        elif new_status == 'delivered':
            delivery_info.status = 'delivered'
            delivery_info.delivered_at = tz_now()
            delivery_info.save()
        
        # Handle photo
        proof_photo = request.FILES.get('proof_photo')
        
        # Create tracking entry
        tracking = OrderTracking.objects.create(
            sale_order=order,
            status=new_status,
            title=dict(OrderTracking.STATUS_CHOICES).get(new_status, new_status),
            description=notes,
            location=location,
            notes=notes,
            proof_photo=proof_photo,
            rider_name=delivery_info.rider_name,
            rider_contact=delivery_info.rider_contact,
            updated_by=request.user,
        )
        
        # Send WhatsApp
        customer = order.customer
        whatsapp_url = None
        WhatsAppSender = _get_whatsapp_sender()
        
        if WhatsAppSender:
            if new_status == 'confirmed':
                whatsapp_url = WhatsAppSender.send_order_confirmed(
                    customer.contact_number, customer.name,
                    order.order_no, float(order.total_amount())
                )
            elif new_status == 'packed':
                whatsapp_url = WhatsAppSender.send_order_packed(
                    customer.contact_number, customer.name, order.order_no
                )
            elif new_status == 'out_for_delivery':
                expected = ''
                if delivery_info.expected_delivery:
                    expected = delivery_info.expected_delivery.strftime('%I:%M %p')
                whatsapp_url = WhatsAppSender.send_out_for_delivery(
                    customer.contact_number, customer.name, order.order_no,
                    rider_name=delivery_info.rider_name or '',
                    rider_contact=delivery_info.rider_contact or '',
                    expected_time=expected,
                )
            elif new_status == 'delivered':
                whatsapp_url = WhatsAppSender.send_delivered(
                    customer.contact_number, customer.name,
                    order.order_no,
                    float(order.advance_payment) if order.advance_payment else 0
                )
            elif new_status == 'cancelled':
                whatsapp_url = WhatsAppSender.send_order_cancelled(
                    customer.contact_number, customer.name,
                    order.order_no, notes
                )
            
            if whatsapp_url:
                tracking.whatsapp_sent = True
                tracking.whatsapp_sent_at = tz_now()
                tracking.save()
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Status updated: {tracking.get_status_display()}',
            'whatsapp_url': whatsapp_url,
            'tracking_id': tracking.id,
        })
        
    except Exception as e:
        logger.error(f"Update status error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# AJAX: GET TIMELINE
# ============================================

@login_required
def order_tracking_timeline(request, order_id):
    """AJAX: Get timeline data"""
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        order = get_object_or_404(SaleOrder, pk=order_id)
        tracking = order.tracking_history.all().order_by('timestamp')
        
        timeline = []
        for t in tracking:
            timeline.append({
                'id': t.id,
                'status': t.status,
                'status_display': t.get_status_display(),
                'title': t.title,
                'description': t.description,
                'location': t.location,
                'notes': t.notes,
                'icon': t.icon,
                'color': t.color,
                'rider_name': t.rider_name,
                'rider_contact': t.rider_contact,
                'photo_url': t.proof_photo.url if t.proof_photo else None,
                'whatsapp_sent': t.whatsapp_sent,
                'timestamp': t.timestamp.strftime('%d %b %Y, %I:%M %p'),
            })
        
        return JsonResponse({'success': True, 'timeline': timeline})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# PUBLIC: TRACK ORDER PAGE
# ============================================

def track_order_public(request):
    """Public tracking page — koi bhi order track kar sakta hai"""
    
    order = None
    delivery_info = None
    tracking_history = []
    error = None
    search_order_no = ''
    search_phone = ''
    
    if request.method == 'POST':
        search_order_no = request.POST.get('order_no', '').strip().upper()
        search_phone = request.POST.get('phone', '').strip()
        
        if not search_order_no:
            error = '❌ Order number zaroori hai'
        else:
            try:
                # Try SaleOrder
                order = SaleOrder.objects.filter(
                    order_no__iexact=search_order_no
                ).select_related('customer').first()
                
                # Try CustomerOrder if not found
                if not order:
                    customer_order = CustomerOrder.objects.filter(
                        order_number__iexact=search_order_no
                    ).select_related('customer').first()
                    if customer_order and customer_order.sale:
                        order = customer_order.sale
                
                if not order:
                    error = f'❌ Order "{search_order_no}" nahi mila'
                else:
                    # Verify phone (optional)
                    if search_phone:
                        clean_input = search_phone.replace(' ', '').replace('-', '').replace('+', '')
                        clean_db = (order.customer.contact_number or '').replace(' ', '').replace('-', '').replace('+', '')
                        
                        if clean_input[-10:] != clean_db[-10:]:
                            error = '❌ Phone number match nahi kar raha'
                            order = None
                
                if order:
                    tracking_history = order.tracking_history.all().order_by('timestamp')
                    try:
                        delivery_info = order.delivery_info
                    except DeliveryInfo.DoesNotExist:
                        delivery_info = None
                        
            except Exception as e:
                logger.error(f"Track order error: {e}")
                error = f'❌ Error: {str(e)}'
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order': order,
        'delivery_info': delivery_info,
        'tracking_history': tracking_history,
        'error': error,
        'search_order_no': search_order_no,
        'search_phone': search_phone,
    }
    return render(request, 'customer_portal/track_order_public.html', context)


# ============================================
# CUSTOMER PORTAL: ORDER TRACKING
# ============================================

@login_required
def customer_order_tracking(request, order_id):
    """Customer ke liye tracking page (login required)"""
    
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Access denied!')
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    try:
        order = SaleOrder.objects.get(id=order_id, customer=customer)
    except SaleOrder.DoesNotExist:
        messages.error(request, 'Order nahi mila!')
        return redirect('my_orders')
    
    tracking_history = order.tracking_history.all().order_by('timestamp')
    
    try:
        delivery_info = order.delivery_info
    except DeliveryInfo.DoesNotExist:
        delivery_info = None
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order': order,
        'tracking_history': tracking_history,
        'delivery_info': delivery_info,
    }
    return render(request, 'customer_portal/order_tracking.html', context)