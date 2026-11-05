"""Frontend views: cash."""
from ..models import *
import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from ..models import CashTransaction, CashBalance, CompanyInfo


@login_required
def cash_withdraw(request):
    """Withdraw cash from system - Updated Categories"""
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            category = request.POST.get('category', '')
            reference_no = request.POST.get('reference_no', '')
            description = request.POST.get('description', '')
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('cash_withdraw')
            
            # Check if sufficient balance
            current_balance = CashBalance.get_balance()
            if amount > current_balance:
                messages.error(request, f'❌ Insufficient cash balance! Available: Rs. {current_balance:,.2f}, Required: Rs. {amount:,.2f}')
                return redirect('cash_withdraw')
            
            new_balance = CashBalance.update_balance(
                amount=amount,
                transaction_type='withdraw',
                user=request.user,
                description=f"[{category}] {description}" if description else category
            )
            
            messages.success(request, f'✅ Rs. {amount:,.2f} withdrawn successfully! New balance: Rs. {new_balance:,.2f}')
            return redirect('cash_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('cash_withdraw')
    
    # GET request - show form
    recent_withdrawals = CashTransaction.objects.filter(
        transaction_type='withdraw'
    ).order_by('-date')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'current_balance': CashBalance.get_balance(),
        'recent_withdrawals': recent_withdrawals,
        'withdrawal_categories': [
            'Personal Use',
            'Mobile Load',             
            'Rent Payment',
            'Utility Bills',
            'Transportation',            
            'Other'
        ],
        'payment_methods': [
            ('cash', '💵 Cash'),
            ('bank_transfer', '🏦 Bank Transfer'),
        ],
    }
    return render(request, 'cash/withdraw.html', context)


@login_required
def cash_dashboard(request):
    """Cash Management Dashboard with Retained Earnings"""
    
    from decimal import Decimal
    from django.db.models import Sum, F
    from django.utils.timezone import now
    from datetime import date, timedelta
    import json
    from ..models import CashTransaction, CashBalance, BalanceDividend, CompanyInfo
    
    # Get current balance
    current_balance = CashBalance.get_balance()
    
    # ========================================== #
    # ✅ CALCULATE RETAINED EARNINGS             #
    # ========================================== #
    total_profit = Decimal('0.00')
    total_distributed = Decimal('0.00')
    retained_earnings = Decimal('0.00')
    
    # Get all distributed dividends
    dividends = BalanceDividend.objects.filter(status='distributed')
    
    for dividend in dividends:
        total_profit += dividend.total_profit
        total_distributed += dividend.amount_to_distribute
        retained_earnings += (dividend.total_profit - dividend.amount_to_distribute)
    
    # ✅ Calculate percentages for progress bar
    distributed_percent = 0
    retained_percent = 0
    if total_profit > 0:
        distributed_percent = int((total_distributed / total_profit) * 100)
        retained_percent = 100 - distributed_percent
    
    # Get pending dividends count
    pending_dividends_count = BalanceDividend.objects.filter(
        status__in=['draft', 'declared', 'approved']
    ).count()
    
    # ========================================== #
    # TODAY'S TRANSACTIONS                       #
    # ========================================== #
    today = date.today()
    
    today_inflow = CashTransaction.objects.filter(
        date__date=today,
        transaction_type__in=['deposit', 'sale', 'opening']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    
    today_outflow = CashTransaction.objects.filter(
        date__date=today,
        transaction_type__in=['withdraw', 'purchase', 'expense']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    
    today_net = today_inflow - today_outflow
    
    # ========================================== #
    # MONTHLY STATS                              #
    # ========================================== #
    month_start = today.replace(day=1)
    
    month_inflow = CashTransaction.objects.filter(
        date__date__gte=month_start,
        transaction_type__in=['deposit', 'sale', 'opening']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    
    month_outflow = CashTransaction.objects.filter(
        date__date__gte=month_start,
        transaction_type__in=['withdraw', 'purchase', 'expense']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    
    month_net = month_inflow - month_outflow
    
    # ========================================== #
    # CHART DATA (LAST 7 DAYS)                   #
    # ========================================== #
    chart_labels = []
    chart_inflow = []
    chart_outflow = []
    
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        inflow = CashTransaction.objects.filter(
            date__date=d,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        
        outflow = CashTransaction.objects.filter(
            date__date=d,
            transaction_type__in=['withdraw', 'purchase', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        
        chart_labels.append(d.strftime('%d %b'))
        chart_inflow.append(float(inflow))
        chart_outflow.append(float(outflow))
    
    # ========================================== #
    # RECENT TRANSACTIONS                        #
    # ========================================== #
    recent_transactions = CashTransaction.objects.select_related('created_by').order_by('-date')[:10]
    
    # ========================================== #
    # CONTEXT                                    #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'current_balance': current_balance,
        # Retained Earnings
        'retained_earnings': retained_earnings,
        'total_profit': total_profit,
        'total_distributed': total_distributed,
        'pending_dividends_count': pending_dividends_count,
        # Percentages for progress bar
        'distributed_percent': distributed_percent,
        'retained_percent': retained_percent,
        # Daily Stats
        'today_inflow': today_inflow,
        'today_outflow': today_outflow,
        'today_net': today_net,
        # Monthly Stats
        'month_inflow': month_inflow,
        'month_outflow': month_outflow,
        'month_net': month_net,
        # Chart
        'chart_labels': json.dumps(chart_labels),
        'chart_inflow': json.dumps(chart_inflow),
        'chart_outflow': json.dumps(chart_outflow),
        # Recent
        'recent_transactions': recent_transactions,
    }
    
    return render(request, 'cash/dashboard.html', context)


@login_required
def cash_add(request):
    """Add cash (deposit) to system - Updated Source Options"""
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'cash')
            source = request.POST.get('source', '')
            reference_no = request.POST.get('reference_no', '')
            description = request.POST.get('description', '')
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('cash_add')
            
            # Update balance
            CashBalance.update_balance(
                amount=amount,
                transaction_type='deposit',
                user=request.user,
                description=f"{source} - {description}" if source else description
            )
            
            messages.success(request, f'✅ Rs. {amount:,.2f} added to cash balance!')
            return redirect('cash_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('cash_add')
    
    # GET request - show form with updated sources
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'source_options': [
            ('sale', '🛒 Sale Income'),
            ('investment', '💰 Owner Investment'),
            ('salary', '💵 Salary'),  # ✅ ADDED
            ('salary_advance', '💳 Salary Advance'),  # ✅ ADDED
            ('cash_deposit', '💵 Cash Deposit'),
            ('other', '📋 Other'),
        ],
        'payment_methods': [
            ('cash', '💵 Cash'),
            ('bank_transfer', '🏦 Bank Transfer'),
        ],
    }
    return render(request, 'cash/add.html', context)


@login_required
def cash_transactions(request):
    """List all cash transactions with Debit/Credit/Balance format"""
    
    transactions = CashTransaction.objects.select_related('created_by').order_by('-date')
    
    # Filters
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    trans_type = request.GET.get('type', '')
    
    if from_date:
        transactions = transactions.filter(date__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(date__date__lte=to_date)
    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)
    
    # ✅ Calculate running balance
    running_balance = 0
    transaction_list = []
    
    # Reverse for running balance calculation
    reversed_trans = list(transactions.order_by('date'))
    
    for trans in reversed_trans:
        # Debit = Inflow, Credit = Outflow
        if trans.transaction_type in ['deposit', 'sale', 'opening']:
            running_balance += trans.amount
        else:
            running_balance -= trans.amount
        
        transaction_list.append({
            'id': trans.id,
            'date': trans.date,
            'description': trans.description,
            'transaction_type': trans.transaction_type,
            'type_display': trans.get_transaction_type_display(),
            'payment_method': trans.payment_method,
            'reference_no': trans.reference_no or '-',
            'debit': trans.debit or (trans.amount if trans.is_inflow else 0),
            'credit': trans.credit or (trans.amount if trans.is_outflow else 0),
            'balance': running_balance,
            'created_by': trans.created_by.username if trans.created_by else 'System',
            'is_inflow': trans.is_inflow,
            'is_outflow': trans.is_outflow,
        })
    
    # ✅ Reverse back for display (newest first)
    transaction_list.reverse()
    
    # Statistics
    total_debit = sum(t['debit'] for t in transaction_list)
    total_credit = sum(t['credit'] for t in transaction_list)
    
    paginator = Paginator(transaction_list, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'net_balance': total_debit - total_credit,
        'current_balance': CashBalance.get_balance(),
        'from_date': from_date,
        'to_date': to_date,
        'selected_type': trans_type,
        'transaction_types': CashTransaction.TRANSACTION_TYPES,
    }
    return render(request, 'cash/transactions.html', context)


@login_required
def cash_set_opening(request):
    """Set opening balance (only once)"""
    
    # Check if already set
    if CashBalance.objects.exists():
        messages.error(request, 'Opening balance already set!')
        return redirect('cash_dashboard')
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            
            if amount < 0:
                messages.error(request, 'Amount cannot be negative!')
                return redirect('cash_set_opening')
            
            CashBalance.set_opening_balance(amount, request.user)
            
            messages.success(request, f'✅ Opening balance set to Rs. {amount:,.2f}!')
            return redirect('cash_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('cash_set_opening')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'cash/set_opening.html', context)


@login_required
def cash_report(request):
    """Cash flow report"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Get transactions
    transactions = CashTransaction.objects.filter(
        date__date__gte=from_date_obj,
        date__date__lte=to_date_obj
    ).order_by('date')
    
    # Calculate totals by type
    inflow_by_type = {}
    outflow_by_type = {}
    
    for trans in transactions:
        if trans.is_inflow:
            inflow_by_type[trans.transaction_type] = inflow_by_type.get(trans.transaction_type, Decimal('0.0')) + trans.amount
        else:
            outflow_by_type[trans.transaction_type] = outflow_by_type.get(trans.transaction_type, Decimal('0.0')) + trans.amount
    
    total_inflow = sum(inflow_by_type.values())
    total_outflow = sum(outflow_by_type.values())
    net_cash = total_inflow - total_outflow
    
    # Daily breakdown
    daily_data = []
    current = from_date_obj
    while current <= to_date_obj:
        day_transactions = transactions.filter(date__date=current)
        day_inflow = sum(t.amount for t in day_transactions if t.is_inflow)
        day_outflow = sum(t.amount for t in day_transactions if t.is_outflow)
        daily_data.append({
            'date': current.strftime('%d-%b'),
            'inflow': day_inflow,
            'outflow': day_outflow,
            'net': day_inflow - day_outflow
        })
        current += timedelta(days=1)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'inflow_by_type': inflow_by_type,
        'outflow_by_type': outflow_by_type,
        'total_inflow': total_inflow,
        'total_outflow': total_outflow,
        'net_cash': net_cash,
        'daily_data': daily_data,
    }
    return render(request, 'cash/report.html', context)


@login_required
def get_cash_balance(request):
    balance = CashBalance.get_balance()
    return JsonResponse({
        'success': True,
        'balance': float(balance),
        'formatted_balance': f"Rs. {balance:,.2f}"
    })
