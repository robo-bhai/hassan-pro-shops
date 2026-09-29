"""
Customer Portal Views — COMPLETE PROFESSIONAL VERSION
=======================================================
✅ Cart awareness
✅ Discount calculation
✅ Recently viewed tracking
✅ Live visitor count
✅ OTP countdown
✅ Search optimization with caching
✅ Category & Brand search
✅ Smart Search with Typo Correction
✅ Buy Now + Add to Cart
✅ REAL-TIME Admin Presence for Chat AI
✅ RATE LIMITING for chat
✅ Guest name auto-assign
✅ Attachment support
✅ Race condition safe
✅ Fresh chat threshold
✅ Manual "New Chat" support
✅ CustomerChatbot (NO business data)
✅ PROFESSIONAL DELIVERY SYSTEM:
    ✅ Admin configurable charges
    ✅ City-based pricing
    ✅ Express delivery option
    ✅ Free delivery progress
    ✅ Store pickup option
    ✅ Time estimates
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Sum, Q, Min, Value, DecimalField
from django.db.models.functions import Coalesce
from django.core.cache import cache
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
    LiveVisitor, ChatConversation, ChatMessage, ChatTypingStatus,
    AdminPresence, DeliverySettings
)

from .decorators import customer_login_required

logger = logging.getLogger(__name__)


# ============================================
# ✅ CHAT CONFIGURATION
# ============================================

FRESH_CHAT_THRESHOLD_MINUTES = 3


# ============================================
# ✅ DELIVERY CONFIGURATION (Fallback)
# ============================================

DEFAULT_DELIVERY = {
    'standard_charge': Decimal('100.00'),
    'express_charge': Decimal('300.00'),
    'free_threshold': Decimal('1000.00'),
    'free_enabled': True,
    'express_enabled': True,
    'pickup_enabled': True,
    'standard_time': '2-4 working days',
    'express_time': 'Same day (within city)',
    'city_charges': {
        'karachi': Decimal('100'),
        'lahore': Decimal('120'),
        'islamabad': Decimal('150'),
        'rawalpindi': Decimal('150'),
        'faisalabad': Decimal('130'),
        'multan': Decimal('140'),
        'peshawar': Decimal('180'),
        'quetta': Decimal('250'),
        'other': Decimal('200'),
    },
}


def get_delivery_settings():
    """
    ✅ Delivery settings get karo — admin configurable
    Cache karo 5 minute ke liye
    """
    cache_key = 'delivery_settings'
    settings = cache.get(cache_key)
    
    if settings is None:
        try:
            # Try to get from DB
            db_settings = DeliverySettings.objects.filter(is_active=True).first()
            
            if db_settings:
                settings = {
                    'standard_charge': db_settings.standard_charge,
                    'express_charge': db_settings.express_charge,
                    'free_threshold': db_settings.free_delivery_threshold,
                    'free_enabled': db_settings.free_delivery_enabled,
                    'express_enabled': db_settings.express_delivery_enabled,
                    'pickup_enabled': db_settings.store_pickup_enabled,
                    'standard_time': db_settings.standard_delivery_time,
                    'express_time': db_settings.express_delivery_time,
                    'city_charges': db_settings.city_charges or DEFAULT_DELIVERY['city_charges'],
                }
            else:
                settings = DEFAULT_DELIVERY
        except Exception as e:
            logger.warning(f"Delivery settings error: {e}")
            settings = DEFAULT_DELIVERY
        
        cache.set(cache_key, settings, 300)
    
    return settings


def extract_city_from_address(address):
    """Address se city extract karo"""
    if not address:
        return 'other'
    
    address_lower = address.lower()
    cities = ['karachi', 'lahore', 'islamabad', 'rawalpindi', 'faisalabad', 
              'multan', 'peshawar', 'quetta']
    
    for city in cities:
        if city in address_lower:
            return city
    
    return 'other'


def calculate_delivery_charges(subtotal, customer=None, delivery_type='standard'):
    """
    ✅ SMART DELIVERY CALCULATION
    
    Args:
        subtotal: Cart subtotal
        customer: Customer object (for city-based)
        delivery_type: 'standard', 'express', 'pickup'
    
    Returns:
        dict with charges, time, options
    """
    settings = get_delivery_settings()
    
    # ========================================== #
    # STORE PICKUP — Always FREE                 #
    # ========================================== #
    if delivery_type == 'pickup':
        return {
            'charges': Decimal('0.00'),
            'type': 'pickup',
            'time_estimate': 'Ready for pickup in 2-4 hours',
            'message': '🏪 Store pickup',
            'is_free': True,
        }
    
    # ========================================== #
    # EXPRESS DELIVERY                           #
    # ========================================== #
    if delivery_type == 'express' and settings['express_enabled']:
        return {
            'charges': settings['express_charge'],
            'type': 'express',
            'time_estimate': settings['express_time'],
            'message': '⚡ Express delivery',
            'is_free': False,
        }
    
    # ========================================== #
    # FREE DELIVERY CHECK                        #
    # ========================================== #
    if (settings['free_enabled'] and 
        subtotal >= settings['free_threshold']):
        return {
            'charges': Decimal('0.00'),
            'type': 'standard',
            'time_estimate': settings['standard_time'],
            'message': '🎁 FREE delivery unlocked!',
            'is_free': True,
        }
    
    # ========================================== #
    # CITY-BASED STANDARD DELIVERY               #
    # ========================================== #
    city = 'other'
    if customer and customer.address:
        city = extract_city_from_address(customer.address)
    
    city_charges = settings.get('city_charges', {})
    standard_charge = city_charges.get(city, settings['standard_charge'])
    
    # Convert to Decimal if needed
    if not isinstance(standard_charge, Decimal):
        standard_charge = Decimal(str(standard_charge))
    
    return {
        'charges': standard_charge,
        'type': 'standard',
        'time_estimate': settings['standard_time'],
        'message': '🚚 Standard delivery',
        'is_free': False,
        'city': city,
    }


def get_delivery_options(subtotal, customer=None):
    """
    ✅ All delivery options — for customer to choose
    """
    settings = get_delivery_settings()
    
    options = []
    
    # Standard
    standard = calculate_delivery_charges(subtotal, customer, 'standard')
    options.append({
        'type': 'standard',
        'label': '🚚 Standard Delivery',
        'charges': standard['charges'],
        'time': standard['time_estimate'],
        'is_free': standard['is_free'],
        'is_default': True,
    })
    
    # Express (agar enabled)
    if settings['express_enabled']:
        express = calculate_delivery_charges(subtotal, customer, 'express')
        options.append({
            'type': 'express',
            'label': '⚡ Express Delivery',
            'charges': express['charges'],
            'time': express['time_estimate'],
            'is_free': False,
            'is_default': False,
        })
    
    # Store Pickup (agar enabled)
    if settings['pickup_enabled']:
        pickup = calculate_delivery_charges(subtotal, customer, 'pickup')
        options.append({
            'type': 'pickup',
            'label': '🏪 Store Pickup',
            'charges': Decimal('0.00'),
            'time': pickup['time_estimate'],
            'is_free': True,
            'is_default': False,
        })
    
    return options


# ============================================
# ✅ TYPO CORRECTION HELPERS
# ============================================

def levenshtein_distance(a, b):
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    
    previous_row = list(range(len(b) + 1))
    
    for i, ca in enumerate(a, 1):
        current_row = [i]
        for j, cb in enumerate(b, 1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def get_max_typo_distance(length):
    if length <= 4:
        return 1
    elif length <= 7:
        return 2
    elif length <= 10:
        return 3
    else:
        return max(3, int(length * 0.3))


def find_typo_correction(query, max_suggestions=3):
    from .models import Product
    
    if not query or len(query) < 3:
        return query, None
    
    query_lower = query.lower().strip()
    
    cache_key = 'all_product_words'
    all_words = cache.get(cache_key)
    
    if all_words is None:
        all_words_set = set()
        products = Product.objects.filter(is_active=True).select_related(
            'category', 'brand'
        ).values('name', 'category__name', 'brand__name')[:500]
        
        for p in products:
            for field in ['name', 'category__name', 'brand__name']:
                text = p.get(field, '') or ''
                for word in text.lower().split():
                    word = word.strip('.,-_/()[]:;!?')
                    if len(word) >= 2:
                        all_words_set.add(word)
        
        all_words = list(all_words_set)
        cache.set(cache_key, all_words, 3600)
    
    if query_lower in all_words:
        return query, None
    
    max_distance = get_max_typo_distance(len(query_lower))
    best_match = None
    best_distance = float('inf')
    
    for word in all_words:
        if abs(len(word) - len(query_lower)) > max_distance:
            continue
        
        is_prefix_match = word.startswith(query_lower[:min(3, len(query_lower))])
        distance = levenshtein_distance(query_lower, word)
        adjusted_distance = distance - 0.5 if is_prefix_match else distance
        
        if adjusted_distance < best_distance and distance <= max_distance:
            best_distance = adjusted_distance
            best_match = word
    
    if not best_match:
        for word in all_words:
            if word in query_lower or query_lower in word:
                if len(word) <= len(query_lower) + 2:
                    best_match = word
                    break
    
    if best_match:
        return best_match, query
    return query, None


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_cart_count_value(request):
    cart = request.session.get('cart', {})
    return sum(item.get('quantity', 0) for item in cart.values())


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_empty_customer():
    return SimpleNamespace(
        name='',
        email='',
        contact_number='',
        address='',
        customer_code='',
    )


def calculate_cart_data(cart, customer=None, delivery_type='standard'):
    """
    ✅ COMPLETE CART CALCULATION
    with professional delivery system
    """
    cart_items = []
    subtotal = Decimal('0.00')
    
    if not cart:
        return {
            'cart_items': [],
            'subtotal': Decimal('0.00'),
            'delivery_charges': Decimal('0.00'),
            'total_amount': Decimal('0.00'),
            'delivery_info': None,
            'delivery_options': [],
            'free_delivery_progress': None,
        }
    
    # Calculate items
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
    
    # ✅ Delivery charges
    delivery_info = calculate_delivery_charges(subtotal, customer, delivery_type)
    delivery_charges = delivery_info['charges']
    
    # ✅ All options
    delivery_options = get_delivery_options(subtotal, customer)
    
    # ✅ Free delivery progress
    settings = get_delivery_settings()
    free_delivery_progress = None
    
    if settings['free_enabled'] and subtotal < settings['free_threshold']:
        remaining = settings['free_threshold'] - subtotal
        percent = int((subtotal / settings['free_threshold']) * 100)
        free_delivery_progress = {
            'remaining': remaining,
            'percent': percent,
            'threshold': settings['free_threshold'],
            'unlocked': False,
        }
    elif settings['free_enabled']:
        free_delivery_progress = {
            'remaining': Decimal('0.00'),
            'percent': 100,
            'threshold': settings['free_threshold'],
            'unlocked': True,
        }
    
    total_amount = subtotal + delivery_charges
    
    return {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'delivery_charges': delivery_charges,
        'total_amount': total_amount,
        'delivery_info': delivery_info,
        'delivery_options': delivery_options,
        'free_delivery_progress': free_delivery_progress,
    }


def check_otp_verified(request):
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


def enrich_recently_viewed_with_prices(recently_viewed, cart=None):
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
    
    cart_product_ids = set()
    cart_quantities = {}
    if cart:
        for key, item in cart.items():
            try:
                pid = int(item.get('product_id'))
                cart_product_ids.add(pid)
                cart_quantities[pid] = item.get('quantity', 0)
            except (ValueError, TypeError):
                pass
    
    for product in recently_viewed:
        if product.id in rv_price_map:
            base_price = rv_price_map[product.id]
            product.has_batch_price = True
        else:
            base_price = product.price
            product.has_batch_price = False
        
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
        product.in_cart = product.id in cart_product_ids
        product.cart_quantity = cart_quantities.get(product.id, 0)
    
    return recently_viewed


def get_product_final_price(product):
    batch = StockBatch.objects.filter(
        product=product,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).order_by('id').first()
    
    if batch:
        base_price = batch.selling_price
    else:
        base_price = product.price
    
    if product.discount_percentage and product.discount_percentage > 0:
        discount_amount = base_price * (product.discount_percentage / Decimal('100'))
        return base_price - discount_amount
    return base_price


# ============================================
# 1. SHOP HOME
# ============================================

def shop_home(request):
    """Shop home page"""
    from django.core.paginator import Paginator
    
    products = Product.objects.filter(
        is_active=True
    ).select_related(
        'category', 'brand', 'unit'
    ).only(
        'id', 'name', 'price', 'discount_percentage', 'original_price',
        'image', 'serial_no', 'barcode', 'description',
        'category__name', 'brand__name', 'unit__name'
    )
    
    search = request.GET.get('search', '').strip()[:100]
    original_search = search
    typo_corrected = None
    
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(serial_no__icontains=search) |
            Q(barcode__icontains=search) |
            Q(description__icontains=search) |
            Q(category__name__icontains=search) |
            Q(brand__name__icontains=search)
        )
        
        if not products.exists() and len(search) >= 3:
            corrected, original = find_typo_correction(search)
            
            if corrected != search.lower() and original:
                products = Product.objects.filter(
                    is_active=True
                ).select_related(
                    'category', 'brand', 'unit'
                ).only(
                    'id', 'name', 'price', 'discount_percentage', 'original_price',
                    'image', 'serial_no', 'barcode', 'description',
                    'category__name', 'brand__name', 'unit__name'
                ).filter(
                    Q(name__icontains=corrected) |
                    Q(serial_no__icontains=corrected) |
                    Q(barcode__icontains=corrected) |
                    Q(description__icontains=corrected) |
                    Q(category__name__icontains=corrected) |
                    Q(brand__name__icontains=corrected)
                )
                typo_corrected = corrected
                logger.info(f"🔍 Typo correction: '{search}' → '{corrected}'")
    
    category_id = request.GET.get('category', '')
    if category_id:
        try:
            category_id = int(category_id)
            products = products.filter(category_id=category_id)
        except (ValueError, TypeError):
            category_id = ''
    
    brand_id = request.GET.get('brand', '')
    if brand_id:
        try:
            brand_id = int(brand_id)
            products = products.filter(brand_id=brand_id)
        except (ValueError, TypeError):
            brand_id = ''
    
    products = products.annotate(
        total_stock=Coalesce(
            Sum('inventory__stock'),
            Value(0.0),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        )
    )
    
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'name':
        products = products.order_by('name')
    else:
        products = products.order_by('-id')
    
    paginator = Paginator(products, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    product_ids = [p.id for p in page_obj]
    
    batch_prices = StockBatch.objects.filter(
        product_id__in=product_ids,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).values('product_id').annotate(
        best_price=Min('selling_price')
    )
    batch_price_map = {bp['product_id']: bp['best_price'] for bp in batch_prices}
    
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
    
    for product in page_obj:
        product.available_stock = product.total_stock or 0
        
        if product.id in batch_price_map:
            base_price = batch_price_map[product.id]
            product.has_batch_price = True
        else:
            base_price = product.price
            product.has_batch_price = False
        
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
        
        product.in_cart = product.id in cart_product_ids
        product.cart_quantity = cart_quantities.get(product.id, 0)
    
    recently_viewed = RecentlyViewed.get_recently_viewed(request, limit=8)
    recently_viewed = enrich_recently_viewed_with_prices(recently_viewed, cart=cart)
    
    cache_key = 'live_visitor_count'
    live_visitor_count = cache.get(cache_key)
    if live_visitor_count is None:
        live_visitor_count = LiveVisitor.get_active_count(seconds=60)
        if live_visitor_count < 1:
            live_visitor_count = 1
        cache.set(cache_key, live_visitor_count, 10)
    
    company = cache.get('company_info')
    if not company:
        company = CompanyInfo.objects.first()
        cache.set('company_info', company, 300)
    
    categories = cache.get('all_categories')
    if not categories:
        categories = list(Category.objects.all().only('id', 'name'))
        cache.set('all_categories', categories, 600)
    
    brands = cache.get('all_brands')
    if not brands:
        brands = list(Brand.objects.all().only('id', 'name'))
        cache.set('all_brands', brands, 600)
    
    selected_category_name = ''
    if category_id:
        for cat in categories:
            if cat.id == category_id:
                selected_category_name = cat.name
                break
    
    selected_brand_name = ''
    if brand_id:
        for br in brands:
            if br.id == brand_id:
                selected_brand_name = br.name
                break
    
    # ✅ Delivery settings for banner
    delivery_settings = get_delivery_settings()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'products': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'brands': brands,
        'search': search,
        'original_search': original_search,
        'typo_corrected': typo_corrected,
        'selected_category': category_id,
        'selected_brand': brand_id,
        'selected_sort': sort,
        'selected_category_name': selected_category_name,
        'selected_brand_name': selected_brand_name,
        'total_products': paginator.count,
        'cart_count': get_cart_count_value(request),
        'recently_viewed': recently_viewed,
        'live_visitor_count': live_visitor_count,
        'delivery_settings': delivery_settings,
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
    
    try:
        RecentlyViewed.track_view(request, product)
    except Exception as e:
        logger.error(f"Track view error: {e}")
    
    total_stock = Inventory.objects.filter(product=product).aggregate(
        total=Sum('stock')
    )['total'] or 0
    product.available_stock = total_stock
    
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
    
    cart = request.session.get('cart', {})
    recently_viewed = RecentlyViewed.get_recently_viewed(request, limit=8)
    recently_viewed = enrich_recently_viewed_with_prices(recently_viewed, cart=cart)
    
    company = CompanyInfo.objects.first()
    delivery_settings = get_delivery_settings()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'product': product,
        'related_products': related,
        'recently_viewed': recently_viewed,
        'cart_count': get_cart_count_value(request),
        'delivery_settings': delivery_settings,
    }
    return render(request, 'customer_portal/product_detail.html', context)


# ============================================
# 3. BUY NOW
# ============================================

def buy_now(request, product_id):
    """Buy Now — Single product direct checkout"""
    try:
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        total_stock = Inventory.objects.filter(product=product).aggregate(
            total=Sum('stock')
        )['total'] or 0
        
        if total_stock <= 0:
            messages.error(request, f'{product.name} out of stock hai!')
            return redirect('shop_product_detail', pk=product.id)
        
        final_price = get_product_final_price(product)
        
        request.session['cart'] = {
            str(product_id): {
                'product_id': product.id,
                'name': product.name,
                'price': float(final_price),
                'quantity': 1,
                'image': product.image.url if product.image else None,
            }
        }
        
        request.session['buy_now_mode'] = True
        request.session['buy_now_product_id'] = product.id
        request.session.modified = True
        request.session.save()
        
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            return redirect('checkout')
        else:
            return redirect(f'/shop/login/?next=/shop/checkout/')
    
    except Exception as e:
        logger.error(f"Buy Now error: {e}")
        messages.error(request, 'Kuch masla hua. Dobara try karein.')
        return redirect('shop_home')


# ============================================
# 4. ADD TO CART
# ============================================

@require_POST
def add_to_cart(request):
    """Add product to cart"""
    try:
        data = json.loads(request.body) if request.body else request.POST
        
        if request.session.get('buy_now_mode'):
            del request.session['buy_now_mode']
        if request.session.get('buy_now_product_id'):
            del request.session['buy_now_product_id']
        
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
        
        final_price = get_product_final_price(product)
        
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
# 5. CART VIEW — WITH PROGRESS BAR
# ============================================

def cart_view(request):
    """Cart page — with delivery options and free progress"""
    
    cart = request.session.get('cart', {})
    
    if not cart:
        company = CompanyInfo.objects.first()
        context = {
            'company_name': company.name if company else 'Shop',
            'company': company,
            'cart_items': [],
            'subtotal': Decimal('0.00'),
            'delivery_charges': Decimal('0.00'),
            'total_amount': Decimal('0.00'),
            'cart_count': 0,
            'delivery_info': None,
            'delivery_options': [],
            'free_delivery_progress': None,
        }
        return render(request, 'customer_portal/cart.html', context)
    
    # ✅ Get customer for city-based pricing
    customer = None
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        customer = request.user.customer_profile.customer
    
    # ✅ Get selected delivery type from session
    delivery_type = request.session.get('delivery_type', 'standard')
    
    # ✅ Calculate with delivery system
    data = calculate_cart_data(cart, customer=customer, delivery_type=delivery_type)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': data['cart_items'],
        'subtotal': data['subtotal'],
        'delivery_charges': data['delivery_charges'],
        'total_amount': data['total_amount'],
        'delivery_info': data['delivery_info'],
        'delivery_options': data['delivery_options'],
        'free_delivery_progress': data['free_delivery_progress'],
        'selected_delivery': delivery_type,
        'cart_count': get_cart_count_value(request),
    }
    return render(request, 'customer_portal/cart.html', context)


# ============================================
# 6. UPDATE CART
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
        
        # ✅ Recalculate
        customer = None
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile.customer
        
        delivery_type = request.session.get('delivery_type', 'standard')
        data = calculate_cart_data(cart, customer=customer, delivery_type=delivery_type)
        
        return JsonResponse({
            'success': True,
            'subtotal': float(data['subtotal']),
            'delivery': float(data['delivery_charges']),
            'total': float(data['total_amount']),
            'free_progress': {
                'percent': data['free_delivery_progress']['percent'] if data['free_delivery_progress'] else 0,
                'remaining': float(data['free_delivery_progress']['remaining']) if data['free_delivery_progress'] else 0,
                'unlocked': data['free_delivery_progress']['unlocked'] if data['free_delivery_progress'] else False,
            } if data['free_delivery_progress'] else None,
        })
    except Exception as e:
        logger.error(f"Update cart error: {e}")
        return JsonResponse({'success': False, 'message': 'Error'})


# ============================================
# 7. REMOVE FROM CART
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
# ✅ NEW: SET DELIVERY TYPE
# ============================================

@require_POST
def set_delivery_type(request):
    """AJAX: Customer delivery type change kare"""
    try:
        data = json.loads(request.body)
        delivery_type = data.get('delivery_type', 'standard')
        
        valid_types = ['standard', 'express', 'pickup']
        if delivery_type not in valid_types:
            delivery_type = 'standard'
        
        request.session['delivery_type'] = delivery_type
        request.session.modified = True
        
        # ✅ Recalculate
        cart = request.session.get('cart', {})
        customer = None
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile.customer
        
        data_result = calculate_cart_data(cart, customer=customer, delivery_type=delivery_type)
        
        return JsonResponse({
            'success': True,
            'delivery_charges': float(data_result['delivery_charges']),
            'total_amount': float(data_result['total_amount']),
            'delivery_info': {
                'message': data_result['delivery_info']['message'],
                'time': data_result['delivery_info']['time_estimate'],
                'is_free': data_result['delivery_info']['is_free'],
            },
        })
    except Exception as e:
        logger.error(f"Set delivery type error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# 8. CHECKOUT — WITH DELIVERY OPTIONS
# ============================================

@customer_login_required
def checkout(request):
    """Checkout page — with delivery options"""
    cart = request.session.get('cart', {})
    if not cart:
        messages.warning(request, 'Cart khali hai!')
        return redirect('shop_home')
    
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
    
    # ✅ Get delivery type
    delivery_type = request.session.get('delivery_type', 'standard')
    
    # ✅ Calculate with delivery system
    data = calculate_cart_data(cart, customer=customer, delivery_type=delivery_type)
    
    buy_now_mode = request.session.get('buy_now_mode', False)
    buy_now_product_id = request.session.get('buy_now_product_id')
    
    order_verified = check_otp_verified(request)
    
    otp_remaining_seconds, otp_obj = get_otp_remaining_seconds(request)
    otp_is_active = otp_remaining_seconds > 0 and not order_verified
    
    if order_verified:
        otp_remaining_seconds = 0
        otp_is_active = False
    
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
        'delivery_info': data['delivery_info'],
        'delivery_options': data['delivery_options'],
        'free_delivery_progress': data['free_delivery_progress'],
        'selected_delivery': delivery_type,
        'cart_count': sum(item['quantity'] for item in cart.values()),
        'customer': customer,
        'profile': profile,
        'skip_otp': skip_otp,
        'order_verified': order_verified,
        'payment_methods': payment_methods,
        'otp_remaining_seconds': otp_remaining_seconds,
        'otp_is_active': otp_is_active,
        'otp_masked_email': otp_masked_email,
        'buy_now_mode': buy_now_mode,
        'buy_now_product_id': buy_now_product_id,
    }
    return render(request, 'customer_portal/checkout.html', context)


# ============================================
# 9. PLACE ORDER — WITH DELIVERY
# ============================================

@transaction.atomic
@customer_login_required
@require_POST
def place_order(request):
    """Order place karo — with delivery charges"""
    from django.contrib.auth.models import User
    
    try:
        from app.utils.email_helper import send_customer_order_email, send_admin_order_notification
    except ImportError:
        send_customer_order_email = None
        send_admin_order_notification = None
    
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
        
        if not profile.should_skip_order_otp():
            otp_verified = check_otp_verified(request)
            if not otp_verified:
                messages.error(request, '❌ Pehle OTP verify karein')
                return redirect('checkout')
        
        customer = profile.customer
        payment_method = request.POST.get('payment_method', 'cod')
        delivery_type = request.POST.get('delivery_type', 'standard')
        
        valid_methods = ['cod', 'jazzcash', 'easypaisa', 'bank']
        if payment_method not in valid_methods:
            payment_method = 'cod'
        
        valid_delivery = ['standard', 'express', 'pickup']
        if delivery_type not in valid_delivery:
            delivery_type = 'standard'
        
        cart = request.session.get('cart', {})
        if not cart:
            messages.error(request, 'Cart khali hai!')
            return redirect('shop_home')
        
        warehouse = Warehouse.objects.first()
        if not warehouse:
            messages.error(request, 'Koi warehouse nahi hai!')
            return redirect('shop_home')
        
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
        
        # ✅ Calculate delivery
        cart_data = calculate_cart_data(cart, customer=customer, delivery_type=delivery_type)
        delivery_charges = cart_data['delivery_charges']
        
        # ✅ Create order
        order = SaleOrder.objects.create(
            customer=customer,
            warehouse=warehouse,
            order_date=now(),
            status='pending',
            notes=(
                f"🌐 WEB ORDER\n"
                f"Payment: {payment_method}\n"
                f"Delivery: {delivery_type}\n"
                f"Delivery Charge: Rs. {delivery_charges}\n"
                f"Time: {cart_data['delivery_info']['time_estimate']}"
            ),
            discount_value=Decimal('0.00'),
            advance_payment=delivery_charges,  # Delivery charges as advance
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
        
        # ✅ Final total with delivery
        final_total = total_amount + delivery_charges
        
        profile.record_successful_order()
        
        # ✅ Clear session
        request.session.pop('order_verified', None)
        request.session.pop('order_verified_at', None)
        request.session.pop('order_otp_phone', None)
        request.session.pop('order_otp_id', None)
        request.session.pop('order_token', None)
        request.session.pop('buy_now_mode', None)
        request.session.pop('buy_now_product_id', None)
        request.session.pop('delivery_type', None)
        request.session['cart'] = {}
        request.session.modified = True
        request.session.save()
        
        company = CompanyInfo.objects.first()
        company_name_str = company.name if company else 'Shop'

        # ✅ Notify admins
        try:
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                Notification.send(
                    user=admin,
                    title=f'🛒 New Web Order - {customer.name}',
                    message=(
                        f'Order #{order.order_no}\n'
                        f'Amount: Rs. {final_total:,.2f}\n'
                        f'Delivery: {delivery_type} (Rs. {delivery_charges:,.2f})\n'
                        f'Phone: {customer.contact_number}\n'
                        f'Items: {len(order_summary)}'
                    ),
                    notification_type='sale',
                    category='sales',
                    link=f'/orders/sale/{order.id}/'
                )
        except Exception as e:
            logger.error(f"Notification error: {e}")

        # ✅ Send emails
        if send_customer_order_email or send_admin_order_notification:
            try:
                customer_email = getattr(customer, 'email', None)
                customer_address = getattr(customer, 'address', 'N/A')
                customer_phone = getattr(customer, 'contact_number', 'N/A')

                if customer_email and send_customer_order_email:
                    send_customer_order_email(
                        recipient_email=customer_email,
                        order_no=order.order_no,
                        customer_name=customer.name,
                        order_summary=order_summary,
                        total_amount=float(final_total),
                        payment_method=payment_method,
                        address=customer_address
                    )

                admin_emails = list(
                    User.objects.filter(is_superuser=True, is_active=True, email__gt='')
                    .values_list('email', flat=True)
                )

                if admin_emails and send_admin_order_notification:
                    admin_order_link = request.build_absolute_uri(f'/orders/sale/{order.id}/')
                    send_admin_order_notification(
                        admin_emails=admin_emails,
                        order_no=order.order_no,
                        customer_name=customer.name,
                        customer_phone=customer_phone,
                        total_amount=float(final_total),
                        items_count=len(order_summary),
                        payment_method=payment_method,
                        order_link=admin_order_link
                    )
            except Exception as e:
                logger.error(f"Order email sending error: {e}")

        # ✅ WhatsApp
        try:
            from .whatsapp_utils import WhatsAppSender
            if customer.contact_number:
                WhatsAppSender.send_order_confirmation(
                    customer.contact_number,
                    order.order_no,
                    float(final_total),
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
            'total_amount': final_total,
            'subtotal': total_amount,
            'delivery_charges': delivery_charges,
            'delivery_type': delivery_type,
            'delivery_info': cart_data['delivery_info'],
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
# 10. AJAX ENDPOINTS
# ============================================

def get_cart_count(request):
    return JsonResponse({
        'success': True,
        'cart_count': get_cart_count_value(request),
    })


def get_live_visitors(request):
    cache_key = 'live_visitor_count'
    count = cache.get(cache_key)
    
    if count is None:
        count = LiveVisitor.get_active_count(seconds=60)
        cache.set(cache_key, count, 10)
    
    if count < 1:
        count = 1
    
    return JsonResponse({
        'success': True,
        'count': count,
    })


def get_otp_remaining_api(request):
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
# 11. TRACK ORDER
# ============================================

def track_order(request):
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
# 12. MY ORDERS
# ============================================

@customer_login_required
def my_orders(request):
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
# 13. ORDER DETAIL
# ============================================

@customer_login_required
def order_detail_customer(request, order_id):
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
# 14. CANCEL ORDER
# ============================================

@transaction.atomic
@customer_login_required
@require_POST
def cancel_order_customer(request, order_id):
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
# 15. ORDER SUCCESS PAGE
# ============================================

@customer_login_required
def order_success_page(request, order_id):
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


# ============================================
# UPDATE DELIVERY ADDRESS
# ============================================

@customer_login_required
@require_POST
def update_delivery_address(request):
    from .models import CustomerAddress
    
    if not hasattr(request.user, 'customer_profile'):
        return JsonResponse({'success': False, 'message': 'Login required'})
    
    try:
        data = json.loads(request.body) if request.body else request.POST
        
        full_name = data.get('full_name', '').strip()
        phone = data.get('phone', '').strip()
        address_line_1 = data.get('address_line_1', '').strip()
        city = data.get('city', '').strip()
        postal_code = data.get('postal_code', '').strip()
        landmark = data.get('landmark', '').strip()
        
        if not full_name:
            return JsonResponse({'success': False, 'message': 'Full name zaroori hai'})
        if not phone:
            return JsonResponse({'success': False, 'message': 'Phone number zaroori hai'})
        if not address_line_1:
            return JsonResponse({'success': False, 'message': 'Address zaroori hai'})
        if not city:
            return JsonResponse({'success': False, 'message': 'City zaroori hai'})
        
        import re
        phone_clean = phone.replace(' ', '').replace('-', '')
        if not re.match(r'^(\+92|92|0)?3\d{9}$', phone_clean):
            return JsonResponse({'success': False, 'message': 'Sahi phone number daalein'})
        
        profile = request.user.customer_profile
        customer = profile.customer
        
        customer.name = full_name
        customer.contact_number = phone
        customer.address = f"{address_line_1}, {city}" + (f", {postal_code}" if postal_code else "")
        customer.save()
        
        default_addr = CustomerAddress.objects.filter(
            customer=customer,
            is_default=True
        ).first()
        
        if default_addr:
            default_addr.full_name = full_name
            default_addr.phone = phone
            default_addr.address_line_1 = address_line_1
            default_addr.city = city
            default_addr.postal_code = postal_code
            default_addr.landmark = landmark
            default_addr.save()
        else:
            CustomerAddress.objects.create(
                customer=customer,
                address_type='home',
                full_name=full_name,
                phone=phone,
                address_line_1=address_line_1,
                city=city,
                postal_code=postal_code,
                landmark=landmark,
                is_default=True,
            )
        
        return JsonResponse({
            'success': True,
            'message': '✅ Address update ho gaya!',
            'address': {
                'full_name': full_name,
                'phone': phone,
                'address_line_1': address_line_1,
                'city': city,
                'postal_code': postal_code,
                'landmark': landmark,
                'full_address': customer.address,
            }
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Update address error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ============================================
# LIVE CHAT VIEWS
# ============================================

def _get_or_create_conversation(request, force_new=False):
    """
    Customer ya guest ke liye conversation get/create karo
    """
    fresh_threshold = timedelta(minutes=FRESH_CHAT_THRESHOLD_MINUTES)
    cutoff_time = now() - fresh_threshold
    
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        customer = request.user.customer_profile.customer
        
        if force_new:
            ChatConversation.objects.filter(
                customer=customer,
                status='active'
            ).update(status='closed', closed_at=now())
            
            conversation = ChatConversation.objects.create(
                customer=customer,
                status='active',
                subject=f"Chat with {customer.name}"
            )
            
            session_conv_key = f'chat_conv_id_{customer.id}'
            request.session[session_conv_key] = conversation.id
            request.session.modified = True
            
            logger.info(f"💬 New chat forced for customer {customer.name} - #{conversation.id}")
            return conversation
        
        session_conv_key = f'chat_conv_id_{customer.id}'
        session_conv_id = request.session.get(session_conv_key)
        
        if session_conv_id:
            conversation = ChatConversation.objects.filter(
                id=session_conv_id,
                customer=customer,
                status='active'
            ).first()
            
            if conversation:
                if conversation.last_message_at and conversation.last_message_at >= cutoff_time:
                    logger.info(f"♻️ Reusing session chat #{conversation.id}")
                    return conversation
        
        conversation = ChatConversation.objects.filter(
            customer=customer,
            status='active',
            last_message_at__gte=cutoff_time
        ).order_by('-last_message_at').first()
        
        if conversation:
            request.session[session_conv_key] = conversation.id
            request.session.modified = True
            logger.info(f"♻️ Found recent chat #{conversation.id}")
            return conversation
        
        old_count = ChatConversation.objects.filter(
            customer=customer,
            status='active'
        ).update(status='closed', closed_at=now())
        
        conversation = ChatConversation.objects.create(
            customer=customer,
            status='active',
            subject=f"Chat with {customer.name}"
        )
        
        request.session[session_conv_key] = conversation.id
        request.session.modified = True
        
        logger.info(f"💬 New chat #{conversation.id} for {customer.name} (closed {old_count} old)")
        return conversation
    
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    
    if force_new:
        ChatConversation.objects.filter(
            session_key=session_key,
            status='active'
        ).update(status='closed', closed_at=now())
        
        conversation = ChatConversation.objects.create(
            session_key=session_key,
            status='active',
            guest_name=request.session.get('guest_name', 'Guest')
        )
        
        session_conv_key = f'chat_conv_id_{session_key[:20]}'
        request.session[session_conv_key] = conversation.id
        request.session.modified = True
        
        logger.info(f"💬 New guest chat forced #{conversation.id}")
        return conversation
    
    session_conv_key = f'chat_conv_id_{session_key[:20]}'
    session_conv_id = request.session.get(session_conv_key)
    
    if session_conv_id:
        conversation = ChatConversation.objects.filter(
            id=session_conv_id,
            session_key=session_key,
            status='active'
        ).first()
        
        if conversation:
            if conversation.last_message_at and conversation.last_message_at >= cutoff_time:
                logger.info(f"♻️ Reusing session guest chat #{conversation.id}")
                return conversation
    
    conversation = ChatConversation.objects.filter(
        session_key=session_key,
        status='active',
        last_message_at__gte=cutoff_time
    ).order_by('-last_message_at').first()
    
    if conversation:
        request.session[session_conv_key] = conversation.id
        request.session.modified = True
        logger.info(f"♻️ Found recent guest chat #{conversation.id}")
        return conversation
    
    old_count = ChatConversation.objects.filter(
        session_key=session_key,
        status='active'
    ).update(status='closed', closed_at=now())
    
    conversation = ChatConversation.objects.create(
        session_key=session_key,
        status='active',
        guest_name=request.session.get('guest_name', 'Guest')
    )
    
    request.session[session_conv_key] = conversation.id
    request.session.modified = True
    
    logger.info(f"💬 New guest chat #{conversation.id} (closed {old_count} old)")
    return conversation


@require_POST
def chat_send_message(request):
    """Customer message bheje"""
    
    try:
        data = json.loads(request.body)
        message_text = data.get('message', '').strip()
        guest_name = data.get('guest_name', '').strip()
        guest_phone = data.get('guest_phone', '').strip()
        
        if not message_text:
            return JsonResponse({'success': False, 'message': 'Message khali hai'})
        
        if len(message_text) > 2000:
            return JsonResponse({'success': False, 'message': 'Message bohot lamba (max 2000 chars)'})
        
        session_key_for_rate = request.session.session_key or 'anonymous'
        rate_key = f'chat_rate_{session_key_for_rate}'
        message_count = cache.get(rate_key, 0)
        
        if message_count >= 10:
            return JsonResponse({
                'success': False, 
                'message': '⚠️ Bohot zyada messages! 1 minute ruk kar try karein.'
            })
        
        cache.set(rate_key, message_count + 1, 60)
        
        with transaction.atomic():
            conversation = _get_or_create_conversation(request)
            conversation = ChatConversation.objects.select_for_update().get(pk=conversation.pk)
            
            if not conversation.customer:
                update_fields = []
                
                if guest_name:
                    conversation.guest_name = guest_name
                    update_fields.append('guest_name')
                elif not conversation.guest_name:
                    conversation.guest_name = f"Guest #{conversation.id}"
                    update_fields.append('guest_name')
                
                if guest_phone:
                    conversation.guest_phone = guest_phone
                    update_fields.append('guest_phone')
                
                if update_fields:
                    conversation.save(update_fields=update_fields)
            
            chat_message = ChatMessage(
                conversation=conversation,
                sender_type='customer',
                sender=request.user if request.user.is_authenticated else None,
                message=message_text
            )
            
            if request.FILES.get('attachment'):
                attachment = request.FILES['attachment']
                if attachment.size > 5 * 1024 * 1024:
                    return JsonResponse({
                        'success': False, 
                        'message': '❌ File bohot bara! Max 5MB allowed.'
                    })
                chat_message.attachment = attachment
                chat_message.attachment_name = attachment.name
            
            chat_message.save()
            
            conversation.last_message_at = now()
            conversation.last_message_preview = message_text[:100]
            conversation.admin_unread_count += 1
            conversation.save(update_fields=[
                'last_message_at', 'last_message_preview', 'admin_unread_count'
            ])
        
        admin_online = AdminPresence.is_any_admin_live(seconds=60)
        
        if not admin_online:
            try:
                from .chatbot_engine import CustomerChatbot
                
                chatbot = CustomerChatbot(
                    user=request.user if request.user.is_authenticated else None
                )
                ai_response = chatbot.get_response(message_text)
                
                if ai_response:
                    ai_msg = ChatMessage.objects.create(
                        conversation=conversation,
                        sender_type='system',
                        message=ai_response
                    )
                    
                    conversation.last_message_at = now()
                    conversation.last_message_preview = ai_response[:100]
                    conversation.customer_unread_count += 1
                    conversation.save(update_fields=[
                        'last_message_at', 'last_message_preview', 'customer_unread_count'
                    ])
                    
                    logger.info(f"🤖 Customer AI reply sent to conversation #{conversation.id}")
                    
            except Exception as e:
                logger.error(f"AI chatbot error: {e}")
                try:
                    company = CompanyInfo.objects.first()
                    contact_info = company.contact_number if company else 'N/A'
                    
                    auto_msg = ChatMessage.objects.create(
                        conversation=conversation,
                        sender_type='system',
                        message=(
                            f"👋 Shukriya! Aapka message mil gaya.\n\n"
                            f"Hamara team abhi offline hai. Usually 1 hour mein reply karte hain.\n\n"
                            f"⏰ Support Hours: 9 AM - 10 PM\n"
                            f"📞 Urgent? Contact: {contact_info}"
                        )
                    )
                    conversation.last_message_preview = auto_msg.message[:100]
                    conversation.customer_unread_count += 1
                    conversation.save(update_fields=['last_message_preview', 'customer_unread_count'])
                except Exception as fe:
                    logger.error(f"Fallback auto-reply error: {fe}")
        
        try:
            from .models import Notification
            from django.contrib.auth.models import User
            
            admin_users = User.objects.filter(is_staff=True, is_active=True)
            customer_display = conversation.get_display_name()
            
            for admin in admin_users:
                try:
                    Notification.send(
                        user=admin,
                        title=f"💬 New Chat: {customer_display}",
                        message=message_text[:150],
                        notification_type='info',
                        category='system',
                        link=f"/admin-chat/{conversation.id}/"
                    )
                except Exception as ne:
                    logger.error(f"Notification error: {ne}")
                
                if admin.email:
                    try:
                        from .utils.email_helper import send_chat_notification_email
                        
                        chat_link = request.build_absolute_uri(
                            f'/admin-chat/{conversation.id}/'
                        )
                        
                        send_chat_notification_email(
                            admin_email=admin.email,
                            customer_name=customer_display,
                            customer_phone=conversation.guest_phone or (
                                conversation.customer.contact_number 
                                if conversation.customer else ''
                            ),
                            message_preview=message_text[:300],
                            chat_link=chat_link,
                            is_guest=not conversation.customer,
                            unread_count=conversation.admin_unread_count
                        )
                    except Exception as ee:
                        logger.error(f"Email error: {ee}")
            
            logger.info(f"✅ Admin notified for conversation #{conversation.id}")
            
        except Exception as e:
            logger.error(f"Admin notification error: {e}")
        
        return JsonResponse({
            'success': True,
            'message_id': chat_message.id,
            'timestamp': chat_message.created_at.strftime('%I:%M %p'),
            'conversation_id': conversation.id,
            'admin_online': admin_online,
        })
        
    except Exception as e:
        logger.error(f"Chat send error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


def chat_get_messages(request):
    try:
        after_id = request.GET.get('after_id', 0)
        try:
            after_id = int(after_id)
        except (ValueError, TypeError):
            after_id = 0
        
        force_new = request.GET.get('new_chat') == 'true'
        
        conversation = _get_or_create_conversation(request, force_new=force_new)
        
        current_conv_id = request.GET.get('conversation_id')
        is_new_conversation = False
        
        if current_conv_id:
            try:
                if int(current_conv_id) != conversation.id:
                    is_new_conversation = True
            except (ValueError, TypeError):
                is_new_conversation = True
        else:
            is_new_conversation = True
        
        messages_qs = conversation.messages.filter(
            id__gt=after_id
        ).order_by('created_at')[:50]
        
        messages_data = []
        for msg in messages_qs:
            messages_data.append({
                'id': msg.id,
                'sender_type': msg.sender_type,
                'sender_name': msg.sender.get_full_name() if msg.sender else (
                    conversation.get_display_name() if msg.sender_type == 'customer' else 'Support'
                ),
                'message': msg.message,
                'attachment_url': msg.attachment.url if msg.attachment else None,
                'attachment_name': msg.attachment_name,
                'created_at': msg.created_at.strftime('%I:%M %p'),
                'is_read': msg.is_read,
            })
            
            if msg.sender_type == 'admin' and not msg.is_read:
                msg.mark_read()
        
        if conversation.customer_unread_count > 0:
            conversation.customer_unread_count = 0
            conversation.save(update_fields=['customer_unread_count'])
        
        typing, _ = ChatTypingStatus.objects.get_or_create(conversation=conversation)
        
        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'conversation_id': conversation.id,
            'is_new_conversation': is_new_conversation,
            'status': conversation.status,
            'is_admin_typing': typing.is_admin_typing,
        })
        
    except Exception as e:
        logger.error(f"Chat get error: {e}")
        return JsonResponse({'success': False, 'message': str(e), 'messages': []})


@require_POST
def chat_new(request):
    try:
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile.customer
            
            old_count = ChatConversation.objects.filter(
                customer=customer,
                status='active'
            ).update(status='closed', closed_at=now())
            
            session_key_name = f'chat_conv_id_{customer.id}'
            if session_key_name in request.session:
                del request.session[session_key_name]
                request.session.modified = True
                
        else:
            session_key_val = request.session.session_key
            if session_key_val:
                old_count = ChatConversation.objects.filter(
                    session_key=session_key_val,
                    status='active'
                ).update(status='closed', closed_at=now())
                
                session_key_name = f'chat_conv_id_{session_key_val[:20]}'
                if session_key_name in request.session:
                    del request.session[session_key_name]
                    request.session.modified = True
            else:
                old_count = 0
        
        request.session.modified = True
        
        conversation = _get_or_create_conversation(request, force_new=True)
        
        logger.info(f"💬 User started new chat #{conversation.id} (closed {old_count} old)")
        
        return JsonResponse({
            'success': True,
            'conversation_id': conversation.id,
            'message': '✅ Nayi chat shuru ho gayi!'
        })
        
    except Exception as e:
        logger.error(f"New chat error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@require_POST
def chat_typing(request):
    try:
        data = json.loads(request.body)
        is_typing = data.get('is_typing', False)
        
        conversation = _get_or_create_conversation(request)
        typing, _ = ChatTypingStatus.objects.get_or_create(conversation=conversation)
        typing.is_customer_typing = bool(is_typing)
        typing.save(update_fields=['is_customer_typing', 'updated_at'])
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


def chat_unread_count(request):
    try:
        conversation = _get_or_create_conversation(request)
        
        unread = conversation.messages.filter(
            sender_type__in=['admin', 'system'],
            is_read=False
        ).count()
        
        return JsonResponse({
            'success': True,
            'unread_count': unread,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'unread_count': 0})


@require_POST
def chat_close(request):
    try:
        conversation = _get_or_create_conversation(request)
        conversation.status = 'closed'
        conversation.closed_at = now()
        conversation.save(update_fields=['status', 'closed_at'])
        
        return JsonResponse({
            'success': True,
            'message': 'Chat band kar diya gaya.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
        
# ============================================
# PUBLIC ORDER TRACKING
# ============================================

def track_order_public(request):
    """Public tracking page - Order # daal kar track karein"""
    from .models import OrderTracking, DeliveryInfo
    
    order = None
    delivery_info = None
    tracking_history = []
    error = None
    
    if request.method == 'POST':
        order_no = request.POST.get('order_no', '').strip().upper()
        phone = request.POST.get('phone', '').strip()
        
        if not order_no:
            error = '❌ Order number zaroori hai'
        else:
            try:
                # Try CustomerOrder first
                order = CustomerOrder.objects.filter(
                    order_number__iexact=order_no
                ).first()
                
                # If not found, try SaleOrder
                if not order:
                    order = SaleOrder.objects.filter(
                        order_no__iexact=order_no
                    ).first()
                
                if order:
                    # Verify phone if provided
                    if phone:
                        if order.customer.contact_number != phone:
                            error = '❌ Phone number match nahi kar raha'
                            order = None
                    else:
                        # Show order if no phone required
                        pass
                
                if not order and not error:
                    error = f'❌ Order "{order_no}" nahi mila'
                
                if order:
                    # Get tracking history
                    tracking_history = order.tracking_history.all().order_by('timestamp')
                    
                    # Get delivery info
                    try:
                        delivery_info = order.delivery_info
                    except:
                        delivery_info = None
                        
            except Exception as e:
                error = f'❌ Error: {str(e)}'
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'order': order,
        'delivery_info': delivery_info,
        'tracking_history': tracking_history,
        'error': error,
        'search_order_no': request.POST.get('order_no', '') if request.method == 'POST' else '',
        'search_phone': request.POST.get('phone', '') if request.method == 'POST' else '',
    }
    return render(request, 'customer_portal/track_order_public.html', context)


@customer_login_required
def customer_order_tracking(request, order_id):
    """Customer portal - View tracking for their order"""
    from .models import OrderTracking
    
    if not hasattr(request.user, 'customer_profile'):
        return redirect('shop_home')
    
    customer = request.user.customer_profile.customer
    
    # Get order
    try:
        order = SaleOrder.objects.get(id=order_id, customer=customer)
    except SaleOrder.DoesNotExist:
        messages.error(request, 'Order nahi mila!')
        return redirect('my_orders')
    
    tracking_history = order.tracking_history.all().order_by('timestamp')
    
    try:
        delivery_info = order.delivery_info
    except:
        delivery_info = None
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'Shop',
        'order': order,
        'tracking_history': tracking_history,
        'delivery_info': delivery_info,
    }
    return render(request, 'customer_portal/order_tracking.html', context)