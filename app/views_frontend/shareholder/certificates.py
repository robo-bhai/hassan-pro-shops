"""Frontend views: shareholder/certificates (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from django.contrib import messages
from django.http import HttpResponse
from ...models import Share, CompanyInfo
from ...certificate_utils import generate_share_certificate_pdf, generate_bulk_certificates


@login_required
@perm_required('view_shareholders')
def share_certificate_view(request, pk):
    """Generate and view single share certificate"""
    share = get_object_or_404(Share, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('share_list')
    
    # Generate certificate
    pdf_buffer = generate_share_certificate_pdf(share)
    
    # Update certificate status
    share.certificate_printed = True
    share.certificate_printed_at = now()
    share.certificate_printed_by = request.user
    share.save()
    
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    filename = f"Share_Certificate_{share.shareholder.name}_{share.id}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
@perm_required('view_shareholders')
def share_certificate_download(request, pk):
    """Download share certificate as PDF"""
    share = get_object_or_404(Share, pk=pk)
    pdf_buffer = generate_share_certificate_pdf(share)
    
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    filename = f"Share_Certificate_{share.shareholder.name}_{share.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@perm_required('manage_shareholders')
def share_certificate_bulk(request):
    """Generate bulk certificates for selected shares"""
    if request.method == 'POST':
        share_ids = request.POST.getlist('share_ids[]')
        if not share_ids:
            messages.error(request, 'No shares selected!')
            return redirect('share_list')
        
        zip_buffer = generate_bulk_certificates(share_ids)
        
        response = HttpResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="share_certificates.zip"'
        return response
    
    # GET request - show selection page
    shares = Share.objects.select_related('shareholder').all()
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shares': shares,
    }
    return render(request, 'shareholders/certificate_bulk.html', context)


@login_required
@perm_required('view_shareholders')
def share_certificate_list(request):
    """List all certificates"""
    shares = Share.objects.select_related('shareholder').filter(
        certificate_printed=True
    ).order_by('-certificate_printed_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shares': shares,
    }
    return render(request, 'shareholders/certificate_list.html', context)
