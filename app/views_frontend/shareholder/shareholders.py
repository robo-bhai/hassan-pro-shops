"""Frontend views: shareholder/shareholders (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F
from decimal import Decimal
from django.utils.timezone import now
from datetime import date
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ...models import (
    CashBalance,
    Shareholder,
    Share,
    SharePrice,
    DividendPayment,
    ShareTransfer,
    ShareholderMeeting,
    ShareholderCashBalance,
    CompanyInfo,
)
from django.contrib.auth.models import User
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


@login_required
@perm_required('view_shareholders')
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
@perm_required('view_shareholders')
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
@perm_required('view_shareholders')
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
@perm_required('manage_shareholders')
def shareholder_create(request):
    """Create new shareholder with cash balance and login access"""
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can create shareholders.')
        return redirect('dashboard')  # ✅ This must be returned
    
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
                        
                        # ✅ Set the password from the form
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
    # ✅ IMPORTANT: GET REQUEST - THIS MUST BE RETURNED
    # ============================================
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder_types': Shareholder.SHAREHOLDER_TYPES,
        'status_choices': Shareholder.STATUS_CHOICES,
        'main_balance': CashBalance.get_balance(),
    }
    return render(request, 'shareholders/create.html', context)  # ✅ THIS MUST BE THERE


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
@perm_required('manage_shareholders')
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
@perm_required('view_shareholders')
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
@perm_required('view_shareholders')
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
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
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
@perm_required('view_shareholders')
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
