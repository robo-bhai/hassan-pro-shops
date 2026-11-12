"""
Step 2 - Multi-vendor cart aur vendor ke orders.

Is file mein 2 hisse hain:

A) CART RULES  (customer side)
   - cart mein ek waqt ek hi store ka maal (store = vendor, ya vendor_id=0 matlab shop ka apna maal)
   - store ki delivery fee, minimum order aur open/closed checkout mein lagte hain

B) VENDOR ORDER ACTIONS  (vendor side)
   - naya order aane par vendor ko notification
   - Accept / Reject / Ready
   - Reject par customer ko wajah ke saath notification + refund note + doosre stores ke suggestions

Order ka status purane SaleOrder statuses se hi chalta hai (admin ka kaam waise hi chalta rahe):
    pending   -> vendor ke liye "New"
    confirmed -> Accepted (tayyar ho raha hai)
    ready     -> Ready (rider/customer ke liye tayyar)
    delivered -> Deliver ho gaya (vendor khud mark karta hai; cash mil gaya)
    cancelled -> Rejected (reject_reason ke saath)
"""
import logging
from decimal import Decimal

from django.utils.timezone import now

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

# Vendor reject karte waqt in mein se wajah chunta hai
REJECT_REASONS = [
    ('out_of_stock', 'Item abhi stock mein nahi'),
    ('store_busy', 'Store abhi bohat busy hai'),
    ('store_closed', 'Store band ho raha hai'),
    ('out_of_area', 'Aap ke area mein delivery nahi'),
    ('price_issue', 'Item ki price/detail mein ghalti'),
    ('other', 'Doosri wajah'),
]
REJECT_REASON_LABELS = dict(REJECT_REASONS)

# vendor action -> (status se, status par, naya status)
ACTIONS = {
    'accept': (('pending',), 'confirmed'),
    'reject': (('pending',), 'cancelled'),
    'ready': (('confirmed', 'processing'), 'ready'),
    'delivered': (('ready',), 'delivered'),
}


# ============================================================
# A) CART RULES
# ============================================================

def _vendor_ids_in_cart(cart):
    """Cart ke items kin stores ke hain. 0 = shop ka apna maal. Purane session items (vendor_id ke baghair) DB se."""
    ids = set()
    missing = []
    for item in (cart or {}).values():
        if 'vendor_id' in item:
            ids.add(int(item.get('vendor_id') or 0))
        elif item.get('product_id'):
            missing.append(item['product_id'])
    if missing:
        from ..models import Product
        for vid in Product.objects.filter(pk__in=missing).values_list('vendor_id', flat=True):
            ids.add(int(vid or 0))
    return ids


def cart_store_id(cart):
    """Cart ka store id (0 = shop). Cart khali ho to None."""
    ids = _vendor_ids_in_cart(cart)
    return sorted(ids)[0] if ids else None


def get_store_profile(vendor_id):
    """vendor_id ka VendorProfile (ya None: shop ka apna maal / profile nahi)."""
    if not vendor_id:
        return None
    from ..models import VendorProfile
    return VendorProfile.objects.filter(vendor_id=vendor_id).first()


def store_name(vendor_id):
    """Customer ko dikhane wala store ka naam."""
    prof = get_store_profile(vendor_id)
    if prof:
        return prof.business_name
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def cart_store_rules(cart, subtotal):
    """
    Cart ke store ke qaide: delivery fee, minimum order, open/closed.

    Shop ke apne maal (vendor_id=0) par kuch nahi lagta - purana delivery system chalta hai.
    """
    ids = _vendor_ids_in_cart(cart)
    vendor_id = sorted(ids)[0] if ids else 0
    prof = get_store_profile(vendor_id)
    subtotal = Decimal(str(subtotal or 0))
    rules = {
        'vendor_id': vendor_id,
        'is_vendor_store': prof is not None,
        'mixed': len(ids) > 1,
        'profile': prof,
        'name': prof.business_name if prof else store_name(0),
        'delivery_fee': ZERO,
        'min_order': ZERO,
        'min_ok': True,
        'short_by': ZERO,
        'is_open': True,
        'closed_message': '',
        'time_text': '',
    }
    if prof is None:
        return rules

    min_order = Decimal(prof.min_order_amount or 0)
    rules.update({
        'delivery_fee': Decimal(prof.delivery_fee or 0),
        'min_order': min_order,
        'min_ok': subtotal >= min_order,
        'short_by': max(min_order - subtotal, ZERO),
        'is_open': prof.is_open_now,
        'time_text': f"{prof.delivery_time_min}-{prof.delivery_time_max} min",
    })
    if not prof.is_open_now:
        rules['closed_message'] = f'{prof.business_name} abhi band hai, baad mein order karein.'
    return rules


def vendor_delivery_info(rules):
    """calculate_delivery_charges jaisa dict, par store ki apni fee ke sath."""
    fee = rules['delivery_fee']
    return {
        'charges': fee,
        'type': 'standard',
        'time_estimate': rules['time_text'],
        'message': f"🚚 {rules['name']} delivery",
        'is_free': fee <= 0,
    }


def vendor_delivery_options(rules):
    info = vendor_delivery_info(rules)
    return [{
        'type': 'standard',
        'label': f"🚚 {rules['name']} Delivery",
        'charges': info['charges'],
        'time': info['time_estimate'],
        'is_free': info['is_free'],
        'is_default': True,
    }]


def validate_cart_for_order(cart, subtotal):
    """Order se pehle check. Masla ho to message (str) lautata hai, theek ho to None."""
    rules = cart_store_rules(cart, subtotal)
    if rules['mixed']:
        return 'Cart mein alag alag stores ka maal hai. Cart khali karke ek hi store se order karein.'
    if rules['is_vendor_store']:
        if not rules['is_open']:
            return rules['closed_message']
        if not rules['min_ok']:
            return (f"{rules['name']} ka minimum order Rs. {rules['min_order']:,.0f} hai. "
                    f"Aur Rs. {rules['short_by']:,.0f} ka maal add karein.")
    return None


def store_order_fields(cart, cart_data, payment_method):
    """SaleOrder.objects.create(...) mein lagane wali store ki fields."""
    rules = cart_data.get('store') or cart_store_rules(cart, cart_data.get('subtotal', 0))
    prof = rules.get('profile')
    return {
        'vendor': prof.vendor if prof else None,
        'delivery_fee': cart_data.get('delivery_charges') or ZERO,
        'payment_method': payment_method or '',
    }


# ============================================================
# B) VENDOR ORDER ACTIONS
# ============================================================

def order_payable_total(order):
    """Items + delivery fee - discount."""
    return order.total_after_discount() + (order.delivery_fee or ZERO)


def _notify(user, title, message, link=None, kind='info'):
    if not user:
        return
    try:
        from ..models import Notification
        Notification.send(user=user, title=title, message=message,
                          notification_type=kind, category='sales', link=link)
    except Exception as exc:  # notification se order kabhi na rukey
        logger.error("Notification error: %s", exc)


def _customer_user(order):
    portal = getattr(order.customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def notify_vendor_new_order(order):
    """Naya order aane par vendor ko in-app notification (vendor dashboard/navbar mein)."""
    if not order.vendor_id:
        return
    prof = get_store_profile(order.vendor_id)
    if not prof:
        return
    items = order.items.count()
    _notify(
        prof.user,
        f'🛒 Naya order #{order.order_no}',
        (f'{order.customer.name} - {items} item(s)\n'
         f'Total: Rs. {order_payable_total(order):,.0f}\n'
         f'Dashboard mein Accept ya Reject karein.'),
        link='/shop/vendor/orders/',
        kind='sale',
    )


def _order_items(order):
    items = []
    for it in order.items.select_related('product'):
        price = it.price or ZERO
        items.append({'name': getattr(it.product, 'name', '?'), 'qty': it.qty,
                      'price': float(price), 'total': float(price * it.qty)})
    return items


def vendor_email_for(vendor_id):
    """Vendor ki email: portal user ki email, warna Vendor record ki (agar ho)."""
    prof = get_store_profile(vendor_id)
    if not prof:
        return ''
    return ((prof.user.email if prof.user_id else '') or getattr(prof.vendor, 'email', '') or '').strip()


def email_new_order(order, request=None):
    """
    Naya order aane par EMAIL: vendor ko (agar order kisi store ka hai) aur admin(s) ko (superusers).
    Order kabhi nahi rukta: koi bhi ghalti log hoti hai. Transaction commit hone ke baad bhejti hai.
    """
    from django.db import transaction

    def _send():
        try:
            from django.contrib.auth.models import User
            from ..utils.email_helper import send_admin_order_notification, send_vendor_order_notification

            customer = order.customer
            items = _order_items(order)
            total = float(order_payable_total(order))
            method = order.payment_method or 'cod'
            phone = getattr(customer, 'contact_number', '') or 'N/A'
            address = getattr(customer, 'address', '') or ''

            def link(path):
                return request.build_absolute_uri(path) if request else None

            # --- vendor ---
            if order.vendor_id:
                to = vendor_email_for(order.vendor_id)
                if to:
                    send_vendor_order_notification(
                        vendor_email=to, order_no=order.order_no, store_name=store_name(order.vendor_id),
                        customer_name=customer.name, customer_phone=phone, address=address, items=items,
                        total_amount=total, payment_method=method, order_link=link('/shop/vendor/orders/'))
                else:
                    logger.warning('Order %s: vendor %s ki email nahi, vendor ko mail nahi gayi.',
                                   order.order_no, order.vendor_id)

            # --- admin(s) ---
            admin_emails = list(User.objects.filter(is_superuser=True, is_active=True, email__gt='')
                                .values_list('email', flat=True))
            if admin_emails:
                send_admin_order_notification(
                    admin_emails=admin_emails, order_no=order.order_no, customer_name=customer.name,
                    customer_phone=phone, total_amount=total, items_count=len(items), payment_method=method,
                    order_link=link(f'/orders/sale/{order.id}/'),
                    store_name=store_name(order.vendor_id) if order.vendor_id else None,
                    items=items, address=address)
            else:
                logger.warning('Order %s: kisi superuser ki email nahi, admin ko mail nahi gayi.', order.order_no)
        except Exception:
            logger.exception('New order email failed (order %s)', getattr(order, 'order_no', '?'))

    transaction.on_commit(_send)


def whatsapp_link(phone, text):
    """wa.me link (khud send nahi hota - vendor click karke bhejta hai)."""
    try:
        from ..whatsapp_utils import WhatsAppSender
        res = WhatsAppSender.send_direct_message(phone, text)
        return res.get('url') if res.get('success') else None
    except Exception:
        return None


def customer_whatsapp_text(order, action):
    shop = store_name(order.vendor_id)
    if action == 'accept':
        eta = f" Taqreeban {order.prep_minutes} minute mein tayyar hoga." if order.prep_minutes else ''
        return f"✅ {shop}: Aap ka order #{order.order_no} qubool ho gaya.{eta}"
    if action == 'ready':
        return f"📦 {shop}: Aap ka order #{order.order_no} tayyar hai."
    if action == 'delivered':
        return f"🎉 {shop}: Aap ka order #{order.order_no} deliver ho gaya. Shukriya!"
    if action == 'reject':
        return (f"❌ {shop}: Maazrat, order #{order.order_no} qubool nahi ho saka. "
                f"Wajah: {order.reject_reason}")
    return ''


def suggest_other_stores(order, limit=3):
    """
    Reject hone par naye stores: wahi category ka maal bechne wale, abhi khule hue.
    Pehle same category wale, phir koi bhi khula store.
    """
    from ..models import Product, VendorProfile

    live = Product.objects.filter(is_active=True, approval_status='approved', vendor__isnull=False)
    base = VendorProfile.objects.filter(
        is_approved=True, vendor__in=live.values('vendor')
    ).exclude(vendor_id=order.vendor_id).select_related('vendor')

    cat_ids = list(
        Product.objects.filter(saleorderitem__order=order)
        .exclude(category__isnull=True).values_list('category_id', flat=True).distinct()
    )
    picked, seen = [], set()
    if cat_ids:
        same = base.filter(vendor__in=live.filter(category_id__in=cat_ids).values('vendor'))
        for prof in same:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    if len(picked) < limit:
        for prof in base:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    return picked[:limit]


def refund_note(order):
    """Reject par paisa ka message. COD mein kuch kata hi nahi hota."""
    if (order.payment_method or 'cod') == 'cod':
        return 'Cash on Delivery tha, is liye aap se koi paisa nahi liya gaya.'
    return ('Aap ne online payment ki thi to poori raqam wapas ki jayegi. '
            'Refund mein masla ho to humse rabta karein.')


class OrderActionError(Exception):
    """Vendor ke action mein masla (galat status, wajah nahi di, ...). Message customer-friendly hota hai."""


def clean_reject_reason(code, note):
    """Chuni hui wajah + optional note -> customer ko dikhane wala text (max 200 chars)."""
    code = (code or '').strip()
    label = REJECT_REASON_LABELS.get(code)
    note = (note or '').strip()
    if not label:
        raise OrderActionError('Reject karne ki wajah chunein.')
    if code == 'other':
        if not note:
            raise OrderActionError('"Doosri wajah" chunne par wajah likhna zaroori hai.')
        return note[:200]
    return (f'{label}. {note}' if note else label)[:200]


def apply_vendor_action(order, action, *, user, prep_minutes=None, reason_code='', reason_note=''):
    """
    Vendor ka action lagao. order select_for_update ke andar (transaction.atomic) hona chahiye.
    Nakaam hone par OrderActionError.
    """
    if action not in ACTIONS:
        raise OrderActionError('Ghalat action.')
    allowed_from, new_status = ACTIONS[action]
    if order.status not in allowed_from:
        raise OrderActionError(
            f'Order #{order.order_no} ab "{order.get_status_display()}" hai, ye action nahi ho sakta.')

    if action == 'reject':
        order.reject_reason = clean_reject_reason(reason_code, reason_note)
    if action == 'accept' and prep_minutes:
        order.prep_minutes = prep_minutes

    order.status = new_status
    order.vendor_responded_at = now()
    order.save()
    if action == 'delivered':
        auto_invoice_delivered(order, user)
    after_vendor_action(order, action, user)


def auto_invoice_delivered(order, user):
    """
    Delivered hote hi invoice (Sale) khud bana do, poora PAID (COD cash mil chuka / online pehle ada).
    Is se vendor dashboard ki sales/commission bharti hain, stock kam hota hai aur accounts ban jate hain.
    Kuch bhi fail ho (stock kam, month locked...) to delivery na ruke: order Delivered hi rehta hai
    aur admin ko notification milti hai ke manually invoice banaye.
    """
    from django.db import transaction
    from ..models import Sale, SaleItem

    if order.converted_to_sale_id:
        return None
    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                warehouse=order.warehouse,
                customer=order.customer,
                bill_no=f"INV-{order.order_no}",
                sale_date=now(),
                paid=Decimal('0.00'),
                discount_value=order.discount_value,
                created_by=user,
            )
            for item in order.items.all():
                SaleItem.objects.create(sale=sale, product=item.product, qty=item.qty, price=item.price)
            # Poora paid: items ki raqam customer ne (COD cash / online) de di hai
            sale.paid = sale.total_amount()
            sale.save()
            order.status = 'invoiced'
            order.converted_to_sale = sale
            order.save()
        return sale
    except Exception as exc:
        logger.error("Auto invoice failed for order %s: %s", order.order_no, exc)
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'⚠️ Order #{order.order_no} ka invoice khud nahi bana',
                        f'Wajah: {exc}\nOrder Delivered hai, manually "Convert to Invoice" karein.',
                        f'/orders/sale/{order.id}/', 'warning')
        except Exception:
            pass
        return None


def after_vendor_action(order, action, user):
    """Customer (aur reject par admin) ko batao."""
    link = f'/shop/order/{order.id}/'
    cust_user = _customer_user(order)
    shop = store_name(order.vendor_id)

    if action == 'accept':
        eta = f'\nTayyar hone mein ~{order.prep_minutes} minute.' if order.prep_minutes else ''
        _notify(cust_user, f'✅ Order #{order.order_no} qubool ho gaya',
                f'{shop} ne aap ka order qubool kar liya.{eta}', link, 'success')
    elif action == 'ready':
        _notify(cust_user, f'📦 Order #{order.order_no} tayyar hai',
                f'{shop} ka maal tayyar hai.', link, 'info')
    elif action == 'delivered':
        _notify(cust_user, f'🎉 Order #{order.order_no} deliver ho gaya',
                f'{shop} ka order aap tak pahunch gaya. Shukriya!', link, 'success')
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'✅ Order #{order.order_no} deliver ho gaya',
                        f'{shop} ne order deliver mark kiya. Rs. {order_payable_total(order):,.0f} '
                        f'({(order.payment_method or "cod").upper()}). '
                        + ('Invoice khud ban gaya.' if order.converted_to_sale_id else 'Ab invoice bana sakte hain.'),
                        f'/orders/sale/{order.id}/', 'success')
        except Exception as exc:
            logger.error("Delivered notify error: %s", exc)
    elif action == 'reject':
        _notify(cust_user, f'❌ Order #{order.order_no} reject ho gaya',
                f'{shop} ne order qubool nahi kiya.\nWajah: {order.reject_reason}\n{refund_note(order)}',
                link, 'warning')
        # Online payment ho to admin ko refund yaad dilao
        if (order.payment_method or 'cod') != 'cod':
            try:
                from django.contrib.auth.models import User
                for admin in User.objects.filter(is_superuser=True, is_active=True):
                    _notify(admin, f'💰 Refund karna hai - #{order.order_no}',
                            f'{shop} ne order reject kiya ({order.reject_reason}).\n'
                            f'Payment: {order.payment_method}, Rs. {order_payable_total(order):,.0f}',
                            f'/orders/sale/{order.id}/', 'warning')
            except Exception as exc:
                logger.error("Refund notify error: %s", exc)
