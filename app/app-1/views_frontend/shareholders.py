"""Frontend views: shareholders."""
from ..models import *
import json
import time
import csv
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ..models import CashBalance, Shareholder, Share, SharePrice, DividendPayment, ShareTransfer, ShareholderMeeting, MeetingAttendance, ShareholderCashBalance, CompanyInfo
from ..certificate_utils import generate_share_certificate_pdf, generate_bulk_certificates
from django.contrib.auth.models import User
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from ..security_utils import safe_error


@login_required
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
def share_certificate_download(request, pk):
    """Download share certificate as PDF"""
    share = get_object_or_404(Share, pk=pk)
    pdf_buffer = generate_share_certificate_pdf(share)
    
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    filename = f"Share_Certificate_{share.shareholder.name}_{share.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
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


@login_required
def shareholder_dashboard(request):
    """Shareholder Dashboard with overview"""
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_shareholders': Shareholder.objects.filter(status='active').count(),
        'total_shares': total_shares,
        'total_investment': Share.objects.aggregate(total=Sum(F('quantity') * F('purchase_price')))['total'] or Decimal('0.00'),
        'recent_shareholders': Shareholder.objects.filter(status='active').order_by('-created_at')[:10],
        'top_shareholders': Shareholder.objects.filter(status='active').annotate(
            total_shares_count=Sum('shares__quantity')
        ).order_by('-total_shares_count')[:5],
        'pending_transfers': ShareTransfer.objects.filter(status='pending').count(),
        'pending_dividends': DividendPayment.objects.filter(status='pending').count(),
        'upcoming_meetings': ShareholderMeeting.objects.filter(status='scheduled', date__gte=date.today()).count(),
        'latest_price': SharePrice.objects.filter(is_active=True).first(),
    }
    return render(request, 'shareholders/dashboard.html', context)


# ✅ NEW CODE
@login_required
def shareholder_list(request):
    shareholders = Shareholder.objects.select_related(
        'user',
        'created_by'
    ).prefetch_related(
        'shares',
        'dividend_payments',
        'cash_transactions'
    ).all()
    
    search = request.GET.get('search', '')
    if search:
        shareholders = shareholders.filter(
            Q(name__icontains=search) |
            Q(shareholder_code__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status:
        shareholders = shareholders.filter(status=status)
    
    shareholder_type = request.GET.get('type', '')
    if shareholder_type:
        shareholders = shareholders.filter(shareholder_type=shareholder_type)
    
    # Get total shares for percentage calculation
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    for shareholder in shareholders:
        shareholder.ownership_percent = shareholder.ownership_percentage(total_shares)
        shareholder.total_shares_count = shareholder.total_shares()
    
    paginator = Paginator(shareholders, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'status': status,
        'shareholder_type': shareholder_type,
        'total_shareholders': shareholders.count(),
        'total_shares': total_shares,
    }
    return render(request, 'shareholders/list.html', context)


# ✅ NEW CODE
@login_required
def shareholder_detail(request, pk):
    shareholder = get_object_or_404(
        Shareholder.objects.select_related(
            'user',
            'created_by',
            'cash_balance'
        ).prefetch_related(
            'shares',
            'dividend_payments',
            'cash_transactions',
            'share_transfers_out',
            'share_transfers_in'
        ),
        pk=pk
    )
    shares = shareholder.shares.select_related('transferred_from').all()
    dividend_payments = shareholder.dividend_payments.all().order_by('-created_at')
    transfers_out = shareholder.share_transfers_out.all()
    transfers_in = shareholder.share_transfers_in.all()
    
    total_shares = shareholder.total_shares()
    total_investment = shareholder.total_investment()
    total_dividends = shareholder.total_dividends()
    
    latest_price = SharePrice.objects.filter(is_active=True).first()
    current_value = shareholder.current_value(latest_price.price if latest_price else None)
    
    profit_loss = current_value - total_investment
    profit_loss_percent = (profit_loss / total_investment * 100) if total_investment > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'shares': shares,
        'dividend_payments': dividend_payments,
        'transfers_out': transfers_out,
        'transfers_in': transfers_in,
        'total_shares': total_shares,
        'total_investment': total_investment,
        'total_dividends': total_dividends,
        'current_value': current_value,
        'profit_loss': profit_loss,
        'profit_loss_percent': profit_loss_percent,
        'latest_price': latest_price,
    }
    return render(request, 'shareholders/detail.html', context)


@login_required
def shareholder_create(request):
    """Create new shareholder with cash balance and login access"""
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can create shareholders.')
        return redirect('dashboard')  # ✅ Yeh return hona chahiye
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # ============================================
                # BASIC INFORMATION
                # ============================================
                shareholder = Shareholder(
                    name=request.POST.get('name'),
                    shareholder_type=request.POST.get('shareholder_type', 'individual'),
                    email=request.POST.get('email', ''),
                    phone=request.POST.get('phone', ''),
                    address=request.POST.get('address', ''),
                    cnic=request.POST.get('cnic', ''),
                    passport_no=request.POST.get('passport_no', ''),
                    company_name=request.POST.get('company_name', ''),
                    registration_no=request.POST.get('registration_no', ''),
                    bank_name=request.POST.get('bank_name', ''),
                    account_number=request.POST.get('account_number', ''),
                    account_title=request.POST.get('account_title', ''),
                    iban=request.POST.get('iban', ''),
                    status=request.POST.get('status', 'active'),
                    is_founder=request.POST.get('is_founder') == 'on',
                    is_board_member=request.POST.get('is_board_member') == 'on',
                    notes=request.POST.get('notes', ''),
                    created_by=request.user,
                    allow_login=request.POST.get('allow_login') == 'on',
                )
                shareholder.save()
                
                # ============================================
                # CREATE CASH BALANCE
                # ============================================
                ShareholderCashBalance.objects.create(
                    shareholder=shareholder,
                    balance=Decimal('0.00')
                )
                
                # ============================================
                # LOGIN ACCESS - EXACT USERNAME
                # ============================================
                login_password = None
                username = None
                
                if shareholder.allow_login:
                    username = shareholder.name.lower().replace(' ', '').replace('-', '').replace('_', '')
                    
                    # ✅ Form se password lo
                    password = request.POST.get('password', '123456')
                    
                    # ✅ Check existing user
                    existing_user = User.objects.filter(username__iexact=username).first()
                    
                    if existing_user:
                        shareholder.user = existing_user
                        shareholder.save()
                        
                        if not existing_user.is_active:
                            existing_user.is_active = True
                            existing_user.save()
                        
                        # ✅ Form wala password set karo
                        existing_user.set_password(password)
                        existing_user.save()
                        login_password = password
                        
                        messages.info(
                            request, 
                            f'🔐 Password updated for existing user "{username}"!'
                        )
                    else:
                        user = User.objects.create_user(
                            username=username,
                            email=shareholder.email or '',
                            password=password
                        )
                        
                        user.is_active = True
                        user.save()
                        
                        shareholder.user = user
                        shareholder.save()
                        login_password = password
                        
                        messages.info(
                            request, 
                            f'🔐 New user created! Username: {username}'
                        )
                
                # ============================================
                # INITIAL DEPOSIT
                # ============================================
                initial_deposit = Decimal(request.POST.get('initial_deposit', 0))
                if initial_deposit > 0:
                    main_balance = CashBalance.get_balance()
                    if main_balance < initial_deposit:
                        messages.warning(
                            request, 
                            f'⚠️ Insufficient main cash for initial deposit! Available: Rs. {main_balance:,.2f}'
                        )
                    else:
                        ShareholderCashBalance.deposit(
                            shareholder=shareholder,
                            amount=initial_deposit,
                            user=request.user,
                            description=f"Initial deposit for new shareholder"
                        )
                        CashBalance.update_balance(
                            amount=initial_deposit,
                            transaction_type='withdraw',
                            user=request.user,
                            description=f"Initial deposit for new shareholder {shareholder.name}"
                        )
                        messages.info(
                            request, 
                            f'💰 Rs. {initial_deposit:,.2f} deposited to {shareholder.name}\'s balance!'
                        )
                
                # ============================================
                # INITIAL SHARES
                # ============================================
                initial_shares = int(request.POST.get('initial_shares', 0))
                purchase_price = Decimal(request.POST.get('purchase_price', 0))
                paid_from_shareholder_balance = request.POST.get('paid_from_shareholder_balance') == 'on'
                
                if initial_shares > 0 and purchase_price > 0:
                    share = Share(
                        shareholder=shareholder,
                        quantity=initial_shares,
                        purchase_price=purchase_price,
                        issue_date=now().date(),
                        created_by=request.user,
                        paid_from_shareholder_balance=paid_from_shareholder_balance
                    )
                    share.save()
                    
                    if paid_from_shareholder_balance:
                        messages.info(
                            request, 
                            f'💰 Rs. {initial_shares * purchase_price:,.2f} deducted from {shareholder.name}\'s cash balance for shares!'
                        )
                    else:
                        messages.info(
                            request, 
                            f'💰 Rs. {initial_shares * purchase_price:,.2f} added to main cash balance for shares!'
                        )
                
                # ============================================
                # SUCCESS MESSAGE
                # ============================================
                success_msg = f'✅ Shareholder "{shareholder.name}" created successfully!'
                if username and login_password:
                    success_msg += f' Login: {username} | Password: {login_password}'
                elif username:
                    success_msg += f' (Linked to existing user: {username})'
                
                messages.success(request, success_msg)
                return redirect('shareholder_detail', pk=shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_create')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_create')
    
    # ============================================
    # ✅ IMPORTANT: GET REQUEST - YEH RETURN HONA CHAHIYE
    # ============================================
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder_types': Shareholder.SHAREHOLDER_TYPES,
        'status_choices': Shareholder.STATUS_CHOICES,
        'main_balance': CashBalance.get_balance(),
    }
    return render(request, 'shareholders/create.html', context)  # ✅ YEH HONA CHAHIYE


def check_username_availability(request):
    """Check if username is available"""
    username = request.GET.get('username', '').strip()
    
    if not username:
        return JsonResponse({'available': False, 'message': 'Username required'})
    
    if len(username) < 3:
        return JsonResponse({'available': False, 'message': 'Username must be at least 3 characters'})
    
    if not username.isalnum() and '_' not in username:
        return JsonResponse({'available': False, 'message': 'Only letters, numbers and underscore allowed'})
    
    exists = User.objects.filter(username=username).exists()
    
    return JsonResponse({
        'available': not exists,
        'username': username,
        'message': 'Username available' if not exists else 'Username already taken'
    })


def shareholder_edit(request, pk):
    """Edit shareholder with share details and cash balance adjustment"""
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can edit shareholders.')
        return redirect('dashboard')
    
    share = shareholder.shares.first()
    shareholder_balance = ShareholderCashBalance.get_balance(shareholder)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # --- Update Shareholder Info ---
                shareholder.name = request.POST.get('name')
                shareholder.shareholder_type = request.POST.get('shareholder_type', 'individual')
                shareholder.email = request.POST.get('email', '')
                shareholder.phone = request.POST.get('phone', '')
                shareholder.address = request.POST.get('address', '')
                shareholder.cnic = request.POST.get('cnic', '')
                shareholder.passport_no = request.POST.get('passport_no', '')
                shareholder.company_name = request.POST.get('company_name', '')
                shareholder.registration_no = request.POST.get('registration_no', '')
                shareholder.bank_name = request.POST.get('bank_name', '')
                shareholder.account_number = request.POST.get('account_number', '')
                shareholder.account_title = request.POST.get('account_title', '')
                shareholder.iban = request.POST.get('iban', '')
                shareholder.status = request.POST.get('status', 'active')
                shareholder.is_founder = request.POST.get('is_founder') == 'on'
                shareholder.is_board_member = request.POST.get('is_board_member') == 'on'
                shareholder.notes = request.POST.get('notes', '')
                
                # ✅ LOGIN ACCESS - Handle Allow Login
                allow_login = request.POST.get('allow_login') == 'on'
                shareholder.allow_login = allow_login
                
                # ✅ If login enabled and no user exists, create user
                if allow_login and not shareholder.user:
                    password = request.POST.get('password', '').strip()
                    if password and len(password) < 8:
                        messages.warning(request, '⚠️ Password was shorter than 8 characters, so a random one was generated.')
                        password = ''
                    user = shareholder.create_user(password or None)
                    messages.info(
                        request, 
                        f'🔐 Login enabled! Username: {user.username}, Password: {shareholder.initial_password} (shown once - please note it down)'
                    )
                # ✅ If login enabled and user exists, update password if provided
                elif allow_login and shareholder.user:
                    password = request.POST.get('password', '')
                    if password and len(password) >= 8:
                        shareholder.set_password(password)
                        messages.info(request, f'🔐 Password updated for {shareholder.user.username}!')
                
                shareholder.save()
                
                # --- Update Share Details ---
                new_qty = int(request.POST.get('initial_shares', 0))
                new_price = Decimal(request.POST.get('purchase_price', 0))
                paid_from_shareholder_balance = request.POST.get('paid_from_shareholder_balance') == 'on'
                
                if share:
                    old_qty = share.quantity
                    old_price = share.purchase_price
                    old_investment = old_qty * old_price
                    new_investment = new_qty * new_price
                    difference = new_investment - old_investment
                    
                    share.quantity = new_qty
                    share.purchase_price = new_price
                    share.paid_from_shareholder_balance = paid_from_shareholder_balance
                    
                    if new_qty > 0 and new_price > 0:
                        share.save()
                    elif new_qty == 0:
                        if old_investment > 0:
                            ShareholderCashBalance.deposit(
                                shareholder=shareholder,
                                amount=old_investment,
                                user=request.user,
                                description=f"Refund for removing shares - {old_qty} shares @ Rs. {old_price:,.2f}"
                            )
                            CashBalance.update_balance(
                                amount=old_investment,
                                transaction_type='withdraw',
                                user=request.user,
                                description=f"Refund to {shareholder.name} - shares removed"
                            )
                        share.delete()
                        share = None
                    else:
                        share.save()
                    
                else:
                    if new_qty > 0 and new_price > 0:
                        new_share = Share.objects.create(
                            shareholder=shareholder,
                            quantity=new_qty,
                            purchase_price=new_price,
                            issue_date=now().date(),
                            created_by=request.user,
                            paid_from_shareholder_balance=paid_from_shareholder_balance
                        )
                        if paid_from_shareholder_balance:
                            messages.info(
                                request, 
                                f'💰 Rs. {new_qty * new_price:,.2f} deducted from {shareholder.name}\'s cash balance (new shares)'
                            )
                        share = new_share
                
                messages.success(request, f'✅ Shareholder "{shareholder.name}" updated successfully!')
                return redirect('shareholder_detail', pk=shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_edit', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_edit', pk=pk)
    
    # --- GET Request - Display Form ---
    if share:
        share.total_investment = share.quantity * share.purchase_price
    else:
        share = None
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'share': share,
        'shareholder_balance': shareholder_balance,
        'shareholder_types': Shareholder.SHAREHOLDER_TYPES,
        'status_choices': Shareholder.STATUS_CHOICES,
    }
    return render(request, 'shareholders/edit.html', context)


@login_required
def shareholder_delete(request, pk):
    """Delete shareholder"""
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    if request.method == 'POST':
        name = shareholder.name
        shareholder.delete()
        messages.success(request, f'🗑️ Shareholder "{name}" deleted successfully!')
        return redirect('shareholder_list')
    
    return redirect('shareholder_list')


@login_required
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
def share_transfer_detail(request, pk):
    """Share transfer detail"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'transfer': transfer,
    }
    return render(request, 'shareholders/transfer_detail.html', context)


@login_required
def share_transfer_approve(request, pk):
    """Approve share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.approve(request.user)
    messages.success(request, f'✅ Transfer #{transfer.transfer_no} approved!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
def share_transfer_complete(request, pk):
    """Complete share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.complete(request.user)
    messages.success(request, f'✅ Transfer #{transfer.transfer_no} completed!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
def share_transfer_reject(request, pk):
    """Reject share transfer"""
    transfer = get_object_or_404(ShareTransfer, pk=pk)
    transfer.reject(request.user)
    messages.success(request, f'❌ Transfer #{transfer.transfer_no} rejected!')
    return redirect('share_transfer_detail', pk=transfer.pk)


@login_required
def share_price_list(request):
    """List share prices"""
    prices = SharePrice.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'prices': prices,
    }
    return render(request, 'shareholders/price_list.html', context)


@login_required
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


@login_required
def meeting_list(request):
    """List shareholder meetings"""
    meetings = ShareholderMeeting.objects.all()
    
    status = request.GET.get('status', '')
    if status:
        meetings = meetings.filter(status=status)
    
    meeting_type = request.GET.get('type', '')
    if meeting_type:
        meetings = meetings.filter(meeting_type=meeting_type)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meetings': meetings,
    }
    return render(request, 'shareholders/meeting_list.html', context)


@login_required
def meeting_create(request):
    """Create new shareholder meeting"""
    if request.method == 'POST':
        try:
            meeting_type = request.POST.get('meeting_type')
            title = request.POST.get('title')
            date = request.POST.get('date')
            time = request.POST.get('time') or None
            venue = request.POST.get('venue')
            agenda = request.POST.get('agenda')
            status = request.POST.get('status', 'scheduled')
            notes = request.POST.get('notes', '')
            
            meeting = ShareholderMeeting.objects.create(
                meeting_type=meeting_type,
                title=title,
                date=date,
                time=time,
                venue=venue,
                agenda=agenda,
                status=status,
                notes=notes,
                created_by=request.user
            )
            
            # Add attendees if provided
            attendee_ids = request.POST.getlist('attendees[]')
            if attendee_ids:
                meeting.attendees.set(attendee_ids)
                meeting.total_attendees = len(attendee_ids)
                meeting.save()
            
            messages.success(request, f'✅ Meeting "{meeting.title}" created!')
            return redirect('meeting_detail', pk=meeting.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('meeting_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting_types': ShareholderMeeting.MEETING_TYPES,
        'status_choices': ShareholderMeeting.STATUS_CHOICES,
        'shareholders': Shareholder.objects.filter(status='active'),
    }
    return render(request, 'shareholders/meeting_create.html', context)


@login_required
def meeting_detail(request, pk):
    """Meeting detail view"""
    meeting = get_object_or_404(ShareholderMeeting, pk=pk)
    attendance = meeting.attendance_records.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': meeting,
        'attendance': attendance,
    }
    return render(request, 'shareholders/meeting_detail.html', context)


@login_required
def meeting_mark_attendance(request, pk):
    """Mark attendance for a meeting"""
    meeting = get_object_or_404(ShareholderMeeting, pk=pk)
    
    if request.method == 'POST':
        for shareholder in meeting.attendees.all():
            status = request.POST.get(f'attendance_{shareholder.id}', 'absent')
            MeetingAttendance.objects.update_or_create(
                meeting=meeting,
                shareholder=shareholder,
                defaults={'status': status}
            )
        
        meeting.total_attendees = MeetingAttendance.objects.filter(meeting=meeting, status='present').count()
        meeting.save()
        
        messages.success(request, f'✅ Attendance marked for {meeting.title}!')
        return redirect('meeting_detail', pk=meeting.pk)
    
    return redirect('meeting_detail', pk=meeting.pk)


@login_required
def shareholder_report(request):
    """Generate shareholder reports"""
    report_type = request.GET.get('type', 'summary')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_type': report_type,
        'shareholders': Shareholder.objects.filter(status='active'),
    }
    return render(request, 'shareholders/report.html', context)


@login_required
def shareholder_report_pdf(request):
    """Generate shareholder report PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP System"
    
    story.append(Paragraph(company_name, styles['Heading1']))
    story.append(Paragraph("Shareholder Report", styles['Heading2']))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    data = [['Code', 'Name', 'Type', 'Shares', 'Investment', 'Dividend', 'Value']]
    
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    latest_price = SharePrice.objects.filter(is_active=True).first()
    
    for shareholder in Shareholder.objects.filter(status='active'):
        shares = shareholder.total_shares()
        investment = shareholder.total_investment()
        dividends = shareholder.total_dividends()
        value = shareholder.current_value(latest_price.price if latest_price else None)
        
        data.append([
            shareholder.shareholder_code,
            shareholder.name,
            shareholder.get_shareholder_type_display(),
            f"{shares:,}",
            f"Rs. {investment:,.2f}",
            f"Rs. {dividends:,.2f}",
            f"Rs. {value:,.2f}",
        ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Total Shareholders: {Shareholder.objects.filter(status='active').count()}", styles['Normal']))
    story.append(Paragraph(f"Total Shares: {total_shares:,}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="shareholder_report.pdf"'
    return response


@login_required
def shareholder_dashboard_api(request):
    """AJAX: Get shareholder dashboard data"""
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    data = {
        'total_shareholders': Shareholder.objects.filter(status='active').count(),
        'total_shares': total_shares,
        'total_investment': float(Share.objects.aggregate(total=Sum(F('quantity') * F('purchase_price')))['total'] or 0),
        'pending_transfers': ShareTransfer.objects.filter(status='pending').count(),
        'pending_dividends': DividendPayment.objects.filter(status='pending').count(),
        'upcoming_meetings': ShareholderMeeting.objects.filter(status='scheduled', date__gte=date.today()).count(),
    }
    return JsonResponse(data)


@login_required
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
def terms_preview(request, pk):
    """Preview Terms & Conditions"""
    
    terms = get_object_or_404(TermsAndConditions, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms': terms,
    }
    return render(request, 'terms/preview.html', context)


@login_required
def shareholder_support_ticket_detail(request, pk):
    """View support ticket detail"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    ticket = get_object_or_404(ShareholderSupportTicket, pk=pk, shareholder=shareholder)
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            SupportTicketReply.objects.create(
                ticket=ticket,
                message=message,
                is_internal=False,
                created_by=request.user
            )
            
            if ticket.status == 'closed':
                ticket.status = 'in_progress'
                ticket.save()
            
            messages.success(request, '✅ Reply sent successfully!')
            return redirect('shareholder_support_ticket_detail', pk=pk)
    
    replies = ticket.replies.filter(is_internal=False).order_by('created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'ticket': ticket,
        'replies': replies,
    }
    return render(request, 'shareholders/portal/ticket_detail.html', context)


@login_required
def admin_support_tickets(request):
    """Admin view all support tickets"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    tickets = ShareholderSupportTicket.objects.select_related('shareholder', 'assigned_to').all()
    
    status = request.GET.get('status', '')
    if status:
        tickets = tickets.filter(status=status)
    
    priority = request.GET.get('priority', '')
    if priority:
        tickets = tickets.filter(priority=priority)
    
    search = request.GET.get('search', '')
    if search:
        tickets = tickets.filter(
            Q(ticket_no__icontains=search) |
            Q(subject__icontains=search) |
            Q(shareholder__name__icontains=search)
        )
    
    total_tickets = tickets.count()
    new_tickets = tickets.filter(status='new').count()
    in_progress = tickets.filter(status='in_progress').count()
    resolved = tickets.filter(status='resolved').count()
    closed = tickets.filter(status='closed').count()
    
    paginator = Paginator(tickets, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'tickets': page_obj,
        'total_tickets': total_tickets,
        'new_tickets': new_tickets,
        'in_progress': in_progress,
        'resolved': resolved,
        'closed': closed,
        'status': status,
        'priority': priority,
        'search': search,
        'status_choices': ShareholderSupportTicket.STATUS_CHOICES,
        'priority_choices': ShareholderSupportTicket.PRIORITY_CHOICES,
    }
    return render(request, 'shareholders/admin/tickets.html', context)


@login_required
def admin_support_ticket_detail(request, pk):
    """Admin view ticket detail"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    ticket = get_object_or_404(ShareholderSupportTicket, pk=pk)
    replies = ticket.replies.all().order_by('created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'reply':
            message = request.POST.get('message')
            is_internal = request.POST.get('is_internal') == 'on'
            
            if message:
                SupportTicketReply.objects.create(
                    ticket=ticket,
                    message=message,
                    is_internal=is_internal,
                    created_by=request.user
                )
                
                if not is_internal:
                    messages.success(request, '✅ Reply sent to shareholder!')
                else:
                    messages.success(request, '✅ Internal note added!')
        
        elif action == 'assign':
            assigned_to_id = request.POST.get('assigned_to')
            if assigned_to_id:
                ticket.assigned_to_id = assigned_to_id
                ticket.status = 'in_progress'
                ticket.save()
                messages.success(request, f'✅ Ticket assigned to {ticket.assigned_to.username}')
        
        elif action == 'resolve':
            ticket.status = 'resolved'
            ticket.resolved_at = now()
            ticket.save()
            messages.success(request, '✅ Ticket resolved!')
        
        elif action == 'close':
            ticket.status = 'closed'
            ticket.save()
            messages.success(request, '✅ Ticket closed!')
        
        return redirect('admin_support_ticket_detail', pk=pk)
    
    users = User.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'ticket': ticket,
        'replies': replies,
        'users': users,
        'status_choices': ShareholderSupportTicket.STATUS_CHOICES,
    }
    return render(request, 'shareholders/admin/ticket_detail.html', context)


@login_required
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
        'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    return render(request, 'terms/admin_acceptance_detail.html', context)


@login_required
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
                acceptance.accepted_at.strftime('%Y-%m-%d %H:%M:%S'),
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


def shareholder_register(request):
    """
    Public page - Shareholder apni details bhar kar request send kare
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
            
            # ✅ YEH CHANGE - Success page par redirect
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
