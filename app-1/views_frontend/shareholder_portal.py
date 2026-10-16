"""Frontend views: shareholder portal."""
from ..models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from ..models import CashBalance, Share, SharePrice, ShareTransfer, ShareholderMeeting, MeetingAttendance, ShareholderCashBalance, ShareholderCashTransaction, CompanyInfo
from ..certificate_utils import generate_share_certificate_pdf
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from ..security_utils import safe_error, blocked, register_failure, clear_failures


@login_required
def shareholder_portal_buy_shares(request):
    """Shareholder portal - Buy shares from own balance"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # Get fresh balance
    balance_obj = ShareholderCashBalance.objects.filter(shareholder=shareholder).first()
    if balance_obj:
        balance_obj.refresh_from_db()
        balance = balance_obj.balance
    else:
        balance = Decimal('0.00')
        balance_obj = ShareholderCashBalance.objects.create(shareholder=shareholder, balance=Decimal('0.00'))
        balance = Decimal('0.00')
    
    # Get current share price
    latest_price = SharePrice.objects.filter(is_active=True).first()
    current_price = latest_price.price if latest_price else Decimal('100.00')
    
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', 0))
            purchase_price = Decimal(request.POST.get('purchase_price', 0))
            share_type = request.POST.get('share_type', 'ordinary')
            paid_from_balance = request.POST.get('paid_from_balance') == 'on'
            
            # Validation
            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero!')
                return redirect('shareholder_portal_buy_shares')
            
            if purchase_price <= 0:
                messages.error(request, 'Purchase price must be greater than zero!')
                return redirect('shareholder_portal_buy_shares')
            
            total_cost = quantity * purchase_price
            
            if paid_from_balance and balance < total_cost:
                messages.error(
                    request, 
                    f'❌ Insufficient balance! Available: Rs. {balance:,.2f}, Required: Rs. {total_cost:,.2f}'
                )
                return redirect('shareholder_portal_buy_shares')
            
            with transaction.atomic():
                # ✅ STEP 1: Create share WITHOUT automatic deduction
                share = Share(
                    shareholder=shareholder,
                    quantity=quantity,
                    purchase_price=purchase_price,
                    share_type=share_type,
                    issue_date=now().date(),
                    created_by=request.user,
                    paid_from_shareholder_balance=paid_from_balance
                )
                
                # ✅ Save without triggering cash update
                share.save_base()
                
                # Generate certificate number
                share.certificate_number = f"CERT-{share.id:06d}"
                Share.objects.filter(id=share.id).update(
                    certificate_number=share.certificate_number,
                    certificate_issue_date=now().date()
                )
                
                if paid_from_balance:
                    # ============================================
                    # ✅ STEP 2: Deduct from shareholder balance
                    # ============================================
                    balance_obj.refresh_from_db()
                    if balance_obj.balance < total_cost:
                        raise ValidationError(f"Insufficient balance!")
                    
                    balance_obj.balance -= total_cost
                    balance_obj.updated_by = request.user
                    balance_obj.save()
                    
                    # Create shareholder transaction
                    ShareholderCashTransaction.objects.create(
                        shareholder=shareholder,
                        amount=total_cost,
                        transaction_type='share_purchase',
                        balance_after=balance_obj.balance,
                        description=f"Share purchase: {quantity} shares @ Rs. {purchase_price:,.2f}",
                        share=share,
                        created_by=request.user
                    )
                    
                    # ============================================
                    # ✅ STEP 3: ADD to main cash (Company receives money)
                    # ============================================
                    CashBalance.update_balance(
                        amount=total_cost,
                        transaction_type='deposit',  # ✅ ADD to main cash
                        user=request.user,
                        description=f"Share purchase by {shareholder.name} - {quantity} shares @ Rs. {purchase_price:,.2f}"
                    )
                    
                    messages.success(
                        request, 
                        f'✅ {quantity} shares purchased successfully! '
                        f'Deducted Rs. {total_cost:,.2f} from your balance. '
                        f'New balance: Rs. {balance_obj.balance:,.2f}'
                    )
                else:
                    # ============================================
                    # If NOT using shareholder balance (main cash)
                    # ============================================
                    CashBalance.update_balance(
                        amount=total_cost,
                        transaction_type='deposit',  # ✅ ADD to main cash
                        user=request.user,
                        description=f"Share purchase by {shareholder.name} - {quantity} shares @ Rs. {purchase_price:,.2f} (Main Cash)"
                    )
                    
                    messages.success(
                        request, 
                        f'✅ {quantity} shares purchased successfully! '
                        f'Total cost: Rs. {total_cost:,.2f} (Main cash)'
                    )
                
                return redirect('shareholder_portal_dashboard')
            
        except ValidationError as e:
            messages.error(request, safe_error(e))
        except Exception as e:
            messages.error(request, f'❌ Error: {safe_error(e)}')
        
        return redirect('shareholder_portal_buy_shares')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'balance': balance,
        'current_price': current_price,
        'share_types': Share.SHARE_TYPES,
        'min_quantity': 1,
    }
    return render(request, 'shareholders/portal/buy_shares.html', context)


@login_required
def shareholder_portal_sell_shares(request):
    """Shareholder portal - Sell shares to main cash"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # Get all shares (not locked and not transferred)
    available_shares = shareholder.shares.filter(
        is_locked=False,
        quantity__gt=0
    )
    
    # Get current share price
    latest_price = SharePrice.objects.filter(is_active=True).first()
    current_price = latest_price.price if latest_price else Decimal('100.00')
    
    if request.method == 'POST':
        try:
            share_id = request.POST.get('share_id')
            sell_quantity = int(request.POST.get('sell_quantity', 0))
            sell_price = Decimal(request.POST.get('sell_price', 0))
            add_to_balance = request.POST.get('add_to_balance') == 'on'
            
            if not share_id:
                messages.error(request, 'Please select shares to sell!')
                return redirect('shareholder_portal_sell_shares')
            
            share = get_object_or_404(Share, id=share_id, shareholder=shareholder)
            
            if sell_quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero!')
                return redirect('shareholder_portal_sell_shares')
            
            if sell_quantity > share.quantity:
                messages.error(request, f'You only have {share.quantity} shares of this type!')
                return redirect('shareholder_portal_sell_shares')
            
            if sell_price <= 0:
                messages.error(request, 'Sell price must be greater than zero!')
                return redirect('shareholder_portal_sell_shares')
            
            total_amount = sell_quantity * sell_price
            
            with transaction.atomic():
                # Reduce share quantity
                share.quantity -= sell_quantity
                
                if share.quantity == 0:
                    share.is_locked = True
                
                share.save()
                
                if add_to_balance:
                    # Add to shareholder balance
                    new_balance = ShareholderCashBalance.deposit(
                        shareholder=shareholder,
                        amount=total_amount,
                        user=request.user,
                        description=f"Share sale: {sell_quantity} shares @ Rs. {sell_price:,.2f}"
                    )
                    
                    # Also add to main cash (company buys back)
                    CashBalance.update_balance(
                        amount=total_amount,
                        transaction_type='deposit',
                        user=request.user,
                        description=f"Share buyback from {shareholder.name} - {sell_quantity} shares"
                    )
                    
                    messages.success(
                        request, 
                        f'✅ {sell_quantity} shares sold successfully! '
                        f'Added Rs. {total_amount:,.2f} to your balance. '
                        f'New balance: Rs. {new_balance:,.2f}'
                    )
                else:
                    # Only main cash (company buys back)
                    CashBalance.update_balance(
                        amount=total_amount,
                        transaction_type='deposit',
                        user=request.user,
                        description=f"Share buyback from {shareholder.name} - {sell_quantity} shares"
                    )
                    messages.success(
                        request, 
                        f'✅ {sell_quantity} shares sold successfully! '
                        f'Amount: Rs. {total_amount:,.2f} (Main cash)'
                    )
                
                return redirect('shareholder_portal_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {safe_error(e)}')
            return redirect('shareholder_portal_sell_shares')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'available_shares': available_shares,
        'current_price': current_price,
        'balance': ShareholderCashBalance.get_balance(shareholder),
    }
    return render(request, 'shareholders/portal/sell_shares.html', context)


@login_required
def shareholder_get_share_price(request):
    """AJAX: Get current share price for selected share type"""
    
    share_id = request.GET.get('share_id')
    
    if not share_id:
        return JsonResponse({'success': False, 'message': 'Share ID required'})
    
    try:
        share = Share.objects.get(id=share_id)
        
        # Get current market price
        latest_price = SharePrice.objects.filter(is_active=True).first()
        current_price = latest_price.price if latest_price else Decimal('100.00')
        
        return JsonResponse({
            'success': True,
            'share_id': share.id,
            'share_type': share.get_share_type_display(),
            'quantity': share.quantity,
            'purchase_price': str(share.purchase_price),
            'current_price': str(current_price),
            'total_value': str(share.quantity * current_price),
            'profit_loss': str((current_price - share.purchase_price) * share.quantity),
        })
    except Share.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Share not found'})


@login_required
def shareholder_get_balance(request):
    """AJAX: Get current balance for shareholder"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        return JsonResponse({'success': False, 'message': 'Not a shareholder'})
    
    shareholder = request.user.shareholder_profile
    balance = ShareholderCashBalance.get_balance(shareholder)
    
    return JsonResponse({
        'success': True,
        'balance': float(balance),
        'formatted_balance': f"Rs. {balance:,.2f}"
    })


def shareholder_logout(request):
    """Logout shareholder"""
    logout(request)
    messages.success(request, 'You have been logged out successfully!')
    return redirect('shareholder_login')


@login_required
def shareholder_portal_profile(request):
    """Shareholder profile management"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    if request.method == 'POST':
        # Update profile
        shareholder.email = request.POST.get('email', shareholder.email)
        shareholder.phone = request.POST.get('phone', shareholder.phone)
        shareholder.address = request.POST.get('address', shareholder.address)
        shareholder.bank_name = request.POST.get('bank_name', shareholder.bank_name)
        shareholder.account_number = request.POST.get('account_number', shareholder.account_number)
        shareholder.account_title = request.POST.get('account_title', shareholder.account_title)
        shareholder.iban = request.POST.get('iban', shareholder.iban)
        shareholder.save()
        
        # Change password
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password:
            if new_password == confirm_password:
                if len(new_password) >= 6:
                    shareholder.set_password(new_password)
                    messages.success(request, 'Password updated successfully!')
                else:
                    messages.error(request, 'Password must be at least 6 characters!')
            else:
                messages.error(request, 'Passwords do not match!')
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('shareholder_portal_profile')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
    }
    return render(request, 'shareholders/portal/profile.html', context)


@login_required
def shareholder_portal_certificates(request):
    """View shareholder certificates"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    certificates = shareholder.shares.filter(certificate_printed=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'certificates': certificates,
    }
    return render(request, 'shareholders/portal/certificates.html', context)


@login_required
def shareholder_portal_transactions(request):
    """View shareholder transactions"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # Get all transactions
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    # Filter by type
    trans_type = request.GET.get('type', '')
    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)
    
    # Date filters
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        transactions = transactions.filter(created_at__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(created_at__date__lte=to_date)
    
    paginator = Paginator(transactions, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'page_obj': page_obj,
        'transactions': page_obj,
        'selected_type': trans_type,
        'from_date': from_date,
        'to_date': to_date,
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/portal/transactions.html', context)


@login_required
def shareholder_portal_dashboard(request):
    """
    Shareholder portal dashboard - Complete with Terms & Conditions check
    """
    
    # ========================================== #
    # 1. CHECK: Is user a shareholder?          #
    # ========================================== #
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied! This portal is for shareholders only.')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # ========================================== #
    # 2. CHECK: Terms & Conditions Accepted?    #
    # ========================================== #
    
    # Check if shareholder has accepted terms
    if not hasattr(shareholder, 'terms_acceptance'):
        messages.info(request, '📋 Please accept the Terms & Conditions to continue.')
        return redirect('shareholder_terms')
    
    # Check if terms version is up-to-date with active version
    active_terms = TermsAndConditions.objects.filter(is_active=True).first()
    if active_terms and shareholder.terms_acceptance.terms_version != active_terms.version:
        messages.warning(
            request, 
            f'📋 New Terms & Conditions (v{active_terms.version}) are available. Please accept them.'
        )
        return redirect('shareholder_terms')
    
    # ========================================== #
    # 3. CHECK: Shareholder Status              #
    # ========================================== #
    if shareholder.status != 'active':
        messages.error(request, 'Your account is not active! Please contact admin.')
        logout(request)
        return redirect('shareholder_login')
    
    if not shareholder.allow_login:
        messages.error(request, 'Login is disabled for your account!')
        logout(request)
        return redirect('shareholder_login')
    
    # ========================================== #
    # 4. GET SHAREHOLDER DATA                    #
    # ========================================== #
    
    # Get cash balance
    balance = ShareholderCashBalance.get_balance(shareholder)
    
    # Get shares data
    total_shares = shareholder.total_shares()
    total_investment = shareholder.total_investment()
    total_dividends = shareholder.total_dividends()
    
    # Get latest share price
    latest_price = SharePrice.objects.filter(is_active=True).first()
    current_price = latest_price.price if latest_price else Decimal('0.00')
    current_value = total_shares * current_price
    
    # Calculate profit/loss
    profit_loss = current_value - total_investment
    if total_investment > 0:
        profit_loss_percent = (profit_loss / total_investment) * 100
    else:
        profit_loss_percent = Decimal('0.00')
    
    # Get share holdings
    shares = shareholder.shares.filter(is_locked=False, quantity__gt=0)
    
    # Get dividend payments
    dividend_payments = shareholder.dividend_payments.all().order_by('-created_at')[:10]
    
    # Get transactions
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')[:10]
    
    # Get pending dividends
    pending_dividends = shareholder.dividend_payments.filter(status='pending')
    
    # Get pending deposit/withdrawal requests
    pending_deposits = ShareholderDepositRequest.objects.filter(
        shareholder=shareholder,
        status='pending'
    ).count()
    
    pending_withdrawals = ShareholderWithdrawalRequest.objects.filter(
        shareholder=shareholder,
        status='pending'
    ).count()
    
    # ========================================== #
    # 5. GET DRIP ENROLLMENT                     #
    # ========================================== #
    drip_enrollment = ShareholderDRIPEnrollment.objects.filter(
        shareholder=shareholder,
        status='active'
    ).select_related('drip', 'drip__dividend').first()
    
    # ========================================== #
    # 6. GET NOTIFICATIONS COUNT                 #
    # ========================================== #
    notification_count = Notification.objects.filter(
        Q(user=request.user) | Q(user__isnull=True),
        is_read=False
    ).count()
    
    # ========================================== #
    # 7. GET MEETING DATA                        #
    # ========================================== #
    upcoming_meetings = ShareholderMeeting.objects.filter(
        date__gte=date.today(),
        status='scheduled'
    ).count()
    
    # Check if shareholder is attending any meeting
    meeting_attendance = MeetingAttendance.objects.filter(
        shareholder=shareholder,
        status__in=['present', 'online', 'proxy']
    ).count()
    
    # ========================================== #
    # 8. GET SHARE TRANSFER DATA                 #
    # ========================================== #
    pending_transfers_out = ShareTransfer.objects.filter(
        from_shareholder=shareholder,
        status='pending'
    ).count()
    
    pending_transfers_in = ShareTransfer.objects.filter(
        to_shareholder=shareholder,
        status='pending'
    ).count()
    
    # ========================================== #
    # 9. CHART DATA (Monthly Dividend)           #
    # ========================================== #
    chart_months = []
    chart_amounts = []
    
    for i in range(6):
        month_date = date.today().replace(day=1) - timedelta(days=30 * i)
        month_name = month_date.strftime('%b %Y')
        chart_months.insert(0, month_name)
        
        # Get dividends for this month
        month_dividends = shareholder.dividend_payments.filter(
            payment_date__year=month_date.year,
            payment_date__month=month_date.month,
            status='paid'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        chart_amounts.insert(0, float(month_dividends))
    
    # ========================================== #
    # 10. COMPANY INFO                           #
    # ========================================== #
    company = CompanyInfo.objects.first()
    company_name = company.name if company else 'ERP System'
    company_logo = company.logo.url if company and company.logo else None
    
    # ========================================== #
    # 11. CONTEXT                               #
    # ========================================== #
    context = {
        'company_name': company_name,
        'company_logo': company_logo,
        'shareholder': shareholder,
        
        # Financial Data
        'balance': balance,
        'total_shares': total_shares,
        'total_investment': total_investment,
        'total_dividends': total_dividends,
        'current_price': current_price,
        'current_value': current_value,
        'profit_loss': profit_loss,
        'profit_loss_percent': profit_loss_percent,
        
        # Holdings
        'shares': shares,
        'share_count': shares.count(),
        
        # Recent Activity
        'dividend_payments': dividend_payments,
        'transactions': transactions,
        'pending_dividends': pending_dividends,
        'pending_dividends_count': pending_dividends.count(),
        
        # Requests
        'pending_deposits': pending_deposits,
        'pending_withdrawals': pending_withdrawals,
        
        # DRIP
        'drip_enrollment': drip_enrollment,
        
        # Notifications
        'notification_count': notification_count,
        
        # Meetings
        'upcoming_meetings': upcoming_meetings,
        'meeting_attendance': meeting_attendance,
        
        # Transfers
        'pending_transfers_out': pending_transfers_out,
        'pending_transfers_in': pending_transfers_in,
        
        # Chart
        'chart_months': json.dumps(chart_months),
        'chart_amounts': json.dumps(chart_amounts),
        
        # Latest Price
        'latest_price': latest_price,
        
        # Timestamps
        'today': date.today(),
        'now': now(),
    }
    
    return render(request, 'shareholders/portal/dashboard.html', context)


@login_required
def shareholder_portal_deposit(request):
    """Shareholder portal - Deposit to own balance"""
    
    if request.method != 'POST':
        return redirect('shareholder_portal_dashboard')
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    try:
        amount = Decimal(request.POST.get('amount', 0))
        description = request.POST.get('description', 'Internal deposit')
        reference_no = request.POST.get('reference_no', '')
        
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero!')
            return redirect('shareholder_portal_dashboard')
        
        with transaction.atomic():
            # Deposit to shareholder's balance
            new_balance = ShareholderCashBalance.deposit(
                shareholder=shareholder,
                amount=amount,
                user=request.user,
                description=description
            )
            
            messages.success(
                request, 
                f'✅ Rs. {amount:,.2f} deposited to your balance! '
                f'New balance: Rs. {new_balance:,.2f}'
            )
            
    except Exception as e:
        messages.error(request, f'❌ Error: {safe_error(e)}')
    
    return redirect('shareholder_portal_dashboard')


@login_required
def shareholder_portal_withdraw(request):
    """Shareholder portal - Withdraw from own balance"""
    
    if request.method != 'POST':
        return redirect('shareholder_portal_dashboard')
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    try:
        amount = Decimal(request.POST.get('amount', 0))
        description = request.POST.get('description', 'Internal withdrawal')
        reference_no = request.POST.get('reference_no', '')
        
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero!')
            return redirect('shareholder_portal_dashboard')
        
        with transaction.atomic():
            # Withdraw from shareholder's balance
            new_balance = ShareholderCashBalance.withdraw(
                shareholder=shareholder,
                amount=amount,
                user=request.user,
                description=description
            )
            
            messages.success(
                request, 
                f'✅ Rs. {amount:,.2f} withdrawn from your balance! '
                f'New balance: Rs. {new_balance:,.2f}'
            )
            
    except ValidationError as e:
        messages.error(request, safe_error(e))
    except Exception as e:
        messages.error(request, f'❌ Error: {safe_error(e)}')
    
    return redirect('shareholder_portal_dashboard')


def shareholder_login(request):
    """Shareholder login page"""
    
    # ✅ Agar already logged in hai toh check karein
    if request.user.is_authenticated:
        # ✅ Check if user is shareholder
        if hasattr(request.user, 'shareholder_profile'):
            return redirect('shareholder_portal_dashboard')
        else:
            # Agar admin hai toh admin dashboard par bhejo
            return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if not username or not password:
            messages.error(request, 'Please enter username and password!')
            return redirect('shareholder_login')
        
        username = username.strip()

        # Brute-force protection: 5 wrong passwords per username+IP, then wait 15 minutes
        if blocked(request, 'sh_login', limit=5, extra=username):
            messages.error(request, '⚠️ Too many failed attempts. Please wait 15 minutes and try again.')
            return redirect('shareholder_login')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            clear_failures(request, 'sh_login', extra=username)
            # ✅ Check if user is shareholder
            if hasattr(user, 'shareholder_profile'):
                shareholder = user.shareholder_profile
                if shareholder.status == 'active' and shareholder.allow_login:
                    login(request, user)
                    messages.success(request, f'Welcome back, {shareholder.name}!')
                    # ✅ YEH IMPORTANT HAI - Shareholder dashboard par redirect
                    return redirect('shareholder_portal_dashboard')
                else:
                    messages.error(request, 'Your account is not active or login is disabled!')
            else:
                messages.error(request, 'This account is not a shareholder account!')
                # ✅ Agar admin hai toh admin login page par bhejo
                return redirect('login')
        else:
            register_failure(request, 'sh_login', extra=username)
            messages.error(request, 'Invalid username or password!')
        
        return redirect('shareholder_login')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'is_shareholder_login': True,
    }
    return render(request, 'shareholders/login.html', context)


@login_required
def shareholder_portal_download_certificate(request, pk):
    """Download share certificate"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    share = get_object_or_404(Share, pk=pk, shareholder=shareholder)
    
    from ..certificate_utils import generate_share_certificate_pdf
    pdf_buffer = generate_share_certificate_pdf(share)
    
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    filename = f"Share_Certificate_{share.shareholder.name}_{share.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def shareholder_portal_deposit_request(request):
    """Shareholder portal - Request deposit (needs admin approval)"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied! Only shareholders can make deposit requests.')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # ✅ Get company info for deposit details
    company = CompanyInfo.objects.first()
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'bank_transfer')
            reference_no = request.POST.get('reference_no', '')
            description = request.POST.get('description', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_portal_deposit_request')
            
            if amount > 10000000:  # Max Rs. 1 crore per request
                messages.error(request, 'Amount exceeds maximum limit (Rs. 10,000,000)!')
                return redirect('shareholder_portal_deposit_request')
            
            # Create deposit request
            deposit_request = ShareholderDepositRequest.objects.create(
                shareholder=shareholder,
                amount=amount,
                payment_method=payment_method,
                reference_no=reference_no,
                description=description,
                created_by=request.user,
                status='pending'
            )
            
            # Save attachment if uploaded
            if request.FILES.get('attachment'):
                deposit_request.attachment = request.FILES['attachment']
                deposit_request.save()
            
            # Send notification to admin
            try:
                from ..models import Notification
                admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
                for admin in admin_users:
                    Notification.send(
                        user=admin,
                        title="💰 New Deposit Request",
                        message=f"{shareholder.name} requested deposit of Rs. {amount:,.2f}. Method: {deposit_request.get_payment_method_display()}",
                        notification_type='payment',
                        category='payments',
                        link=f"/shareholders/deposit-requests/"
                    )
            except Exception:
                pass
            
            messages.success(
                request, 
                f'✅ Deposit request of Rs. {amount:,.2f} submitted for approval!'
            )
            return redirect('shareholder_portal_deposit_history')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {safe_error(e)}')
            return redirect('shareholder_portal_deposit_request')
    
    # GET request - show form
    context = {
        'company_name': company.name if company else 'ERP System',
        'shareholder': shareholder,
        'payment_methods': ShareholderDepositRequest.PAYMENT_METHODS,
        'current_balance': ShareholderCashBalance.get_balance(shareholder),
        'pending_requests': ShareholderDepositRequest.objects.filter(shareholder=shareholder, status='pending').count(),
        # ✅ NEW: Deposit details from company
        'jazzcash_number': company.jazzcash_number if company else '',
        'easypaisa_number': company.easypaisa_number if company else '',
        'bank_account_title': company.bank_account_title if company else '',
        'bank_account_number': company.bank_account_number if company else '',
        'bank_name': company.bank_name if company else '',
        'deposit_instructions': company.deposit_instructions if company else '',
        'company_phone': company.contact_number if company else '',
        'company_email': company.email if company else '',
    }
    return render(request, 'shareholders/portal/deposit_request.html', context)


@login_required
def shareholder_portal_deposit_history(request):
    """Shareholder portal - View deposit request history"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    deposit_requests = ShareholderDepositRequest.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        deposit_requests = deposit_requests.filter(status=status)
    
    # Statistics
    total_requests = deposit_requests.count()
    pending_count = deposit_requests.filter(status='pending').count()
    approved_count = deposit_requests.filter(status='approved').count()
    rejected_count = deposit_requests.filter(status='rejected').count()
    total_amount = deposit_requests.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(deposit_requests, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'page_obj': page_obj,
        'deposit_requests': page_obj,
        'status': status,
        'status_choices': ShareholderDepositRequest.STATUS_CHOICES,
        'current_balance': ShareholderCashBalance.get_balance(shareholder),
        'total_requests': total_requests,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'total_amount': total_amount,
    }
    return render(request, 'shareholders/portal/deposit_history.html', context)


@login_required
def shareholder_portal_withdrawal_request(request):
    """Shareholder portal - Request withdrawal (needs admin approval)"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied! Only shareholders can make withdrawal requests.')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    current_balance = ShareholderCashBalance.get_balance(shareholder)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'bank_transfer')
            account_details = request.POST.get('account_details', '')
            reference_no = request.POST.get('reference_no', '')
            description = request.POST.get('description', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_portal_withdrawal_request')
            
            if amount > current_balance:
                messages.error(
                    request, 
                    f'Insufficient balance! Available: Rs. {current_balance:,.2f}, Requested: Rs. {amount:,.2f}'
                )
                return redirect('shareholder_portal_withdrawal_request')
            
            if amount > 5000000:  # Max Rs. 50 Lakh per request
                messages.error(request, 'Amount exceeds maximum limit (Rs. 5,000,000)!')
                return redirect('shareholder_portal_withdrawal_request')
            
            # Create withdrawal request
            withdrawal_request = ShareholderWithdrawalRequest.objects.create(
                shareholder=shareholder,
                amount=amount,
                payment_method=payment_method,
                account_details=account_details,
                reference_no=reference_no,
                description=description,
                created_by=request.user,
                status='pending'
            )
            
            # Save attachment if uploaded
            if request.FILES.get('attachment'):
                withdrawal_request.attachment = request.FILES['attachment']
                withdrawal_request.save()
            
            # Send notification to admin
            try:
                from ..models import Notification
                admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
                for admin in admin_users:
                    Notification.send(
                        user=admin,
                        title="💸 New Withdrawal Request",
                        message=f"{shareholder.name} requested withdrawal of Rs. {amount:,.2f}. Method: {withdrawal_request.get_payment_method_display()}",
                        notification_type='payment',
                        category='payments',
                        link=f"/shareholders/withdrawal-requests/"
                    )
            except Exception:
                pass
            
            messages.success(
                request, 
                f'✅ Withdrawal request of Rs. {amount:,.2f} submitted for approval! '
                f'You will be notified once approved. Request #: {withdrawal_request.request_no}'
            )
            return redirect('shareholder_portal_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {safe_error(e)}')
            return redirect('shareholder_portal_withdrawal_request')
    
    # GET request - show form
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'payment_methods': ShareholderWithdrawalRequest.PAYMENT_METHODS,
        'current_balance': current_balance,
        'pending_requests': ShareholderWithdrawalRequest.objects.filter(shareholder=shareholder, status='pending').count(),
        'min_amount': 100,
        'max_amount': min(current_balance, Decimal('5000000')),
    }
    return render(request, 'shareholders/portal/withdrawal_request.html', context)


@login_required
def shareholder_portal_withdrawal_history(request):
    """Shareholder portal - View withdrawal request history"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    withdrawal_requests = ShareholderWithdrawalRequest.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        withdrawal_requests = withdrawal_requests.filter(status=status)
    
    # Statistics
    total_requests = withdrawal_requests.count()
    pending_count = withdrawal_requests.filter(status='pending').count()
    approved_count = withdrawal_requests.filter(status='approved').count()
    rejected_count = withdrawal_requests.filter(status='rejected').count()
    total_amount = withdrawal_requests.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(withdrawal_requests, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'page_obj': page_obj,
        'withdrawal_requests': page_obj,
        'status': status,
        'status_choices': ShareholderWithdrawalRequest.STATUS_CHOICES,
        'current_balance': ShareholderCashBalance.get_balance(shareholder),
        'total_requests': total_requests,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'total_amount': total_amount,
    }
    return render(request, 'shareholders/portal/withdrawal_history.html', context)


@login_required
def shareholder_terms(request):
    """Show Terms & Conditions to shareholder"""
    
    # ========================================== #
    # 1. Check: Is user a shareholder?           #
    # ========================================== #
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # ========================================== #
    # 2. Check: Already accepted?                #
    # ========================================== #
    if hasattr(shareholder, 'terms_acceptance'):
        messages.info(request, '✅ You have already accepted the terms.')
        return redirect('shareholder_portal_dashboard')
    
    # ========================================== #
    # 3. Get active terms OR use fallback        #
    # ========================================== #
    terms = TermsAndConditions.objects.filter(is_active=True).first()
    
    # ✅ FALLBACK: Agar terms DB mein nahi hain toh placeholder use karo
    if not terms:
        terms = TermsAndConditions(
            version='1.0',
            title='Shareholder Terms & Conditions',
            content='''1. All information provided must be accurate and complete.
2. Company reserves the right to verify all documents.
3. Investment is subject to company policies and approval.
4. Shareholder must keep login credentials confidential.
5. Any misuse of the portal will result in account suspension.
6. Company is not liable for market-related losses.
7. Shareholder must comply with all applicable laws.
8. Disputes will be resolved through arbitration.
9. Company may modify terms with prior notice.
10. Continued use implies acceptance of updated terms.''',
            urdu_content='''1. تمام فراہم کردہ معلومات درست اور مکمل ہونی چاہئیں۔
2. کمپنی تمام دستاویزات کی تصدیق کا حق محفوظ رکھتی ہے۔
3. سرمایہ کاری کمپنی کی پالیسیوں اور منظوری کے تابع ہے۔
4. شیئر ہولڈر کو لاگ ان کی معلومات خفیہ رکھنی ہوں گی۔
5. پورٹل کا غلط استعمال اکاؤنٹ معطلی کا باعث بنے گا۔
6. مارکیٹ کے نقصانات کے لیے کمپنی ذمہ دار نہیں ہوگی۔
7. شیئر ہولڈر تمام قابل اطلاق قوانین کی پاسداری کرے گا۔
8. تنازعات ثالثی کے ذریعے حل کیے جائیں گے۔
9. کمپنی پیشگی اطلاع کے ساتھ شرائط تبدیل کر سکتی ہے۔
10. مسلسل استعمال کا مطلب ہے کہ آپ اپ ڈیٹڈ شرائط سے متفق ہیں۔''',
            is_active=True,
            effective_date=date.today(),
        )
    
    # ========================================== #
    # 4. POST: Handle acceptance                 #
    # ========================================== #
    if request.method == 'POST':
        if request.POST.get('agree'):
            ShareholderTermsAcceptance.objects.create(
                shareholder=shareholder,
                terms_version=terms.version,
                accepted_at=now(),
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            messages.success(request, '✅ Terms accepted! Welcome to the portal.')
            return redirect('shareholder_portal_dashboard')
        else:
            messages.error(request, '❌ Please accept the terms to continue.')
            return redirect('shareholder_terms')
    
    # ========================================== #
    # 5. Render                                  #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'terms': terms,
        'shareholder': shareholder,
    }
    return render(request, 'terms/terms.html', context)


@login_required
def shareholder_support(request):
    """Shareholder support ticket system"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    tickets = shareholder.support_tickets.all().order_by('-created_at')
    
    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        priority = request.POST.get('priority', 'medium')
        
        if not subject or not message:
            messages.error(request, 'Subject and message are required!')
            return redirect('shareholder_support')
        
        ticket = ShareholderSupportTicket.objects.create(
            shareholder=shareholder,
            subject=subject,
            message=message,
            priority=priority,
            created_by=request.user
        )
        
        if request.FILES.get('attachment'):
            ticket.attachment = request.FILES['attachment']
            ticket.save()
        
        # Notify admin
        from ..models import Notification
        admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(is_staff=True)
        for admin in admin_users:
            Notification.send(
                user=admin,
                title="🎫 New Support Ticket",
                message=f"Ticket #{ticket.ticket_no} from {shareholder.name}: {subject[:50]}",
                notification_type='info',
                category='system',
                link=f"/admin/support/ticket/{ticket.id}/"
            )
        
        messages.success(request, f'✅ Ticket #{ticket.ticket_no} created! We will respond soon.')
        return redirect('shareholder_support')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'tickets': tickets,
        'priority_choices': ShareholderSupportTicket.PRIORITY_CHOICES,
    }
    return render(request, 'shareholders/portal/support.html', context)
