"""Frontend views: shareholder/registration_requests (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from ...models import Shareholder, CompanyInfo
from django.contrib.auth.models import User
from ...security.security_utils import safe_error


def shareholder_register(request):
    """
    Public page - the Shareholder fills in their details and sends a request
    """
    
    if request.method == 'POST':
        try:
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            cnic = request.POST.get('cnic', '').strip()
            address = request.POST.get('address', '').strip()
            notes = request.POST.get('notes', '').strip()
            
            # Validation
            if not full_name:
                messages.error(request, '❌ Full name is required!')
                return redirect('shareholder_register')
            
            if not email:
                messages.error(request, '❌ Email is required!')
                return redirect('shareholder_register')
            
            if not phone:
                messages.error(request, '❌ Phone number is required!')
                return redirect('shareholder_register')
            
            # Check if already exists
            if Shareholder.objects.filter(email=email).exists():
                messages.error(request, '❌ This email is already registered!')
                return redirect('shareholder_register')
            
            if ShareholderLoginRequest.objects.filter(email=email, status='pending').exists():
                messages.warning(request, '⚠️ A request with this email is already pending!')
                return redirect('shareholder_register')
            
            # Create request
            request_obj = ShareholderLoginRequest.objects.create(
                full_name=full_name,
                email=email,
                phone=phone,
                cnic=cnic,
                address=address,
                notes=notes,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                status='pending'
            )
            
            # Send notification to admins
            try:
                admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
                for admin in admin_users:
                    Notification.send(
                        user=admin,
                        title="🆕 New Shareholder Registration Request",
                        message=f"{full_name} wants to register as shareholder. Email: {email}",
                        notification_type='info',
                        category='system',
                        link=f"/shareholder-requests/{request_obj.id}/"
                    )
            except:
                pass
            
            # ✅ THIS CHANGE - Redirect to the success page
            return redirect('shareholder_register_success')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_register')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'is_register_page': True,
    }
    return render(request, 'shareholders/register.html', context)


def shareholder_register_success(request):
    """
    Show success page after registration
    """
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'is_success_page': True,
    }
    return render(request, 'shareholders/register_success.html', context)


@login_required
@perm_required('view_shareholders')
def shareholder_requests_list(request):
    """
    Admin: List all shareholder registration requests
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can view requests.')
        return redirect('dashboard')
    
    requests = ShareholderLoginRequest.objects.all().order_by('-requested_at')
    
    # Filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests = requests.filter(status=status_filter)
    
    search = request.GET.get('search', '')
    if search:
        requests = requests.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Statistics
    total = requests.count()
    pending = requests.filter(status='pending').count()
    approved = requests.filter(status='approved').count()
    rejected = requests.filter(status='rejected').count()
    
    paginator = Paginator(requests, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'requests': page_obj,
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'status_filter': status_filter,
        'search': search,
        'status_choices': ShareholderLoginRequest.STATUS_CHOICES,
    }
    return render(request, 'shareholders/admin/requests_list.html', context)


@login_required
@perm_required('view_shareholders')
def shareholder_request_detail(request, pk):
    """
    Admin: View request detail and approve/reject
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    request_obj = get_object_or_404(ShareholderLoginRequest, pk=pk)
    
    # ✅ Check if credentials are available
    show_credentials = False
    username = None
    password = None

    # The password is shown ONCE (right after approval) and then forgotten.
    new_creds = request.session.pop(f'new_credentials_{request_obj.pk}', None)

    if request_obj.status == 'approved':
        if request_obj.generated_username:
            show_credentials = True
            username = request_obj.generated_username
            password = new_creds['password'] if new_creds else "🔒 Shown only once, right after approval"
        elif request_obj.created_shareholder and request_obj.created_shareholder.user:
            # Fallback: Get from created shareholder
            show_credentials = True
            username = request_obj.created_shareholder.user.username
            password = "🔒 Password not stored"  # Can't retrieve plain password
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request_obj': request_obj,
        'can_act': request_obj.status == 'pending',
        'show_credentials': show_credentials,
        'username': username,
        'password': password,
    }
    return render(request, 'shareholders/admin/request_detail.html', context)


@login_required
@perm_required('manage_shareholders')
def shareholder_request_approve(request, pk):
    """Admin: Approve request"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    request_obj = get_object_or_404(ShareholderLoginRequest, pk=pk)
    
    if request_obj.status != 'pending':
        messages.warning(request, '⚠️ This request is already processed!')
        return redirect('shareholder_request_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            result = request_obj.approve(request.user)
            request.session[f'new_credentials_{request_obj.pk}'] = {'password': result['password']}
            messages.success(request, '✅ Request approved! The login details are shown below - note them down now, they will not be shown again.')
            return redirect('shareholder_request_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {safe_error(e)}')
            return redirect('shareholder_request_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request_obj': request_obj,
    }
    return render(request, 'shareholders/admin/request_approve.html', context)


@login_required
@perm_required('manage_shareholders')
def shareholder_request_reject(request, pk):
    """
    Admin: Reject request with reason
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    request_obj = get_object_or_404(ShareholderLoginRequest, pk=pk)
    
    if request_obj.status != 'pending':
        messages.warning(request, '⚠️ This request is already processed!')
        return redirect('shareholder_request_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            reason = request.POST.get('reason', '')
            request_obj.reject(request.user, reason)
            
            messages.success(
                request, 
                f'❌ Request rejected!\n'
                f'Reason: {reason or "Not specified"}'
            )
            return redirect('shareholder_requests_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_request_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'request': request_obj,
    }
    return render(request, 'shareholders/admin/request_reject.html', context)


@login_required
@perm_required('manage_shareholders')
def shareholder_request_delete(request, pk):
    """
    Admin: Delete request
    """
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can delete requests.')
        return redirect('dashboard')
    
    request_obj = get_object_or_404(ShareholderLoginRequest, pk=pk)
    
    if request.method == 'POST':
        name = request_obj.full_name
        request_obj.delete()
        messages.success(request, f'🗑️ Request from "{name}" deleted!')
        return redirect('shareholder_requests_list')
    
    return redirect('shareholder_request_detail', pk=pk)


@login_required
@perm_required('manage_shareholders')
def shareholder_requests_bulk_action(request):
    """
    Admin: Bulk approve/reject requests
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method!'})
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        request_ids = data.get('request_ids', [])
        
        if not request_ids:
            return JsonResponse({'success': False, 'message': 'No requests selected!'})
        
        requests = ShareholderLoginRequest.objects.filter(id__in=request_ids, status='pending')
        
        if not requests.exists():
            return JsonResponse({'success': False, 'message': 'No pending requests found!'})
        
        if action == 'approve':
            approved = 0
            failed = 0
            for req in requests:
                try:
                    req.approve(request.user)
                    approved += 1
                except:
                    failed += 1
            message = f'✅ {approved} requests approved! {failed} failed.'
            
        elif action == 'reject':
            reason = data.get('reason', 'Bulk rejected by admin')
            rejected = 0
            for req in requests:
                try:
                    req.reject(request.user, reason)
                    rejected += 1
                except:
                    pass
            message = f'❌ {rejected} requests rejected!'
            
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action!'})
        
        return JsonResponse({'success': True, 'message': message})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@perm_required('view_shareholders')
def shareholder_requests_stats_api(request):
    """
    AJAX API: Get request statistics
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        total = ShareholderLoginRequest.objects.count()
        pending = ShareholderLoginRequest.objects.filter(status='pending').count()
        approved = ShareholderLoginRequest.objects.filter(status='approved').count()
        rejected = ShareholderLoginRequest.objects.filter(status='rejected').count()
        
        # Last 7 days trend
        trend_data = []
        today = date.today()
        for i in range(7):
            day = today - timedelta(days=i)
            count = ShareholderLoginRequest.objects.filter(
                requested_at__date=day
            ).count()
            trend_data.append({
                'date': day.strftime('%d-%b'),
                'count': count
            })
        trend_data.reverse()
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total': total,
                'pending': pending,
                'approved': approved,
                'rejected': rejected,
                'trend_data': trend_data,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
