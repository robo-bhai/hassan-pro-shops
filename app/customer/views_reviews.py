"""Customer ki rating/review: store aur rider ke liye (delivered order par, ek dafa)."""
import logging

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import DeliveryInfo, OrderReview, SaleOrder, VendorProfile
from . import store_orders

logger = logging.getLogger(__name__)

REVIEWABLE = ('delivered', 'invoiced')


def _stars(raw):
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    return v if 1 <= v <= 5 else None


def rating_summary(qs, field):
    """{'avg': 4.5, 'count': 12} ya avg=None agar koi rating nahi."""
    rated = qs.exclude(**{f'{field}__isnull': True})
    a = rated.aggregate(avg=Avg(field), n=Count('id'))
    return {'avg': round(float(a['avg']), 1) if a['avg'] else None, 'count': a['n'] or 0}


def vendor_rating(vendor):
    return rating_summary(OrderReview.objects.filter(vendor=vendor), 'vendor_rating')


def rider_rating(rider):
    return rating_summary(OrderReview.objects.filter(rider=rider), 'rider_rating')


@customer_login_required
@require_POST
def rate_order(request, order_id):
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Access denied')
        return redirect('shop_home')
    customer = request.user.customer_profile.customer
    order = get_object_or_404(SaleOrder, id=order_id, customer=customer)

    if order.status not in REVIEWABLE:
        messages.error(request, '❌ Rating sirf deliver hone ke baad de sakte hain.')
        return redirect('order_detail_customer', order_id=order.id)
    if OrderReview.objects.filter(sale_order=order).exists():
        messages.info(request, 'Aap is order ki rating de chuke hain.')
        return redirect('order_detail_customer', order_id=order.id)

    di = DeliveryInfo.objects.filter(sale_order=order, status='delivered', rider__isnull=False).select_related('rider').first()
    rider = di.rider if di else None

    vendor_stars = _stars(request.POST.get('vendor_rating')) if order.vendor_id else None
    rider_stars = _stars(request.POST.get('rider_rating')) if rider else None
    if not vendor_stars and not rider_stars:
        messages.error(request, '❌ Kam az kam ek rating (⭐) chunein.')
        return redirect('order_detail_customer', order_id=order.id)

    try:
        with transaction.atomic():
            OrderReview.objects.create(
                sale_order=order, vendor_id=order.vendor_id, rider=rider,
                vendor_rating=vendor_stars, vendor_comment=request.POST.get('vendor_comment', '').strip()[:300],
                rider_rating=rider_stars, rider_comment=request.POST.get('rider_comment', '').strip()[:300],
            )
    except IntegrityError:
        messages.info(request, 'Aap is order ki rating de chuke hain.')
        return redirect('order_detail_customer', order_id=order.id)

    # Store aur rider ko khabar
    try:
        if vendor_stars:
            vp = VendorProfile.objects.filter(vendor_id=order.vendor_id).select_related('user').first()
            store_orders._notify(vp.user if vp else None, f'⭐ Order #{order.order_no}: {vendor_stars}/5',
                                 request.POST.get('vendor_comment', '').strip()[:200] or 'Customer ne aap ke store ko rating di.',
                                 '/shop/vendor/', 'success' if vendor_stars >= 4 else 'warning')
        if rider_stars:
            store_orders._notify(rider.user, f'⭐ Order #{order.order_no}: {rider_stars}/5',
                                 request.POST.get('rider_comment', '').strip()[:200] or 'Customer ne aap ko rating di.',
                                 '/shop/rider/earnings/', 'success' if rider_stars >= 4 else 'warning')
    except Exception as exc:
        logger.error("Review notify error: %s", exc)

    messages.success(request, '⭐ Rating dene ka shukriya!')
    return redirect('order_detail_customer', order_id=order.id)


def store_rating_map():
    """Saare stores ki rating ek query mein: {vendor_id: {'avg': 4.5, 'count': 12}}"""
    rows = (OrderReview.objects.filter(vendor_rating__isnull=False)
            .values('vendor').annotate(avg=Avg('vendor_rating'), n=Count('id')))
    return {r['vendor']: {'avg': round(float(r['avg']), 1), 'count': r['n']} for r in rows if r['vendor']}


def _reviewer_name(order):
    """Privacy: 'Hadi Ahmed' -> 'Hadi A.'"""
    parts = (getattr(order.customer, 'name', '') or 'Customer').split()
    return parts[0] + (f' {parts[-1][0]}.' if len(parts) > 1 else '')


def store_reviews(vendor, limit=10):
    """Store page ke liye: average, 5-1 star ka hisaab (percent) aur aakhri reviews."""
    qs = OrderReview.objects.filter(vendor=vendor, vendor_rating__isnull=False)
    summary = rating_summary(qs, 'vendor_rating')
    counts = {r['vendor_rating']: r['n'] for r in qs.values('vendor_rating').annotate(n=Count('id'))}
    total = summary['count'] or 1
    bars = [{'stars': i, 'count': counts.get(i, 0), 'pct': round(counts.get(i, 0) * 100 / total)}
            for i in (5, 4, 3, 2, 1)]
    latest = []
    for rv in qs.select_related('sale_order__customer')[:limit]:
        latest.append({'stars': rv.vendor_rating, 'comment': rv.vendor_comment,
                       'name': _reviewer_name(rv.sale_order), 'date': rv.created_at})
    return {'summary': summary, 'bars': bars, 'latest': latest}
