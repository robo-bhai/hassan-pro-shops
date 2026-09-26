"""
Customer Portal Views — Complete with All Features
====================================================
✅ Cart awareness
✅ Discount calculation (FIXED)
✅ Recently viewed tracking (with batch prices)
✅ Live visitor count
✅ Image zoom support
✅ OTP countdown (refresh-proof)
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Sum, Q, Min
from django.urls import reverse
from decimal import Decimal
from datetime import datetime, timedelta
from types import SimpleNamespace
import json
import logging

from .models import (
    Product, Category, Brand, CompanyInfo,
    Customer, CustomerProfile, CustomerOTP, CustomerAddress,
    SaleOrder, SaleOrderItem, Sale, Warehouse,
    CustomerOrder, CustomerOrderItem, OrderStatusHistory,
    Notification, Inventory, StockBatch, RecentlyViewed,
    LiveVisitor
)

from .decorators import customer_login_required

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


def get_empty_customer():
    """Return empty customer namespace"""
    return SimpleNamespace(
        name='',
        email='',
        contact_number='',
        address='',
        customer_code='',
    )


def calculate_cart_data(cart):
    """Calculate cart items, subtotal, delivery, total"""
    cart_items = []
    subtotal = Decimal('0.00')
    
    if not cart:
        return {
            'cart_items': [],
            'subtotal': Decimal('0.00'),
            'delivery_charges': Decimal('0.00'),
            'total_amount': Decimal('0.00'),
        }
    
    product_ids = []
    for item in cart.values():
        pid = item.get('product_id')
        if pid:
            product_ids.append(pid)
    
    products = Product.objects.in_bulk(product_ids) if product_ids else {}
    
    for key, item in cart.items():
        cart_item = {
            'product_id': item.get('product_id'),
            'name': item.get('name'),
            'price': float(item.get('price', 0)),
            'quantity': int(item.get('quantity', 0)),
            'image': item.get('image'),
        }
        
        item_total = Decimal(str(cart_item['price'])) * cart_item['quantity']
        subtotal += item_total
        cart_item['total'] = float(item_total)
        cart_item['subtotal'] = float(item_total)
        cart_item['product_obj'] = products.get(cart_item['product_id'])
        
        cart_items.append(cart_item)
    
    delivery_charges = Decimal('0.00')
    if subtotal > 0 and subtotal < Decimal('1000'):
        delivery_charges = Decimal('100.00')
    
    total_amount = subtotal + delivery_charges
    
    return {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charges': delivery_charges,
        'total_amount': total_amount,
    }


def check_otp_verified(request):
    """Check if order_verified flag is still valid (30 min)"""
    order_verified = request.session.get('order_verified', False)
    
    if order_verified:
        verified_at_str = request.session.get('order_verified_at')
        if verified_at_str:
            try:
                verified_at = datetime.fromisoformat(
                    verified_at_str.replace('Z', '+00:00')
                )
                if now() - verified_at > timedelta(minutes=30):
                    order_verified = False
            except Exception:
                order_verified = False
        else:
            order_verified = False
    
    return order_verified


def get_otp_remaining_seconds(request):
    """
    ✅ NEW: OTP ka remaining time calculate karo (refresh-proof)
    Returns: (remaining_seconds, otp_object)
    """
    otp_phone = request.session.get('order_otp_phone')
    
    if not otp_phone:
        return 0, None
    
    try:
        latest_otp = CustomerOTP.objects.filter(
            phone=otp_phone,
            purpose='order',
            is_used=False
        ).order_by('-created_at').first()
        
        if latest_otp and latest_otp.expires_at > now():
            delta = latest_otp.expires_at - now()
            remaining = max(0, int(delta.total_seconds()))
            return remaining, latest_otp
        
        return 0, latest_otp
    except Exception as e:
        logger.error(f"OTP remaining calc error: {e}")
        return 0, None


def enrich_recently_viewed_with_prices(recently_viewed):
    """
    ✅ Helper: Recently viewed products ke liye batch price aur stock calculate karo
    ✅ NEW: Discount bhi apply karo
    """
    if not recently_viewed:
        return recently_viewed
    
    rv_product_ids = [p.id for p in recently_viewed]
    
    rv_batch_prices = StockBatch.objects.filter(
        product_id__in=rv_product_ids,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).values('product_id').annotate(
        best_price=Min('selling_price')
    )
    rv_price_map = {bp['product_id']: bp['best_price'] for bp in rv_batch_prices}
    
    rv_stocks = Inventory.objects.filter(
        product_id__in=rv_product_ids
    ).values('product_id').annotate(
        total_stock=Sum('stock')
    )
    rv_stock_map = {s['product_id']: s['total_stock'] or 0 for s in rv_stocks}
    
    for product in recently_viewed:
        # ✅ Base price determine karo
        if product.id in rv_price_map:
            base_price = rv_price_map[product.id]
            product.has_batch_price = True
        else:
            base_price = product.price
            product.has_batch_price = False
        
        # ✅ Discount apply karo
        if product.discount_percentage and product.discount_percentage > 0:
            product.original_price = base_price
            discount_amount = base_price * (product.discount_percentage / Decimal('100'))
            product.price = base_price - discount_amount
            product.has_discount = True
        else:
            product.price = base_price
            product.has_discount = False
            product.original_price = base_price
        
        product.available_stock = rv_stock_map.get(product.id, 0)
    
    return recently_viewed


# ============================================
# 1. SHOP HOME
# ============================================

def shop_home(request):
    """Shop home page with all features"""
    from django.core.paginator import Paginator
    
    products = Product.objects.filter(is_active=True).select_related(
        'category', 'brand', 'unit'
    )
    
    # Search
    search = request.GET.get('search', '').strip()[:100]
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(serial_no__icontains=search) |
            Q(barcode__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Category filter
    category_id = request.GET.get('category', '')
    if category_id:
        try:
            category_id = int(category_id)
            products = products.filter(category_id=category_id)
        except (ValueError, TypeError):
            category_id = ''
    
    # Brand filter
    brand_id = request.GET.get('brand', '')
    if brand_id:
        try:
            brand_id = int(brand_id)
            products = products.filter(brand_id=brand_id)
        except (ValueError, TypeError):
            brand_id = ''
    
    # Annotation
    products = products.annotate(total_stock=Sum('inventory__stock'))
    
    # Sort
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'name':
        products = products.order_by('name')
    else:
        products = products.order_by('-id')
    
    # Paginator
    paginator = Paginator(products, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Batch fetch selling prices
    product_ids = [p.id for p in page_obj]
    
    batch_prices = StockBatch.objects.filter(
        product_id__in=product_ids,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).values('product_id').annotate(
        best_price=Min('selling_price')
    )
    batch_price_map = {bp['product_id']: bp['best_price'] for bp in batch_prices}
    
    # Cart awareness
    cart = request.session.get('cart', {})
    cart_product_ids = set()
    cart_quantities = {}
    
    for key, item in cart.items():
        try:
            pid = int(item.get('product_id'))
            cart_product_ids.add(pid)
            cart_quantities[pid] = item.get('quantity', 0)
        except (ValueError, TypeError):
            pass
    
    # ========================================== #
    # ✅ Apply Discount & Stock to products       #
    # ========================================== #
    for product in page_obj:
        product.available_stock = product.total_stock or 0
        
        # Base price determine karo
        if product.id in batch_price_map:
            base_price = batch_price_map[product.id]
            product.has_batch_price = True
        else:
            base_price = product.price
            product.has_batch_price = False
        
        # ✅ Discount price calculation
        if product.discount_percentage and product.discount_percentage > 0:
            product.original_price = base_price
            discount_amount = base_price * (product.discount_percentage / Decimal('100'))
            product.price = base_price - discount_amount
            product.discount_amount = discount_amount
            product.has_discount = True
        else:
            product.price = base_price
            product.has_discount = False
            product.original_price = base_price
        
        # Cart awareness
        product.in_cart = product.id in cart_product_ids
        product.cart_quantity = cart_quantities.get(product.id, 0)
    
    # ✅ Recently viewed — with batch prices
    recently_viewed = RecentlyViewed.get_recently_viewed(request, limit=8)
    recently_viewed = enrich_recently_viewed_with_prices(recently_viewed)
    
    # ✅ Live visitor count
    live_visitor_count = LiveVisitor.get_active_count(seconds=60)
    
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
        'total_products': paginator.count,
        'cart_count': get_cart_count_value(request),
        'recently_viewed': recently_viewed,
        'live_visitor_count': live_visitor_count,
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
    
    # Track view
    try:
        RecentlyViewed.track_view(request, product)
    except Exception as e:
        logger.error(f"Track view error: {e}")
    
    # Stock
    total_stock = Inventory.objects.filter(product=product).aggregate(
        total=Sum('stock')
    )['total'] or 0
    product.available_stock = total_stock
    
    # ✅ Base price determine karo
    batch = StockBatch.objects.filter(
        product=product,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).order_by('id').first()
    
    if batch:
        base_price = batch.selling_price
        product.has_batch_price = True
    else:
        base_price = product.price
        product.has_batch_price = False
    
    # ✅ Discount price calculation
    if product.discount_percentage and product.discount_percentage > 0:
        product.original_price = base_price
        discount_amount = base_price * (product.discount_percentage / Decimal('100'))
        product.price = base_price - discount_amount
        product.discount_amount = discount_amount
        product.has_discount = True
    else:
        product.price = base_price
        product.has_discount = False
        product.original_price = base_price
    
    # Related products
    related = Product.objects.filter(
        Q(category=product.category) | Q(brand=product.brand),
        is_active=True
    ).exclude(id=product.id).select_related('category', 'brand')[:8]
    
    if related:
        related_ids = [p.id for p in related]
        
        related_batch_prices = StockBatch.objects.filter(
            product_id__in=related_ids,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).values('product_id').annotate(
            best_price=Min('selling_price')
        )
        related_price_map = {bp['product_id']: bp['best_price'] for bp in related_batch_prices}
        
        related_stocks = Inventory.objects.filter(
            product_id__in=related_ids
        ).values('product_id').annotate(
            total_stock=Sum('stock')
        )
        related_stock_map = {s['product_id']: s['total_stock'] or 0 for s in related_stocks}
        
        for rp in related:
            if rp.id in related_price_map:
                rp_base_price = related_price_map[rp.id]
                rp.has_batch_price = True
            else:
                rp_base_price = rp.price
                rp.has_batch_price = False
            
            if rp.discount_percentage and rp.discount_percentage > 0:
                rp.original_price = rp_base_price
                rp_discount = rp_base_price * (rp.discount_percentage / Decimal('100'))
                rp.price = rp_base_price - rp_discount
                rp.has_discount = True
            else:
                rp.price = rp_base_price
                rp.has_discount = False
                rp.original_price = rp_base_price
            
            rp.available_stock = related_stock_map.get(rp.id, 0)
    
    # Recently viewed
    recently_viewed = RecentlyViewed.get_recently_viewed(request, limit=8)
    recently_viewed = enrich_recently_viewed_with_prices(recently_viewed)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'product': product,
        'related_products': related,
        'recently_viewed': recently_viewed,
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/product_detail.html', context)


# ============================================
# 3. ADD TO CART
# ============================================

@require_POST
def add_to_cart(request):
    """Add product to cart with validation"""
    try:
        data = json.loads(request.body) if request.body else request.POST
        
        try:
            product_id = int(data.get('product_id'))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid product'})
        
        try:
            quantity = int(data.get('quantity', 1))
        except (ValueError, TypeError):
            quantity = 1
        
        if quantity < 1:
            return JsonResponse({'success': False, 'message': 'Quantity kam se kam 1 honi chahiye'})
        
        if quantity > 1000:
            return JsonResponse({'success': False, 'message': 'Quantity zyada hai (max 1000)'})
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        total_stock = Inventory.objects.filter(product=product).aggregate(
            total=Sum('stock')
        )['total'] or 0
        
        if total_stock <= 0:
            return JsonResponse({'success': False, 'message': 'Yeh product out of stock hai'})
        
        # ✅ Base price
        batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if batch:
            base_price = batch.selling_price
        else:
            base_price = product.price
        
        # ✅ Discount apply
        if product.discount_percentage and product.discount_percentage > 0:
            discount_amount = base_price * (product.discount_percentage / Decimal('100'))
            final_price = base_price - discount_amount
        else:
            final_price = base_price
        
        cart = request.session.get('cart', {})
        product_key = str(product_id)
        
        if product_key in cart:
            new_qty = cart[product_key]['quantity'] + quantity
            if new_qty > total_stock:
                return JsonResponse({
                    'success': False,
                    'message': f'Sirf {int(total_stock)} units available hain'
                })
            cart[product_key]['quantity'] = new_qty
            cart[product_key]['price'] = float(final_price)
        else:
            if quantity > total_stock:
                return JsonResponse({
                    'success': False,
                    'message': f'Sirf {int(total_stock)} units available hain'
                })
            cart[product_key] = {
                'product_id': product.id,
                'name': product.name,
                'price': float(final_price),
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
        logger.error(f"Add to cart error: {e}")
        return JsonResponse({'success': False, 'message': 'Kuch masla hua'})


# ============================================
# 4. CART VIEW
# ============================================

def cart_view(request):
    """Cart page"""
    cart = request.session.get('cart', {})
    data = calculate_cart_data(cart)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': data['cart_items'],
        'subtotal': data['subtotal'],
        'delivery_charges': data['delivery_charges'],
        'total_amount': data['total_amount'],
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/cart.html', context)


# ============================================
# 5. UPDATE CART
# ============================================

@require_POST
def update_cart(request):
    """Update cart item quantity"""
    try:
        data = json.loads(request.body)
        
        try:
            product_id = int(data.get('product_id'))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid product'})
        
        try:
            quantity = int(data.get('quantity', 1))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid quantity'})
        
        if quantity > 0:
            product = Product.objects.filter(id=product_id).first()
            if product:
                total_stock = Inventory.objects.filter(product=product).aggregate(
                    total=Sum('stock')
                )['total'] or 0
                
                if quantity > total_stock:
                    return JsonResponse({
                        'success': False,
                        'message': f'Sirf {int(total_stock)} units available hain'
                    })
        
        cart = request.session.get('cart', {})
        product_key = str(product_id)
        
        if product_key in cart:
            if quantity > 0:
                cart[product_key]['quantity'] = quantity
            else:
                del cart[product_key]
            
            request.session['cart'] = cart
            request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Update cart error: {e}")
        return JsonResponse({'success': False, 'message': 'Error'})


# ============================================
# 6. REMOVE FROM CART
# ============================================

@require_POST
def remove_from_cart(request, product_id):
    """Remove item from cart"""
    try:
        try:
            product_id = int(product_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid product'})
        
        cart = request.session.get('cart', {})
        product_key = str(product_id)
        
        if product_key in cart:
            del cart[product_key]
            request.session['cart'] = cart
            request.session.modified = True
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Remove from cart error: {e}")
        return JsonResponse({'success': False, 'message': 'Error'})


# ============================================
# 7. CHECKOUT (WITH OTP COUNTDOWN)
# ============================================

@customer_login_required
def checkout(request):
    """Checkout page with OTP countdown (refresh-proof)"""
    cart = request.session.get('cart', {})
    if not cart:
        messages.warning(request, 'Cart khali hai!')
        return redirect('shop_home')
    
    data = calculate_cart_data(cart)
    
    profile = None
    customer = None
    skip_otp = False
    
    if hasattr(request.user, 'customer_profile'):
        try:
            profile = request.user.customer_profile
            customer = profile.customer
            skip_otp = profile.should_skip_order_otp()
        except Exception as e:
            logger.error(f"Checkout profile error: {e}")
            profile = None
            customer = None
    
    if customer is None:
        customer = get_empty_customer()
    
    order_verified = check_otp_verified(request)
    
    # ========================================== #
    # ✅ OTP COUNTDOWN (Refresh-Proof)            #
    # ========================================== #
    otp_remaining_seconds, otp_obj = get_otp_remaining_seconds(request)
    otp_is_active = otp_remaining_seconds > 0 and not order_verified
    
    # Agar OTP verified hai to countdown band karo
    if order_verified:
        otp_remaining_seconds = 0
        otp_is_active = False
    
    # ✅ Masked email for display
    otp_masked_email = ''
    if otp_obj and customer.email:
        email = customer.email
        if '@' in email:
            name, domain = email.split('@')
            otp_masked_email = f"{name[:2]}***@{domain}"
        else:
            otp_masked_email = email
    
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
        'cart_items': data['cart_items'],
        'subtotal': data['subtotal'],
        'delivery_charges': data['delivery_charges'],
        'total_amount': data['total_amount'],
        'cart_count': sum(item['quantity'] for item in cart.values()),
        'customer': customer,
        'profile': profile,
        'skip_otp': skip_otp,
        'order_verified': order_verified,
        'payment_methods': payment_methods,
        
        # ✅ NEW: OTP countdown data
        'otp_remaining_seconds': otp_remaining_seconds,
        'otp_is_active': otp_is_active,
        'otp_masked_email': otp_masked_email,
    }
    return render(request, 'customer_portal/checkout.html', context)


# ============================================
# 8. PLACE ORDER
# ============================================

from django.db import transaction
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.timezone import now
from datetime import timedelta
from decimal import Decimal
import logging

# Email helper functions import karein
from .email_helper import send_customer_order_email, send_admin_order_notification

logger = logging.getLogger(__name__)


@transaction.atomic
@customer_login_required
@require_POST
def place_order(request):
    """Order place karo with email_helper integration"""
    from django.contrib.auth.models import User
    
    try:
        profile = None
        if hasattr(request.user, 'customer_profile'):
            try:
                profile = CustomerProfile.objects.select_for_update().get(
                    pk=request.user.customer_profile.pk
                )
            except CustomerProfile.DoesNotExist:
                messages.error(request, '❌ Customer profile nahi mila')
                return redirect('checkout')
        
        if not profile:
            messages.error(request, '❌ Customer profile nahi mila')
            return redirect('checkout')
        
        # OTP check
        if not profile.should_skip_order_otp():
            otp_verified = check_otp_verified(request)
            if not otp_verified:
                messages.error(request, '❌ Pehle OTP verify karein')
                return redirect('checkout')
        
        customer = profile.customer
        payment_method = request.POST.get('payment_method', 'cod')
        
        valid_methods = ['cod', 'jazzcash', 'easypaisa', 'bank']
        if payment_method not in valid_methods:
            payment_method = 'cod'
        
        cart = request.session.get('cart', {})
        if not cart:
            messages.error(request, 'Cart khali hai!')
            return redirect('shop_home')
        
        warehouse = Warehouse.objects.first()
        if not warehouse:
            messages.error(request, 'Koi warehouse nahi hai!')
            return redirect('shop_home')
        
        # Stock check
        product_ids = [item['product_id'] for item in cart.values()]
        products = Product.objects.in_bulk(product_ids)
        
        for key, item in cart.items():
            product = products.get(item['product_id'])
            if not product:
                messages.error(request, f'Product nahi mila: {item["name"]}')
                return redirect('cart_view')
            
            stock = Inventory.objects.filter(
                product=product, warehouse=warehouse
            ).values_list('stock', flat=True).first() or 0
            
            if stock < item['quantity']:
                messages.error(
                    request,
                    f'{product.name} ka stock kam hai. Available: {int(stock)}'
                )
                return redirect('cart_view')
        
        # Duplicate check
        recent_order = SaleOrder.objects.filter(
            customer=customer,
            created_at__gte=now() - timedelta(seconds=30),
            status='pending'
        ).first()
        
        if recent_order:
            messages.warning(
                request,
                f'Aapka order #{recent_order.order_no} pehle hi place ho chuka hai!'
            )
            return redirect('my_orders')
        
        # Create order
        order = SaleOrder.objects.create(
            customer=customer,
            warehouse=warehouse,
            order_date=now(),
            status='pending',
            notes=f"🌐 WEB ORDER | Payment: {payment_method}",
            discount_value=Decimal('0.00'),
            advance_payment=Decimal('0.00'),
            created_by=request.user if request.user.is_authenticated else None,
        )
        
        total_amount = Decimal('0.00')
        order_summary = []
        
        for key, item in cart.items():
            product_id = item['product_id']
            quantity = item['quantity']
            price = Decimal(str(item['price']))
            product = products.get(product_id)
            
            SaleOrderItem.objects.create(
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
        
        profile.record_successful_order()
        
        # Clear session
        request.session.pop('order_verified', None)
        request.session.pop('order_verified_at', None)
        request.session.pop('order_otp_phone', None)
        request.session.pop('order_otp_id', None)
        request.session.pop('order_token', None)
        request.session['cart'] = {}
        request.session.modified = True
        request.session.save()
        
        company = CompanyInfo.objects.first()
        company_name_str = company.name if company else 'Shop'

        # Notify admin via in-app notification
        try:
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                Notification.send(
                    user=admin,
                    title=f'🛒 New Web Order - {customer.name}',
                    message=(
                        f'Order #{order.order_no}\n'
                        f'Amount: Rs. {total_amount:,.2f}\n'
                        f'Phone: {customer.contact_number}\n'
                        f'Items: {len(order_summary)}'
                    ),
                    notification_type='sale',
                    category='sales',
                    link=f'/orders/sale/{order.id}/'
                )
        except Exception as e:
            logger.error(f"Notification error: {e}")

        # =========================================================
        # ⚡ SEND RESPONSIVE HTML EMAILS VIA EMAIL_HELPER.PY
        # =========================================================
        try:
            customer_email = getattr(customer, 'email', None)
            customer_address = getattr(customer, 'address', 'N/A')
            customer_phone = getattr(customer, 'contact_number', 'N/A')

            # 1. Customer Email
            if customer_email:
                send_customer_order_email(
                    recipient_email=customer_email,
                    order_no=order.order_no,
                    customer_name=customer.name,
                    order_summary=order_summary,
                    total_amount=float(total_amount),
                    payment_method=payment_method,
                    address=customer_address
                )

            # 2. Admin Emails
            admin_emails = list(
                User.objects.filter(is_superuser=True, is_active=True, email__gt='')
                .values_list('email', flat=True)
            )

            if admin_emails:
                admin_order_link = request.build_absolute_uri(f'/orders/sale/{order.id}/')
                send_admin_order_notification(
                    admin_emails=admin_emails,
                    order_no=order.order_no,
                    customer_name=customer.name,
                    customer_phone=customer_phone,
                    total_amount=float(total_amount),
                    items_count=len(order_summary),
                    payment_method=payment_method,
                    order_link=admin_order_link
                )

        except Exception as e:
            logger.error(f"Order email sending error via email_helper: {e}")

        # WhatsApp Notification
        try:
            from .whatsapp_utils import WhatsAppSender
            if customer.contact_number:
                WhatsAppSender.send_order_confirmation(
                    customer.contact_number,
                    order.order_no,
                    float(total_amount),
                    order_summary
                )
        except Exception as e:
            logger.error(f"WhatsApp error: {e}")
        
        context = {
            'company_name': company_name_str,
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
        messages.error(request, 'Order mein masla hua. Please dobara try karein.')
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
# 9.1 GET LIVE VISITOR COUNT (AJAX)
# ============================================

def get_live_visitors(request):
    """Live visitor count (AJAX)"""
    count = LiveVisitor.get_active_count(seconds=60)
    
    if count < 1:
        count = 1
    
    return JsonResponse({
        'success': True,
        'count': count,
        'message': f'{count} log abhi yeh store dekh rahe hain',
    })


# ============================================
# 9.2 GET OTP REMAINING TIME (AJAX)
# ============================================

def get_otp_remaining_api(request):
    """
    ✅ AJAX: OTP ka remaining time server se fetch karo
    Frontend isse polling kar sakta hai taake countdown accurate rahe
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Login required'})
    
    remaining, otp_obj = get_otp_remaining_seconds(request)
    order_verified = check_otp_verified(request)
    
    if order_verified:
        return JsonResponse({
            'success': True,
            'remaining': 0,
            'is_active': False,
            'verified': True,
        })
    
    return JsonResponse({
        'success': True,
        'remaining': remaining,
        'is_active': remaining > 0,
        'verified': False,
    })


# ============================================
# 10. TRACK ORDER
# ============================================

def track_order(request):
    """Order track karo"""
    order_no = request.GET.get('order_no', '').strip()[:50]
    bill_no = request.GET.get('bill_no', '').strip()[:50]
    
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

@customer_login_required
def my_orders(request):
    """Customer order history"""
    from django.core.paginator import Paginator
    
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Yeh page sirf customers ke liye hai')
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    status_filter = request.GET.get('status', '')[:20]
    
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

@customer_login_required
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

@transaction.atomic
@customer_login_required
@require_POST
def cancel_order_customer(request, order_id):
    """Cancel order with lock"""
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    customer = request.user.customer_profile.customer
    
    try:
        order = SaleOrder.objects.select_for_update().get(
            id=order_id, customer=customer
        )
    except SaleOrder.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order nahi mila'})
    
    cancellable_statuses = ['pending', 'confirmed']
    if order.status not in cancellable_statuses:
        return JsonResponse({
            'success': False,
            'message': f'Order cancel nahi ho sakta (status: {order.get_status_display()})'
        })
    
    try:
        reason = request.POST.get('reason', 'Customer requested cancellation')[:500]
        
        order.status = 'cancelled'
        order.save()
        
        profile = request.user.customer_profile
        profile.record_failed_order(
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
            'message': f'Order #{order.order_no} cancel ho gaya',
        })
    except Exception as e:
        logger.error(f"Cancel order error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 14. ORDER SUCCESS PAGE
# ============================================

@customer_login_required
def order_success_page(request, order_id):
    """Order success page"""
    if not hasattr(request.user, 'customer_profile'):
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    try:
        order = SaleOrder.objects.get(id=order_id, customer=customer)
    except SaleOrder.DoesNotExist:
        messages.error(request, 'Order nahi mila')
        return redirect('my_orders')
    
    items = order.items.all().select_related('product')
    total_amount = sum(item.total_amt for item in items)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order': order,
        'customer': customer,
        'items': items,
        'total_amount': total_amount,
        'cart_count': 0,
        'page_title': f'Order #{order.order_no} Placed!',
    }
    return render(request, 'customer_portal/order_success_auto.html', context)