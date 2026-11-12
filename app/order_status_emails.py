"""
Order status badalte hi CUSTOMER ko email.

Kaise kaam karta hai: SaleOrder (aur rider ki DeliveryInfo) ka status jahan se bhi badle
(vendor Accept/Reject/Ready/Delivered, admin panel, rider) - yahan ke signals pakad lete hain.
Is liye purane views mein koi tabdeeli nahi chahiye.

Email ka order kabhi nahi rukta: koi bhi ghalti sirf log hoti hai. Email transaction commit hone ke baad jati hai.
Customer ki email: Customer.email, warna customer portal user ki email.
"""
import logging
import os

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# SaleOrder.status -> email wala status (invoiced/pending par email nahi: delivered par ja chuki hoti hai)
ORDER_STATUS_EMAILS = {
    'confirmed': 'confirmed',          # vendor/admin ne accept kiya
    'processing': 'processing',
    'ready': 'ready',
    'partially_delivered': 'partially_delivered',
    'delivered': 'delivered',
    'cancelled': 'cancelled',          # reject / cancel
}
# DeliveryInfo.status -> email wala status
DELIVERY_STATUS_EMAILS = {
    'picked_up': 'dispatched',
    'in_transit': 'dispatched',
}


def _site_url():
    url = (os.environ.get('SITE_URL') or getattr(settings, 'SITE_URL', '') or '').strip()
    if not url:
        for origin in getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) or []:
            if origin.startswith('https://') and '*' not in origin:
                url = origin
                break
    return url.rstrip('/')


def _customer_email(order):
    customer = order.customer
    email = (getattr(customer, 'email', '') or '').strip()
    if not email:
        portal = getattr(customer, 'portal_profile', None)
        user = getattr(portal, 'user', None)
        email = (getattr(user, 'email', '') or '').strip()
    return email


def _send_status_email(order_id, email_status, dedupe_key):
    """Order dobara DB se parh kar (taake taza data ho) email bhejo."""
    def _send():
        try:
            from django.core.cache import cache
            from .models import SaleOrder
            from .utils.email_helper import send_order_status_update_email

            # Ek hi status ki email do baar na jaye (jaise save() do dafa chale)
            if not cache.add(f'order_status_mail:{order_id}:{dedupe_key}', 1, 60 * 60 * 24):
                return
            order = SaleOrder.objects.select_related('customer').get(pk=order_id)
            to = _customer_email(order)
            if not to:
                logger.info('Order %s: customer ki email nahi, status email skip.', order.order_no)
                return

            store = None
            note = None
            if order.vendor_id:
                from .customer.store_orders import store_name
                store = store_name(order.vendor_id)
            if email_status == 'cancelled' and order.reject_reason:
                note = f'Wajah: {order.reject_reason}'
            elif email_status == 'confirmed' and order.prep_minutes:
                note = f'Tayyar hone mein taqreeban {order.prep_minutes} minute.'

            base = _site_url()
            tracking = f'{base}/shop/order/{order.id}/' if base else None
            send_order_status_update_email(
                recipient_email=to, order_no=order.order_no, customer_name=order.customer.name,
                new_status=email_status, tracking_url=tracking, note=note, store_name=store)
        except Exception:
            logger.exception('Order status email failed (order %s, %s)', order_id, email_status)

    transaction.on_commit(_send)


def _register():
    from .models import SaleOrder, DeliveryInfo

    @receiver(pre_save, sender=SaleOrder, weak=False, dispatch_uid='order_status_mail_pre')
    def _remember_old_status(sender, instance, **kwargs):
        instance._old_status = None
        if instance.pk:
            instance._old_status = (sender.objects.filter(pk=instance.pk)
                                    .values_list('status', flat=True).first())

    @receiver(post_save, sender=SaleOrder, weak=False, dispatch_uid='order_status_mail_post')
    def _order_status_changed(sender, instance, created, **kwargs):
        old = getattr(instance, '_old_status', None)
        if created or old is None or old == instance.status:
            return
        email_status = ORDER_STATUS_EMAILS.get(instance.status)
        if email_status:
            _send_status_email(instance.pk, email_status, instance.status)

    @receiver(pre_save, sender=DeliveryInfo, weak=False, dispatch_uid='delivery_status_mail_pre')
    def _remember_old_delivery_status(sender, instance, **kwargs):
        instance._old_status = None
        if instance.pk:
            instance._old_status = (sender.objects.filter(pk=instance.pk)
                                    .values_list('status', flat=True).first())

    @receiver(post_save, sender=DeliveryInfo, weak=False, dispatch_uid='delivery_status_mail_post')
    def _delivery_status_changed(sender, instance, created, **kwargs):
        old = getattr(instance, '_old_status', None)
        if created or old == instance.status or not instance.sale_order_id:
            return
        email_status = DELIVERY_STATUS_EMAILS.get(instance.status)
        if email_status:
            # picked_up aur in_transit dono "Out for Delivery" hain: ek hi email
            _send_status_email(instance.sale_order_id, email_status, 'dispatched')


_register()
