"""Frontend views: shareholder cash."""
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper
from ..models import *
import json
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Value, DecimalField, IntegerField
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from django.db import transaction
from ..models import CashBalance, Shareholder, SharePrice, DividendPayment, ShareTransfer, ShareholderCashBalance, ShareholderCashTransaction, CompanyInfo, Purchase, SystemSetting
from django.contrib.auth.models import User
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from openpyxl.utils import get_column_letter
import logging

logger = logging.getLogger(__name__)


@login_required
def shareholder_balance_dashboard(request):
    """
    Shareholder Balance Dashboard - FULLY OPTIMIZED (400+ queries → 3 queries)
    """
    from django.db.models import Sum, Q, F, Value, DecimalField, IntegerField, ExpressionWrapper
    from django.db.models.functions import Coalesce
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    # ✅ STEP 1: Bulk create missing cash_balance records (ek query)
    active_sids = list(Shareholder.objects.filter(status='active').values_list('id', flat=True))
    
    existing_sids = set(
        ShareholderCashBalance.objects.filter(
            shareholder_id__in=active_sids
        ).values_list('shareholder_id', flat=True)
    )
    
    missing = [
        ShareholderCashBalance(shareholder_id=sid, balance=Decimal('0.00'))
        for sid in active_sids
        if sid not in existing_sids
    ]
    if missing:
        ShareholderCashBalance.objects.bulk_create(missing, ignore_conflicts=True)
    
    # ✅ STEP 2: Ek query mein SAARA data fetch karo
    shareholders = Shareholder.objects.filter(status='active').annotate(
        annotated_balance=Coalesce(
            Sum('cash_balance__balance', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        ),
        annotated_shares=Coalesce(
            Sum('shares__quantity'),
            Value(0),
            output_field=IntegerField()
        ),
        annotated_investment=Coalesce(
            Sum(
                ExpressionWrapper(
                    F('shares__quantity') * F('shares__purchase_price'),
                    output_field=DecimalField(max_digits=20, decimal_places=2)
                )
            ),
            Value(Decimal('0.00'))
        ),
        annotated_dividends=Coalesce(
            Sum('dividend_payments__amount', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        ),
        annotated_paid_dividends=Coalesce(
            Sum(
                'dividend_payments__amount',
                filter=Q(dividend_payments__status='paid'),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        annotated_unpaid_dividends=Coalesce(
            Sum(
                'dividend_payments__amount',
                filter=Q(dividend_payments__status='pending'),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
    )
    
    # ✅ STEP 3: Share price ek query
    latest_price = SharePrice.objects.filter(is_active=True).first()
    if latest_price:
        current_price = latest_price.price
    else:
        current_price = Decimal('100.00')
        latest_price = SharePrice.objects.create(
            price=current_price,
            date=now().date(),
            is_active=True,
            notes='Default share price (auto-created)'
        )
    
    # ✅ STEP 4: Python loop mein sirf calculation (no queries!)
    shareholder_balances = []
    total_balance = Decimal('0.00')
    total_balance_without_share = Decimal('0.00')
    total_dividends = Decimal('0.00')
    total_paid_dividends = Decimal('0.00')
    total_unpaid_dividends = Decimal('0.00')
    total_shareholders = 0
    zero_balance_count = 0
    positive_balance_count = 0
    total_shares_all = 0
    total_investment_all = Decimal('0.00')
    
    for shareholder in shareholders:
        balance = shareholder.annotated_balance
        shares = shareholder.annotated_shares
        investment = shareholder.annotated_investment
        dividends = shareholder.annotated_dividends
        paid_dividends = shareholder.annotated_paid_dividends
        unpaid_dividends = shareholder.annotated_unpaid_dividends
        
        dividend_percent = (
            (dividends / investment) * 100
            if investment > 0
            else Decimal('0.00')
        )
        balance_without_share = balance - investment
        
        shareholder_balances.append({
            'shareholder': shareholder,
            'balance': balance,
            'balance_without_share': balance_without_share,
            'dividends': dividends,
            'paid_dividends': paid_dividends,
            'unpaid_dividends': unpaid_dividends,
            'dividend_percent': dividend_percent,
            'shares': shares,
            'investment': investment,
        })
        
        total_balance += balance
        total_balance_without_share += balance_without_share
        total_dividends += dividends
        total_paid_dividends += paid_dividends
        total_unpaid_dividends += unpaid_dividends
        total_shareholders += 1
        total_shares_all += shares
        total_investment_all += investment
        
        if balance == 0:
            zero_balance_count += 1
        elif balance > 0:
            positive_balance_count += 1
    
    total_dividend_percent = (
        (total_dividends / total_investment_all) * 100
        if total_investment_all > 0
        else Decimal('0.00')
    )
    
    shareholder_balances.sort(key=lambda x: x['balance'], reverse=True)
    
    # ✅ STEP 5: Recent transactions (1 query)
    recent_transactions = ShareholderCashTransaction.objects.select_related(
        'shareholder', 'created_by'
    ).order_by('-created_at')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder_balances': shareholder_balances,
        'total_balance': total_balance,
        'total_balance_without_share': total_balance_without_share,
        'total_dividends': total_dividends,
        'total_paid_dividends': total_paid_dividends,
        'total_unpaid_dividends': total_unpaid_dividends,
        'total_dividend_percent': total_dividend_percent,
        'total_shareholders': total_shareholders,
        'zero_balance_count': zero_balance_count,
        'positive_balance_count': positive_balance_count,
        'latest_price': latest_price,
        'current_price': current_price,
        'recent_transactions': recent_transactions,
        'total_shares': total_shares_all,
        'total_investment': total_investment_all,
    }
    return render(request, 'shareholders/balance_dashboard.html', context)


@login_required
def shareholder_balance_detail(request, pk):
    """
    Detail view of a shareholder's cash balance with complete transaction history
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can view shareholder details.')
        return redirect('dashboard')
    
    balance = ShareholderCashBalance.get_balance(shareholder)
    
    # Get transactions with pagination
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).select_related('created_by', 'share', 'dividend_payment', 'share_transfer')
    
    # Apply filters
    transaction_type = request.GET.get('type', '')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    date_from = request.GET.get('date_from', '')
    if date_from:
        transactions = transactions.filter(created_at__date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if date_to:
        transactions = transactions.filter(created_at__date__lte=date_to)
    
    # Pagination
    paginator = Paginator(transactions, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Get share holdings
    shares = shareholder.shares.all()
    total_shares = shareholder.total_shares()
    total_investment = shareholder.total_investment()
    total_dividends = shareholder.total_dividends()
    
    # Calculate current value
    latest_price = SharePrice.objects.filter(is_active=True).first()
    current_value = shareholder.current_value(latest_price.price if latest_price else None)
    
    # Calculate profit/loss
    profit_loss = current_value - total_investment
    profit_loss_percent = (profit_loss / total_investment * 100) if total_investment > 0 else 0
    
    # Get pending dividend payments
    pending_dividends = DividendPayment.objects.filter(
        shareholder=shareholder,
        status='pending'
    ).select_related('dividend')
    
    # Get pending transfers (where this shareholder is involved)
    pending_transfers_out = ShareTransfer.objects.filter(
        from_shareholder=shareholder,
        status='pending'
    )
    pending_transfers_in = ShareTransfer.objects.filter(
        to_shareholder=shareholder,
        status='pending'
    )
    
    # Transaction summary by type
    type_summary = {}
    for trans_type, label in ShareholderCashTransaction.TRANSACTION_TYPES:
        count = ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            transaction_type=trans_type
        ).count()
        if count > 0:
            type_summary[trans_type] = {
                'label': label,
                'count': count,
                'total_amount': ShareholderCashTransaction.objects.filter(
                    shareholder=shareholder,
                    transaction_type=trans_type
                ).aggregate(total=Sum('amount'))['total'] or 0
            }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'balance': balance,
        'page_obj': page_obj,
        'transactions': page_obj,
        'shares': shares,
        'total_shares': total_shares,
        'total_investment': total_investment,
        'total_dividends': total_dividends,
        'current_value': current_value,
        'profit_loss': profit_loss,
        'profit_loss_percent': profit_loss_percent,
        'latest_price': latest_price,
        'pending_dividends': pending_dividends,
        'pending_transfers_out': pending_transfers_out,
        'pending_transfers_in': pending_transfers_in,
        'type_summary': type_summary,
        'selected_type': transaction_type,
        'date_from': date_from,
        'date_to': date_to,
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/balance_detail.html', context)


@login_required
def shareholder_deposit(request, pk):
    """
    Deposit money into shareholder's cash balance ONLY
    No impact on main cash balance
    Shareholder's internal account is being credited
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can deposit money.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            description = request.POST.get('description', 'Internal deposit')
            reference_no = request.POST.get('reference_no', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_deposit', pk=pk)
            
            with transaction.atomic():
                # ============================================
                # STEP 1: ONLY Shareholder balance mein ADD karo
                # ============================================
                new_shareholder_balance = ShareholderCashBalance.deposit(
                    shareholder=shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Internal deposit - {description}"
                )
                
                # ============================================
                # STEP 2: Main Cash ko TOUCH MAT KARO ❌
                # ============================================
                # CashBalance.update_balance(...) - YEH HATANA HAI
                
                messages.success(
                    request, 
                    f'✅ Rs. {amount:,.2f} deposited to {shareholder.name}\'s balance! '
                    f'New balance: Rs. {new_shareholder_balance:,.2f}'
                )
                return redirect('shareholder_balance_detail', pk=shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_deposit', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_deposit', pk=pk)
    
    # GET request - show form
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'current_balance': ShareholderCashBalance.get_balance(shareholder),
    }
    return render(request, 'shareholders/deposit.html', context)


@login_required
def shareholder_withdraw(request, pk):
    """
    Withdraw money from shareholder's cash balance ONLY
    No impact on main cash balance
    Shareholder's internal account is being debited
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can withdraw money.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            description = request.POST.get('description', 'Internal withdrawal')
            reference_no = request.POST.get('reference_no', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_withdraw', pk=pk)
            
            with transaction.atomic():
                # ============================================
                # STEP 1: ONLY Shareholder balance se MINUS karo
                # ============================================
                new_shareholder_balance = ShareholderCashBalance.withdraw(
                    shareholder=shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Internal withdrawal - {description}"
                )
                
                # ============================================
                # STEP 2: Main Cash ko TOUCH MAT KARO ❌
                # ============================================
                # CashBalance.update_balance(...) - YEH HATANA HAI
                
                messages.success(
                    request, 
                    f'✅ Rs. {amount:,.2f} withdrawn from {shareholder.name}\'s balance! '
                    f'New balance: Rs. {new_shareholder_balance:,.2f}'
                )
                return redirect('shareholder_balance_detail', pk=shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_withdraw', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_withdraw', pk=pk)
    
    # GET request - show form
    current_balance = ShareholderCashBalance.get_balance(shareholder)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'current_balance': current_balance,
    }
    return render(request, 'shareholders/withdraw.html', context)


@login_required
def shareholder_transfer_balance(request, pk):
    """
    Transfer balance from one shareholder to another
    No main cash impact - just between shareholders
    """
    from_shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only administrators can transfer balances.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            to_shareholder_id = request.POST.get('to_shareholder')
            amount = Decimal(request.POST.get('amount', 0))
            description = request.POST.get('description', 'Balance transfer')
            reference_no = request.POST.get('reference_no', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_transfer_balance', pk=pk)
            
            if not to_shareholder_id:
                messages.error(request, 'Please select a recipient!')
                return redirect('shareholder_transfer_balance', pk=pk)
            
            to_shareholder = get_object_or_404(Shareholder, pk=to_shareholder_id)
            
            if to_shareholder == from_shareholder:
                messages.error(request, 'Cannot transfer to yourself!')
                return redirect('shareholder_transfer_balance', pk=pk)
            
            with transaction.atomic():
                # Withdraw from sender
                new_from_balance = ShareholderCashBalance.withdraw(
                    shareholder=from_shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Transfer to {to_shareholder.name} - {description}"
                )
                
                # Deposit to receiver
                new_to_balance = ShareholderCashBalance.deposit(
                    shareholder=to_shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Transfer from {from_shareholder.name} - {description}"
                )
                
                messages.success(
                    request, 
                    f'✅ Rs. {amount:,.2f} transferred from {from_shareholder.name} to {to_shareholder.name}!'
                )
                return redirect('shareholder_balance_detail', pk=from_shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_transfer_balance', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_transfer_balance', pk=pk)
    
    # GET request - show form
    shareholders = Shareholder.objects.filter(status='active').exclude(pk=pk)
    current_balance = ShareholderCashBalance.get_balance(from_shareholder)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_shareholder': from_shareholder,
        'current_balance': current_balance,
        'shareholders': shareholders,
    }
    return render(request, 'shareholders/transfer_balance.html', context)


@login_required
def shareholder_adjust_balance(request, pk):
    """
    Adjust shareholder balance (add or remove without main cash impact)
    For corrections and adjustments - SUPERUSER ONLY
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission - only superuser
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superusers can adjust balances.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            adjustment_type = request.POST.get('adjustment_type', 'add')
            description = request.POST.get('description', 'Balance adjustment')
            reference_no = request.POST.get('reference_no', '')
            
            # Validation
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_adjust_balance', pk=pk)
            
            with transaction.atomic():
                if adjustment_type == 'add':
                    new_balance = ShareholderCashBalance.deposit(
                        shareholder=shareholder,
                        amount=amount,
                        user=request.user,
                        description=f"ADJUSTMENT (Add): {description}"
                    )
                    messages.success(
                        request, 
                        f'✅ Rs. {amount:,.2f} added to {shareholder.name}\'s balance. '
                        f'New balance: Rs. {new_balance:,.2f}'
                    )
                else:
                    new_balance = ShareholderCashBalance.withdraw(
                        shareholder=shareholder,
                        amount=amount,
                        user=request.user,
                        description=f"ADJUSTMENT (Remove): {description}"
                    )
                    messages.success(
                        request, 
                        f'✅ Rs. {amount:,.2f} removed from {shareholder.name}\'s balance. '
                        f'New balance: Rs. {new_balance:,.2f}'
                    )
                
                return redirect('shareholder_balance_detail', pk=shareholder.pk)
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('shareholder_adjust_balance', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_adjust_balance', pk=pk)
    
    # GET request - show form
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'current_balance': ShareholderCashBalance.get_balance(shareholder),
    }
    return render(request, 'shareholders/adjust_balance.html', context)


@login_required
def shareholder_balance_api(request):
    """
    AJAX API: Get shareholder balance for dropdowns and live updates
    """
    shareholder_id = request.GET.get('shareholder_id')
    
    if not shareholder_id:
        return JsonResponse({
            'success': False,
            'message': 'Shareholder ID required'
        })
    
    try:
        shareholder = Shareholder.objects.get(id=shareholder_id, status='active')
        balance = ShareholderCashBalance.get_balance(shareholder)
        
        return JsonResponse({
            'success': True,
            'shareholder_id': shareholder.id,
            'shareholder_name': shareholder.name,
            'balance': float(balance),
            'formatted_balance': f"Rs. {balance:,.2f}",
            'total_shares': shareholder.total_shares(),
            'total_investment': float(shareholder.total_investment()),
        })
    except Shareholder.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Shareholder not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def shareholder_transactions_export(request, pk):
    """
    Export shareholder transactions to Excel
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from django.http import HttpResponse
    
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')
    
    # Apply filters
    transaction_type = request.GET.get('type', '')
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    date_from = request.GET.get('date_from', '')
    if date_from:
        transactions = transactions.filter(created_at__date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if date_to:
        transactions = transactions.filter(created_at__date__lte=date_to)
    
    # Create Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ['Date', 'Type', 'Amount', 'Balance After', 'Description', 'Reference No', 'Created By']
    ws.append(headers)
    
    # Style headers
    header_fill = PatternFill(start_color="1a1a2e", end_color="1a1a2e", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    
    # Add data
    total_deposits = Decimal('0.00')
    total_withdrawals = Decimal('0.00')
    
    for trans in transactions:
        type_display = trans.get_transaction_type_display()
        amount = trans.amount
        if trans.is_withdraw:
            amount = -amount
            total_withdrawals += abs(trans.amount)
        else:
            total_deposits += trans.amount
        
        ws.append([
            trans.created_at.strftime('%d-%m-%Y %H:%M'),
            type_display,
            float(amount),
            float(trans.balance_after),
            trans.description or '',
            trans.reference_no or '',
            trans.created_by.username if trans.created_by else 'System'
        ])
    
    # Add summary
    summary_row = ws.max_row + 2
    ws.cell(row=summary_row, column=1, value="SUMMARY")
    ws.cell(row=summary_row + 1, column=1, value="Total Deposits:")
    ws.cell(row=summary_row + 1, column=2, value=float(total_deposits))
    ws.cell(row=summary_row + 2, column=1, value="Total Withdrawals:")
    ws.cell(row=summary_row + 2, column=2, value=float(total_withdrawals))
    ws.cell(row=summary_row + 3, column=1, value="Net Change:")
    ws.cell(row=summary_row + 3, column=2, value=float(total_deposits - total_withdrawals))
    ws.cell(row=summary_row + 4, column=1, value="Current Balance:")
    ws.cell(row=summary_row + 4, column=2, value=float(ShareholderCashBalance.get_balance(shareholder)))
    
    # Adjust column widths
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 40)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"shareholder_{shareholder.shareholder_code}_transactions.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def shareholder_balance_report_pdf(request, pk):
    """
    Generate PDF report for shareholder balance
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    from django.http import HttpResponse
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP System"
    company_address = company.address if company else ""
    company_phone = company.contact_number if company else ""
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    if company_address:
        story.append(Paragraph(company_address, styles['Normal']))
    story.append(Paragraph(f"Shareholder Balance Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Shareholder Info
    balance = ShareholderCashBalance.get_balance(shareholder)
    
    info_data = [
        ['Name:', shareholder.name],
        ['Code:', shareholder.shareholder_code],
        ['Type:', shareholder.get_shareholder_type_display()],
        ['Current Balance:', f"Rs. {balance:,.2f}"],
        ['Total Shares:', f"{shareholder.total_shares():,}"],
        ['Total Investment:', f"Rs. {shareholder.total_investment():,.2f}"],
        ['Total Dividends:', f"Rs. {shareholder.total_dividends():,.2f}"],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e3eb')),
        ('BACKGROUND', (0, 3), (1, 3), colors.HexColor('#fff3cd')),
        ('FONTNAME', (0, 3), (1, 3), 'Helvetica-Bold'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Recent Transactions
    story.append(Paragraph("<b>Recent Transactions</b>", styles['Heading2']))
    
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')[:20]
    
    trans_data = [['Date', 'Type', 'Amount', 'Balance After', 'Description']]
    
    for trans in transactions:
        amount_str = f"+Rs. {trans.amount:,.2f}" if trans.is_deposit else f"-Rs. {trans.amount:,.2f}"
        trans_data.append([
            trans.created_at.strftime('%d-%m-%Y %H:%M'),
            trans.get_transaction_type_display()[:15],
            amount_str,
            f"Rs. {trans.balance_after:,.2f}",
            (trans.description or '')[:30]
        ])
    
    trans_table = Table(trans_data, repeatRows=1, colWidths=[1.2*inch, 1.2*inch, 1*inch, 1.2*inch, 1.8*inch])
    trans_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f6fa')]),
    ]))
    story.append(trans_table)
    
    # Footer
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    story.append(Paragraph("This is a computer generated report.", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Shareholder_Balance_{shareholder.shareholder_code}.pdf"'
    return response


@login_required
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
def shareholder_deposit_request_notification(request, pk):
    """Resend notification for a deposit request"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    deposit_request = get_object_or_404(ShareholderDepositRequest, pk=pk)
    
    # Send notification to admin
    try:
        from ..models import Notification
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
def shareholder_withdrawal_request_notification(request, pk):
    """Resend notification for a withdrawal request"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    withdrawal_request = get_object_or_404(ShareholderWithdrawalRequest, pk=pk)
    
    try:
        from ..models import Notification
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


@login_required
def process_purchase_deduction(request, pk):
    """
    Process shareholder deduction for a specific purchase
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can process deductions.')
        return redirect('purchase_detail', pk=purchase.pk)
    
    # Check if already processed
    if purchase.shareholder_deduction_done:
        messages.warning(request, '⚠️ Deduction already processed for this purchase!')
        return redirect('purchase_deduction_details', pk=purchase.pk)
    
    # Get deduction type
    deduction_type = request.GET.get('type', 'proportional')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                success, result = purchase.process_shareholder_deduction(request.user)
                
                if success:
                    messages.success(
                        request, 
                        f'✅ Deduction processed successfully!\n'
                        f'Total: Rs. {purchase.total_amount():,.2f}\n'
                        f'Deducted from {len(result.get("deducted_from", []))} shareholders'
                    )
                else:
                    messages.error(request, f'❌ Deduction failed: {result}')
                
                return redirect('purchase_deduction_details', pk=purchase.pk)
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('purchase_detail', pk=purchase.pk)
    
    # GET request - show confirmation
    shareholders = Shareholder.objects.filter(status='active')
    total_shareholders = shareholders.count()
    
    # Calculate per shareholder based on type
    total_amount = purchase.total_amount()
    if deduction_type == 'equal':
        per_shareholder = total_amount / total_shareholders if total_shareholders > 0 else 0
    else:  # proportional
        total_balance = 0
        balances = []
        for sh in shareholders:
            balance = sh.get_balance()
            balances.append(balance)
            total_balance += balance
        # Show preview
        preview_data = []
        for i, sh in enumerate(shareholders):
            if deduction_type == 'equal':
                amount = per_shareholder
            else:
                proportion = balances[i] / total_balance if total_balance > 0 else 0
                amount = total_amount * proportion
            preview_data.append({
                'name': sh.name,
                'balance': balances[i],
                'deduction': amount,
                'percentage': (amount / total_amount * 100) if total_amount > 0 else 0
            })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'purchase': purchase,
        'total_shareholders': total_shareholders,
        'total_amount': total_amount,
        'per_shareholder': per_shareholder if deduction_type == 'equal' else None,
        'deduction_type': deduction_type,
        'preview_data': preview_data if deduction_type == 'proportional' else None,
        'is_enabled': SystemSetting.get_bool('enable_shareholder_purchase_deduction', True),
    }
    return render(request, 'shareholders/deduction/process.html', context)


@login_required
def purchase_deduction_details(request, pk):
    """
    View deduction details for a purchase
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    
    if not purchase.shareholder_deduction_done:
        messages.warning(request, '⚠️ No deduction processed for this purchase yet!')
        return redirect('process_purchase_deduction', pk=purchase.pk)
    
    summary = purchase.get_deduction_summary()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'purchase': purchase,
        'summary': summary,
        'deducted_from': summary.get('deducted_from', []) if summary else [],
        'failed': summary.get('failed', []) if summary else [],
        'skipped': summary.get('skipped', []) if summary else [],
        'total_shareholders': summary.get('total_shareholders', 0) if summary else 0,
        'total_amount': summary.get('total_amount', 0) if summary else 0,
        'deduction_type': purchase.shareholder_deduction_type,
        'deduction_date': purchase.shareholder_deduction_date,
    }
    return render(request, 'shareholders/deduction/details.html', context)


@login_required
def toggle_shareholder_deduction(request):
    """
    Toggle the shareholder deduction feature on/off
    """
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can toggle this feature.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        new_value = SystemSetting.toggle('enable_shareholder_purchase_deduction', request.user)
        status = 'enabled' if new_value else 'disabled'
        messages.success(request, f'✅ Shareholder purchase deduction {status}!')
        return redirect('system_settings')
    
    return redirect('system_settings')


@login_required
def change_deduction_type(request):
    """
    Change deduction type between equal and proportional
    """
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method == 'POST':
        try:
            deduction_type = request.POST.get('deduction_type', 'proportional')
            
            if deduction_type not in ['equal', 'proportional']:
                return JsonResponse({'success': False, 'message': 'Invalid deduction type!'})
            
            SystemSetting.set_value('shareholder_deduction_type', deduction_type, request.user)
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Deduction type changed to: {deduction_type}',
                'deduction_type': deduction_type
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def shareholder_deduction_report(request):
    """
    Complete report of all shareholder deductions
    """
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get all purchases with deductions
    purchases = Purchase.objects.filter(
        shareholder_deduction_done=True
    ).order_by('-shareholder_deduction_date')
    
    # Filters
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    shareholder_id = request.GET.get('shareholder', '')
    deduction_type = request.GET.get('type', '')
    
    if from_date:
        purchases = purchases.filter(shareholder_deduction_date__date__gte=from_date)
    if to_date:
        purchases = purchases.filter(shareholder_deduction_date__date__lte=to_date)
    if deduction_type:
        purchases = purchases.filter(shareholder_deduction_type=deduction_type)
    
    # Calculate totals
    total_deductions = purchases.count()
    total_amount = Decimal('0.00')
    total_shareholders_affected = 0
    
    for p in purchases:
        data = p.shareholder_deduction_data
        if data:
            total_amount += Decimal(str(data.get('total_amount', 0)))
            total_shareholders_affected += len(data.get('deducted_from', []))
    
    # Shareholder-wise summary
    shareholder_summary = {}
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                name = item.get('name', 'Unknown')
                code = item.get('code', '')
                if name not in shareholder_summary:
                    shareholder_summary[name] = {
                        'name': name,
                        'code': code,
                        'total_deductions': 0,
                        'total_amount': Decimal('0.00'),
                        'purchases': []
                    }
                shareholder_summary[name]['total_deductions'] += 1
                shareholder_summary[name]['total_amount'] += Decimal(str(item.get('deducted', 0)))
                shareholder_summary[name]['purchases'].append({
                    'bill_no': purchase.bill_no,
                    'amount': Decimal(str(item.get('deducted', 0))),
                    'date': purchase.shareholder_deduction_date
                })
    
    # Sort by total amount
    shareholder_summary = sorted(
        shareholder_summary.values(),
        key=lambda x: x['total_amount'],
        reverse=True
    )
    
    # Apply shareholder filter
    if shareholder_id:
        try:
            shareholder = Shareholder.objects.get(id=shareholder_id)
            shareholder_summary = [s for s in shareholder_summary if s['name'] == shareholder.name]
        except Shareholder.DoesNotExist:
            pass
    
    # Pagination
    paginator = Paginator(purchases, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # System settings
    is_enabled = SystemSetting.get_bool('enable_shareholder_purchase_deduction', True)
    current_type = SystemSetting.get_value('shareholder_deduction_type', 'proportional')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'purchases': page_obj,
        'total_deductions': total_deductions,
        'total_amount': total_amount,
        'total_shareholders_affected': total_shareholders_affected,
        'shareholder_summary': shareholder_summary,
        'is_enabled': is_enabled,
        'current_type': current_type,
        'shareholders': Shareholder.objects.filter(status='active'),
        'from_date': from_date,
        'to_date': to_date,
        'shareholder_id': shareholder_id,
        'deduction_type': deduction_type,
        'deduction_types': [
            ('equal', 'Equal Division'),
            ('proportional', 'Proportional by Balance'),
        ],
        'today': date.today(),
    }
    return render(request, 'shareholders/deduction/report.html', context)


@login_required
def shareholder_deduction_report_pdf(request):
    """
    Generate PDF report for shareholder deductions
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get data
    purchases = Purchase.objects.filter(
        shareholder_deduction_done=True
    ).order_by('-shareholder_deduction_date')[:100]
    
    total_amount = Decimal('0.00')
    for p in purchases:
        data = p.shareholder_deduction_data
        if data:
            total_amount += Decimal(str(data.get('total_amount', 0)))
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Shareholder Deduction Report", title_style))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Summary
    summary_data = [
        ['Total Deductions', str(purchases.count())],
        ['Total Amount', f"Rs. {total_amount:,.2f}"],
        ['Deduction Type', SystemSetting.get_value('shareholder_deduction_type', 'proportional')],
    ]
    
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Deductions Table
    data = [['Bill No', 'Vendor', 'Total', 'Shareholders', 'Date']]
    for purchase in purchases:
        data.append([
            purchase.bill_no or 'N/A',
            purchase.vendor.name[:20],
            f"Rs. {purchase.total_amount():,.2f}",
            str(len(purchase.shareholder_deduction_data.get('deducted_from', [])) if purchase.shareholder_deduction_data else 0),
            purchase.shareholder_deduction_date.strftime('%d-%m-%Y') if purchase.shareholder_deduction_date else '-'
        ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f6fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (3, 0), (4, -1), 'CENTER'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("This is a computer generated report.", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Shareholder_Deduction_Report_{date.today()}.pdf"'
    return response


@login_required
def shareholder_deduction_report_export(request):
    """
    Export shareholder deduction report to Excel
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    purchases = Purchase.objects.filter(
        shareholder_deduction_done=True
    ).order_by('-shareholder_deduction_date')[:500]
    
    wb = openpyxl.Workbook()
    
    # ========================================== #
    # SHEET 1: SUMMARY                          #
    # ========================================== #
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    ws_summary.merge_cells('A1:C1')
    ws_summary['A1'] = company_name
    ws_summary['A1'].font = Font(bold=True, size=16)
    ws_summary['A1'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A2:C2')
    ws_summary['A2'] = "Shareholder Deduction Report"
    ws_summary['A2'].font = Font(bold=True, size=14)
    ws_summary['A2'].alignment = Alignment(horizontal='center')
    
    ws_summary.merge_cells('A3:C3')
    ws_summary['A3'] = f"Generated: {now().strftime('%d-%m-%Y %H:%M')}"
    ws_summary['A3'].alignment = Alignment(horizontal='center')
    
    # Summary data
    total_amount = Decimal('0.00')
    total_shareholders = set()
    
    for p in purchases:
        data = p.shareholder_deduction_data
        if data:
            total_amount += Decimal(str(data.get('total_amount', 0)))
            for item in data.get('deducted_from', []):
                total_shareholders.add(item.get('name', ''))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Deductions', len(purchases)],
        ['Total Amount', float(total_amount)],
        ['Total Shareholders Affected', len(total_shareholders)],
        ['Deduction Type', SystemSetting.get_value('shareholder_deduction_type', 'proportional')],
    ]
    
    row = 5
    for data in summary_data:
        ws_summary.cell(row=row, column=1, value=data[0])
        ws_summary.cell(row=row, column=2, value=data[1])
        if row == 5:
            ws_summary.cell(row=row, column=1).font = Font(bold=True)
            ws_summary.cell(row=row, column=2).font = Font(bold=True)
        row += 1
    
    for r in range(6, 9):
        cell = ws_summary.cell(row=r, column=2)
        if isinstance(cell.value, (int, float)):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    ws_summary.column_dimensions['A'].width = 30
    ws_summary.column_dimensions['B'].width = 20
    
    # ========================================== #
    # SHEET 2: DETAILED DEDUCTIONS              #
    # ========================================== #
    ws_details = wb.create_sheet("Deductions")
    
    headers = ['#', 'Bill No', 'Vendor', 'Total Amount', 'Deduction Date', 'Shareholders']
    for col, header in enumerate(headers, 1):
        cell = ws_details.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    for idx, purchase in enumerate(purchases, 1):
        row = idx + 1
        ws_details.cell(row=row, column=1, value=idx)
        ws_details.cell(row=row, column=2, value=purchase.bill_no or 'N/A')
        ws_details.cell(row=row, column=3, value=purchase.vendor.name[:30])
        ws_details.cell(row=row, column=4, value=float(purchase.total_amount()))
        ws_details.cell(row=row, column=5, value=purchase.shareholder_deduction_date.strftime('%d-%m-%Y') if purchase.shareholder_deduction_date else '-')
        ws_details.cell(row=row, column=6, value=len(purchase.shareholder_deduction_data.get('deducted_from', [])) if purchase.shareholder_deduction_data else 0)
        
        ws_details.cell(row=row, column=4).number_format = '#,##0.00'
        ws_details.cell(row=row, column=4).alignment = Alignment(horizontal='right')
        ws_details.cell(row=row, column=6).alignment = Alignment(horizontal='center')
    
    # Column widths
    widths = [5, 15, 30, 15, 15, 15]
    for i, width in enumerate(widths, 1):
        ws_details.column_dimensions[get_column_letter(i)].width = width
    
    # ========================================== #
    # SHEET 3: SHAREHOLDER SUMMARY              #
    # ========================================== #
    ws_shareholder = wb.create_sheet("Shareholder Summary")
    
    # Calculate shareholder totals
    shareholder_totals = {}
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                name = item.get('name', 'Unknown')
                if name not in shareholder_totals:
                    shareholder_totals[name] = {
                        'code': item.get('code', ''),
                        'total_deductions': 0,
                        'total_amount': Decimal('0.00')
                    }
                shareholder_totals[name]['total_deductions'] += 1
                shareholder_totals[name]['total_amount'] += Decimal(str(item.get('deducted', 0)))
    
    sh_headers = ['#', 'Shareholder Name', 'Code', 'Total Deductions', 'Total Amount']
    for col, header in enumerate(sh_headers, 1):
        cell = ws_shareholder.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    sorted_shareholders = sorted(
        shareholder_totals.items(),
        key=lambda x: x[1]['total_amount'],
        reverse=True
    )
    
    for idx, (name, data) in enumerate(sorted_shareholders, 1):
        row = idx + 1
        ws_shareholder.cell(row=row, column=1, value=idx)
        ws_shareholder.cell(row=row, column=2, value=name)
        ws_shareholder.cell(row=row, column=3, value=data['code'])
        ws_shareholder.cell(row=row, column=4, value=data['total_deductions'])
        ws_shareholder.cell(row=row, column=5, value=float(data['total_amount']))
        ws_shareholder.cell(row=row, column=5).number_format = '#,##0.00'
        ws_shareholder.cell(row=row, column=5).alignment = Alignment(horizontal='right')
        ws_shareholder.cell(row=row, column=4).alignment = Alignment(horizontal='center')
    
    sh_widths = [5, 30, 15, 18, 20]
    for i, width in enumerate(sh_widths, 1):
        ws_shareholder.column_dimensions[get_column_letter(i)].width = width
    
    # Response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Shareholder_Deduction_Report_{date.today()}.xlsx"'
    wb.save(response)
    return response


@login_required
def bulk_process_deductions(request):
    """
    Bulk process deductions for multiple purchases
    """
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # ========================================== #
    # GET REQUEST - Show pending purchases      #
    # ========================================== #
    if request.method == 'GET':
        pending_purchases = Purchase.objects.filter(
            shareholder_deduction_done=False
        ).order_by('-pur_date')[:100]  # ✅ Increased limit to 100
        
        total_pending = Purchase.objects.filter(
            shareholder_deduction_done=False
        ).count()
        
        context = {
            'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
            'pending_purchases': pending_purchases,
            'total_pending': total_pending,
            'is_enabled': SystemSetting.get_bool('enable_shareholder_purchase_deduction', True),
            'deduction_type': SystemSetting.get_value('shareholder_deduction_type', 'proportional'),
        }
        return render(request, 'shareholders/deduction/bulk_process.html', context)
    
    # ========================================== #
    # POST REQUEST - Process selected purchases #
    # ========================================== #
    if request.method == 'POST':
        try:
            # Get data from request
            if request.headers.get('Content-Type') == 'application/json':
                data = json.loads(request.body)
                purchase_ids = data.get('purchase_ids', [])
            else:
                purchase_ids = request.POST.getlist('purchase_ids[]')
            
            if not purchase_ids:
                return JsonResponse({
                    'success': False, 
                    'message': 'No purchases selected!'
                })
            
            processed = 0
            failed = 0
            skipped = 0
            total_amount = Decimal('0.00')
            errors = []
            results = []
            
            with transaction.atomic():
                for purchase_id in purchase_ids:
                    try:
                        purchase = Purchase.objects.get(pk=purchase_id)
                        
                        # ✅ Skip if already processed
                        if purchase.shareholder_deduction_done:
                            skipped += 1
                            continue
                        
                        # ✅ Process deduction
                        success, result = purchase.process_shareholder_deduction(request.user)
                        
                        if success:
                            processed += 1
                            total_amount += purchase.total_amount()
                            results.append({
                                'bill_no': purchase.bill_no,
                                'amount': float(purchase.total_amount()),
                                'status': 'success'
                            })
                            logger.info(f"✅ Bulk processed: {purchase.bill_no}")
                        else:
                            failed += 1
                            errors.append(f"Purchase #{purchase_id}: {result}")
                            results.append({
                                'bill_no': purchase.bill_no,
                                'amount': float(purchase.total_amount()),
                                'status': 'failed',
                                'error': result
                            })
                            
                    except Purchase.DoesNotExist:
                        failed += 1
                        errors.append(f"Purchase #{purchase_id}: Not found")
                    except Exception as e:
                        failed += 1
                        errors.append(f"Purchase #{purchase_id}: {str(e)}")
            
            # ✅ Return JSON response for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': f'✅ {processed} purchases processed! Total: Rs. {total_amount:,.2f}',
                    'processed': processed,
                    'failed': failed,
                    'skipped': skipped,
                    'total_amount': float(total_amount),
                    'errors': errors[:5],
                    'results': results
                })
            
            # ✅ Return HTML response for form submission
            messages.success(
                request, 
                f'✅ {processed} purchases processed! Total: Rs. {total_amount:,.2f}. Failed: {failed}'
            )
            return redirect('shareholder_deduction_report')
            
        except Exception as e:
            logger.error(f"Bulk processing error: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False, 
                    'message': str(e)
                })
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('bulk_process_deductions')
    
    return redirect('bulk_process_deductions')


@login_required
def shareholder_balance_summary(request):
    """
    Summary of all shareholder balances with deduction history
    """
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholders = Shareholder.objects.filter(status='active')
    
    data = []
    total_balance = Decimal('0.00')
    total_deductions = Decimal('0.00')
    total_shares = 0
    
    for shareholder in shareholders:
        balance = shareholder.get_balance()
        total_shares += shareholder.total_shares()
        total_balance += balance
        
        # Get total deductions for this shareholder
        deduction_total = Decimal('0.00')
        deduction_count = 0
        
        # Check all purchases
        purchases = Purchase.objects.filter(shareholder_deduction_done=True)
        for purchase in purchases:
            data_dict = purchase.shareholder_deduction_data
            if data_dict and data_dict.get('deducted_from'):
                for item in data_dict['deducted_from']:
                    if item.get('name') == shareholder.name:
                        deduction_total += Decimal(str(item.get('deducted', 0)))
                        deduction_count += 1
        
        total_deductions += deduction_total
        
        data.append({
            'shareholder': shareholder,
            'balance': balance,
            'total_shares': shareholder.total_shares(),
            'deduction_count': deduction_count,
            'deduction_total': deduction_total,
            'status': shareholder.status,
        })
    
    # Sort by balance
    data.sort(key=lambda x: x['balance'], reverse=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholders': data,
        'total_shareholders': len(data),
        'total_balance': total_balance,
        'total_deductions': total_deductions,
        'total_shares': total_shares,
        'is_enabled': SystemSetting.get_bool('enable_shareholder_purchase_deduction', True),
        'deduction_type': SystemSetting.get_value('shareholder_deduction_type', 'proportional'),
    }
    return render(request, 'shareholders/balance_summary.html', context)


@login_required
def shareholder_deduction_history(request, pk):
    """
    View deduction history for a specific shareholder
    """
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Find all purchases where this shareholder was deducted
    deduction_history = []
    total_deducted = Decimal('0.00')
    
    purchases = Purchase.objects.filter(
        shareholder_deduction_done=True
    ).order_by('-shareholder_deduction_date')
    
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    deduction_history.append({
                        'purchase': purchase,
                        'amount': Decimal(str(item.get('deducted', 0))),
                        'percentage': item.get('percentage', 0),
                        'balance_before': Decimal(str(item.get('balance_before', 0))),
                        'balance_after': Decimal(str(item.get('balance_after', 0))),
                        'date': purchase.shareholder_deduction_date,
                    })
                    total_deducted += Decimal(str(item.get('deducted', 0)))
                    break
    
    # Get all transactions for this shareholder
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder
    ).order_by('-created_at')[:50]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'deduction_history': deduction_history,
        'total_deducted': total_deducted,
        'total_deductions': len(deduction_history),
        'transactions': transactions,
        'current_balance': shareholder.get_balance(),
        'total_shares': shareholder.total_shares(),
    }
    return render(request, 'shareholders/deduction_history.html', context)


def get_shareholder_balance_used(shareholder):
    """Calculate total balance used by a specific shareholder"""
    total = Decimal('0.00')
    
    purchases = Purchase.objects.filter(shareholder_deduction_done=True)
    for purchase in purchases:
        data = purchase.shareholder_deduction_data
        if data and data.get('deducted_from'):
            for item in data['deducted_from']:
                if item.get('name') == shareholder.name:
                    total += Decimal(str(item.get('deducted', 0)))
    
    return total


def get_total_balance_used():
    """Calculate total balance used by all shareholders"""
    total = Decimal('0.00')
    
    for shareholder in Shareholder.objects.filter(status='active'):
        total += get_shareholder_balance_used(shareholder)
    
    return total


def get_eligible_shareholders_count():
    """Get count of shareholders eligible for balance dividend"""
    count = 0
    min_balance = Decimal(SystemSetting.get_value('min_balance_for_dividend', '0'))
    min_months = int(SystemSetting.get_value('min_holding_months', '0'))
    
    for shareholder in Shareholder.objects.filter(status='active'):
        balance_used = get_shareholder_balance_used(shareholder)
        
        if balance_used < min_balance:
            continue
        
        if min_months > 0:
            first_share = shareholder.shares.order_by('issue_date').first()
            if not first_share:
                continue
            months_held = (date.today() - first_share.issue_date).days // 30
            if months_held < min_months:
                continue
        
        count += 1
    
    return count


@login_required
def shareholder_withdraw_from_balance(request, pk):
    """Shareholder withdraws money from their balance"""
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    current_balance = ShareholderCashBalance.get_balance(shareholder)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'Bank Transfer')
            reference_no = request.POST.get('reference_no', '')
            description = request.POST.get('description', '')
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('shareholder_withdraw_from_balance', pk=pk)
            
            if amount > current_balance:
                messages.error(
                    request, 
                    f'Insufficient balance! Available: Rs. {current_balance:,.2f}'
                )
                return redirect('shareholder_withdraw_from_balance', pk=pk)
            
            # ✅ Withdraw from both shareholder balance and main cash
            ShareholderCashBalance.withdraw_from_main_cash(
                shareholder=shareholder,
                amount=amount,
                user=request.user,
                description=f"Withdrawal: {description or 'Cash withdrawal'}"
            )
            
            messages.success(
                request, 
                f'✅ Rs. {amount:,.2f} withdrawn from {shareholder.name}\'s balance!\n'
                f'💰 New Balance: Rs. {current_balance - amount:,.2f}\n'
                f'💵 Main Cash: -Rs. {amount:,.2f}'
            )
            
            return redirect('shareholder_balance_detail', pk=shareholder.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('shareholder_withdraw_from_balance', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'current_balance': current_balance,
        'main_balance': CashBalance.get_balance(),
    }
    return render(request, 'shareholders/withdraw_from_balance.html', context)


@login_required
def shareholder_cash_report(request):
    """
    Shareholder Cash Report - FULLY OPTIMIZED (400+ → 2 queries)
    """
    from django.db.models import Sum, Q, F, Value, DecimalField, Count
    from django.db.models.functions import Coalesce
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Date filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    shareholder_id = request.GET.get('shareholder', '')
    transaction_type = request.GET.get('type', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # ✅ STEP 1: Base queryset
    shareholders = Shareholder.objects.filter(status='active')
    
    if shareholder_id:
        shareholders = shareholders.filter(id=shareholder_id)
    
    # ✅ STEP 2: Filter for transactions
    transaction_filter = Q(
        cash_transactions__created_at__date__gte=from_date_obj,
        cash_transactions__created_at__date__lte=to_date_obj
    )
    
    if transaction_type:
        transaction_filter &= Q(cash_transactions__transaction_type=transaction_type)
    
    # ✅ STEP 3: ✅ CRITICAL FIX - Ek query mein SAARA data!
    shareholders = shareholders.annotate(
        annotated_deposits=Coalesce(
            Sum(
                'cash_transactions__amount',
                filter=transaction_filter & Q(
                    cash_transactions__transaction_type__in=[
                        'deposit', 'dividend', 'balance_dividend', 'transfer_in'
                    ]
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        annotated_withdrawals=Coalesce(
            Sum(
                'cash_transactions__amount',
                filter=transaction_filter & Q(
                    cash_transactions__transaction_type__in=[
                        'withdraw', 'share_purchase', 'transfer_out'
                    ]
                ),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00'))
        ),
        annotated_balance=Coalesce(
            Sum('cash_balance__balance', output_field=DecimalField(max_digits=20, decimal_places=2)),
            Value(Decimal('0.00'))
        ),
        annotated_transaction_count=Count(
            'cash_transactions',
            filter=transaction_filter,
            distinct=True
        ),
    )
    
    # ✅ STEP 4: Build report data (NO queries!)
    report_data = []
    total_deposits = Decimal('0.00')
    total_withdrawals = Decimal('0.00')
    total_balance = Decimal('0.00')
    total_transactions = 0
    
    for shareholder in shareholders:
        deposits = shareholder.annotated_deposits
        withdrawals = shareholder.annotated_withdrawals
        balance = shareholder.annotated_balance
        tx_count = shareholder.annotated_transaction_count
        
        if deposits > 0 or withdrawals > 0:
            report_data.append({
                'shareholder': shareholder,
                'deposits': deposits,
                'withdrawals': withdrawals,
                'balance': balance,
                'transaction_count': tx_count,
            })
            
            total_deposits += deposits
            total_withdrawals += withdrawals
            total_balance += balance
            total_transactions += tx_count
    
    report_data.sort(key=lambda x: x['deposits'], reverse=True)
    
    # ✅ STEP 5: Stats (Python calculation)
    stats = {
        'total_shareholders': len(report_data),
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'total_balance': total_balance,
        'total_transactions': total_transactions,
        'net_cash': total_deposits - total_withdrawals,
        'avg_deposit': total_deposits / len(report_data) if report_data else 0,
        'avg_withdrawal': total_withdrawals / len(report_data) if report_data else 0,
    }
    
    # ✅ STEP 6: Type breakdown (1 query)
    type_breakdown_raw = ShareholderCashTransaction.objects.filter(
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).values('transaction_type').annotate(
        count=Count('id'),
        amount=Sum('amount')
    )
    
    type_breakdown = {}
    type_labels = dict(ShareholderCashTransaction.TRANSACTION_TYPES)
    for item in type_breakdown_raw:
        type_breakdown[item['transaction_type']] = {
            'label': type_labels.get(item['transaction_type'], item['transaction_type']),
            'count': item['count'],
            'amount': item['amount'] or Decimal('0.00')
        }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_data': report_data,
        'stats': stats,
        'type_breakdown': type_breakdown,
        'shareholders': Shareholder.objects.filter(status='active'),
        'selected_shareholder': shareholder_id,
        'selected_type': transaction_type,
        'from_date': from_date,
        'to_date': to_date,
        'today': date.today().strftime('%Y-%m-%d'),
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/cash_report.html', context)


@login_required
def shareholder_cash_report_detail(request, pk):
    """
    Detailed cash report for a single shareholder
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    # Get filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    transaction_type = request.GET.get('type', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=90)
        to_date_obj = date.today()
    
    # Get transactions
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder,
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).order_by('-created_at')
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    # Calculate running balance
    running_balance = shareholder.get_balance()
    for trans in transactions.reverse():
        if trans.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in']:
            running_balance -= trans.amount
        else:
            running_balance += trans.amount
        trans.running_balance = running_balance
    
    # Summary
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'transactions': transactions,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'current_balance': shareholder.get_balance(),
        'from_date': from_date,
        'to_date': to_date,
        'selected_type': transaction_type,
        'transaction_types': ShareholderCashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'shareholders/cash_report_detail.html', context)


@login_required
def shareholder_cash_report_export(request):
    """
    Export shareholder cash report to Excel
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # Get all transactions
    transactions = ShareholderCashTransaction.objects.filter(
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).select_related('shareholder').order_by('-created_at')
    
    # Create Excel
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    
    wb = openpyxl.Workbook()
    
    # Sheet 1: Summary
    ws = wb.active
    ws.title = "Summary"
    
    # Title
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    ws.merge_cells('A1:F1')
    ws['A1'] = company_name
    ws['A1'].font = Font(bold=True, size=16)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:F2')
    ws['A2'] = "Shareholder Deposit Withdraw Report"
    ws['A2'].font = Font(bold=True, size=14)
    ws['A2'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A3:F3')
    ws['A3'] = f"Period: {from_date} to {to_date}"
    ws['A3'].alignment = Alignment(horizontal='center')
    
    # Summary Data
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    row = 5
    summary_data = [
        ['Metric', 'Amount (Rs.)'],
        ['Total Deposits', float(total_deposits)],
        ['Total Withdrawals', float(total_withdrawals)],
        ['Net Cash Flow', float(total_deposits - total_withdrawals)],
        ['Total Transactions', transactions.count()],
        ['Unique Shareholders', transactions.values('shareholder').distinct().count()],
    ]
    
    for data in summary_data:
        ws.cell(row=row, column=1, value=data[0])
        ws.cell(row=row, column=2, value=data[1])
        if row == 5:
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=2).font = Font(bold=True)
        row += 1
    
    for r in range(6, 10):
        cell = ws.cell(row=r, column=2)
        if isinstance(cell.value, (int, float)):
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal='right')
    
    # Sheet 2: Transaction Details
    ws2 = wb.create_sheet("Transactions")
    
    headers = ['Date', 'Shareholder', 'Type', 'Amount', 'Balance After', 'Description', 'Reference No']
    for col, header in enumerate(headers, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    row = 2
    for trans in transactions[:500]:  # Limit to 500 rows
        ws2.cell(row=row, column=1, value=trans.created_at.strftime('%d-%m-%Y %H:%M'))
        ws2.cell(row=row, column=2, value=trans.shareholder.name)
        ws2.cell(row=row, column=3, value=trans.get_transaction_type_display())
        ws2.cell(row=row, column=4, value=float(trans.amount))
        ws2.cell(row=row, column=4).number_format = '#,##0.00'
        ws2.cell(row=row, column=5, value=float(trans.balance_after))
        ws2.cell(row=row, column=5).number_format = '#,##0.00'
        ws2.cell(row=row, column=6, value=trans.description or '')
        ws2.cell(row=row, column=7, value=trans.reference_no or '')
        row += 1
    
    # Auto-fit columns
    for ws_sheet in [ws, ws2]:
        for col in ws_sheet.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 40)
            ws_sheet.column_dimensions[col_letter].width = adjusted_width
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"Shareholder_Cash_Report_{date.today().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def shareholder_cash_report_pdf(request, pk):
    """
    Generate PDF report for single shareholder cash transactions
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    shareholder = get_object_or_404(Shareholder, pk=pk)
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=90)
        to_date_obj = date.today()
    
    transactions = ShareholderCashTransaction.objects.filter(
        shareholder=shareholder,
        created_at__date__gte=from_date_obj,
        created_at__date__lte=to_date_obj
    ).order_by('-created_at')
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"<b>Shareholder deposit withdraw Report</b>", styles['Heading2']))
    story.append(Paragraph(f"{shareholder.name} ({shareholder.shareholder_code})", styles['Normal']))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Summary
    total_deposits = transactions.filter(
        transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_withdrawals = transactions.filter(
        transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    summary_data = [
        ['Current Balance:', f"Rs. {shareholder.get_balance():,.2f}"],
        ['Total Deposits:', f"Rs. {total_deposits:,.2f}"],
        ['Total Withdrawals:', f"Rs. {total_withdrawals:,.2f}"],
        ['Net Cash Flow:', f"Rs. {total_deposits - total_withdrawals:,.2f}"],
        ['Total Transactions:', str(transactions.count())],
    ]
    
    summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Transactions Table
    data = [['Date', 'Type', 'Amount', 'Balance After', 'Description']]
    
    for trans in transactions[:100]:
        amount_str = f"+Rs. {trans.amount:,.2f}" if trans.transaction_type in ['deposit', 'dividend', 'balance_dividend', 'transfer_in'] else f"-Rs. {trans.amount:,.2f}"
        data.append([
            trans.created_at.strftime('%d-%m-%Y %H:%M'),
            trans.get_transaction_type_display()[:20],
            amount_str,
            f"Rs. {trans.balance_after:,.2f}",
            (trans.description or '')[:30]
        ])
    
    trans_table = Table(data, repeatRows=1)
    trans_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f6fa')]),
        ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
    ]))
    
    story.append(trans_table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Cash_Report_{shareholder.shareholder_code}.pdf"'
    return response


@login_required
def shareholder_cash_stats_api(request):
    """
    AJAX API: Get shareholder cash statistics
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        transactions = ShareholderCashTransaction.objects.filter(
            created_at__date__gte=from_date_obj,
            created_at__date__lte=to_date_obj
        )
        
        total_deposits = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_withdrawals = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Daily trend
        daily_data = []
        current = from_date_obj
        while current <= to_date_obj:
            day_transactions = transactions.filter(created_at__date=current)
            day_deposits = day_transactions.filter(
                transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            day_withdrawals = day_transactions.filter(
                transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            daily_data.append({
                'date': current.strftime('%d-%b'),
                'deposits': float(day_deposits),
                'withdrawals': float(day_withdrawals)
            })
            current += timedelta(days=1)
        
        # Top shareholders
        top_depositors = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).values('shareholder__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]
        
        top_withdrawers = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).values('shareholder__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_deposits': float(total_deposits),
                'total_withdrawals': float(total_withdrawals),
                'net_cash': float(total_deposits - total_withdrawals),
                'total_transactions': transactions.count(),
                'unique_shareholders': transactions.values('shareholder').distinct().count(),
                'daily_data': daily_data,
                'top_depositors': list(top_depositors),
                'top_withdrawers': list(top_withdrawers),
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def shareholder_cash_report_all_pdf(request):
    """
    Generate PDF report for ALL shareholders cash transactions
    """
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Get filters
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    shareholder_id = request.GET.get('shareholder', '')
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=30)
        to_date_obj = date.today()
    
    # Get shareholders
    shareholders = Shareholder.objects.filter(status='active')
    if shareholder_id:
        shareholders = shareholders.filter(id=shareholder_id)
    
    # Build report data
    report_data = []
    total_deposits = Decimal('0.00')
    total_withdrawals = Decimal('0.00')
    total_balance = Decimal('0.00')
    
    for shareholder in shareholders:
        transactions = ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            created_at__date__gte=from_date_obj,
            created_at__date__lte=to_date_obj
        )
        
        deposits = transactions.filter(
            transaction_type__in=['deposit', 'dividend', 'balance_dividend', 'transfer_in']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        withdrawals = transactions.filter(
            transaction_type__in=['withdraw', 'share_purchase', 'transfer_out']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        balance = shareholder.get_balance()
        
        if deposits > 0 or withdrawals > 0 or balance > 0:
            report_data.append({
                'shareholder': shareholder,
                'deposits': deposits,
                'withdrawals': withdrawals,
                'balance': balance,
                'transaction_count': transactions.count(),
                'latest_transaction': transactions.first(),
            })
            
            total_deposits += deposits
            total_withdrawals += withdrawals
            total_balance += balance
    
    # Sort by balance (highest first)
    report_data.sort(key=lambda x: x['balance'], reverse=True)
    
    # Generate PDF
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4),
        topMargin=0.3*inch,
        bottomMargin=0.3*inch,
        leftMargin=0.3*inch,
        rightMargin=0.3*inch
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    
    # Title Style
    title_style = ParagraphStyle(
        'Title', 
        parent=styles['Heading1'], 
        fontSize=16, 
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=3
    )
    
    # ==========================================
    # HEADER
    # ==========================================
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Shareholder Deposit Withdraw Report ", title_style))
    story.append(Paragraph(f"Period: {from_date} to {to_date}", subtitle_style))
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %H:%M')}", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # SUMMARY SECTION
    # ==========================================
    summary_data = [
        ['Metric', 'Value'],
        ['Total Shareholders', str(len(report_data))],
        ['Total Deposits', f"Rs. {total_deposits:,.2f}"],
        ['Total Withdrawals', f"Rs. {total_withdrawals:,.2f}"],
        ['Net Cash Flow', f"Rs. {total_deposits - total_withdrawals:,.2f}"],
        ['Total Balance', f"Rs. {total_balance:,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # MAIN TABLE
    # ==========================================
    story.append(Paragraph("<b>Shareholder Summary</b>", styles['Heading3']))
    story.append(Spacer(1, 0.1*inch))
    
    data = [
        ['#', 'Shareholder', 'Code', 'Deposits', 'Withdrawals', 'Net', 'Balance', 'Transactions']
    ]
    
    for idx, item in enumerate(report_data, 1):
        net = item['deposits'] - item['withdrawals']
        data.append([
            str(idx),
            item['shareholder'].name[:25],
            item['shareholder'].shareholder_code,
            f"Rs. {item['deposits']:,.2f}",
            f"Rs. {item['withdrawals']:,.2f}",
            f"Rs. {net:,.2f}",
            f"Rs. {item['balance']:,.2f}",
            str(item['transaction_count'])
        ])
    
    # Add total row
    data.append([
        '', '', 'TOTAL',
        f"Rs. {total_deposits:,.2f}",
        f"Rs. {total_withdrawals:,.2f}",
        f"Rs. {total_deposits - total_withdrawals:,.2f}",
        f"Rs. {total_balance:,.2f}",
        str(sum(item['transaction_count'] for item in report_data))
    ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -2), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fc')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (3, 0), (7, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.2*inch))
    
    # ==========================================
    # FOOTER
    # ==========================================
    story.append(Paragraph(
        f"Generated: {now().strftime('%d-%m-%Y %H:%M')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "This is a computer generated report.",
        ParagraphStyle('Footer2', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    ))
    
    # Build document
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Shareholder_Cash_Report_{date.today().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
