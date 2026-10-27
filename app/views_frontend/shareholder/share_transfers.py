"""Frontend views: shareholder/share_transfers (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date
from django.core.paginator import Paginator
from django.contrib import messages
from ...models import Shareholder, Share, SharePrice, ShareTransfer, CompanyInfo


@login_required
@perm_required('view_shareholders')
def share_list(request):
    """List all shares"""
    shares = Share.objects.select_related('shareholder').all()
    
    search = request.GET.get('search', '')
    if search:
        shares = shares.filter(
            Q(shareholder__name__icontains=search) |
            Q(shareholder__shareholder_code__icontains=search) |
            Q(certificate_number__icontains=search)
        )
    
    share_type = request.GET.get('type', '')
    if share_type:
        shares = shares.filter(share_type=share_type)
    
    shareholder_id = request.GET.get('shareholder', '')
    if shareholder_id:
        shares = shares.filter(shareholder_id=shareholder_id)
    
    latest_price = SharePrice.objects.filter(is_active=True).first()
    
    total_shares = shares.aggregate(total=Sum('quantity'))['total'] or 0
    total_value = sum(share.total_value(latest_price.price if latest_price else None) for share in shares)
    
    paginator = Paginator(shares, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'share_type': share_type,
        'shareholder_id': shareholder_id,
        'shareholders': Shareholder.objects.filter(status='active'),
        'total_shares': total_shares,
        'total_value': total_value,
        'latest_price': latest_price,
    }
    return render(request, 'shareholders/share_list.html', context)


@login_required
@perm_required('manage_share_transfers')
def share_transfer_create(request):
    """Create share transfer"""
    if request.method == 'POST':
        try:
            from_shareholder_id = request.POST.get('from_shareholder')
            to_shareholder_id = request.POST.get('to_shareholder')
            quantity = int(request.POST.get('quantity', 0))
            transfer_price = Decimal(request.POST.get('transfer_price', 0))
            transfer_date = request.POST.get('transfer_date') or now().date()
            reason = request.POST.get('reason', '')
            notes = request.POST.get('notes', '')
            
            # ✅ Validation
            if from_shareholder_id == to_shareholder_id:
                messages.error(request, '❌ From and To shareholder cannot be the same!')
                return redirect('share_transfer_create')
            
            if quantity <= 0:
                messages.error(request, '❌ Quantity must be greater than zero!')
                return redirect('share_transfer_create')
            
            if transfer_price < 0:
                messages.error(request, '❌ Transfer price cannot be negative!')
                return redirect('share_transfer_create')
            
            from_shareholder = get_object_or_404(Shareholder, pk=from_shareholder_id)
            to_shareholder = get_object_or_404(Shareholder, pk=to_shareholder_id)
            
            # ✅ Check if from shareholder has enough shares
            total_shares = from_shareholder.total_shares()
            if total_shares < quantity:
                messages.error(
                    request, 
                    f'❌ Insufficient shares! {from_shareholder.name} has {total_shares} shares, requested {quantity}'
                )
                return redirect('share_transfer_create')
            
            # ✅ FIX: Select shares to transfer with correct quantity
            # Get all unlocked shares with quantity > 0
            shares_to_transfer = from_shareholder.shares.filter(
                is_locked=False,
                quantity__gt=0
            ).order_by('issue_date')
            
            remaining = quantity
            selected_shares = []
            total_selected_quantity = 0  # ✅ Track total quantity selected
            
            for share in shares_to_transfer:
                if remaining <= 0:
                    break
                # ✅ Take min of remaining and share quantity
                take = min(share.quantity, remaining)
                selected_shares.append(share)
                total_selected_quantity += take  # ✅ Track total
                remaining -= take
            
            # ✅ Check if we got exactly the requested quantity
            if total_selected_quantity != quantity:
                messages.error(
                    request, 
                    f'❌ Could not select required shares! Available: {total_selected_quantity}, Requested: {quantity}'
                )
                return redirect('share_transfer_create')
            
            if remaining > 0:
                messages.error(
                    request, 
                    f'❌ Not enough available shares! Remaining needed: {remaining}'
                )
                return redirect('share_transfer_create')
            
            # ✅ Create transfer
            transfer = ShareTransfer.objects.create(
                from_shareholder=from_shareholder,
                to_shareholder=to_shareholder,
                quantity=quantity,  # ✅ Store the correct quantity
                transfer_price=transfer_price,
                transfer_date=transfer_date,
                reason=reason,
                notes=notes,
                created_by=request.user
            )
            
            # ✅ Add shares to transfer
            transfer.shares.set(selected_shares)
            
            messages.success(
                request, 
                f'✅ Share transfer #{transfer.transfer_no} created! '
                f'From {from_shareholder.name} to {to_shareholder.name} '
                f'({quantity} shares)'
            )
            return redirect('share_transfer_detail', pk=transfer.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('share_transfer_create')
    
    # GET request
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholders': Shareholder.objects.filter(status='active'),
    }
    return render(request, 'shareholders/transfer_create.html', context)


@login_required
@perm_required('view_shareholders')
def share_transfer_list(request):
    """List all share transfers"""
    transfers = ShareTransfer.objects.select_related('from_shareholder', 'to_shareholder').all()
    
    search = request.GET.get('search', '')
    if search:
        transfers = transfers.filter(
            Q(transfer_no__icontains=search) |
            Q(from_shareholder__name__icontains=search) |
            Q(to_shareholder__name__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        transfers = transfers.filter(status=status)
    
    paginator = Paginator(transfers, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'status': status,
    }
    return render(request, 'shareholders/transfer_list.html', context)


@login_required
@perm_required('view_shareholders')
def share_transfer_detail(request, pk):
    """Share transfer detail"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'transfer': transfer,
    }
    return render(request, 'shareholders/transfer_detail.html', context)


@login_required
@perm_required('manage_share_transfers')
def share_transfer_approve(request, pk):
    """Approve share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.approve(request.user)
    messages.success(request, f'✅ Transfer #{transfer.transfer_no} approved!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
@perm_required('manage_share_transfers')
def share_transfer_complete(request, pk):
    """Complete share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.complete(request.user)
    messages.success(request, f'✅ Transfer #{transfer.transfer_no} completed!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
@perm_required('manage_share_transfers')
def share_transfer_reject(request, pk):
    """Reject share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.reject(request.user)
    messages.success(request, f'❌ Transfer #{transfer.transfer_no} rejected!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
@perm_required('view_shareholders')
def share_price_list(request):
    """List share prices"""
    prices = SharePrice.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'prices': prices,
    }
    return render(request, 'shareholders/price_list.html', context)


@login_required
@perm_required('manage_shareholders')
def share_price_create(request):
    """Create new share price"""
    if request.method == 'POST':
        try:
            price = Decimal(request.POST.get('price', 0))
            date = request.POST.get('date') or now().date()
            is_active = request.POST.get('is_active') == 'on'
            notes = request.POST.get('notes', '')
            
            if price <= 0:
                messages.error(request, '❌ Price must be greater than zero!')
                return redirect('share_price_create')
            
            SharePrice.objects.create(
                price=price,
                date=date,
                is_active=is_active,
                notes=notes,
                created_by=request.user
            )
            
            messages.success(request, f'✅ Share price Rs. {price:,.2f} added!')
            return redirect('share_price_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('share_price_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'shareholders/price_create.html', context)
