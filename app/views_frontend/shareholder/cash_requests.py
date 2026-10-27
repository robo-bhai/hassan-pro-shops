"""Frontend views: shareholder/cash_requests (split from the former shareholder_cash.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from django.contrib import messages
from ...models import CashBalance, Shareholder, ShareholderCashBalance, CompanyInfo
from django.contrib.auth.models import User


@login_required
@perm_required('view_shareholders')
def shareholder_deposit_requests(request):
    """Admin: List all deposit requests for approval"""
    
    # Only admin and staff can view
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can view deposit requests.')
        return redirect('dashboard')
    
    deposit_requests = ShareholderDepositRequest.objects.select_related(
        'shareholder', 'approved_by'
    ).order_by('-created_at')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        deposit_requests = deposit_requests.filter(status=status)
    
    shareholder_id = request.GET.get('shareholder', '')
    if shareholder_id:
        deposit_requests = deposit_requests.filter(shareholder_id=shareholder_id)
    
    search = request.GET.get('search', '')
    if search:
        deposit_requests = deposit_requests.filter(
            Q(request_no__icontains=search) |
            Q(shareholder__name__icontains=search) |
            Q(reference_no__icontains=search)
        )
    
    # Statistics
    pending_count = deposit_requests.filter(status='pending').count()
    approved_count = deposit_requests.filter(status='approved').count()
    rejected_count = deposit_requests.filter(status='rejected').count()
    total_amount = deposit_requests.aggregate(total=Sum('amount'))['total'] or 0
    pending_amount = deposit_requests.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(deposit_requests, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'deposit_requests': page_obj,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'total_amount': total_amount,
        'pending_amount': pending_amount,
        'status': status,
        'shareholder_id': shareholder_id,
        'search': search,
        'shareholders': Shareholder.objects.filter(status='active'),
        'status_choices': ShareholderDepositRequest.STATUS_CHOICES,
    }
    return render(request, 'shareholders/admin/deposit_requests.html', context)


@login_required
@perm_required('view_shareholders', post='manage_shareholder_cash')
def shareholder_deposit_request_detail(request, pk):
    """Admin: View deposit request detail"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    deposit_request = get_object_or_404(ShareholderDepositRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            try:
                deposit_request.approve(request.user)
                messages.success(
                    request, 
                    f'✅ Deposit request #{deposit_request.request_no} approved! '
                    f'Rs. {deposit_request.amount:,.2f} added to {deposit_request.shareholder.name}\'s balance.'
                )
            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
                
        elif action == 'reject':
            reason = request.POST.get('reason', '')
            try:
                deposit_request.reject(request.user, reason)
                messages.success(
                    request, 
                    f'❌ Deposit request #{deposit_request.request_no} rejected!'
                )
            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
        
        return redirect('shareholder_deposit_requests')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'deposit_request': deposit_request,
        'shareholder_balance': ShareholderCashBalance.get_balance(deposit_request.shareholder),
    }
    return render(request, 'shareholders/admin/deposit_request_detail.html', context)


@login_required
@perm_required('manage_shareholder_cash')
def shareholder_deposit_request_bulk_approve(request):
    """Admin: Bulk approve deposit requests"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        request_ids = request.POST.getlist('request_ids[]')
        
        if not request_ids:
            messages.error(request, 'No requests selected!')
            return redirect('shareholder_deposit_requests')
        
        approved = 0
        failed = 0
        total_amount = 0
        
        for req_id in request_ids:
            try:
                deposit_request = ShareholderDepositRequest.objects.get(id=req_id, status='pending')
                total_amount += deposit_request.amount
                deposit_request.approve(request.user)
                approved += 1
            except Exception as e:
                failed += 1
        
        messages.success(
            request, 
            f'✅ {approved} requests approved! Total amount: Rs. {total_amount:,.2f}. {failed} failed.'
        )
        return redirect('shareholder_deposit_requests')
    
    return redirect('shareholder_deposit_requests')


@login_required
@perm_required('view_shareholders')
def shareholder_deposit_request_notification(request, pk):
    """Resend notification for a deposit request"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    deposit_request = get_object_or_404(ShareholderDepositRequest, pk=pk)
    
    # Send notification to admin
    try:
        from ...models import Notification
        admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
        sent_count = 0
        for admin in admin_users:
            Notification.send(
                user=admin,
                title="💰 Deposit Request Reminder",
                message=f"{deposit_request.shareholder.name} - Rs. {deposit_request.amount:,.2f} - {deposit_request.request_no}",
                notification_type='warning',
                category='payments',
                link=f"/shareholders/deposit-requests/{deposit_request.id}/"
            )
            sent_count += 1
        messages.success(request, f'✅ Notification sent to {sent_count} admins!')
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('shareholder_deposit_request_detail', pk=pk)


@login_required
@perm_required('view_shareholders')
def shareholder_deposit_requests_for_shareholder(request, pk):
    """Admin: View deposit requests for a specific shareholder"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    deposit_requests = ShareholderDepositRequest.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'deposit_requests': deposit_requests,
        'total_requests': deposit_requests.count(),
        'pending_requests': deposit_requests.filter(status='pending').count(),
        'approved_requests': deposit_requests.filter(status='approved').count(),
        'total_amount': deposit_requests.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0,
    }
    return render(request, 'shareholders/admin/deposit_requests_for_shareholder.html', context)


@login_required
@perm_required('view_shareholders')
def shareholder_withdrawal_requests(request):
    """Admin: List all withdrawal requests for approval"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can view withdrawal requests.')
        return redirect('dashboard')
    
    withdrawal_requests = ShareholderWithdrawalRequest.objects.select_related(
        'shareholder', 'approved_by'
    ).order_by('-created_at')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        withdrawal_requests = withdrawal_requests.filter(status=status)
    
    shareholder_id = request.GET.get('shareholder', '')
    if shareholder_id:
        withdrawal_requests = withdrawal_requests.filter(shareholder_id=shareholder_id)
    
    search = request.GET.get('search', '')
    if search:
        withdrawal_requests = withdrawal_requests.filter(
            Q(request_no__icontains=search) |
            Q(shareholder__name__icontains=search) |
            Q(reference_no__icontains=search)
        )
    
    # Statistics
    pending_count = withdrawal_requests.filter(status='pending').count()
    approved_count = withdrawal_requests.filter(status='approved').count()
    rejected_count = withdrawal_requests.filter(status='rejected').count()
    total_amount = withdrawal_requests.aggregate(total=Sum('amount'))['total'] or 0
    pending_amount = withdrawal_requests.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(withdrawal_requests, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'withdrawal_requests': page_obj,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'total_amount': total_amount,
        'pending_amount': pending_amount,
        'status': status,
        'shareholder_id': shareholder_id,
        'search': search,
        'shareholders': Shareholder.objects.filter(status='active'),
        'status_choices': ShareholderWithdrawalRequest.STATUS_CHOICES,
    }
    return render(request, 'shareholders/admin/withdrawal_requests.html', context)


@login_required
@perm_required('view_shareholders', post='manage_shareholder_cash')
def shareholder_withdrawal_request_detail(request, pk):
    """Admin: View withdrawal request detail"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    withdrawal_request = get_object_or_404(ShareholderWithdrawalRequest, pk=pk)
    current_balance = ShareholderCashBalance.get_balance(withdrawal_request.shareholder)
    main_balance = CashBalance.get_balance()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            try:
                withdrawal_request.approve(request.user)
                messages.success(
                    request, 
                    f'✅ Withdrawal request #{withdrawal_request.request_no} approved! '
                    f'Rs. {withdrawal_request.amount:,.2f} deducted from {withdrawal_request.shareholder.name}\'s balance.'
                )
            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
                
        elif action == 'reject':
            reason = request.POST.get('reason', '')
            try:
                withdrawal_request.reject(request.user, reason)
                messages.success(
                    request, 
                    f'❌ Withdrawal request #{withdrawal_request.request_no} rejected!'
                )
            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
        
        return redirect('shareholder_withdrawal_requests')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'withdrawal_request': withdrawal_request,
        'shareholder_balance': current_balance,
        'main_balance': main_balance,
        'after_approval_balance': current_balance - withdrawal_request.amount,
        'after_approval_main': main_balance - withdrawal_request.amount,
    }
    return render(request, 'shareholders/admin/withdrawal_request_detail.html', context)


@login_required
@perm_required('manage_shareholder_cash')
def shareholder_withdrawal_request_bulk_approve(request):
    """Admin: Bulk approve withdrawal requests"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        request_ids = request.POST.getlist('request_ids[]')
        
        if not request_ids:
            messages.error(request, 'No requests selected!')
            return redirect('shareholder_withdrawal_requests')
        
        approved = 0
        failed = 0
        total_amount = 0
        
        for req_id in request_ids:
            try:
                withdrawal_request = ShareholderWithdrawalRequest.objects.get(id=req_id, status='pending')
                total_amount += withdrawal_request.amount
                withdrawal_request.approve(request.user)
                approved += 1
            except Exception as e:
                failed += 1
        
        messages.success(
            request, 
            f'✅ {approved} withdrawal requests approved! Total amount: Rs. {total_amount:,.2f}. {failed} failed.'
        )
        return redirect('shareholder_withdrawal_requests')
    
    return redirect('shareholder_withdrawal_requests')


@login_required
@perm_required('view_shareholders')
def shareholder_withdrawal_request_notification(request, pk):
    """Resend notification for a withdrawal request"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    withdrawal_request = get_object_or_404(ShareholderWithdrawalRequest, pk=pk)
    
    try:
        from ...models import Notification
        admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
        sent_count = 0
        for admin in admin_users:
            Notification.send(
                user=admin,
                title="💸 Withdrawal Request Reminder",
                message=f"{withdrawal_request.shareholder.name} - Rs. {withdrawal_request.amount:,.2f} - {withdrawal_request.request_no}",
                notification_type='warning',
                category='payments',
                link=f"/shareholders/withdrawal-requests/{withdrawal_request.id}/"
            )
            sent_count += 1
        messages.success(request, f'✅ Notification sent to {sent_count} admins!')
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('shareholder_withdrawal_request_detail', pk=pk)


@login_required
@perm_required('view_shareholders')
def shareholder_withdrawal_requests_for_shareholder(request, pk):
    """Admin: View withdrawal requests for a specific shareholder"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    withdrawal_requests = ShareholderWithdrawalRequest.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    # Statistics
    total_requests = withdrawal_requests.count()
    pending_requests = withdrawal_requests.filter(status='pending').count()
    approved_requests = withdrawal_requests.filter(status='approved').count()
    rejected_requests = withdrawal_requests.filter(status='rejected').count()
    total_amount = withdrawal_requests.aggregate(total=Sum('amount'))['total'] or 0
    pending_amount = withdrawal_requests.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
    approved_amount = withdrawal_requests.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'withdrawal_requests': withdrawal_requests,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'total_amount': total_amount,
        'pending_amount': pending_amount,
        'approved_amount': approved_amount,
    }
    return render(request, 'shareholders/admin/withdrawal_requests_for_shareholder.html', context)
