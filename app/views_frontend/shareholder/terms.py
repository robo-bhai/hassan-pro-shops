"""Frontend views: shareholder/terms (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from ...models import Shareholder, CompanyInfo


@login_required
@perm_required('view_shareholders')
def terms_admin(request):
    """Admin panel for Terms & Conditions"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can manage terms.')
        return redirect('dashboard')
    
    terms_list = TermsAndConditions.objects.all().order_by('-version')
    active_terms = terms_list.filter(is_active=True).first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms_list': terms_list,
        'active_terms': active_terms,
        'total_terms': terms_list.count(),
    }
    return render(request, 'terms/admin_list.html', context)


@login_required
@perm_required('manage_shareholders')
def terms_create(request):
    """Create new Terms & Conditions"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            version = request.POST.get('version')
            title = request.POST.get('title', 'Shareholder Terms & Conditions')
            content = request.POST.get('content')  # English
            urdu_content = request.POST.get('urdu_content')  # ✅ Urdu
            is_active = request.POST.get('is_active') == 'on'
            effective_date = request.POST.get('effective_date')
            
            if not version:
                messages.error(request, '❌ Version is required!')
                return redirect('terms_create')
            
            if not content:
                messages.error(request, '❌ English content is required!')
                return redirect('terms_create')
            
            if TermsAndConditions.objects.filter(version=version).exists():
                messages.error(request, f'❌ Version {version} already exists!')
                return redirect('terms_create')
            
            terms = TermsAndConditions.objects.create(
                version=version,
                title=title,
                content=content,
                urdu_content=urdu_content,  # ✅ Save Urdu content
                is_active=is_active,
                effective_date=effective_date or date.today(),
                created_by=request.user
            )
            
            if is_active:
                TermsAndConditions.objects.exclude(pk=terms.pk).update(is_active=False)
            
            messages.success(request, f'✅ Terms v{version} created successfully!')
            return redirect('terms_admin')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('terms_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'terms/create.html', context)


@login_required
@perm_required('manage_shareholders')
def terms_edit(request, pk):
    """Edit existing Terms & Conditions"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    terms = get_object_or_404(TermsAndConditions, pk=pk)
    
    if request.method == 'POST':
        try:
            version = request.POST.get('version')
            title = request.POST.get('title')
            content = request.POST.get('content')
            urdu_content = request.POST.get('urdu_content')  # ✅ Urdu content
            is_active = request.POST.get('is_active') == 'on'
            effective_date = request.POST.get('effective_date')
            
            if not version:
                messages.error(request, '❌ Version is required!')
                return redirect('terms_edit', pk=pk)
            
            if not content:
                messages.error(request, '❌ English content is required!')
                return redirect('terms_edit', pk=pk)
            
            if TermsAndConditions.objects.filter(version=version).exclude(pk=pk).exists():
                messages.error(request, f'❌ Version {version} already exists!')
                return redirect('terms_edit', pk=pk)
            
            terms.version = version
            terms.title = title
            terms.content = content
            terms.urdu_content = urdu_content  # ✅ Update Urdu content
            terms.is_active = is_active
            terms.effective_date = effective_date or date.today()
            terms.save()
            
            if is_active:
                TermsAndConditions.objects.exclude(pk=terms.pk).update(is_active=False)
            
            messages.success(request, f'✅ Terms v{version} updated successfully!')
            return redirect('terms_admin')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('terms_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms': terms,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'terms/edit.html', context)


@login_required
@perm_required('manage_shareholders')
def terms_delete(request, pk):
    """Delete Terms & Conditions"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can delete terms.')
        return redirect('dashboard')
    
    terms = get_object_or_404(TermsAndConditions, pk=pk)
    
    if request.method == 'POST':
        version = terms.version
        terms.delete()
        messages.success(request, f'🗑️ Terms v{version} deleted successfully!')
        return redirect('terms_admin')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms': terms,
    }
    return render(request, 'terms/delete.html', context)


@login_required
@perm_required('manage_shareholders')
def terms_activate(request, pk):
    """Activate a Terms version"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    terms = get_object_or_404(TermsAndConditions, pk=pk)
    TermsAndConditions.objects.exclude(pk=pk).update(is_active=False)
    terms.is_active = True
    terms.save()
    
    messages.success(request, f'✅ Terms v{terms.version} activated successfully!')
    return redirect('terms_admin')


@login_required
@perm_required('view_shareholders')
def terms_preview(request, pk):
    """Preview Terms & Conditions"""
    
    terms = get_object_or_404(TermsAndConditions, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms': terms,
    }
    return render(request, 'terms/preview.html', context)


@login_required
@perm_required('view_shareholders')
def terms_acceptance_list(request):
    """
    Admin: List all shareholders with their terms acceptance status
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can view this page.')
        return redirect('dashboard')
    
    # Get all shareholders with acceptance status
    shareholders = Shareholder.objects.select_related(
        'terms_acceptance'
    ).prefetch_related(
        'shares'
    ).all()
    
    # Filters
    search = request.GET.get('search', '')
    if search:
        shareholders = shareholders.filter(
            Q(name__icontains=search) |
            Q(shareholder_code__icontains=search) |
            Q(email__icontains=search)
        )
    
    status_filter = request.GET.get('status', '')
    if status_filter == 'accepted':
        shareholders = shareholders.filter(terms_acceptance__isnull=False)
    elif status_filter == 'pending':
        shareholders = shareholders.filter(terms_acceptance__isnull=True)
    
    version_filter = request.GET.get('version', '')
    if version_filter:
        shareholders = shareholders.filter(terms_acceptance__terms_version=version_filter)
    
    # Add acceptance info to each shareholder
    for shareholder in shareholders:
        if hasattr(shareholder, 'terms_acceptance'):
            shareholder.acceptance_status = '✅ Accepted'
            shareholder.acceptance_date = shareholder.terms_acceptance.accepted_at
            shareholder.accepted_version = shareholder.terms_acceptance.terms_version
            shareholder.acceptance_ip = shareholder.terms_acceptance.ip_address
        else:
            shareholder.acceptance_status = '⏳ Pending'
            shareholder.acceptance_date = None
            shareholder.accepted_version = '-'
            shareholder.acceptance_ip = '-'
    
    # Statistics
    total_shareholders = shareholders.count()
    accepted_count = shareholders.filter(terms_acceptance__isnull=False).count()
    pending_count = shareholders.filter(terms_acceptance__isnull=True).count()
    acceptance_percentage = (accepted_count / total_shareholders * 100) if total_shareholders > 0 else 0
    
    # Version wise stats
    version_stats = {}
    for acceptance in ShareholderTermsAcceptance.objects.all():
        version = acceptance.terms_version
        if version not in version_stats:
            version_stats[version] = 0
        version_stats[version] += 1
    
    # Latest active terms
    active_terms = TermsAndConditions.objects.filter(is_active=True).first()
    
    # Pagination
    paginator = Paginator(shareholders, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'shareholders': page_obj,
        'total_shareholders': total_shareholders,
        'accepted_count': accepted_count,
        'pending_count': pending_count,
        'acceptance_percentage': acceptance_percentage,
        'version_stats': version_stats,
        'active_terms': active_terms,
        'all_versions': TermsAndConditions.objects.values_list('version', flat=True).distinct(),
        'search': search,
        'status_filter': status_filter,
        'version_filter': version_filter,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'terms/admin_acceptance_list.html', context)


@login_required
@perm_required('view_shareholders')
def terms_acceptance_detail(request, pk):
    """
    Admin: View specific shareholder's acceptance detail
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Get acceptance record
    acceptance = None
    if hasattr(shareholder, 'terms_acceptance'):
        acceptance = shareholder.terms_acceptance
    
    # Get the terms document that was accepted
    terms = None
    if acceptance:
        terms = TermsAndConditions.objects.filter(version=acceptance.terms_version).first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'acceptance': acceptance,
        'terms': terms,
        'now': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
    }
    return render(request, 'terms/admin_acceptance_detail.html', context)


@login_required
@perm_required('manage_shareholders')
def terms_acceptance_delete(request, pk):
    """
    Admin: Delete a shareholder's acceptance record (force them to re-accept)
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    acceptance = get_object_or_404(ShareholderTermsAcceptance, pk=pk)
    shareholder_name = acceptance.shareholder.name
    
    if request.method == 'POST':
        acceptance.delete()
        messages.success(
            request, 
            f'✅ Acceptance record for "{shareholder_name}" deleted! '
            f'They will need to accept terms again.'
        )
        return redirect('terms_acceptance_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'acceptance': acceptance,
        'shareholder': acceptance.shareholder,
    }
    return render(request, 'terms/admin_acceptance_delete.html', context)


@login_required
@perm_required('view_shareholders')
def terms_acceptance_export(request):
    """
    Admin: Export terms acceptance data to CSV
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get all shareholders
    shareholders = Shareholder.objects.select_related('terms_acceptance').all()
    
    # Filters from request
    status_filter = request.GET.get('status', '')
    if status_filter == 'accepted':
        shareholders = shareholders.filter(terms_acceptance__isnull=False)
    elif status_filter == 'pending':
        shareholders = shareholders.filter(terms_acceptance__isnull=True)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="terms_acceptance_report_{timestamp}.csv"'
    
    writer = csv.writer(response)
    
    # Headers
    writer.writerow([
        'Shareholder Code',
        'Name',
        'Email',
        'Phone',
        'Status',
        'Accepted Version',
        'Accepted Date',
        'IP Address',
        'User Agent'
    ])
    
    # Data
    for shareholder in shareholders:
        if hasattr(shareholder, 'terms_acceptance'):
            acceptance = shareholder.terms_acceptance
            writer.writerow([
                shareholder.shareholder_code,
                shareholder.name,
                shareholder.email or '',
                shareholder.phone or '',
                'Accepted',
                acceptance.terms_version,
                acceptance.accepted_at.strftime('%Y-%m-%d %I:%M:%S %p'),
                acceptance.ip_address or '',
                acceptance.user_agent or '',
            ])
        else:
            writer.writerow([
                shareholder.shareholder_code,
                shareholder.name,
                shareholder.email or '',
                shareholder.phone or '',
                'Pending',
                '-',
                '-',
                '-',
                '-',
            ])
    
    return response


@login_required
@perm_required('view_shareholders')
def terms_acceptance_stats_api(request):
    """
    AJAX API: Get terms acceptance statistics
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        total = Shareholder.objects.filter(status='active').count()
        accepted = ShareholderTermsAcceptance.objects.count()
        pending = total - accepted
        
        # Version wise breakdown
        version_data = {}
        for acceptance in ShareholderTermsAcceptance.objects.all():
            version = acceptance.terms_version
            if version not in version_data:
                version_data[version] = 0
            version_data[version] += 1
        
        # Daily acceptance trend (last 30 days)
        trend_data = []
        from datetime import timedelta
        today = date.today()
        
        for i in range(30):
            day = today - timedelta(days=i)
            count = ShareholderTermsAcceptance.objects.filter(
                accepted_at__date=day
            ).count()
            trend_data.append({
                'date': day.strftime('%d-%b'),
                'count': count
            })
        trend_data.reverse()
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_shareholders': total,
                'accepted': accepted,
                'pending': pending,
                'acceptance_percentage': round((accepted / total * 100) if total > 0 else 0, 1),
                'version_breakdown': version_data,
                'trend_data': trend_data,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
