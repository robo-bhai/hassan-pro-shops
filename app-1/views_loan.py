from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from datetime import datetime, timedelta, date
from decimal import Decimal
from app.models import (
    CompanyInfo, LoanProvider, Borrower, Loan, 
    LoanPayment, LoanEMI, LoanCollateral
)


@login_required
def loan_dashboard(request):
    """Loan Management Dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    total_loans = Loan.objects.count()
    active_loans = Loan.objects.filter(status='active').count()
    pending_loans = Loan.objects.filter(status='pending').count()
    defaulted_loans = Loan.objects.filter(status='defaulted').count()
    
    total_principal = Loan.objects.aggregate(total=Sum('principal'))['total'] or 0
    total_paid = Loan.objects.aggregate(total=Sum('paid_amount'))['total'] or 0
    total_outstanding = total_principal - total_paid
    
    recent_loans = Loan.objects.order_by('-created_at')[:10]
    overdue_loans = []
    for loan in Loan.objects.filter(status__in=['active', 'partial']):
        if loan.is_overdue():
            overdue_loans.append(loan)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_loans': total_loans,
        'active_loans': active_loans,
        'pending_loans': pending_loans,
        'defaulted_loans': defaulted_loans,
        'total_principal': total_principal,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'recent_loans': recent_loans,
        'overdue_loans': overdue_loans,
    }
    return render(request, 'loan/dashboard.html', context)


@login_required
def borrower_list(request):
    """List all borrowers"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    borrowers = Borrower.objects.all()
    
    search = request.GET.get('search', '')
    if search:
        borrowers = borrowers.filter(
            Q(name__icontains=search) |
            Q(borrower_code__icontains=search) |
            Q(phone__icontains=search)
        )
    
    paginator = Paginator(borrowers, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
    }
    return render(request, 'loan/borrowers.html', context)


@login_required
def borrower_create(request):
    """Create new borrower"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            borrower = Borrower.objects.create(
                name=request.POST.get('name'),
                borrower_type=request.POST.get('borrower_type'),
                cnic=request.POST.get('cnic', ''),
                email=request.POST.get('email', ''),
                phone=request.POST.get('phone'),
                address=request.POST.get('address'),
                company_name=request.POST.get('company_name', ''),
                registration_no=request.POST.get('registration_no', ''),
                bank_name=request.POST.get('bank_name', ''),
                account_number=request.POST.get('account_number', ''),
                account_title=request.POST.get('account_title', ''),
                iban=request.POST.get('iban', ''),
                credit_score=int(request.POST.get('credit_score', 0)),
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            messages.success(request, f'✅ Borrower "{borrower.name}" created!')
            return redirect('borrower_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'borrower_types': Borrower.BORROWER_TYPES,
    }
    return render(request, 'loan/borrower_create.html', context)


@login_required
def loan_list(request):
    """List all loans"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    loans = Loan.objects.select_related('borrower', 'provider').all()
    
    status = request.GET.get('status', '')
    if status:
        loans = loans.filter(status=status)
    
    loan_type = request.GET.get('type', '')
    if loan_type:
        loans = loans.filter(loan_type=loan_type)
    
    search = request.GET.get('search', '')
    if search:
        loans = loans.filter(
            Q(loan_no__icontains=search) |
            Q(borrower__name__icontains=search)
        )
    
    paginator = Paginator(loans, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'loan_type': loan_type,
        'status_choices': Loan.LOAN_STATUS,
        'loan_types': Loan.LOAN_TYPES,
    }
    return render(request, 'loan/loans.html', context)


@login_required
def loan_create(request):
    """Create new loan application"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            loan = Loan.objects.create(
                borrower_id=request.POST.get('borrower'),
                loan_type=request.POST.get('loan_type'),
                provider_id=request.POST.get('provider') or None,
                principal=Decimal(request.POST.get('principal', 0)),
                interest_rate=Decimal(request.POST.get('interest_rate', 0)),
                processing_fee=Decimal(request.POST.get('processing_fee', 0)),
                late_fee_per_day=Decimal(request.POST.get('late_fee_per_day', 0)),
                tenure_months=int(request.POST.get('tenure_months', 12)),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                collateral_type=request.POST.get('collateral_type', ''),
                collateral_value=Decimal(request.POST.get('collateral_value', 0)),
                collateral_description=request.POST.get('collateral_description', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='pending'
            )
            
            # Generate EMI schedule
            generate_emi_schedule(loan)
            
            messages.success(request, f'✅ Loan #{loan.loan_no} created!')
            return redirect('loan_detail', pk=loan.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    borrowers = Borrower.objects.filter(status='active')
    providers = LoanProvider.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'borrowers': borrowers,
        'providers': providers,
        'loan_types': Loan.LOAN_TYPES,
    }
    return render(request, 'loan/loan_create.html', context)


def generate_emi_schedule(loan):
    """Generate EMI schedule for loan"""
    from datetime import timedelta
    
    # Clear existing EMIs
    loan.emis.all().delete()
    
    for i in range(1, loan.tenure_months + 1):
        due_date = loan.start_date + timedelta(days=30 * i)
        LoanEMI.objects.create(
            loan=loan,
            emi_number=i,
            due_date=due_date,
            amount_due=loan.emi_amount
        )
    
    # Update next due date
    first_emi = loan.emis.order_by('due_date').first()
    if first_emi:
        loan.next_due_date = first_emi.due_date
        loan.save()


@login_required
def loan_detail(request, pk):
    """Loan detail view"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    loan = get_object_or_404(Loan, pk=pk)
    emis = loan.emis.all().order_by('emi_number')
    payments = loan.payments.all().order_by('-payment_date')
    collaterals = loan.collaterals.all()
    
    # Calculate stats
    total_emis = emis.count()
    paid_emis = emis.filter(status='paid').count()
    overdue_emis = emis.filter(status='overdue').count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'loan': loan,
        'emis': emis,
        'payments': payments,
        'collaterals': collaterals,
        'total_emis': total_emis,
        'paid_emis': paid_emis,
        'overdue_emis': overdue_emis,
        'outstanding': loan.outstanding_balance(),
        'is_overdue': loan.is_overdue(),
    }
    return render(request, 'loan/loan_detail.html', context)


@login_required
def loan_approve(request, pk):
    """Approve loan"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    loan = get_object_or_404(Loan, pk=pk)
    
    if loan.status != 'pending':
        messages.error(request, 'Only pending loans can be approved!')
        return redirect('loan_detail', pk=pk)
    
    loan.status = 'approved'
    loan.approval_date = date.today()
    loan.approved_by = request.user
    loan.save()
    
    messages.success(request, f'✅ Loan #{loan.loan_no} approved!')
    return redirect('loan_detail', pk=pk)


@login_required
def loan_disburse(request, pk):
    """Disburse loan"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    loan = get_object_or_404(Loan, pk=pk)
    
    if loan.status != 'approved':
        messages.error(request, 'Loan must be approved first!')
        return redirect('loan_detail', pk=pk)
    
    loan.status = 'active'
    loan.disbursement_date = date.today()
    loan.save()
    
    messages.success(request, f'💰 Loan #{loan.loan_no} disbursed!')
    return redirect('loan_detail', pk=pk)


@login_required
def loan_make_payment(request, pk):
    """Make loan payment"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    loan = get_object_or_404(Loan, pk=pk)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_method = request.POST.get('payment_method', 'cash')
            reference_no = request.POST.get('reference_no', '')
            notes = request.POST.get('notes', '')
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero!')
                return redirect('loan_make_payment', pk=pk)
            
            if amount > loan.outstanding_balance():
                messages.error(request, f'Amount cannot exceed outstanding: Rs. {loan.outstanding_balance():,.2f}')
                return redirect('loan_make_payment', pk=pk)
            
            # Create payment
            payment = LoanPayment.objects.create(
                loan=loan,
                amount=amount,
                payment_method=payment_method,
                reference_no=reference_no,
                notes=notes,
                created_by=request.user,
                status='completed'
            )
            
            # Update loan
            loan.paid_amount += amount
            loan.status = 'paid' if loan.paid_amount >= loan.total_payable else 'partial'
            loan.save()
            
            # Update EMIs (FIFO)
            remaining = amount
            for emi in loan.emis.filter(status__in=['pending', 'overdue']).order_by('due_date'):
                if remaining <= 0:
                    break
                due = emi.remaining()
                if remaining >= due:
                    emi.amount_paid = emi.amount_due
                    emi.status = 'paid'
                    emi.paid_at = now()
                    emi.payment = payment
                    remaining -= due
                else:
                    emi.amount_paid += remaining
                    emi.status = 'partial'
                    remaining = 0
                emi.save()
            
            messages.success(request, f'✅ Payment of Rs. {amount:,.2f} received!')
            return redirect('loan_detail', pk=pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'loan': loan,
        'payment_methods': LoanPayment.PAYMENT_METHODS,
    }
    return render(request, 'loan/loan_payment.html', context)


@login_required
def loan_provider_list(request):
    """List loan providers"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    providers = LoanProvider.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'providers': providers,
    }
    return render(request, 'loan/providers.html', context)


@login_required
def loan_provider_create(request):
    """Create loan provider"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            provider = LoanProvider.objects.create(
                name=request.POST.get('name'),
                provider_type=request.POST.get('provider_type'),
                contact_person=request.POST.get('contact_person', ''),
                email=request.POST.get('email', ''),
                phone=request.POST.get('phone', ''),
                address=request.POST.get('address', ''),
                website=request.POST.get('website', ''),
                is_active=request.POST.get('is_active') == 'on'
            )
            messages.success(request, f'✅ Provider "{provider.name}" created!')
            return redirect('loan_provider_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'provider_types': LoanProvider.PROVIDER_TYPES,
    }
    return render(request, 'loan/provider_create.html', context)