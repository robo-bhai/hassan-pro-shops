"""Frontend views: shareholder/cash_balances (split from the former shareholder_cash.py)."""
from ...security.permissions import perm_required
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper
from ...models import *
import openpyxl
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F, Value, DecimalField, IntegerField
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
    SharePrice,
    DividendPayment,
    ShareTransfer,
    ShareholderCashBalance,
    ShareholderCashTransaction,
    CompanyInfo,
    Purchase,
    SystemSetting,
)
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


@login_required
@perm_required('view_shareholders')
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
    
    # ✅ STEP 2: Fetch ALL the data in one query
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
    
    # ✅ STEP 4: Only calculation in the Python loop (no queries!)
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
@perm_required('view_shareholders')
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
@perm_required('manage_shareholder_cash')
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
                # STEP 1: ONLY ADD to the Shareholder balance
                # ============================================
                new_shareholder_balance = ShareholderCashBalance.deposit(
                    shareholder=shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Internal deposit - {description}"
                )
                
                # ============================================
                # STEP 2: DO NOT TOUCH Main Cash ❌
                # ============================================
                # CashBalance.update_balance(...) - REMOVE THIS
                
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
@perm_required('manage_shareholder_cash')
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
                # STEP 1: ONLY SUBTRACT from the Shareholder balance
                # ============================================
                new_shareholder_balance = ShareholderCashBalance.withdraw(
                    shareholder=shareholder,
                    amount=amount,
                    user=request.user,
                    description=f"Internal withdrawal - {description}"
                )
                
                # ============================================
                # STEP 2: DO NOT TOUCH Main Cash ❌
                # ============================================
                # CashBalance.update_balance(...) - REMOVE THIS
                
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
@perm_required('manage_shareholder_cash')
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
@perm_required('manage_shareholder_cash')
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
@perm_required('view_shareholders')
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
@perm_required('view_shareholders')
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
            trans.created_at.strftime('%d-%m-%Y %I:%M %p'),
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
@perm_required('view_shareholders')
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
            trans.created_at.strftime('%d-%m-%Y %I:%M %p'),
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
    story.append(Paragraph(f"Generated: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    story.append(Paragraph("This is a computer generated report.", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Shareholder_Balance_{shareholder.shareholder_code}.pdf"'
    return response


@login_required
@perm_required('view_shareholders')
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
@perm_required('manage_shareholder_cash')
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
