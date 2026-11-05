"""Frontend views: purchase/shop_banners

Shop ke promo banners (stores page ka slider) ab Django admin ke bajaye seedha app se manage hote hain:
  - List   : status (Live / Scheduled / Expired / Off), order badlo, on/off, edit, delete
  - Add/Edit: image upload (preview ke sath), store ya link, date range

Permissions: dekhna = view_vendors, badalna = edit_vendors (vendor approvals wali).
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ...models import CompanyInfo, ShopBanner, VendorProfile
from ...security.permissions import perm_required

MAX_IMAGE_MB = 4
MIN_WIDTH = 600
ALLOWED_FORMATS = ('JPEG', 'PNG', 'WEBP')
LIST_URL = '/vendors/banners/'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'ERP System'


class ShopBannerForm(forms.ModelForm):
    class Meta:
        model = ShopBanner
        fields = ['title', 'image', 'store', 'link_url', 'is_active', 'starts_on', 'ends_on']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 100,
                                            'placeholder': 'e.g. Free delivery this weekend'}),
            'image': forms.FileInput(attrs={'class': 'd-none', 'id': 'id_image',
                                            'accept': 'image/jpeg,image/png,image/webp'}),
            'store': forms.Select(attrs={'class': 'form-select'}),
            'link_url': forms.TextInput(attrs={'class': 'form-control',
                                               'placeholder': '/shop/stores/?free=1   ya   https://...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'starts_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'ends_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['store'].queryset = VendorProfile.objects.filter(is_approved=True).order_by('business_name')
        self.fields['store'].empty_label = '— Select a store —'
        self.fields['image'].error_messages['required'] = 'Banner image zaroori hai.'

    def clean_image(self):
        img = self.cleaned_data.get('image')
        # Naya upload hai? (edit par purani image FieldFile hoti hai, uspar content_type nahi hota)
        if img and getattr(img, 'content_type', None):
            if img.size > MAX_IMAGE_MB * 1024 * 1024:
                raise forms.ValidationError(f'Image {MAX_IMAGE_MB} MB se chhoti honi chahiye.')
            pil = getattr(img, 'image', None)
            if pil is not None:
                if pil.format not in ALLOWED_FORMATS:
                    raise forms.ValidationError('Sirf JPG, PNG ya WEBP image allowed hai.')
                if pil.width < MIN_WIDTH:
                    raise forms.ValidationError(
                        f'Image bohot chhoti hai ({pil.width}px). Kam az kam {MIN_WIDTH}px chaudi chahiye, '
                        f'behtar 1200 x 400 px.')
        return img

    def clean(self):
        data = super().clean()
        mode = (self.data.get('link_mode') or '').strip()
        if mode in ('none', 'store'):
            self.errors.pop('link_url', None)       # chhupa hua purana link ab ignore hai
        if mode == 'none':
            data['store'] = None
            data['link_url'] = ''
        elif mode == 'store':
            data['link_url'] = ''
            if not data.get('store') and 'store' not in self.errors:
                self.add_error('store', 'Store select karein.')
        elif mode == 'url':
            data['store'] = None
            if not (data.get('link_url') or '').strip() and 'link_url' not in self.errors:
                self.add_error('link_url', 'Link likhein.')
        start, end = data.get('starts_on'), data.get('ends_on')
        if start and end and end < start:
            self.add_error('ends_on', 'End date start date se pehle nahi ho sakti.')
        if data.get('link_url'):
            data['link_url'] = data['link_url'].strip()
        return data


def _link_mode(banner, form):
    """Form ka 'Link to' selector: none / store / url."""
    if form.is_bound:
        mode = form.data.get('link_mode')
        if mode in ('none', 'store', 'url'):
            return mode
    if banner is not None and banner.store_id:
        return 'store'
    if banner is not None and banner.link_url:
        return 'url'
    return 'none'


@login_required
@perm_required('view_vendors')
def shop_banner_list(request):
    banners = list(ShopBanner.objects.select_related('store'))
    counts = {'live': 0, 'scheduled': 0, 'expired': 0, 'off': 0}
    for b in banners:
        b.state = b.status
        b.target = b.get_link()
        counts[b.state] += 1
    return render(request, 'vendors/shop_banners.html', {
        'company_name': _company_name(),
        'banners': banners,
        'counts': counts,
        'total': len(banners),
    })


@login_required
@perm_required('view_vendors', post='edit_vendors')
def shop_banner_form(request, pk=None):
    banner = get_object_or_404(ShopBanner, pk=pk) if pk else None
    old_image = banner.image.name if banner and banner.image else ''

    if request.method == 'POST':
        form = ShopBannerForm(request.POST, request.FILES, instance=banner)
        if form.is_valid():
            obj = form.save(commit=False)
            if banner is None:
                obj.sort_order = (ShopBanner.objects.aggregate(m=Max('sort_order'))['m'] or 0) + 1
            obj.save()
            if old_image and obj.image.name != old_image:      # image badli to purani file hata do
                try:
                    obj.image.storage.delete(old_image)
                except Exception:
                    pass
            messages.success(request, f'✅ Banner "{obj.title}" save ho gaya.')
            return redirect(LIST_URL)
        messages.error(request, '❌ Form mein ghaltiyan hain, neeche dekhein.')
    else:
        form = ShopBannerForm(instance=banner)

    return render(request, 'vendors/shop_banner_form.html', {
        'company_name': _company_name(),
        'form': form,
        'banner': banner,
        'link_mode': _link_mode(banner, form),
        'max_mb': MAX_IMAGE_MB,
        'min_width': MIN_WIDTH,
    })


@login_required
@perm_required('edit_vendors')
@require_POST
def shop_banner_toggle(request, pk):
    banner = get_object_or_404(ShopBanner, pk=pk)
    banner.is_active = not banner.is_active
    banner.save(update_fields=['is_active'])
    messages.success(request, f'✅ "{banner.title}" ' + ('ON kar diya.' if banner.is_active else 'OFF kar diya.'))
    return redirect(LIST_URL)


@login_required
@perm_required('edit_vendors')
@require_POST
def shop_banner_delete(request, pk):
    banner = get_object_or_404(ShopBanner, pk=pk)
    title = banner.title
    image_name, storage = (banner.image.name, banner.image.storage) if banner.image else ('', None)
    banner.delete()
    if image_name:
        try:
            storage.delete(image_name)
        except Exception:
            pass
    messages.warning(request, f'🗑️ Banner "{title}" delete ho gaya.')
    return redirect(LIST_URL)


@login_required
@perm_required('edit_vendors')
@require_POST
def shop_banner_move(request, pk):
    """Banner ek jagah upar ('up') ya neeche ('down'). Sab ka order 0..n-1 kar ke swap karte hain."""
    direction = request.POST.get('direction')
    items = list(ShopBanner.objects.all())
    ids = [b.pk for b in items]
    if pk not in ids or direction not in ('up', 'down'):
        messages.error(request, '❌ Invalid action')
        return redirect(LIST_URL)
    i = ids.index(pk)
    j = i - 1 if direction == 'up' else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    for n, b in enumerate(items):
        b.sort_order = n
    ShopBanner.objects.bulk_update(items, ['sort_order'])
    return redirect(LIST_URL)
