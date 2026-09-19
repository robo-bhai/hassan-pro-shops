"""
Customer Portal
Public-facing shop where anyone can view products and place orders
WITH Batch Price Support and Sale Order Integration
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Min, Max, Avg
from django.utils.timezone import now
from django.contrib import messages
from django.core.paginator import Paginator
from decimal import Decimal
import json
import logging

logger = logging.getLogger(__name__)


# ========================================== #
# 1. SHOP HOME — All Products with Batch Price #
# ========================================== #

def shop_home(request):
    """Public shop — sab products dikhao (Batch Price ke saath)"""
    
    from .models import (
        Product, Category, Brand, CompanyInfo, 
        Inventory, StockBatch
    )
    
    # Get all active products
    products = Product.objects.filter(
        is_active=True
    ).select_related('category', 'brand', 'unit')
    
    # Search
    search = request.GET.get('search', '').strip()
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search) |
            Q(serial_no__icontains=search) |
            Q(barcode__icontains=search)
        )
    
    # Category filter
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)
    
    # Brand filter
    brand_id = request.GET.get('brand', '')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    # Sort
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'name':
        products = products.order_by('name')
    else:
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ✅ For each product — get stock AND batch selling price
    for product in page_obj:
        inventory = Inventory.objects.filter(product=product).aggregate(
            total=Sum('stock')
        )['total'] or 0
        product.available_stock = inventory
        
        latest_batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if latest_batch and latest_batch.selling_price > 0:
            product.batch_price = latest_batch.selling_price
            product.price = latest_batch.selling_price
            product.has_batch_price = True
        elif product.price and product.price > 0:
            product.batch_price = product.price
            product.has_batch_price = False
        else:
            avg_batch = StockBatch.objects.filter(
                product=product,
                remaining_qty__gt=0
            ).aggregate(avg=Avg('selling_price'))['avg']
            
            if avg_batch and avg_batch > 0:
                product.batch_price = avg_batch
                product.price = avg_batch
            else:
                product.batch_price = Decimal('0.00')
            product.has_batch_price = False
    
    # Filter options
    categories = Category.objects.filter(
        products__is_active=True
    ).distinct()
    
    brands = Brand.objects.filter(
        products__is_active=True
    ).distinct()
    
    company = CompanyInfo.objects.first()
    
    cart = request.session.get('cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'page_obj': page_obj,
        'products': page_obj,
        'search': search,
        'selected_category': category_id,
        'selected_brand': brand_id,
        'selected_sort': sort,
        'categories': categories,
        'brands': brands,
        'total_products': products.count(),
        'cart_count': cart_count,
    }
    return render(request, 'customer_portal/shop.html', context)


# ========================================== #
# 2. PRODUCT DETAIL with Batch Price          #
# ========================================== #

def product_detail(request, pk):
    """Single product ki detail (Batch Price ke saath)"""
    
    from .models import Product, Inventory, CompanyInfo, StockBatch
    
    product = get_object_or_404(Product, pk=pk, is_active=True)
    
    inventory = Inventory.objects.filter(product=product).aggregate(
        total=Sum('stock')
    )['total'] or 0
    product.available_stock = inventory
    
    latest_batch = StockBatch.objects.filter(
        product=product,
        remaining_qty__gt=0,
        selling_price__gt=0
    ).order_by('id').first()
    
    if latest_batch and latest_batch.selling_price > 0:
        product.batch_price = latest_batch.selling_price
        product.price = latest_batch.selling_price
        product.has_batch_price = True
    elif product.price and product.price > 0:
        product.batch_price = product.price
        product.has_batch_price = False
    else:
        avg_batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0
        ).aggregate(avg=Avg('selling_price'))['avg']
        
        if avg_batch and avg_batch > 0:
            product.batch_price = avg_batch
            product.price = avg_batch
        else:
            product.batch_price = Decimal('0.00')
        product.has_batch_price = False
    
    related = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(pk=product.pk)[:4]
    
    for rp in related:
        rp_batch = StockBatch.objects.filter(
            product=rp,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if rp_batch and rp_batch.selling_price > 0:
            rp.price = rp_batch.selling_price
    
    company = CompanyInfo.objects.first()
    
    cart = request.session.get('cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'product': product,
        'related_products': related,
        'cart_count': cart_count,
    }
    return render(request, 'customer_portal/product_detail.html', context)


# ========================================== #
# 3. ADD TO CART                              #
# ========================================== #

@require_POST
def add_to_cart(request):
    """Cart mein product add karo (Batch Price ke saath)"""
    
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        
        if not product_id or quantity <= 0:
            return JsonResponse({'success': False, 'message': 'Invalid data'})
        
        from .models import Product, Inventory, StockBatch
        
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        
        stock = Inventory.objects.filter(product=product).aggregate(
            total=Sum('stock')
        )['total'] or 0
        
        if stock < quantity:
            return JsonResponse({
                'success': False,
                'message': f'Only {stock} items available'
            })
        
        latest_batch = StockBatch.objects.filter(
            product=product,
            remaining_qty__gt=0,
            selling_price__gt=0
        ).order_by('id').first()
        
        if latest_batch and latest_batch.selling_price > 0:
            cart_price = latest_batch.selling_price
        elif product.price and product.price > 0:
            cart_price = product.price
        else:
            cart_price = Decimal('0.00')
        
        cart = request.session.get('cart', {})
        
        if str(product_id) in cart:
            cart[str(product_id)]['quantity'] += quantity
            cart[str(product_id)]['price'] = float(cart_price)
        else:
            cart[str(product_id)] = {
                'product_id': product.id,
                'name': product.name,
                'price': float(cart_price),
                'quantity': quantity,
                'unit': product.unit.name if product.unit else '',
            }
        
        request.session['cart'] = cart
        request.session.modified = True
        
        total_items = sum(item['quantity'] for item in cart.values())
        
        return JsonResponse({
            'success': True,
            'message': 'Product added to cart',
            'cart_count': total_items,
            'price': float(cart_price),
        })
    
    except Exception as e:
        logger.error(f"Add to cart error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


# ========================================== #
# 4. CART VIEW                                #
# ========================================== #

def cart_view(request):
    """Cart dekho"""
    
    from .models import CompanyInfo, StockBatch, Product
    
    cart = request.session.get('cart', {})
    
    cart_items = []
    subtotal = Decimal('0.00')
    cart_updated = False
    
    for key, item in cart.items():
        product_id = item['product_id']
        
        try:
            product = Product.objects.get(pk=product_id)
            
            latest_batch = StockBatch.objects.filter(
                product=product,
                remaining_qty__gt=0,
                selling_price__gt=0
            ).order_by('id').first()
            
            if latest_batch and latest_batch.selling_price > 0:
                current_price = float(latest_batch.selling_price)
            elif product.price and product.price > 0:
                current_price = float(product.price)
            else:
                current_price = item['price']
            
            if current_price != item['price']:
                item['price'] = current_price
                cart[key]['price'] = current_price
                cart_updated = True
        
        except Exception:
            pass
        
        item_total = Decimal(str(item['price'])) * item['quantity']
        subtotal += item_total
        item['total'] = float(item_total)
        cart_items.append(item)
    
    if cart_updated:
        request.session['cart'] = cart
        request.session.modified = True
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'cart_count': sum(item['quantity'] for item in cart.values()),
    }
    return render(request, 'customer_portal/cart.html', context)


# ========================================== #
# 5. UPDATE CART                              #
# ========================================== #

@require_POST
def update_cart(request):
    """Cart quantity update karo"""
    
    try:
        data = json.loads(request.body)
        product_id = str(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        
        cart = request.session.get('cart', {})
        
        if product_id in cart:
            if quantity <= 0:
                del cart[product_id]
            else:
                cart[product_id]['quantity'] = quantity
        
        request.session['cart'] = cart
        request.session.modified = True
        
        subtotal = sum(
            Decimal(str(item['price'])) * item['quantity']
            for item in cart.values()
        )
        
        total_items = sum(item['quantity'] for item in cart.values())
        
        return JsonResponse({
            'success': True,
            'subtotal': float(subtotal),
            'cart_count': total_items,
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ========================================== #
# 6. REMOVE FROM CART                          #
# ========================================== #

@require_POST
def remove_from_cart(request, product_id):
    """Cart se hatao"""
    
    cart = request.session.get('cart', {})
    product_id = str(product_id)
    
    if product_id in cart:
        del cart[product_id]
        request.session['cart'] = cart
        request.session.modified = True
    
    return JsonResponse({'success': True})


# ========================================== #
# 7. CHECKOUT                                 #
# ========================================== #

def checkout(request):
    """Order form"""
    
    from .models import CompanyInfo
    
    cart = request.session.get('cart', {})
    
    if not cart:
        messages.warning(request, 'Cart khali hai!')
        return redirect('shop_home')
    
    cart_items = []
    subtotal = Decimal('0.00')
    
    for key, item in cart.items():
        item_total = Decimal(str(item['price'])) * item['quantity']
        subtotal += item_total
        item['total'] = float(item_total)
        cart_items.append(item)
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'Shop',
        'company': company,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'cart_count': sum(item['quantity'] for item in cart.values()),
    }
    return render(request, 'customer_portal/checkout.html', context)


# ========================================== #
# 8. PLACE ORDER — Sale Order Banata Hai     #
# ========================================== #

@require_POST
def place_order(request):
    """Order place karo — Sale Order banata hai (Sale nahi)"""
    
    from .models import (
        Customer, SaleOrder, SaleOrderItem, Warehouse, CompanyInfo,
        Notification, Product
    )
    from django.contrib.auth.models import User
    
    try:
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
            messages.error(request, 'Koi warehouse nahi hai! Admin se rabta karein.')
            return redirect('shop_home')
        
        # ==========================================
        # ✅ Create SALE ORDER (not Sale)
        # ==========================================
        order = SaleOrder.objects.create(
            customer=customer,
            warehouse=warehouse,
            order_date=now(),
            status='pending',
            notes=f"🌐 WEB ORDER | Payment: {payment_method} | {notes}",
            discount_value=Decimal('0.00'),
            advance_payment=Decimal('0.00'),
            created_by=None,
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
        # Clear cart
        # ==========================================
        request.session['cart'] = {}
        request.session.modified = True
        
        # ==========================================
        # ✅ Notification to Admin
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
                        f'Items: {len(order_summary)}\n\n'
                        f'👉 Go to Sale Orders to process'
                    ),
                    notification_type='sale',
                    category='sales',
                    link=f'/orders/sale/{order.id}/'
                )
        except Exception as e:
            logger.error(f"Notification error: {e}")
        
        # ==========================================
        # WhatsApp to customer (optional)
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
        # Success
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
        }
        return render(request, 'customer_portal/order_success.html', context)
    
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        messages.error(request, f'Order mein masla hua: {str(e)}')
        return redirect('cart_view')


# ========================================== #
# 9. GET CART COUNT (AJAX)                     #
# ========================================== #

def get_cart_count(request):
    """Cart mein kitne items hain"""
    cart = request.session.get('cart', {})
    count = sum(item['quantity'] for item in cart.values())
    return JsonResponse({'cart_count': count})


# ========================================== #
# 10. TRACK ORDER                              #
# ========================================== #

def track_order(request):
    """Order track karo — Sale Order ya Sale dono"""
    
    from .models import CompanyInfo, Sale, SaleOrder
    
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