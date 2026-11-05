"""Frontend views: purchase/vendor_approvals

Admin vendor portal ki approvals yahin se karta hai (pehle sirf Django admin se hoti thin):
  - Vendor accounts : approve / suspend
  - Vendor products : approve (shop par live) / reject (reason ke sath)
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.shortcuts import render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ...models import CompanyInfo, Product, VendorProfile
from ...security.permissions import perm_required
from ...vendor_commission import (
    MAX_COMMISSION, commission_percent, default_commission, reprice_open_batches, vendor_earnings,
)

DEFAULT_REJECT_REASON = 'Listing guidelines par poora nahi utarta. Edit karke dobara bhejein.'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'ERP System'


def _redirect_back(request, tab):
    """Action ke baad usi tab/filter par wapas."""
    nxt = request.POST.get('next', '')
    if nxt.startswith('/vendors/approvals/'):
        return redirect(nxt)
    return redirect(f"/vendors/approvals/?tab={tab}")


@login_required
@perm_required('view_vendors')
def vendor_approvals(request):
    tab = request.GET.get('tab', 'accounts')
    if tab not in ('accounts', 'products'):
        tab = 'accounts'
    status = request.GET.get('status', 'pending')
    search = request.GET.get('search', '').strip()

    accounts_qs = VendorProfile.objects.select_related('vendor', 'user')
    products_qs = Product.objects.filter(vendor__isnull=False).select_related('vendor', 'category')

    # ---- counts (tab badges) ----
    counts = {
        'acc_pending': accounts_qs.filter(is_approved=False, approved_at__isnull=True).count(),
        'acc_approved': accounts_qs.filter(is_approved=True).count(),
        'acc_suspended': accounts_qs.filter(is_approved=False, approved_at__isnull=False).count(),
        'prod_pending': products_qs.filter(approval_status='pending').count(),
        'prod_approved': products_qs.filter(approval_status='approved').count(),
        'prod_rejected': products_qs.filter(approval_status='rejected').count(),
    }

    if tab == 'accounts':
        qs = accounts_qs
        if status == 'pending':
            qs = qs.filter(is_approved=False, approved_at__isnull=True)
        elif status == 'approved':
            qs = qs.filter(is_approved=True)
        elif status == 'suspended':
            qs = qs.filter(is_approved=False, approved_at__isnull=False)
        else:
            status = 'all'
        if search:
            qs = qs.filter(
                Q(business_name__icontains=search) | Q(vendor__name__icontains=search) |
                Q(vendor__contact_number__icontains=search) | Q(user__email__icontains=search) |
                Q(city__icontains=search) | Q(delivery_areas__icontains=search)
            )
        qs = qs.order_by('-created_at')
    else:
        qs = products_qs
        if status in ('pending', 'approved', 'rejected'):
            qs = qs.filter(approval_status=status)
        else:
            status = 'all'
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(vendor__name__icontains=search) | Q(barcode__icontains=search)
            )
        qs = qs.order_by('-id')

    page_obj = Paginator(qs, 25).get_page(request.GET.get('page', 1))

    if tab == 'accounts':
        for p in page_obj:
            p.commission_effective = commission_percent(p)
            p.earn = vendor_earnings(p.vendor)

    return render(request, 'vendors/approvals.html', {
        'company_name': _company_name(),
        'tab': tab,
        'status': status,
        'search': search,
        'page_obj': page_obj,
        'counts': counts,
        'default_reject_reason': DEFAULT_REJECT_REASON,
        'default_commission': default_commission(),
    })


@login_required
@perm_required('edit_vendors')
@require_POST
def vendor_account_action(request, pk, action):
    profile = get_object_or_404(VendorProfile.objects.select_related('vendor'), pk=pk)

    if action == 'approve':
        VendorProfile.objects.filter(pk=pk).update(is_approved=True, approved_at=now())
        messages.success(request, f'✅ "{profile.business_name}" approve ho gaya. Ab woh products list kar sakta hai.')
    elif action == 'suspend':
        VendorProfile.objects.filter(pk=pk).update(is_approved=False)
        hidden = Product.objects.filter(vendor_id=profile.vendor_id, is_active=True).update(is_active=False)
        messages.warning(request, f'⛔ "{profile.business_name}" suspend ho gaya, {hidden} product(s) shop se hata diye.')
    else:
        messages.error(request, '❌ Invalid action')
    return _redirect_back(request, 'accounts')


@login_required
@perm_required('edit_vendors')
@require_POST
def vendor_product_action(request, pk, action):
    product = get_object_or_404(Product, pk=pk, vendor__isnull=False)

    # .update() use hota hai taake Product.save() ka image-processing dobara na chale.
    if action == 'approve':
        Product.objects.filter(pk=pk).update(approval_status='approved', is_active=True, rejection_reason='')
        messages.success(request, f'✅ "{product.name}" approve ho gaya aur shop par live hai.')
    elif action == 'reject':
        reason = request.POST.get('reason', '').strip()[:200] or DEFAULT_REJECT_REASON
        Product.objects.filter(pk=pk).update(approval_status='rejected', is_active=False, rejection_reason=reason)
        messages.warning(request, f'❌ "{product.name}" reject ho gaya.')
    else:
        messages.error(request, '❌ Invalid action')
    return _redirect_back(request, 'products')


@login_required
@perm_required('edit_vendors')
@require_POST
def vendor_approvals_bulk(request):
    """Selected products ek sath approve/reject."""
    ids = [i for i in request.POST.getlist('ids') if i.isdigit()]
    action = request.POST.get('action')
    qs = Product.objects.filter(pk__in=ids, vendor__isnull=False)
    if not ids:
        messages.warning(request, '⚠️ Koi product select nahi kiya.')
    elif action == 'approve':
        n = qs.exclude(approval_status='approved').update(
            approval_status='approved', is_active=True, rejection_reason='')
        messages.success(request, f'✅ {n} product(s) approve ho gaye aur shop par live hain.')
    elif action == 'reject':
        reason = request.POST.get('reason', '').strip()[:200] or DEFAULT_REJECT_REASON
        n = qs.update(approval_status='rejected', is_active=False, rejection_reason=reason)
        messages.warning(request, f'❌ {n} product(s) reject ho gaye.')
    else:
        messages.error(request, '❌ Invalid action')
    return _redirect_back(request, 'products')


@login_required
@perm_required('edit_vendors')
@require_POST
def vendor_commission_update(request, pk):
    """Is vendor ka commission % badlo (khali = default). Open batches ka cost naye rate par update hota hai."""
    profile = get_object_or_404(VendorProfile.objects.select_related('vendor'), pk=pk)
    raw = request.POST.get('commission', '').strip()

    if raw == '':
        pct_value = None
    else:
        try:
            pct_value = Decimal(raw).quantize(Decimal('0.01'))
            if pct_value < 0 or pct_value > MAX_COMMISSION:
                raise InvalidOperation
        except InvalidOperation:
            messages.error(request, f'❌ Commission 0 se {MAX_COMMISSION}% ke darmiyan hona chahiye.')
            return _redirect_back(request, 'accounts')

    profile.commission_percent = pct_value
    profile.save(update_fields=['commission_percent'])
    pct = commission_percent(profile)

    failed = []
    for product in Product.objects.filter(vendor=profile.vendor):
        base = product.original_price if product.original_price and product.original_price > 0 else product.price
        try:
            reprice_open_batches(product, base, product.discount_percentage, pct)
        except ValidationError as exc:
            failed.append(f'{product.name}: {"; ".join(exc.messages)}')

    messages.success(request, f'✅ "{profile.business_name}" ka commission {pct}% kar diya gaya.')
    if failed:
        messages.warning(
            request,
            '⚠️ In products ka cost update nahi ho saka (margin policy): ' + ' | '.join(failed[:5]))
    return _redirect_back(request, 'accounts')
