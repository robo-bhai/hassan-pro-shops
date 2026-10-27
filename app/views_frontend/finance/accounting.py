"""Frontend views: accounting."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import HttpResponse
from ...models import CompanyInfo, Sale, Purchase, Expense, Account, AccountType, JournalEntry, JournalEntryItem, FinancialPeriod
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl import Workbook


@login_required
@perm_required('view_accounting')
def accounts_dashboard(request):
    """Accounts Dashboard"""
    
    today = date.today()
    month_start = today.replace(day=1)
    
    # Get total accounts
    total_accounts = Account.objects.count()
    active_accounts = Account.objects.filter(is_active=True).count()
    
    # Get journal entries
    journal_entries = JournalEntry.objects.filter(status='posted')
    total_entries = journal_entries.count()
    total_debit = JournalEntryItem.objects.filter(is_debit=True).aggregate(total=Sum('amount'))['total'] or 0
    total_credit = JournalEntryItem.objects.filter(is_debit=False).aggregate(total=Sum('amount'))['total'] or 0
    
    # This month entries
    this_month_entries = JournalEntry.objects.filter(
        entry_date__gte=month_start,
        entry_date__lte=today,
        status='posted'
    ).count()
    
    # Pending entries
    pending_entries = JournalEntry.objects.filter(status='draft').count()
    
    # Account balances
    asset_accounts = Account.objects.filter(account_type__account_class='asset')
    liability_accounts = Account.objects.filter(account_type__account_class='liability')
    equity_accounts = Account.objects.filter(account_type__account_class='equity')
    income_accounts = Account.objects.filter(account_type__account_class='income')
    expense_accounts = Account.objects.filter(account_type__account_class='expense')
    
    total_assets = sum(a.current_balance() for a in asset_accounts)
    total_liabilities = sum(a.current_balance() for a in liability_accounts)
    total_equity = sum(a.current_balance() for a in equity_accounts)
    total_income = sum(a.current_balance() for a in income_accounts)
    total_expenses = sum(a.current_balance() for a in expense_accounts)
    
    # Recent journal entries
    recent_entries = JournalEntry.objects.order_by('-created_at')[:10]
    
    # Get financial periods
    current_period = FinancialPeriod.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        is_closed=False
    ).first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'total_entries': total_entries,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'this_month_entries': this_month_entries,
        'pending_entries': pending_entries,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'recent_entries': recent_entries,
        'current_period': current_period,
        'today': today,
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
@perm_required('view_accounting')
def chart_of_accounts(request):
    """Chart of Accounts - List all accounts"""
    
    account_type = request.GET.get('type', '')
    search = request.GET.get('search', '')
    
    accounts = Account.objects.select_related('account_type', 'parent')
    
    if search:
        accounts = accounts.filter(
            Q(code__icontains=search) |
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    if account_type:
        accounts = accounts.filter(account_type_id=account_type)
    
    # Group by account class
    grouped_accounts = {}
    for acc_type in AccountType.objects.all():
        grouped_accounts[acc_type] = accounts.filter(account_type=acc_type)
    
    # Statistics
    total_accounts = accounts.count()
    active_accounts = accounts.filter(is_active=True).count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'grouped_accounts': grouped_accounts,
        'account_types': AccountType.objects.all(),
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'search': search,
        'selected_type': account_type,
    }
    return render(request, 'accounts/chart_of_accounts.html', context)


@login_required
@perm_required('manage_accounting')
def account_create(request):
    """Create new account"""
    
    if request.method == 'POST':
        try:
            account = Account.objects.create(
                code=request.POST.get('code'),
                name=request.POST.get('name'),
                account_type_id=request.POST.get('account_type'),
                parent_id=request.POST.get('parent') or None,
                opening_balance=Decimal(request.POST.get('opening_balance', 0)),
                opening_balance_date=request.POST.get('opening_balance_date') or None,
                is_active=request.POST.get('is_active') == 'on',
                is_bank=request.POST.get('is_bank') == 'on',
                is_cash=request.POST.get('is_cash') == 'on',
                is_payable=request.POST.get('is_payable') == 'on',
                is_receivable=request.POST.get('is_receivable') == 'on',
                bank_name=request.POST.get('bank_name', ''),
                bank_account_no=request.POST.get('bank_account_no', ''),
                description=request.POST.get('description', ''),
                created_by=request.user
            )
            messages.success(request, f'✅ Account "{account.name}" created successfully!')
            return redirect('chart_of_accounts')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'account_types': AccountType.objects.all(),
        'parent_accounts': Account.objects.filter(parent__isnull=True),
    }
    return render(request, 'accounts/account_create.html', context)


@login_required
@perm_required('view_accounting')
def journal_entry_list(request):
    """List all journal entries"""
    
    entries = JournalEntry.objects.select_related('created_by', 'approved_by').all().order_by('-entry_date', '-created_at')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        entries = entries.filter(status=status)
    
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        entries = entries.filter(entry_date__gte=from_date)
    if to_date:
        entries = entries.filter(entry_date__lte=to_date)
    
    search = request.GET.get('search', '')
    if search:
        entries = entries.filter(
            Q(entry_no__icontains=search) |
            Q(description__icontains=search) |
            Q(reference__icontains=search)
        )
    
    # Statistics
    total_entries = entries.count()
    draft_entries = entries.filter(status='draft').count()
    posted_entries = entries.filter(status='posted').count()
    reversed_entries = entries.filter(status='reversed').count()
    
    paginator = Paginator(entries, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'entries': page_obj,
        'status': status,
        'from_date': from_date,
        'to_date': to_date,
        'search': search,
        'total_entries': total_entries,
        'draft_entries': draft_entries,
        'posted_entries': posted_entries,
        'reversed_entries': reversed_entries,
        'status_choices': JournalEntry.STATUS_CHOICES,
    }
    return render(request, 'accounts/journal_entry_list.html', context)


@login_required
@perm_required('manage_accounting')
def journal_entry_create(request):
    """Create new journal entry"""
    
    if request.method == 'POST':
        try:
            entry_date = request.POST.get('entry_date')
            entry_type = request.POST.get('entry_type', 'manual')
            reference = request.POST.get('reference', '')
            description = request.POST.get('description')
            notes = request.POST.get('notes', '')
            
            # Create journal entry
            entry = JournalEntry.objects.create(
                entry_date=entry_date,
                entry_type=entry_type,
                reference=reference,
                description=description,
                notes=notes,
                created_by=request.user,
                status='draft'
            )
            
            # Get line items
            account_ids = request.POST.getlist('account_id[]')
            amounts = request.POST.getlist('amount[]')
            is_debits = request.POST.getlist('is_debit[]')
            descriptions = request.POST.getlist('item_description[]')
            
            total_debit = 0
            total_credit = 0
            
            for i in range(len(account_ids)):
                if account_ids[i] and float(amounts[i]) > 0:
                    is_debit = is_debits[i] == 'true' if i < len(is_debits) else True
                    amount = Decimal(amounts[i])
                    
                    JournalEntryItem.objects.create(
                        journal_entry=entry,
                        account_id=account_ids[i],
                        is_debit=is_debit,
                        amount=amount,
                        description=descriptions[i] if i < len(descriptions) else ''
                    )
                    
                    if is_debit:
                        total_debit += amount
                    else:
                        total_credit += amount
            
            # Check if balanced
            if total_debit != total_credit:
                entry.delete()
                messages.error(request, f'❌ Journal entry is not balanced! Debit: {total_debit}, Credit: {total_credit}')
                return redirect('journal_entry_create')
            
            # Auto-post if balanced
            if total_debit == total_credit and total_debit > 0:
                entry.post(request.user)
                messages.success(request, f'✅ Journal Entry #{entry.entry_no} created and posted!')
            else:
                messages.success(request, f'✅ Journal Entry #{entry.entry_no} created as draft!')
            
            return redirect('journal_entry_detail', pk=entry.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('journal_entry_create')
    
    accounts = Account.objects.filter(is_active=True).order_by('code')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'accounts': accounts,
        'entry_types': JournalEntry.ENTRY_TYPES,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'accounts/journal_entry_create.html', context)


@login_required
@perm_required('view_accounting')
def journal_entry_detail(request, pk):
    """Journal Entry Detail"""
    
    entry = get_object_or_404(JournalEntry.objects.prefetch_related('items', 'items__account'), pk=pk)
    items = entry.items.all()
    
    # Calculate totals
    total_debit = sum(item.amount for item in items if item.is_debit)
    total_credit = sum(item.amount for item in items if not item.is_debit)
    
    # Check permissions for actions
    can_post = entry.status == 'draft' and entry.is_balanced()
    can_reverse = entry.status == 'posted'
    can_edit = entry.status == 'draft'
    can_delete = entry.status == 'draft'
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'entry': entry,
        'items': items,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': total_debit == total_credit,
        'can_post': can_post,
        'can_reverse': can_reverse,
        'can_edit': can_edit,
        'can_delete': can_delete,
    }
    return render(request, 'accounts/journal_entry_detail.html', context)


@login_required
@perm_required('manage_accounting')
def journal_entry_post(request, pk):
    """Post a journal entry"""
    
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    if entry.status != 'draft':
        messages.error(request, '❌ Only draft entries can be posted!')
        return redirect('journal_entry_detail', pk=pk)
    
    if not entry.is_balanced():
        messages.error(request, '❌ Journal entry is not balanced! Debit must equal Credit.')
        return redirect('journal_entry_detail', pk=pk)
    
    try:
        entry.post(request.user)
        messages.success(request, f'✅ Journal Entry #{entry.entry_no} posted successfully!')
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('journal_entry_detail', pk=pk)


@login_required
@perm_required('view_accounting')
def general_ledger(request):
    """General Ledger Report"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    account_id = request.GET.get('account', '')
    
    ledgers = LedgerEntry.objects.select_related('account', 'journal_entry')
    
    if from_date:
        ledgers = ledgers.filter(date__gte=from_date)
    if to_date:
        ledgers = ledgers.filter(date__lte=to_date)
    if account_id:
        ledgers = ledgers.filter(account_id=account_id)
    
    # Get all accounts with balances
    accounts = Account.objects.filter(is_active=True)
    
    account_summary = []
    for account in accounts:
        if account_id and str(account.id) != account_id:
            continue
        
        ledger_entries = ledgers.filter(account=account)
        if not ledger_entries.exists():
            continue
        
        total_debit = ledger_entries.aggregate(total=Sum('debit'))['total'] or 0
        total_credit = ledger_entries.aggregate(total=Sum('credit'))['total'] or 0
        balance = account.current_balance()
        
        account_summary.append({
            'account': account,
            'entries': ledger_entries,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balance': balance,
        })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'account_summary': account_summary,
        'from_date': from_date,
        'to_date': to_date,
        'account_id': account_id,
        'accounts': Account.objects.filter(is_active=True),
    }
    return render(request, 'accounts/general_ledger.html', context)


@login_required
@perm_required('view_accounting')
def account_ledger(request, account_id):
    """Account Ledger - Detailed view for single account"""
    
    account = get_object_or_404(Account, pk=account_id)
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    ledgers = LedgerEntry.objects.filter(
        account=account,
        date__gte=from_date,
        date__lte=to_date
    ).order_by('date', 'id')
    
    # Calculate running balance
    running_balance = account.opening_balance
    for ledger in ledgers:
        running_balance += ledger.debit - ledger.credit
        ledger.running_balance = running_balance
    
    total_debit = ledgers.aggregate(total=Sum('debit'))['total'] or 0
    total_credit = ledgers.aggregate(total=Sum('credit'))['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'account': account,
        'ledgers': ledgers,
        'from_date': from_date,
        'to_date': to_date,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'closing_balance': account.current_balance(),
    }
    return render(request, 'accounts/account_ledger.html', context)


@login_required
@perm_required('view_accounting')
def trial_balance(request):
    """Trial Balance Report"""
    
    as_at_date = request.GET.get('as_at_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        as_at_date_obj = datetime.strptime(as_at_date, '%Y-%m-%d').date()
    except:
        as_at_date_obj = date.today()
    
    # Get all accounts with balances
    accounts = Account.objects.filter(is_active=True)
    
    trial_balance_data = []
    total_debit = 0
    total_credit = 0
    
    for account in accounts:
        balance = account.current_balance()
        
        if account.account_type.account_class in ['asset', 'expense']:
            debit = balance if balance > 0 else 0
            credit = -balance if balance < 0 else 0
        else:
            credit = balance if balance > 0 else 0
            debit = -balance if balance < 0 else 0
        
        if debit != 0 or credit != 0:
            trial_balance_data.append({
                'account': account,
                'debit': debit,
                'credit': credit,
            })
            total_debit += debit
            total_credit += credit
    
    # Check if trial balance is balanced
    is_balanced = abs(total_debit - total_credit) < 0.01
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'trial_balance_data': trial_balance_data,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': is_balanced,
        'as_at_date': as_at_date,
    }
    return render(request, 'accounts/trial_balance.html', context)


@login_required
@perm_required('view_accounting')
def balance_sheet(request):
    """Balance Sheet Report"""
    
    as_at_date = request.GET.get('as_at_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        as_at_date_obj = datetime.strptime(as_at_date, '%Y-%m-%d').date()
    except:
        as_at_date_obj = date.today()
    
    # Get account types
    asset_types = AccountType.objects.filter(account_class='asset')
    liability_types = AccountType.objects.filter(account_class='liability')
    equity_types = AccountType.objects.filter(account_class='equity')
    
    # Assets
    assets = []
    total_assets = 0
    for acc_type in asset_types:
        accounts = Account.objects.filter(account_type=acc_type, is_active=True)
        for account in accounts:
            balance = account.current_balance()
            if balance > 0:
                assets.append({'account': account, 'balance': balance})
                total_assets += balance
    
    # Liabilities
    liabilities = []
    total_liabilities = 0
    for acc_type in liability_types:
        accounts = Account.objects.filter(account_type=acc_type, is_active=True)
        for account in accounts:
            balance = account.current_balance()
            if balance > 0:
                liabilities.append({'account': account, 'balance': balance})
                total_liabilities += balance
    
    # Equity
    equities = []
    total_equity = 0
    for acc_type in equity_types:
        accounts = Account.objects.filter(account_type=acc_type, is_active=True)
        for account in accounts:
            balance = account.current_balance()
            if balance > 0:
                equities.append({'account': account, 'balance': balance})
                total_equity += balance
    
    # Check if balance sheet balances
    is_balanced = abs(total_assets - (total_liabilities + total_equity)) < 0.01
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'assets': assets,
        'liabilities': liabilities,
        'equities': equities,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'is_balanced': is_balanced,
        'as_at_date': as_at_date,
    }
    return render(request, 'accounts/balance_sheet.html', context)


@login_required
@perm_required('manage_accounting')
def account_edit(request, pk):
    """Edit an existing account"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can edit accounts.')
        return redirect('chart_of_accounts')
    
    account = get_object_or_404(Account, pk=pk)
    
    if request.method == 'POST':
        try:
            account.code = request.POST.get('code')
            account.name = request.POST.get('name')
            account.account_type_id = request.POST.get('account_type')
            account.parent_id = request.POST.get('parent') or None
            account.opening_balance = Decimal(request.POST.get('opening_balance', 0))
            account.opening_balance_date = request.POST.get('opening_balance_date') or None
            account.is_active = request.POST.get('is_active') == 'on'
            account.is_bank = request.POST.get('is_bank') == 'on'
            account.is_cash = request.POST.get('is_cash') == 'on'
            account.is_payable = request.POST.get('is_payable') == 'on'
            account.is_receivable = request.POST.get('is_receivable') == 'on'
            account.bank_name = request.POST.get('bank_name', '')
            account.bank_account_no = request.POST.get('bank_account_no', '')
            account.description = request.POST.get('description', '')
            account.save()
            
            messages.success(request, f'✅ Account "{account.name}" updated successfully!')
            return redirect('chart_of_accounts')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('account_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'account': account,
        'account_types': AccountType.objects.all(),
        'parent_accounts': Account.objects.filter(parent__isnull=True).exclude(pk=pk),
    }
    return render(request, 'accounts/account_edit.html', context)


@login_required
@perm_required('manage_accounting')
def account_delete(request, pk):
    """Delete an account"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can delete accounts.')
        return redirect('chart_of_accounts')
    
    account = get_object_or_404(Account, pk=pk)
    
    # Check if account has any transactions
    if account.journal_items.exists():
        messages.error(
            request, 
            f'❌ Cannot delete "{account.name}" because it has {account.journal_items.count()} journal entries associated with it!'
        )
        return redirect('chart_of_accounts')
    
    if request.method == 'POST':
        try:
            account_name = account.name
            account.delete()
            messages.success(request, f'🗑️ Account "{account_name}" deleted successfully!')
            return redirect('chart_of_accounts')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('chart_of_accounts')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'account': account,
    }
    return render(request, 'accounts/account_delete.html', context)


@login_required
@perm_required('manage_accounting')
def journal_entry_reverse(request, pk):
    """Reverse a posted journal entry"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can reverse journal entries.')
        return redirect('journal_entry_list')
    
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Check if entry can be reversed
    if entry.status != 'posted':
        messages.error(request, '❌ Only posted entries can be reversed!')
        return redirect('journal_entry_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            reason = request.POST.get('reason', '')
            
            # Create reversal entry
            reversal = entry.reverse(request.user, reason)
            
            messages.success(
                request, 
                f'✅ Journal Entry #{entry.entry_no} reversed successfully!\n'
                f'🔄 Reversal Entry: {reversal.entry_no}'
            )
            return redirect('journal_entry_detail', pk=reversal.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('journal_entry_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'entry': entry,
        'items': entry.items.all(),
        'total_debit': entry.total_debit(),
        'total_credit': entry.total_credit(),
    }
    return render(request, 'accounts/journal_entry_reverse.html', context)


@login_required
@perm_required('manage_accounting')
def journal_entry_delete(request, pk):
    """Delete a journal entry"""
    
    entry = get_object_or_404(JournalEntry, pk=pk)
    
    # Only draft entries can be deleted
    if entry.status != 'draft':
        messages.error(request, '❌ Only draft entries can be deleted!')
        return redirect('journal_entry_detail', pk=pk)
    
    if request.method == 'POST':
        entry_no = entry.entry_no
        entry.delete()
        messages.success(request, f'🗑️ Journal Entry #{entry_no} deleted successfully!')
        return redirect('journal_entry_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'entry': entry,
    }
    return render(request, 'accounts/journal_entry_delete.html', context)


@login_required
@perm_required('view_accounting')
def generate_trial_balance(request):
    """Generate trial balance report"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can generate trial balance.')
        return redirect('dashboard')
    
    as_at_date = request.GET.get('as_at_date', date.today().strftime('%Y-%m-%d'))
    
    # Get all active accounts with their account types
    accounts = Account.objects.select_related('account_type').filter(is_active=True)
    
    trial_balance_data = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    
    for account in accounts:
        balance = account.current_balance()
        
        # Determine if account has debit or credit balance based on account class
        if account.account_type.account_class in ['asset', 'expense']:
            # Asset and Expense accounts have debit balance
            if balance > 0:
                debit = balance
                credit = Decimal('0.00')
            else:
                debit = Decimal('0.00')
                credit = abs(balance)
        else:
            # Liability, Equity, Income accounts have credit balance
            if balance > 0:
                debit = Decimal('0.00')
                credit = balance
            else:
                debit = abs(balance)
                credit = Decimal('0.00')
        
        # Only include accounts with non-zero balance
        if debit != 0 or credit != 0:
            trial_balance_data.append({
                'account': account,
                'debit': debit,
                'credit': credit,
            })
            total_debit += debit
            total_credit += credit
    
    # Check if trial balance is balanced
    is_balanced = abs(total_debit - total_credit) < Decimal('0.01')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'trial_balance_data': trial_balance_data,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': is_balanced,
        'as_at_date': as_at_date,
        'total_accounts': len(trial_balance_data),
    }
    return render(request, 'accounts/trial_balance.html', context)


@login_required
@perm_required('view_accounting')
def profit_loss_statement(request):
    """Generate Profit & Loss Statement"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    # Get income accounts (Revenue)
    income_accounts = Account.objects.filter(
        account_type__account_class='income',
        is_active=True
    )
    
    # Get expense accounts
    expense_accounts = Account.objects.filter(
        account_type__account_class='expense',
        is_active=True
    )
    
    # Calculate income
    total_income = Decimal('0.00')
    income_data = []
    
    for account in income_accounts:
        balance = account.current_balance()
        if balance != 0:
            income_data.append({
                'account': account,
                'amount': balance
            })
            total_income += balance
    
    # Calculate expenses
    total_expenses = Decimal('0.00')
    expense_data = []
    
    for account in expense_accounts:
        balance = account.current_balance()
        if balance != 0:
            expense_data.append({
                'account': account,
                'amount': balance
            })
            total_expenses += balance
    
    # Calculate net profit/loss
    net_profit = total_income - total_expenses
    profit_margin = (net_profit / total_income * 100) if total_income > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'income_data': income_data,
        'expense_data': expense_data,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'profit_margin': profit_margin,
        'is_profit': net_profit > 0,
        'is_loss': net_profit < 0,
    }
    return render(request, 'accounts/profit_loss.html', context)


@login_required
@perm_required('view_accounting')
def cash_flow_statement(request):
    """Generate Cash Flow Statement"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    # Cash Inflows
    # 1. Cash Sales
    cash_sales = Sale.objects.filter(
        sale_date__date__gte=from_date,
        sale_date__date__lte=to_date
    ).aggregate(total=Sum('paid'))['total'] or Decimal('0.00')
    
    # 2. Cash from customers (payment received)
    cash_received = SalePayment.objects.filter(
        payment_date__date__gte=from_date,
        payment_date__date__lte=to_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Cash Outflows
    # 1. Cash Purchases
    cash_purchases = Purchase.objects.filter(
        pur_date__date__gte=from_date,
        pur_date__date__lte=to_date
    ).aggregate(total=Sum('paid'))['total'] or Decimal('0.00')
    
    # 2. Cash Expenses
    cash_expenses = Expense.objects.filter(
        expense_date__gte=from_date,
        expense_date__lte=to_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate totals
    total_inflow = cash_sales + cash_received
    total_outflow = cash_purchases + cash_expenses
    net_cash_flow = total_inflow - total_outflow
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'cash_sales': cash_sales,
        'cash_received': cash_received,
        'total_inflow': total_inflow,
        'cash_purchases': cash_purchases,
        'cash_expenses': cash_expenses,
        'total_outflow': total_outflow,
        'net_cash_flow': net_cash_flow,
        'is_positive': net_cash_flow >= 0,
        'is_negative': net_cash_flow < 0,
    }
    return render(request, 'accounts/cash_flow.html', context)


@login_required
@perm_required('view_accounting')
def financial_periods(request):
    """List all financial periods"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can view financial periods.')
        return redirect('dashboard')
    
    periods = FinancialPeriod.objects.all().order_by('-start_date')
    
    # Calculate status for each period
    today = date.today()
    for period in periods:
        if period.is_closed:
            period.status_display = '🔒 Closed'
            period.status_color = 'secondary'
        elif period.start_date <= today <= period.end_date:
            period.status_display = '✅ Active'
            period.status_color = 'success'
        elif period.end_date < today:
            period.status_display = '⏰ Expired'
            period.status_color = 'warning'
        else:
            period.status_display = '📅 Upcoming'
            period.status_color = 'info'
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'periods': periods,
        'total_periods': periods.count(),
        'active_periods': periods.filter(is_closed=False).count(),
        'closed_periods': periods.filter(is_closed=True).count(),
    }
    return render(request, 'accounts/periods.html', context)


@login_required
@perm_required('manage_accounting')
def financial_period_create(request):
    """Create new financial period"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can create financial periods.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            period_type = request.POST.get('period_type')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            # Validate dates
            if start_date > end_date:
                messages.error(request, '❌ Start date cannot be after end date!')
                return redirect('financial_period_create')
            
            # Check for overlapping periods
            overlapping = FinancialPeriod.objects.filter(
                start_date__lte=end_date,
                end_date__gte=start_date
            ).exists()
            
            if overlapping:
                messages.error(request, '❌ This period overlaps with an existing period!')
                return redirect('financial_period_create')
            
            period = FinancialPeriod.objects.create(
                name=name,
                period_type=period_type,
                start_date=start_date,
                end_date=end_date
            )
            
            messages.success(request, f'✅ Financial Period "{period.name}" created successfully!')
            return redirect('financial_periods')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('financial_period_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'period_types': FinancialPeriod.PERIOD_TYPES,
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'accounts/period_create.html', context)


@login_required
@perm_required('manage_accounting')
def financial_period_close(request, pk):
    """Close a financial period"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can close financial periods.')
        return redirect('dashboard')
    
    period = get_object_or_404(FinancialPeriod, pk=pk)
    
    if period.is_closed:
        messages.warning(request, f'⚠️ Period "{period.name}" is already closed!')
        return redirect('financial_periods')
    
    if request.method == 'POST':
        try:
            period.is_closed = True
            period.closed_by = request.user
            period.closed_at = now()
            period.save()
            
            messages.success(request, f'✅ Period "{period.name}" closed successfully!')
            return redirect('financial_periods')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('financial_periods')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'period': period,
    }
    return render(request, 'accounts/period_close.html', context)


@login_required
@perm_required('view_accounting')
def accounts_reports(request):
    """Accounts Reports Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can view accounts reports.')
        return redirect('dashboard')
    
    # Get report type
    report_type = request.GET.get('type', 'summary')
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    # Get financial periods
    periods = FinancialPeriod.objects.all().order_by('-start_date')
    
    # Summary Statistics
    total_accounts = Account.objects.filter(is_active=True).count()
    total_journal_entries = JournalEntry.objects.filter(status='posted').count()
    total_debit = JournalEntryItem.objects.filter(is_debit=True).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_credit = JournalEntryItem.objects.filter(is_debit=False).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Account balances by type
    account_balances = {}
    for account_type in ['asset', 'liability', 'equity', 'income', 'expense']:
        accounts = Account.objects.filter(
            account_type__account_class=account_type,
            is_active=True
        )
        total = sum(a.current_balance() for a in accounts)
        account_balances[account_type] = {
            'count': accounts.count(),
            'total': total,
            'formatted': f"Rs. {total:,.2f}"
        }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report_type': report_type,
        'from_date': from_date,
        'to_date': to_date,
        'periods': periods,
        'total_accounts': total_accounts,
        'total_journal_entries': total_journal_entries,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'account_balances': account_balances,
        'current_period': FinancialPeriod.objects.filter(
            start_date__lte=date.today(),
            end_date__gte=date.today(),
            is_closed=False
        ).first(),
    }
    return render(request, 'accounts/reports.html', context)


@login_required
@perm_required('view_accounting')
def export_accounts_report(request):
    """Export accounts report to Excel - FIXED"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can export accounts reports.')
        return redirect('dashboard')
    
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    
    wb = Workbook()
    
    # ========================================== #
    # SHEET 1: Summary                          #
    # ========================================== #
    ws1 = wb.active
    ws1.title = "Summary"
    
    # Title
    ws1.merge_cells('A1:D1')
    ws1['A1'] = "ACCOUNTS REPORT"
    ws1['A1'].font = Font(bold=True, size=16)
    ws1['A1'].alignment = Alignment(horizontal='center')
    
    ws1.merge_cells('A2:D2')
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    ws1['A2'] = company_name
    ws1['A2'].alignment = Alignment(horizontal='center')
    
    ws1.merge_cells('A3:D3')
    ws1['A3'] = f"Generated: {date.today().strftime('%d-%m-%Y %I:%M %p')}"
    ws1['A3'].alignment = Alignment(horizontal='center')
    
    # Account Type Summary
    row = 5
    ws1.cell(row=row, column=1, value="Account Type").font = Font(bold=True)
    ws1.cell(row=row, column=2, value="Count").font = Font(bold=True)
    ws1.cell(row=row, column=3, value="Total Balance").font = Font(bold=True)
    ws1.cell(row=row, column=4, value="Status").font = Font(bold=True)
    
    # Style headers
    header_fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col in range(1, 5):
        cell = ws1.cell(row=row, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    
    row += 1
    account_types = ['asset', 'liability', 'equity', 'income', 'expense']
    for acc_type in account_types:
        accounts = Account.objects.filter(
            account_type__account_class=acc_type,
            is_active=True
        )
        total = sum(a.current_balance() for a in accounts)
        
        ws1.cell(row=row, column=1, value=acc_type.title())
        ws1.cell(row=row, column=2, value=accounts.count())
        ws1.cell(row=row, column=3, value=float(total))
        ws1.cell(row=row, column=3).number_format = '#,##0.00'
        ws1.cell(row=row, column=4, value="Active" if accounts.count() > 0 else "No Accounts")
        row += 1
    
    # Total row
    total_accounts = Account.objects.filter(is_active=True).count()
    total_balance = Account.objects.filter(is_active=True).aggregate(
        total=Sum('opening_balance')
    )['total'] or 0
    
    ws1.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
    ws1.cell(row=row, column=2, value=total_accounts).font = Font(bold=True)
    ws1.cell(row=row, column=3, value=float(total_balance)).font = Font(bold=True)
    ws1.cell(row=row, column=3).number_format = '#,##0.00'
    
    # ========================================== #
    # SHEET 2: All Accounts                     #
    # ========================================== #
    ws2 = wb.create_sheet("All Accounts")
    
    headers = ['Code', 'Name', 'Account Type', 'Class', 'Parent', 'Opening Balance', 'Current Balance', 'Status']
    for col, header in enumerate(headers, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")
    
    row = 2
    for account in Account.objects.filter(is_active=True).order_by('code'):
        ws2.cell(row=row, column=1, value=account.code)
        ws2.cell(row=row, column=2, value=account.name)
        ws2.cell(row=row, column=3, value=account.account_type.name if account.account_type else '')
        ws2.cell(row=row, column=4, value=account.account_type.account_class if account.account_type else '')
        ws2.cell(row=row, column=5, value=account.parent.name if account.parent else '')
        ws2.cell(row=row, column=6, value=float(account.opening_balance))
        ws2.cell(row=row, column=6).number_format = '#,##0.00'
        ws2.cell(row=row, column=7, value=float(account.current_balance()))
        ws2.cell(row=row, column=7).number_format = '#,##0.00'
        ws2.cell(row=row, column=8, value="Active" if account.is_active else "Inactive")
        row += 1
    
    # ========================================== #
    # SHEET 3: Journal Entries                   #
    # ========================================== #
    ws3 = wb.create_sheet("Journal Entries")
    
    headers = ['Entry No', 'Date', 'Type', 'Description', 'Reference', 'Debit', 'Credit', 'Status']
    for col, header in enumerate(headers, 1):
        cell = ws3.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")
    
    row = 2
    entries = JournalEntry.objects.filter(status='posted').order_by('-entry_date')[:100]
    total_debit = 0
    total_credit = 0
    
    for entry in entries:
        ws3.cell(row=row, column=1, value=entry.entry_no)
        ws3.cell(row=row, column=2, value=entry.entry_date.strftime('%d-%m-%Y'))
        ws3.cell(row=row, column=3, value=entry.get_entry_type_display())
        ws3.cell(row=row, column=4, value=entry.description[:50])
        ws3.cell(row=row, column=5, value=entry.reference or '')
        debit = entry.total_debit()
        credit = entry.total_credit()
        ws3.cell(row=row, column=6, value=float(debit))
        ws3.cell(row=row, column=6).number_format = '#,##0.00'
        ws3.cell(row=row, column=7, value=float(credit))
        ws3.cell(row=row, column=7).number_format = '#,##0.00'
        ws3.cell(row=row, column=8, value=entry.get_status_display())
        total_debit += debit
        total_credit += credit
        row += 1
    
    # Total row
    ws3.cell(row=row, column=5, value="TOTAL").font = Font(bold=True)
    ws3.cell(row=row, column=6, value=float(total_debit)).font = Font(bold=True)
    ws3.cell(row=row, column=6).number_format = '#,##0.00'
    ws3.cell(row=row, column=7, value=float(total_credit)).font = Font(bold=True)
    ws3.cell(row=row, column=7).number_format = '#,##0.00'
    
    # ========================================== #
    # SHEET 4: Journal Entry Items               #
    # ========================================== #
    ws4 = wb.create_sheet("Entry Items")
    
    headers = ['Entry No', 'Account', 'Debit', 'Credit', 'Description']
    for col, header in enumerate(headers, 1):
        cell = ws4.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1a1d2e", end_color="1a1d2e", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")
    
    row = 2
    for entry in entries[:50]:
        for item in entry.items.all():
            ws4.cell(row=row, column=1, value=entry.entry_no)
            ws4.cell(row=row, column=2, value=item.account.name)
            if item.is_debit:
                ws4.cell(row=row, column=3, value=float(item.amount))
                ws4.cell(row=row, column=3).number_format = '#,##0.00'
                ws4.cell(row=row, column=4, value='')
            else:
                ws4.cell(row=row, column=3, value='')
                ws4.cell(row=row, column=4, value=float(item.amount))
                ws4.cell(row=row, column=4).number_format = '#,##0.00'
            ws4.cell(row=row, column=5, value=item.description or '')
            row += 1
    
    # ========================================== #
    # AUTO-FIT COLUMNS - FIXED                   #
    # ========================================== #
    
    # Function to auto-fit columns without using column_letter on MergedCell
    def auto_fit_columns(ws):
        for col_idx in range(1, ws.max_column + 1):
            max_length = 0
            col_letter = get_column_letter(col_idx)
            
            # Check all rows for this column
            for row_idx in range(1, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                try:
                    if cell.value:
                        length = len(str(cell.value))
                        if length > max_length:
                            max_length = length
                except:
                    pass
            
            # Set width (max 50 characters)
            adjusted_width = min(max_length + 2, 50)
            if adjusted_width > 5:  # Only set if width > 5
                ws.column_dimensions[col_letter].width = adjusted_width
    
    # Auto-fit all sheets
    for ws in [ws1, ws2, ws3, ws4]:
        auto_fit_columns(ws)
    
    # ========================================== #
    # RESPONSE                                   #
    # ========================================== #
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"Accounts_Report_{date.today().strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
