"""
Customer Portal Views — Complete with Order OTP + Trust System
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Sum, Q
from decimal import Decimal
from datetime import datetime, timedelta
import json
import logging

from .models import (
    Product, Category, Brand, CompanyInfo,
    Customer, CustomerProfile, CustomerOTP, CustomerAddress,
    SaleOrder, SaleOrderItem, Sale, Warehouse,
    CustomerOrder, CustomerOrderItem, OrderStatusHistory,
    Notification, Inventory, StockBatch
)

logger = logging.getLogger(__name__)


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_cart_count_value(request):
    """Get cart item count"""
    cart = request.session.get('cart', {})
    return sum(item.get('quantity', 0) for item in cart.values())


def get_client_ip(request):
    """Get client IP safely"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ============================================
# 1. SHOP HOME — Product List
# ============================================

def shop_home(request):
    """Shop home page with products"""
    from django.core.paginator import Paginator
    
    products = Product.objects.filter(is_active=True).select_related(
        'category', 'brand', 'unit'
    )
    
    # Filters
    search = request.GET.get('search', '').strip()
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(serial_no__icontains=search) |
            Q(barcode__icontains=search)
        )
    
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)
    
    brand_id = request.GET.get('brand', '')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    # Sorting
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'name':
        products = products.order_by('name')
    else:
        products = products.order_by('-id')
    
    # Add stock + batch price to each product
    for product in products:
        # Get stock
        total_stock = Inventory.objects.filter(product=product).aggregate(
            total=Sum('stock')
        )['total'] or 0
        product.available_stock = total_stock
        
        # Get batch price
        batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if batch:
            product.price = batch.selling_price
            product.has_batch_price = True
        else:
            product.has_batch_price = False
    
    # Pagination
    paginator = Paginator(products, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'products': page_obj,
        'page_obj': page_obj,
        'categories': Category.objects.all(),
        'brands': Brand.objects.all(),
        'search': search,
        'selected_category': category_id,
        'selected_brand': brand_id,
        'selected_sort': sort,
        'total_products': products.count(),
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/shop.html', context)


# ============================================
# 2. PRODUCT DETAIL
# ============================================

def product_detail(request, pk):
    """Product detail page"""
    product = get_object_or_404(
        Product.objects.select_related('category', 'brand', 'unit'),
        pk=pk, is_active=True
    )
    
    # Stock
    total_stock = Inventory.objects.filter(product=product).aggregate(
        total=Sum('stock')
    )['total'] or 0
    product.available_stock = total_stock
    
    # Batch price
    batch = StockBatch.objects.filter(
        product=product,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).order_by('id').first()
    
    if batch:
        product.price = batch.selling_price
        product.has_batch_price = True
    else:
        product.has_batch_price = False
    
    # Related products
    related = Product.objects.filter(
        Q(category=product.category) | Q(brand=product.brand),
        is_active=True
    ).exclude(id=product.id)[:8]
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'product': product,
        'related_products': related,
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/product_detail.html', context)


# ============================================
# 3. ADD TO CART
# ============================================

@require_POST
def add_to_cart(request):
    """Add product to cart (AJAX)"""
    try:
        data = json.loads(request.body) if request.body else request.POST
        product_id = str(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        
        if not product_id or quantity < 1:
            return JsonResponse({'success': False, 'message': 'Invalid data'})
        
        product = get_object_or_404(Product, id=int(product_id), is_active=True)
        
        # Get price (batch or product)
        batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        price = float(batch.selling_price) if batch else float(product.price)
        
        # Get cart
        cart = request.session.get('cart', {})
        
        # Add or update
        if product_id in cart:
            cart[product_id]['quantity'] += quantity
        else:
            cart[product_id] = {
                'product_id': product.id,
                'name': product.name,
                'price': price,
                'quantity': quantity,
                'image': product.image.url if product.image else None,
            }
        
        request.session['cart'] = cart
        request.session.modified = True
        
        cart_count = sum(item['quantity'] for item in cart.values())
        
        return JsonResponse({
            'success': True,
            'message': f'{product.name} cart mein add ho gaya!',
            'cart_count': cart_count,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 4. CART VIEW
# ============================================

def cart_view(request):
    """Cart page"""
    cart = request.session.get('cart', {})
    
    cart_items = []
    subtotal = Decimal('0.00')
    
    for key, item in cart.items():
        item_total = Decimal(str(item['price'])) * int(item['quantity'])
        subtotal += item_total
        item['total'] = float(item_total)
        cart_items.append(item)
    
    # Delivery
    delivery_charges = Decimal('0.00')
    if subtotal > 0 and subtotal < Decimal('1000'):
        delivery_charges = Decimal('100.00')
    
    total_amount = subtotal + delivery_charges
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charges': delivery_charges,
        'total_amount': total_amount,
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/cart.html', context)


# ============================================
# 5. UPDATE CART
# ============================================

@require_POST
def update_cart(request):
    """Update cart item quantity (AJAX)"""
    try:
        data = json.loads(request.body)
        product_id = str(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        
        cart = request.session.get('cart', {})
        
        if product_id in cart:
            if quantity > 0:
                cart[product_id]['quantity'] = quantity
            else:
                del cart[product_id]
            
            request.session['cart'] = cart
            request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 6. REMOVE FROM CART
# ============================================

@require_POST
def remove_from_cart(request, product_id):
    """Remove item from cart"""
    try:
        cart = request.session.get('cart', {})
        product_id = str(product_id)
        
        if product_id in cart:
            del cart[product_id]
            request.session['cart'] = cart
            request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 7. CHECKOUT — Order Form (WITH OTP STATUS)
# ============================================

@login_required
def checkout(request):
    """
    Checkout page — Order form with OTP prep
    ✅ NEW: order_verified check (session mein)
    """
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, '❌ Pehle login karein')
        return redirect('customer_login')
    
    cart = request.session.get('cart', {})
    if not cart:
        messages.warning(request, 'Cart khali hai!')
        return redirect('shop_home')
    
    # Calculate cart
    cart_items = []
    subtotal = Decimal('0.00')
    for key, item in cart.items():
        item_total = Decimal(str(item['price'])) * int(item['quantity'])
        subtotal += item_total
        item['total'] = float(item_total)
        cart_items.append(item)
    
    # Delivery charges
    delivery_charges = Decimal('0.00')
    if subtotal < Decimal('1000'):
        delivery_charges = Decimal('100.00')
    
    total_amount = subtotal + delivery_charges
    
    # Trust check
    profile = request.user.customer_profile
    customer = profile.customer
    skip_otp = profile.should_skip_order_otp()
    
    # ==========================================
    # ✅ NEW: Check if already OTP verified
    # ==========================================
    order_verified = request.session.get('order_verified', False)
    
    # Check timestamp validity (30 min)
    if order_verified:
        verified_at_str = request.session.get('order_verified_at')
        if verified_at_str:
            try:
                verified_at = datetime.fromisoformat(
                    verified_at_str.replace('Z', '+00:00')
                )
                
                if now() - verified_at > timedelta(minutes=30):
                    order_verified = False  # Expire
            except Exception:
                order_verified = False
        else:
            order_verified = False
    
    # ==========================================
    # ✅ DEBUG
    # ==========================================
    print("=" * 60)
    print("🔍 CHECKOUT PAGE — OTP STATUS")
    print("=" * 60)
    print(f"User: {request.user.username}")
    print(f"skip_otp: {skip_otp}")
    print(f"order_verified: {order_verified}")
    print(f"Session keys: {list(request.session.keys())}")
    print("=" * 60)
    
    # Customer addresses
    addresses = customer.addresses.all()
    default_address = addresses.filter(is_default=True).first()
    
    # Payment methods
    payment_methods = [
        ('cod', '💵 Cash on Delivery', 'Ghar par cash dein'),
        ('jazzcash', '📱 JazzCash', 'Mobile payment'),
        ('easypaisa', '📱 EasyPaisa', 'Mobile payment'),
        ('bank', '🏦 Bank Transfer', 'Bank se transfer'),
    ]
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charges': delivery_charges,
        'total_amount': total_amount,
        'cart_count': sum(item['quantity'] for item in cart.values()),
        'customer': customer,
        'profile': profile,
        'addresses': addresses,
        'default_address': default_address,
        'skip_otp': skip_otp,
        'order_verified': order_verified,  # ✅ NEW
        'payment_methods': payment_methods,
    }
    return render(request, 'customer_portal/checkout.html', context)


# ============================================
# 8. PLACE ORDER — Creates Sale Order
# ============================================

@login_required
@require_POST
def place_order(request):
    """
    Order place karo — SaleOrder banata hai
    ✅ OTP check (agar trusted nahi)
    ✅ Trust tracking
    ✅ 30-minute OTP validity
    """
    from django.contrib.auth.models import User
    
    try:
        # ==========================================
        # ✅ OTP VERIFICATION CHECK
        # ==========================================
        profile = None
        if hasattr(request.user, 'customer_profile'):
            profile = request.user.customer_profile
            
            # Debug
            print("=" * 60)
            print("🔍 PLACE ORDER — OTP CHECK DEBUG")
            print("=" * 60)
            print(f"User: {request.user.username}")
            print(f"is_trusted: {profile.is_trusted}")
            print(f"should_skip: {profile.should_skip_order_otp()}")
            print(f"Session keys: {list(request.session.keys())}")
            print(f"order_verified: {request.session.get('order_verified')}")
            print(f"order_verified_at: {request.session.get('order_verified_at')}")
            print(f"Session ID: {request.session.session_key}")
            print("=" * 60)
            
            if not profile.should_skip_order_otp():
                
                otp_verified = request.session.get('order_verified', False)
                verified_at_str = request.session.get('order_verified_at')
                
                # Check timestamp validity
                if otp_verified and verified_at_str:
                    try:
                        verified_at = datetime.fromisoformat(
                            verified_at_str.replace('Z', '+00:00')
                        )
                        
                        if now() - verified_at > timedelta(minutes=30):
                            print(f"⚠️  OTP EXPIRED")
                            otp_verified = False
                        else:
                            print(f"✅ OTP VALID")
                            
                    except Exception as e:
                        print(f"❌ Timestamp error: {e}")
                        otp_verified = False
                
                if not otp_verified:
                    print("❌ OTP NOT VERIFIED — Redirecting")
                    messages.error(request, '❌ Pehle OTP verify karein')
                    return redirect('checkout')
                
                print("✅ OTP VERIFIED — Proceeding")
        
        # ==========================================
        # Get form data
        # ==========================================
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        notes = request.POST.get('notes', '').strip()
        payment_method = request.POST.get('payment_method', 'cod')
        
        # Validation
        if not name or not phone:
            messages.error(request, 'Naam aur phone number zaroori hai!')
            return redirect('checkout')
        
        # Cart
        cart = request.session.get('cart', {})
        if not cart:
            messages.error(request, 'Cart khali hai!')
            return redirect('shop_home')
        
        # ==========================================
        # Get or create customer
        # ==========================================
        customer = Customer.objects.filter(contact_number=phone).first()
        if not customer:
            full_address = f"{address}, {city}".strip(', ')
            if email:
                full_address += f" | Email: {email}"
            if notes:
                full_address += f" | Notes: {notes}"
            
            customer = Customer.objects.create(
                name=name,
                contact_number=phone,
                address=full_address,
            )
        
        # ==========================================
        # Get default warehouse
        # ==========================================
        warehouse = Warehouse.objects.first()
        if not warehouse:
            messages.error(request, 'Koi warehouse nahi hai!')
            return redirect('shop_home')
        
        # ==========================================
        # ✅ Create SALE ORDER
        # ==========================================
        order = SaleOrder.objects.create(
            customer=customer,
            warehouse=warehouse,
            order_date=now(),
            status='pending',
            notes=f"🌐 WEB ORDER | Payment: {payment_method} | {notes}",
            discount_value=Decimal('0.00'),
            advance_payment=Decimal('0.00'),
            created_by=request.user if request.user.is_authenticated else None,
        )
        
        # ==========================================
        # ✅ Add items to SALE ORDER
        # ==========================================
        total_amount = Decimal('0.00')
        order_summary = []
        
        for key, item in cart.items():
            product_id = item['product_id']
            quantity = item['quantity']
            price = Decimal(str(item['price']))
            product = Product.objects.get(pk=product_id)
            
            order_item = SaleOrderItem.objects.create(
                order=order,
                product=product,
                qty=quantity,
                price=price,
            )
            
            item_total = price * quantity
            total_amount += item_total
            
            order_summary.append({
                'name': product.name,
                'qty': quantity,
                'price': float(price),
                'total': float(item_total),
            })
        
        # ==========================================
        # ✅ RECORD SUCCESSFUL ORDER
        # ==========================================
        if profile:
            profile.record_successful_order()
            
            # Cleanup OTP session
            request.session.pop('order_verified', None)
            request.session.pop('order_verified_at', None)
            request.session.pop('order_otp_phone', None)
            request.session.modified = True
            request.session.save()
        
        # ==========================================
        # Clear cart
        # ==========================================
        request.session['cart'] = {}
        request.session.modified = True
        
        # ==========================================
        # Notification to Admin
        # ==========================================
        try:
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                Notification.send(
                    user=admin,
                    title=f'🛒 New Web Order - {customer.name}',
                    message=(
                        f'Order #{order.order_no}\n'
                        f'Amount: Rs. {total_amount:,.2f}\n'
                        f'Phone: {phone}\n'
                        f'Items: {len(order_summary)}'
                    ),
                    notification_type='sale',
                    category='sales',
                    link=f'/orders/sale/{order.id}/'
                )
        except Exception as e:
            logger.error(f"Notification error: {e}")
        
        # ==========================================
        # WhatsApp (optional)
        # ==========================================
        try:
            from .whatsapp_utils import WhatsAppSender
            if phone:
                WhatsAppSender.send_order_confirmation(
                    phone,
                    order.order_no,
                    float(total_amount),
                    order_summary
                )
        except Exception as e:
            logger.error(f"WhatsApp error: {e}")
        
        # ==========================================
        # Success page
        # ==========================================
        company = CompanyInfo.objects.first()
        context = {
            'company_name': company.name if company else 'Shop',
            'company': company,
            'order': order,
            'customer': customer,
            'order_summary': order_summary,
            'total_amount': total_amount,
            'payment_method': payment_method,
            'cart_count': 0,
        }
        return render(request, 'customer_portal/order_success.html', context)
        
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'Order mein masla hua: {str(e)}')
        return redirect('cart_view')


# ============================================
# 9. GET CART COUNT (AJAX)
# ============================================

def get_cart_count(request):
    """Get cart count (AJAX)"""
    return JsonResponse({
        'success': True,
        'cart_count': get_cart_count_value(request),
    })


# ============================================
# 10. TRACK ORDER
# ============================================

def track_order(request):
    """Order track karo"""
    order_no = request.GET.get('order_no', '').strip()
    bill_no = request.GET.get('bill_no', '').strip()
    
    sale_order = None
    sale = None
    
    if order_no:
        sale_order = SaleOrder.objects.filter(order_no__iexact=order_no).first()
        if sale_order and sale_order.converted_to_sale:
            sale = sale_order.converted_to_sale
    elif bill_no:
        sale = Sale.objects.filter(bill_no__iexact=bill_no).first()
    
    company = CompanyInfo.objects.first()
    cart = request.session.get('cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order_no': order_no,
        'bill_no': bill_no,
        'sale_order': sale_order,
        'sale': sale,
        'cart_count': cart_count,
    }
    return render(request, 'customer_portal/track_order.html', context)


# ============================================
# 11. MY ORDERS
# ============================================

@login_required
def my_orders(request):
    """Customer order history page"""
    from django.core.paginator import Paginator
    
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Yeh page sirf customers ke liye hai')
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    status_filter = request.GET.get('status', '')
    
    orders = SaleOrder.objects.filter(customer=customer).order_by('-order_date')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    all_orders = SaleOrder.objects.filter(customer=customer)
    stats = {
        'total': all_orders.count(),
        'pending': all_orders.filter(
            status__in=['pending', 'confirmed', 'processing', 'ready']
        ).count(),
        'delivered': all_orders.filter(status='delivered').count(),
        'cancelled': all_orders.filter(status='cancelled').count(),
    }
    
    paginator = Paginator(orders, 10)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    company = CompanyInfo.objects.first()
    cart = request.session.get('cart', {})
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'orders': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'cart_count': sum(item['quantity'] for item in cart.values()),
        'page_title': 'My Orders',
    }
    return render(request, 'customer_portal/my_orders.html', context)


# ============================================
# 12. ORDER DETAIL
# ============================================

@login_required
def order_detail_customer(request, order_id):
    """Customer order detail page"""
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Access denied')
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    order = get_object_or_404(SaleOrder, id=order_id, customer=customer)
    items = order.items.all().select_related('product')
    
    status_steps = [
        ('pending', '⏳', 'Order Placed'),
        ('confirmed', '✅', 'Confirmed'),
        ('processing', '⚙️', 'Processing'),
        ('ready', '📦', 'Ready to Ship'),
        ('partially_delivered', '🚚', 'Partially Delivered'),
        ('delivered', '🎉', 'Delivered'),
    ]
    
    current_index = 0
    for i, (status, icon, label) in enumerate(status_steps):
        if order.status == status:
            current_index = i
            break
    
    total_amount = sum(item.total_amt for item in items)
    
    company = CompanyInfo.objects.first()
    cart = request.session.get('cart', {})
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order': order,
        'items': items,
        'total_amount': total_amount,
        'status_steps': status_steps,
        'current_index': current_index,
        'cart_count': sum(item['quantity'] for item in cart.values()),
        'page_title': f'Order #{order.order_no}',
    }
    return render(request, 'customer_portal/order_detail.html', context)


# ============================================
# 13. CANCEL ORDER
# ============================================

@login_required
@require_POST
def cancel_order_customer(request, order_id):
    """Customer cancels order"""
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    customer = request.user.customer_profile.customer
    order = get_object_or_404(SaleOrder, id=order_id, customer=customer)
    
    cancellable_statuses = ['pending', 'confirmed']
    if order.status not in cancellable_statuses:
        return JsonResponse({
            'success': False,
            'message': f'Order cannot be cancelled (status: {order.get_status_display()})'
        })
    
    try:
        reason = request.POST.get('reason', 'Customer requested cancellation')
        
        order.status = 'cancelled'
        order.save()
        
        request.user.customer_profile.record_failed_order(
            f"Cancelled order #{order.order_no}: {reason}"
        )
        
        try:
            from django.contrib.auth.models import User
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                Notification.send(
                    user=admin,
                    title=f'❌ Order Cancelled - #{order.order_no}',
                    message=f'Customer: {customer.name}\nReason: {reason}',
                    notification_type='warning',
                    category='sales',
                )
        except Exception:
            pass
        
        return JsonResponse({
            'success': True,
            'message': f'Order #{order.order_no} cancelled successfully',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})