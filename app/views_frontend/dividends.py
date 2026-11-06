"""Frontend views: dividends."""
from ..models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ..models import CashBalance, Shareholder, Share, Dividend, DividendPayment, ShareholderCashBalance, CompanyInfo, Product


@login_required
def dividend_create(request):
    """Create new dividend - Admin & Store Manager"""
    
    # ✅ CHECK: Admin OR Store Manager allowed
    is_admin = request.user.is_superuser
    is_store_manager = request.user.groups.filter(name='Store Manager').exists()
    
    if not (is_admin or is_store_manager):
        messages.error(request, '❌ Access denied! Only Admin or Store Manager can create dividends.')
        return redirect('dividend_list')
    
    if request.method == 'POST':
        try:
            amount_per_share = Decimal(request.POST.get('amount_per_share', 0))
            declaration_date = request.POST.get('declaration_date')
            record_date = request.POST.get('record_date')
            payment_date = request.POST.get('payment_date') or None
            is_interim = request.POST.get('is_interim') == 'on'
            notes = request.POST.get('notes', '')
            
            # Get custom percentages
            admin_percentage = Decimal(request.POST.get('admin_percentage', 5))
            manager_percentage = Decimal(request.POST.get('manager_percentage', 28))
            
            # Validate percentages
            total_percentage = admin_percentage + manager_percentage
            shareholders_percentage = Decimal('100') - total_percentage
            
            if shareholders_percentage < 0:
                messages.error(
                    request, 
                    f'❌ Admin ({admin_percentage}%) + Manager ({manager_percentage}%) cannot exceed 100%!'
                )
                return redirect('dividend_create')
            
            if amount_per_share <= 0:
                messages.error(request, '❌ Amount per share must be greater than zero!')
                return redirect('dividend_create')
            
            total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
            if total_shares == 0:
                messages.error(request, '❌ No shares found!')
                return redirect('dividend_create')
            
            total_profit = get_total_profit()
            total_dividend = amount_per_share * total_shares
            
            if total_dividend > total_profit:
                max_per_share = (total_profit / total_shares)
                messages.error(
                    request, 
                    f'❌ Dividend exceeds profit! Max per share: Rs. {max_per_share:,.2f}'
                )
                return redirect('dividend_create')
            
            # CREATE DIVIDEND WITH ALLOCATIONS
            dividend = Dividend.objects.create(
                amount_per_share=amount_per_share,
                declaration_date=declaration_date,
                record_date=record_date,
                payment_date=payment_date,
                is_interim=is_interim,
                notes=notes,
                created_by=request.user,
                status='declared',
                admin_percentage=admin_percentage,
                manager_percentage=manager_percentage,
                shareholders_percentage=shareholders_percentage
            )
            
            # CREATE ALLOCATION RECORDS
            dividend.generate_allocations(request.user)
            
            messages.success(
                request, 
                f'✅ Dividend #{dividend.dividend_no} created!\n'
                f'📊 Admin: {admin_percentage}% (Rs. {dividend.admin_amount:,.2f})\n'
                f'👔 Manager: {manager_percentage}% (Rs. {dividend.manager_amount:,.2f})\n'
                f'👥 Shareholders: {shareholders_percentage}% (Rs. {dividend.shareholders_amount:,.2f})'
            )
            return redirect('dividend_detail', pk=dividend.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('dividend_create')
    
    # GET REQUEST - Show form
    total_profit = get_total_profit()
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    max_per_share = (total_profit / total_shares) if total_shares > 0 else 0
    recommended_50 = max_per_share * Decimal('0.5')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_profit': total_profit,
        'total_shares': total_shares,
        'max_per_share': max_per_share,
        'recommended_50': recommended_50,
        'today': date.today().strftime('%Y-%m-%d'),
        'is_admin': request.user.is_superuser,
        'is_store_manager': request.user.groups.filter(name='Store Manager').exists(),
    }
    return render(request, 'shareholders/dividend_create.html', context)


@login_required
def dividend_edit(request, pk):
    """Edit dividend allocation - Only Admin"""
    
    # ✅ CHECK: Sirf superuser allowed
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only Admin can edit dividend allocations.')
        return redirect('dividend_detail', pk=pk)
    
    dividend = get_object_or_404(Dividend, pk=pk)
    
    if dividend.status in ['distributed', 'cancelled']:
        messages.error(request, '❌ Cannot edit distributed or cancelled dividend!')
        return redirect('dividend_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            admin_percentage = Decimal(request.POST.get('admin_percentage', 5))
            manager_percentage = Decimal(request.POST.get('manager_percentage', 28))
            
            total_percentage = admin_percentage + manager_percentage
            shareholders_percentage = Decimal('100') - total_percentage
            
            if shareholders_percentage < 0:
                messages.error(request, '❌ Admin + Manager cannot exceed 100%!')
                return redirect('dividend_edit', pk=pk)
            
            dividend.admin_percentage = admin_percentage
            dividend.manager_percentage = manager_percentage
            dividend.shareholders_percentage = shareholders_percentage
            
            dividend.calculate_allocation()
            dividend.generate_allocations(request.user)
            
            messages.success(
                request, 
                f'✅ Dividend #{dividend.dividend_no} allocations updated!'
            )
            return redirect('dividend_detail', pk=dividend.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('dividend_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
        'is_admin': request.user.is_superuser,
    }
    return render(request, 'shareholders/dividend_edit.html', context)


@login_required
def mark_allocation_paid(request, pk):
    """Mark admin/manager allocation as paid - Admin & Store Manager"""
    
    allocation = get_object_or_404(DividendAllocation, pk=pk)
    
    # ✅ CHECK: Admin OR Store Manager allowed
    is_admin = request.user.is_superuser
    is_store_manager = request.user.groups.filter(name='Store Manager').exists()
    
    if not (is_admin or is_store_manager):
        messages.error(request, '❌ Access denied! Only Admin or Store Manager can mark allocations as paid.')
        return redirect('dividend_detail', pk=allocation.dividend.pk)
    
    if allocation.allocation_type == 'shareholders':
        messages.error(request, '❌ Shareholder allocations are handled separately!')
        return redirect('dividend_detail', pk=allocation.dividend.pk)
    
    if allocation.is_paid:
        messages.warning(request, '⚠️ This allocation is already paid!')
        return redirect('dividend_detail', pk=allocation.dividend.pk)
    
    if request.method == 'POST':
        try:
            payment_method = request.POST.get('payment_method', 'Bank Transfer')
            reference_no = request.POST.get('reference_no', '')
            
            # Check cash balance
            current_balance = CashBalance.get_balance()
            if current_balance < allocation.amount:
                messages.error(
                    request, 
                    f'❌ Insufficient cash balance! Available: Rs. {current_balance:,.2f}, Required: Rs. {allocation.amount:,.2f}'
                )
                return redirect('dividend_detail', pk=allocation.dividend.pk)
            
            # Mark as paid
            allocation.mark_paid(request.user, payment_method, reference_no)
            
            messages.success(
                request, 
                f'✅ {allocation.get_allocation_type_display()} allocation of Rs. {allocation.amount:,.2f} marked as paid!'
            )
            return redirect('dividend_detail', pk=allocation.dividend.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('dividend_detail', pk=allocation.dividend.pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'allocation': allocation,
        'dividend': allocation.dividend,
        'current_balance': CashBalance.get_balance(),
        'is_admin': request.user.is_superuser,
        'is_store_manager': request.user.groups.filter(name='Store Manager').exists(),
    }
    return render(request, 'shareholders/allocation_pay.html', context)


@login_required
def dividend_detail(request, pk):
    """Dividend detail view with allocation breakdown"""
    
    dividend = get_object_or_404(Dividend, pk=pk)
    payments = dividend.payments.all().order_by('-created_at')
    allocations = dividend.allocations.all()
    
    # Allocations
    admin_allocation = allocations.filter(allocation_type='admin').first()
    manager_allocation = allocations.filter(allocation_type='manager').first()
    shareholders_allocation = allocations.filter(allocation_type='shareholders').first()
    
    # Payment stats
    total_paid = payments.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0
    total_pending = payments.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0
    paid_count = payments.filter(status='paid').count()
    pending_count = payments.filter(status='pending').count()
    total_payments = payments.count()
    
    # Profit stats
    total_profit = get_total_profit()
    remaining_profit = total_profit - dividend.total_amount
    dividend_percent = (dividend.total_amount / total_profit * 100) if total_profit > 0 else 0
    
    # ✅ Check if user is admin
    is_admin = request.user.is_superuser
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
        'payments': payments,
        'allocations': allocations,
        'admin_allocation': admin_allocation,
        'manager_allocation': manager_allocation,
        'shareholders_allocation': shareholders_allocation,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'paid_count': paid_count,
        'pending_count': pending_count,
        'total_payments': total_payments,
        'total_profit': total_profit,
        'remaining_profit': remaining_profit,
        'dividend_percent': dividend_percent,
        'is_admin': is_admin,  # ✅ Pass to template
    }
    return render(request, 'shareholders/dividend_detail.html', context)


@login_required
def generate_dividend_payments(request, pk):
    """Generate payments for a dividend - Only Admin"""
    
    # ✅ CHECK: Sirf superuser allowed
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only Admin can generate dividend payments.')
        return redirect('dividend_detail', pk=pk)
    
    dividend = get_object_or_404(Dividend, pk=pk)
    
    if dividend.status not in ['declared', 'approved']:
        messages.error(request, '❌ Dividend must be declared or approved to generate payments!')
        return redirect('dividend_detail', pk=pk)
    
    total_profit = get_total_profit()
    if dividend.total_amount > total_profit:
        messages.error(
            request, 
            f'❌ Cannot generate payments! Dividend (Rs. {dividend.total_amount:,.2f}) '
            f'exceeds profit (Rs. {total_profit:,.2f})'
        )
        return redirect('dividend_detail', pk=pk)
    
    try:
        count = dividend.generate_shareholder_payments(request.user)
        
        if count == 0:
            messages.warning(request, '⚠️ No active shareholders found with shares!')
            return redirect('dividend_detail', pk=pk)
        
        messages.success(
            request, 
            f'✅ {count} dividend payments generated! Total: Rs. {dividend.total_amount:,.2f}'
        )
        
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('dividend_detail', pk=pk)


@login_required
def mark_dividend_paid(request, pk):
    """Mark a dividend payment as paid - Only Admin"""
    
    # ✅ CHECK: Sirf superuser allowed
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only Admin can mark payments as paid.')
        return redirect('dividend_detail', pk=pk)
    
    payment = get_object_or_404(DividendPayment, pk=pk)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'Bank Transfer')
        reference_no = request.POST.get('reference_no', '')
        notes = request.POST.get('notes', '')
        
        if payment.status == 'paid':
            messages.warning(request, '⚠️ This payment is already marked as paid!')
            return redirect('dividend_detail', pk=payment.dividend.pk)
        
        current_balance = CashBalance.get_balance()
        if current_balance < payment.amount:
            messages.error(
                request, 
                f'❌ Insufficient cash balance! Available: Rs. {current_balance:,.2f}, '
                f'Required: Rs. {payment.amount:,.2f}'
            )
            return redirect('dividend_detail', pk=payment.dividend.pk)
        
        payment.mark_paid(payment_method, reference_no, request.user)
        
        if notes:
            payment.notes = notes
            payment.save()
        
        messages.success(
            request, 
            f'✅ Payment of Rs. {payment.amount:,.2f} marked as paid! '
            f'New cash balance: Rs. {CashBalance.get_balance():,.2f}'
        )
        return redirect('dividend_detail', pk=payment.dividend.pk)
    
    # GET request - show form
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'payment': payment,
        'dividend': payment.dividend,
        'current_balance': CashBalance.get_balance(),
        'is_admin': request.user.is_superuser,
    }
    return render(request, 'shareholders/dividend_mark_paid.html', context)


@login_required
def dividend_preview_api(request):
    """AJAX API: Preview dividend calculation"""
    try:
        amount_per_share = Decimal(request.GET.get('amount', 0))
    except:
        amount_per_share = Decimal('0')
    
    total_shares = Share.objects.aggregate(total=Sum('quantity'))['total'] or 0
    total_profit = get_total_profit()
    
    total_dividend = amount_per_share * total_shares
    
    return JsonResponse({
        'success': True,
        'total_shares': float(total_shares),
        'total_profit': float(total_profit),
        'total_dividend': float(total_dividend),
        'exceeds_profit': total_dividend > total_profit,
        'remaining_profit': float(total_profit - total_dividend) if total_dividend <= total_profit else 0,
        'message': '✅ Dividend is within profit' if total_dividend <= total_profit else '❌ Dividend exceeds profit!',
        'is_valid': total_dividend <= total_profit,
        'max_per_share': float(total_profit / total_shares) if total_shares > 0 else 0
    })


@login_required
def dividend_list(request):
    """List all dividends"""
    dividends = Dividend.objects.all().order_by('-declaration_date')
    
    # Get profit for each dividend
    total_profit = get_total_profit()
    for dividend in dividends:
        dividend.is_valid = dividend.total_amount <= total_profit
        dividend.profit_percent = (dividend.total_amount / total_profit * 100) if total_profit > 0 else 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividends': dividends,
        'total_profit': total_profit,
    }
    return render(request, 'shareholders/dividend_list.html', context)


@login_required
def drip_dashboard(request):
    """DRIP Dashboard for shareholders"""
    
    # ✅ Allow both admin and shareholders
    if request.user.is_superuser or request.user.is_staff:
        # Admin can view all DRIP data
        shareholder = None
        enrollments = ShareholderDRIPEnrollment.objects.all().select_related('drip', 'drip__dividend')
        transactions = DRIPTransaction.objects.all().order_by('-created_at')[:50]
        pending_dividends = DividendPayment.objects.filter(status='pending')
        
        total_reinvested = DRIPTransaction.objects.filter(
            status='completed'
        ).aggregate(total=Sum('total_cost'))['total'] or 0
        
        total_shares = DRIPTransaction.objects.filter(
            status='completed'
        ).aggregate(total=Sum('shares_purchased'))['total'] or 0
        
        is_admin_view = True
        
    elif hasattr(request.user, 'shareholder_profile'):
        shareholder = request.user.shareholder_profile
        enrollments = ShareholderDRIPEnrollment.objects.filter(
            shareholder=shareholder
        ).select_related('drip', 'drip__dividend')
        transactions = DRIPTransaction.objects.filter(
            dividend_payment__shareholder=shareholder
        ).order_by('-created_at')[:10]
        pending_dividends = DividendPayment.objects.filter(
            shareholder=shareholder,
            status='pending'
        )
        
        total_reinvested = DRIPTransaction.objects.filter(
            dividend_payment__shareholder=shareholder,
            status='completed'
        ).aggregate(total=Sum('total_cost'))['total'] or 0
        
        total_shares = DRIPTransaction.objects.filter(
            dividend_payment__shareholder=shareholder,
            status='completed'
        ).aggregate(total=Sum('shares_purchased'))['total'] or 0
        
        is_admin_view = False
        
    else:
        messages.error(request, 'Access denied! Only shareholders and admins can view DRIP.')
        return redirect('dashboard')
    
    # Get active DRIP plans
    active_drips = DividendReinvestmentPlan.objects.filter(
        status='active',
        start_date__lte=date.today()
    )
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'shareholder': shareholder,
        'enrollments': enrollments,
        'active_drips': active_drips,
        'transactions': transactions,
        'pending_dividends': pending_dividends,
        'total_reinvested': total_reinvested,
        'total_shares': total_shares,
        'is_admin_view': is_admin_view,
        'balance': ShareholderCashBalance.get_balance(shareholder) if shareholder else 0,
    }
    return render(request, 'shareholders/drip/dashboard.html', context)


@login_required
def drip_enroll(request, drip_id):
    """Enroll shareholder in DRIP"""
    
    drip = get_object_or_404(DividendReinvestmentPlan, id=drip_id, status='active')
    
    # ✅ Admin can enroll on behalf of shareholders
    if request.user.is_superuser or request.user.is_staff:
        if request.method == 'POST':
            shareholder_id = request.POST.get('shareholder_id')
            if not shareholder_id:
                messages.error(request, 'Please select a shareholder!')
                return redirect('drip_enroll', drip_id=drip_id)
            
            shareholder = get_object_or_404(Shareholder, id=shareholder_id)
            enrollment, created = ShareholderDRIPEnrollment.objects.get_or_create(
                shareholder=shareholder,
                drip=drip,
                defaults={
                    'status': 'active',
                    'created_by': request.user,
                    'min_dividend_to_reinvest': Decimal(request.POST.get('min_amount', 500)),
                    'auto_reinvest': request.POST.get('auto_reinvest') == 'on',
                }
            )
            
            if created:
                messages.success(request, f'✅ Enrolled {shareholder.name} in {drip.plan_name}!')
            else:
                enrollment.status = 'active'
                enrollment.save()
                messages.success(request, f'✅ Re-enrolled {shareholder.name} in {drip.plan_name}!')
            
            return redirect('drip_dashboard')
        
        # GET - show admin enrollment form
        shareholders = Shareholder.objects.filter(status='active')
        context = {
            'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
            'drip': drip,
            'shareholders': shareholders,
            'is_admin': True,
        }
        return render(request, 'shareholders/drip/enroll.html', context)
    
    # ✅ Shareholder self-enrollment
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied! Only shareholders can enroll.')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    if request.method == 'POST':
        enrollment, created = ShareholderDRIPEnrollment.objects.get_or_create(
            shareholder=shareholder,
            drip=drip,
            defaults={
                'status': 'active',
                'created_by': request.user,
                'min_dividend_to_reinvest': Decimal(request.POST.get('min_amount', 500)),
                'auto_reinvest': request.POST.get('auto_reinvest') == 'on',
            }
        )
        
        if created:
            messages.success(request, f'✅ Enrolled in {drip.plan_name} successfully!')
        else:
            enrollment.status = 'active'
            enrollment.save()
            messages.success(request, f'✅ Re-enrolled in {drip.plan_name}!')
        
        return redirect('drip_dashboard')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'drip': drip,
        'shareholder': shareholder,
        'is_admin': False,
    }
    return render(request, 'shareholders/drip/enroll.html', context)


@login_required
def drip_unenroll(request, enrollment_id):
    """Unenroll shareholder from DRIP"""
    
    enrollment = get_object_or_404(ShareholderDRIPEnrollment, id=enrollment_id)
    
    # ✅ Admin can unenroll any shareholder
    if request.user.is_superuser or request.user.is_staff:
        if request.method == 'POST':
            enrollment.status = 'cancelled'
            enrollment.save()
            messages.success(request, f'✅ Unenrolled {enrollment.shareholder.name} from {enrollment.drip.plan_name}')
            return redirect('drip_dashboard')
        
        context = {
            'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
            'enrollment': enrollment,
            'is_admin': True,
        }
        return render(request, 'shareholders/drip/unenroll.html', context)
    
    # ✅ Shareholder self-unenroll
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if enrollment.shareholder != request.user.shareholder_profile:
        messages.error(request, 'Access denied! You can only unenroll yourself.')
        return redirect('drip_dashboard')
    
    if request.method == 'POST':
        enrollment.status = 'cancelled'
        enrollment.save()
        messages.success(request, f'✅ Unenrolled from {enrollment.drip.plan_name}')
        return redirect('drip_dashboard')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'enrollment': enrollment,
        'is_admin': False,
    }
    return render(request, 'shareholders/drip/unenroll.html', context)


@login_required
def drip_process(request, dividend_payment_id):
    """Process DRIP for a specific dividend payment"""
    
    # ✅ Allow both admin and staff
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only admins can process DRIP.')
        return redirect('dashboard')
    
    payment = get_object_or_404(
        DividendPayment, 
        id=dividend_payment_id,
        status='pending'
    )
    
    # Check if enrollment exists
    enrollment = ShareholderDRIPEnrollment.objects.filter(
        shareholder=payment.shareholder,
        drip__dividend=payment.dividend,
        status='active'
    ).first()
    
    if not enrollment:
        messages.error(request, '❌ No active DRIP enrollment found for this shareholder!')
        return redirect('dividend_detail', pk=payment.dividend.pk)
    
    # Create DRIP transaction
    transaction = DRIPTransaction.objects.create(
        dividend_payment=payment,
        enrollment=enrollment,
        dividend_amount=payment.amount,
        admin_fee=enrollment.drip.admin_fee,
        created_by=request.user,
        status='processing'
    )
    
    # Process
    if transaction.process():
        messages.success(request, f'✅ DRIP processed! Shares purchased: {transaction.shares_purchased}')
    else:
        messages.error(request, f'❌ DRIP processing failed: {transaction.notes}')
    
    return redirect('dividend_detail', pk=payment.dividend.pk)


@login_required
def drip_bulk_process(request):
    """Process all pending DRIPs in bulk"""
    
    # ✅ Allow both admin and staff
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only admins can bulk process DRIP.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        pending_payments = DividendPayment.objects.filter(
            status='pending'
        ).select_related('shareholder', 'dividend')
        
        processed = 0
        failed = 0
        
        for payment in pending_payments:
            enrollment = ShareholderDRIPEnrollment.objects.filter(
                shareholder=payment.shareholder,
                drip__dividend=payment.dividend,
                status='active'
            ).first()
            
            if enrollment and enrollment.is_eligible(payment.amount):
                transaction = DRIPTransaction.objects.create(
                    dividend_payment=payment,
                    enrollment=enrollment,
                    dividend_amount=payment.amount,
                    admin_fee=enrollment.drip.admin_fee,
                    created_by=request.user,
                    status='processing'
                )
                
                if transaction.process():
                    processed += 1
                else:
                    failed += 1
        
        messages.success(
            request, 
            f'✅ {processed} DRIPs processed successfully! {failed} failed.'
        )
        return redirect('dividend_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'pending_payments': DividendPayment.objects.filter(status='pending').count(),
    }
    return render(request, 'shareholders/drip/bulk_process.html', context)


@login_required
def buyback_list(request):
    """List all share buybacks"""
    
    buybacks = ShareBuyback.objects.all().order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        buybacks = buybacks.filter(status=status)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'buybacks': buybacks,
        'status': status,
    }
    return render(request, 'shareholders/buyback/list.html', context)


@login_required
def buyback_create(request):
    """Create new share buyback"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied! Only admins can create buybacks.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            buyback = ShareBuyback.objects.create(
                buyback_type=request.POST.get('buyback_type'),
                description=request.POST.get('description'),
                total_amount=Decimal(request.POST.get('total_amount', 0)),
                price_per_share=Decimal(request.POST.get('price_per_share', 0)),
                max_shares=int(request.POST.get('max_shares', 0)),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                record_date=request.POST.get('record_date'),
                status='draft',
                created_by=request.user,
                notes=request.POST.get('notes', '')
            )
            messages.success(request, f'✅ Buyback #{buyback.buyback_no} created!')
            return redirect('buyback_detail', pk=buyback.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'buyback_types': ShareBuyback.BUYBACK_TYPES,
    }
    return render(request, 'shareholders/buyback/create.html', context)


@login_required
def buyback_detail(request, pk):
    """Buyback detail view"""
    
    buyback = get_object_or_404(ShareBuyback, pk=pk)
    offers = buyback.offers.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'buyback': buyback,
        'offers': offers,
        'is_eligible': True,  # Check if user can offer
    }
    return render(request, 'shareholders/buyback/detail.html', context)


@login_required
def buyback_offer(request, pk):
    """Shareholder offer shares for buyback"""
    
    buyback = get_object_or_404(ShareBuyback, pk=pk)
    
    if not buyback.is_active():
        messages.error(request, '❌ This buyback is not active!')
        return redirect('buyback_detail', pk=pk)
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, '❌ Only shareholders can offer shares!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    
    # Check if already offered
    existing = BuybackOffer.objects.filter(buyback=buyback, shareholder=shareholder).first()
    if existing:
        messages.warning(request, '⚠️ You have already offered shares for this buyback!')
        return redirect('buyback_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            shares_offered = int(request.POST.get('shares_offered', 0))
            
            if shares_offered <= 0:
                messages.error(request, '❌ Shares must be greater than zero!')
                return redirect('buyback_offer', pk=pk)
            
            if shares_offered > shareholder.total_shares():
                messages.error(request, f'❌ You only have {shareholder.total_shares()} shares!')
                return redirect('buyback_offer', pk=pk)
            
            offer = BuybackOffer.objects.create(
                buyback=buyback,
                shareholder=shareholder,
                shares_offered=shares_offered,
                price_offered=buyback.price_per_share,
                total_amount=shares_offered * buyback.price_per_share,
                created_by=request.user,
                status='pending'
            )
            
            messages.success(request, f'✅ {shares_offered} shares offered for buyback!')
            return redirect('buyback_detail', pk=buyback.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'buyback': buyback,
        'total_shares': shareholder.total_shares(),
    }
    return render(request, 'shareholders/buyback/offer.html', context)


@login_required
def discount_list(request):
    """List all discount programs"""
    
    discounts = ShareholderDiscountProgram.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'discounts': discounts,
    }
    return render(request, 'shareholders/discount/list.html', context)


@login_required
def apply_discount(request):
    """Apply discount to a sale"""
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            amount = Decimal(data.get('amount', 0))
            shareholder_id = data.get('shareholder_id')
            
            if not shareholder_id:
                return JsonResponse({'success': False, 'message': 'Shareholder not found'})
            
            shareholder = get_object_or_404(Shareholder, id=shareholder_id)
            
            # Get best discount
            best_discount = None
            best_amount = Decimal('0.00')
            
            for discount in ShareholderDiscountProgram.objects.filter(is_active=True):
                discount_amt = discount.get_discount_amount(
                    shareholder, 
                    Product.objects.get(id=product_id) if product_id else None,
                    amount
                )
                if discount_amt > best_amount:
                    best_amount = discount_amt
                    best_discount = discount
            
            if best_discount and best_amount > 0:
                return JsonResponse({
                    'success': True,
                    'discount_amount': float(best_amount),
                    'discount_name': best_discount.name,
                    'final_amount': float(amount - best_amount),
                    'discount_percent': float(best_discount.discount_value),
                })
            
            return JsonResponse({'success': False, 'message': 'No discount available'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def my_discounts(request):
    """View discounts available to logged-in shareholder"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, '❌ Only shareholders can view discounts!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    discounts = ShareholderDiscountProgram.objects.filter(is_active=True)
    
    available_discounts = []
    for discount in discounts:
        discount_amt = discount.get_discount_amount(shareholder, None, 1000)  # Sample amount
        if discount_amt > 0:
            available_discounts.append({
                'program': discount,
                'discount_amt': discount_amt,
                'eligibility': 'Eligible'
            })
    
    # Get usage history
    usages = ShareholderDiscountUsage.objects.filter(shareholder=shareholder).order_by('-used_at')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'available_discounts': available_discounts,
        'usages': usages,
        'shareholder': shareholder,
    }
    return render(request, 'shareholders/discount/my_discounts.html', context)


@login_required
def balance_dividend_create(request):
    """Create new balance-based dividend with refund option"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    # Auto calculate profit
    from_date = request.GET.get('from_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today().replace(day=1)
        to_date_obj = date.today()
    
    profit_data = BalanceDividend.get_auto_profit(from_date_obj, to_date_obj, exclude_used=True)
    auto_profit = profit_data['final_profit']
    
    if request.method == 'POST':
        try:
            total_profit = Decimal(request.POST.get('total_profit', auto_profit))
            dividend_percentage = Decimal(request.POST.get('dividend_percentage', 50))
            declaration_date = request.POST.get('declaration_date')
            record_date = request.POST.get('record_date')
            distribution_type = request.POST.get('distribution_type', 'balance_used')
            
            # ✅ NEW: Refund settings
            refund_type = request.POST.get('refund_type', 'full')
            refund_percentage = Decimal(request.POST.get('refund_percentage', 100))
            
            notes = request.POST.get('notes', '')
            
            if total_profit <= 0:
                messages.error(request, '⚠️ Total profit must be greater than zero!')
                return redirect('balance_dividend_create')
            
            if dividend_percentage <= 0 or dividend_percentage > 100:
                messages.error(request, '⚠️ Dividend percentage must be between 1 and 100!')
                return redirect('balance_dividend_create')
            
            if refund_percentage < 0 or refund_percentage > 100:
                messages.error(request, '⚠️ Refund percentage must be between 0 and 100!')
                return redirect('balance_dividend_create')
            
            # ✅ Create dividend with refund settings
            dividend = BalanceDividend.objects.create(
                total_profit=total_profit,
                dividend_percentage=dividend_percentage,
                declaration_date=declaration_date,
                record_date=record_date,
                distribution_type=distribution_type,
                refund_type=refund_type,
                refund_percentage=refund_percentage,
                notes=notes,
                created_by=request.user,
                profit_from_date=from_date_obj,
                profit_to_date=to_date_obj,
                status='draft'
            )
            
            # ✅ Calculate distribution with refund
            distribution = dividend.calculate_distribution()
            total_refund = sum(item.get('refund_amount', 0) for item in distribution)
            
            if not distribution:
                messages.warning(request, '⚠️ No eligible shareholders found!')
            
            # ✅ Auto-generate payments
            try:
                count, total_amount, total_refund_amount = dividend.generate_payments()
                if count > 0:
                    messages.success(
                        request, 
                        f'✅ {count} payments generated!\n'
                        f'💰 Profit: Rs. {total_amount:,.2f}\n'
                        f'🔄 Refund: Rs. {total_refund_amount:,.2f}\n'
                        f'💵 Total Payment: Rs. {total_amount + total_refund_amount:,.2f}'
                    )
                else:
                    messages.warning(request, '⚠️ No payments generated!')
            except Exception as e:
                messages.warning(request, f'⚠️ Error generating payments: {str(e)}')
            
            return redirect('balance_dividend_detail', pk=dividend.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('balance_dividend_create')
    
    # GET request
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'active_shareholders': Shareholder.objects.filter(status='active').count(),
        'today': date.today().strftime('%Y-%m-%d'),
        'from_date': from_date,
        'to_date': to_date,
        'profit_data': profit_data,
        'auto_profit': auto_profit,
        'eligible_count': BalanceDividend.get_eligible_shareholders_count(),
        'distribution_types': BalanceDividend.DISTRIBUTION_TYPES,
        'refund_types': BalanceDividend.REFUND_TYPES,
    }
    return render(request, 'dividends/balance_dividend_create.html', context)


@login_required
def balance_dividend_detail(request, pk):
    """Balance dividend detail view with payment list"""
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    payments = dividend.payments.all().select_related('shareholder')
    
    # ✅ Calculate totals
    total_amount = dividend.payments.aggregate(
        total=Sum('total_payment')
    )['total'] or Decimal('0.00')
    
    paid_amount = dividend.payments.filter(
        status='paid'
    ).aggregate(
        total=Sum('total_payment')
    )['total'] or Decimal('0.00')
    
    pending_amount = dividend.payments.filter(
        status='pending'
    ).aggregate(
        total=Sum('total_payment')
    )['total'] or Decimal('0.00')
    
    paid_count = dividend.payments.filter(status='paid').count()
    pending_count = dividend.payments.filter(status='pending').count()
    total_payments = dividend.payments.count()
    
    # ✅ Calculate refund totals
    total_refund = dividend.payments.aggregate(
        total=Sum('refund_amount')
    )['total'] or Decimal('0.00')
    
    total_profit_amount = dividend.payments.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # ✅ NEW: Calculate Retained Earnings
    total_profit = dividend.total_profit
    amount_to_distribute = dividend.amount_to_distribute
    retained_earnings = total_profit - amount_to_distribute
    
    if total_profit > 0:
        remaining_percentage = 100 - dividend.dividend_percentage
    else:
        remaining_percentage = 0
    
    # ✅ Check if all paid
    all_paid = pending_count == 0 and total_payments > 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
        'payments': payments,
        'total_amount': total_amount,
        'paid_amount': paid_amount,
        'pending_amount': pending_amount,
        'paid_count': paid_count,
        'pending_count': pending_count,
        'total_payments': total_payments,
        'all_paid': all_paid,
        'total_refund': total_refund,
        'total_profit_amount': total_profit_amount,
        # ✅ NEW: Retained Earnings
        'retained_earnings': retained_earnings,
        'remaining_percentage': remaining_percentage,
        'can_generate': dividend.status in ['draft', 'declared'] and not payments.exists(),
        'can_distribute': dividend.status in ['declared', 'approved'] and payments.exists(),
        'can_edit': dividend.status in ['draft', 'declared'],
        'can_delete': dividend.status == 'draft',
        'is_admin': request.user.is_superuser or request.user.is_staff,
    }
    return render(request, 'dividends/balance_dividend_detail.html', context)


@login_required
def balance_dividend_generate(request, pk):
    """Generate dividend payments for all eligible shareholders"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    if dividend.status != 'draft':
        messages.error(request, '❌ Only draft dividends can generate payments!')
        return redirect('balance_dividend_detail', pk=pk)
    
    try:
        with transaction.atomic():
            count = dividend.generate_payments()
            
            if count == 0:
                messages.warning(request, '⚠️ No eligible shareholders found!')
                return redirect('balance_dividend_detail', pk=pk)
            
            messages.success(
                request, 
                f'✅ {count} dividend payments generated! Total: Rs. {dividend.total_profit * (dividend.dividend_percentage / 100):,.2f}'
            )
            
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('balance_dividend_detail', pk=pk)


@login_required
def balance_dividend_distribute(request, pk):
    """Distribute dividend (mark all as distributed)"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    if dividend.status != 'declared':
        messages.error(request, '❌ Only declared dividends can be distributed!')
        return redirect('balance_dividend_detail', pk=pk)
    
    # Check if all payments are paid
    pending_payments = dividend.payments.filter(status='pending')
    if pending_payments.exists():
        messages.error(
            request, 
            f'❌ {pending_payments.count()} payments are still pending! Please mark them paid first.'
        )
        return redirect('balance_dividend_detail', pk=pk)
    
    try:
        with transaction.atomic():
            dividend.status = 'distributed'
            dividend.distribution_date = now().date()
            dividend.save()
            
            messages.success(request, f'✅ Dividend #{dividend.dividend_no} distributed successfully!')
            
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('balance_dividend_detail', pk=pk)


@login_required
def balance_dividend_pay(request, pk):
    """Mark individual dividend payment as paid"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    payment = get_object_or_404(BalanceDividendPayment, pk=pk)
    
    if payment.status == 'paid':
        messages.warning(request, '⚠️ This payment is already marked as paid!')
        return redirect('balance_dividend_detail', pk=payment.dividend.pk)
    
    if request.method == 'POST':
        try:
            payment_method = request.POST.get('payment_method', 'Bank Transfer')
            reference_no = request.POST.get('reference_no', '')
            notes = request.POST.get('notes', '')
            
            # ✅ NEW: Check if main cash should be deducted
            deduct_main_cash = request.POST.get('deduct_main_cash') == 'on'
            
            if deduct_main_cash:
                # With main cash deduction
                payment.mark_paid_with_cash(request.user, payment_method, reference_no)
                messages.success(
                    request, 
                    f'✅ Payment of Rs. {payment.total_payment:,.2f} marked as paid!\n'
                    f'💰 Shareholder Balance: +Rs. {payment.total_payment:,.2f}\n'
                    f'💵 Main Cash: -Rs. {payment.total_payment:,.2f}'
                )
            else:
                # Without main cash deduction (balance only)
                payment.mark_paid_no_cash(request.user, payment_method, reference_no)
                messages.success(
                    request, 
                    f'✅ Payment of Rs. {payment.total_payment:,.2f} credited to {payment.shareholder.name}!\n'
                    f'💰 Shareholder Balance: +Rs. {payment.total_payment:,.2f}\n'
                    f'💵 Main Cash: No Change (Balance Only)'
                )
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
        
        return redirect('balance_dividend_detail', pk=payment.dividend.pk)
    
    # GET request - show form
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'payment': payment,
        'dividend': payment.dividend,
        'current_balance': CashBalance.get_balance(),
        'shareholder_balance': ShareholderCashBalance.get_balance(payment.shareholder),
        'formatted_total': f"Rs. {payment.total_payment:,.2f}",
        'formatted_refund': f"Rs. {payment.refund_amount:,.2f}",
        'formatted_profit': f"Rs. {payment.amount:,.2f}",
    }
    return render(request, 'dividends/balance_dividend_pay.html', context)


@login_required
def balance_dividend_bulk_pay(request, pk):
    """Bulk mark all pending payments as paid"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    if dividend.status not in ['declared', 'distributed']:
        messages.error(request, '❌ Only declared or distributed dividends can be bulk paid!')
        return redirect('balance_dividend_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            payment_method = request.POST.get('payment_method', 'Bank Transfer')
            reference_no = request.POST.get('reference_no', '')
            
            pending_payments = dividend.payments.filter(status='pending')
            
            if not pending_payments.exists():
                messages.warning(request, '⚠️ No pending payments found!')
                return redirect('balance_dividend_detail', pk=pk)
            
            with transaction.atomic():
                for payment in pending_payments:
                    payment.mark_paid(request.user, payment_method, reference_no)
            
            messages.success(
                request, 
                f'✅ {pending_payments.count()} payments marked as paid!'
            )
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
        
        return redirect('balance_dividend_detail', pk=pk)
    
    pending_count = dividend.payments.filter(status='pending').count()
    total_amount = dividend.payments.filter(status='pending').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
        'pending_count': pending_count,
        'total_amount': total_amount,
    }
    return render(request, 'dividends/balance_dividend_bulk_pay.html', context)


@login_required
def balance_dividend_list(request):
    """List all balance-based dividends"""
    
    dividends = BalanceDividend.objects.all().order_by('-declaration_date')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        dividends = dividends.filter(status=status)
    
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        dividends = dividends.filter(declaration_date__gte=from_date)
    if to_date:
        dividends = dividends.filter(declaration_date__lte=to_date)
    
    # ✅ FIX: Calculate total amount for each dividend
    for dividend in dividends:
        # Total amount from payments
        total_amount = dividend.payments.aggregate(
            total=Sum('total_payment')
        )['total'] or Decimal('0.00')
        
        # Paid amount
        paid_amount = dividend.payments.filter(
            status='paid'
        ).aggregate(
            total=Sum('total_payment')
        )['total'] or Decimal('0.00')
        
        # Pending amount
        pending_amount = dividend.payments.filter(
            status='pending'
        ).aggregate(
            total=Sum('total_payment')
        )['total'] or Decimal('0.00')
        
        dividend.total_amount = total_amount
        dividend.paid_amount = paid_amount
        dividend.pending_amount = pending_amount
        dividend.payment_count = dividend.payments.count()
    
    # Statistics
    total_dividends = dividends.count()
    total_distributed = dividends.filter(status='distributed').aggregate(
        total=Sum('total_payment_amount')
    )['total'] or Decimal('0.00')
    pending_dividends = dividends.filter(status__in=['draft', 'declared']).count()
    
    paginator = Paginator(dividends, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'dividends': page_obj,
        'status': status,
        'from_date': from_date,
        'to_date': to_date,
        'total_dividends': total_dividends,
        'total_distributed': total_distributed,
        'pending_dividends': pending_dividends,
        'status_choices': BalanceDividend.STATUS_CHOICES,
    }
    return render(request, 'dividends/balance_dividend_list.html', context)


@login_required
def balance_dividend_report(request):
    """Generate balance dividend report"""
    
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date_obj = date.today() - timedelta(days=90)
        to_date_obj = date.today()
    
    dividends = BalanceDividend.objects.filter(
        declaration_date__gte=from_date_obj,
        declaration_date__lte=to_date_obj
    )
    
    # Statistics
    total_dividends = dividends.count()
    total_amount = dividends.aggregate(
        total=Sum('total_profit')
    )['total'] or Decimal('0.00')
    
    total_distributed = dividends.filter(status='distributed').aggregate(
        total=Sum('total_profit')
    )['total'] or Decimal('0.00')
    
    total_pending = dividends.filter(status__in=['draft', 'declared']).aggregate(
        total=Sum('total_profit')
    )['total'] or Decimal('0.00')
    
    # Get all payments for this period
    payments = BalanceDividendPayment.objects.filter(
        dividend__in=dividends
    )
    
    total_paid = payments.filter(status='paid').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Shareholder wise summary
    shareholder_summary = {}
    for payment in payments:
        name = payment.shareholder.name
        if name not in shareholder_summary:
            shareholder_summary[name] = {
                'name': name,
                'total_dividend': Decimal('0.00'),
                'total_paid': Decimal('0.00'),
                'count': 0,
            }
        shareholder_summary[name]['total_dividend'] += payment.amount
        if payment.status == 'paid':
            shareholder_summary[name]['total_paid'] += payment.amount
        shareholder_summary[name]['count'] += 1
    
    # Convert to list and sort
    shareholder_list = sorted(
        shareholder_summary.values(),
        key=lambda x: x['total_dividend'],
        reverse=True
    )
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'from_date': from_date,
        'to_date': to_date,
        'total_dividends': total_dividends,
        'total_amount': total_amount,
        'total_distributed': total_distributed,
        'total_pending': total_pending,
        'total_paid': total_paid,
        'dividends': dividends[:100],
        'shareholder_summary': shareholder_list,
        'status_choices': BalanceDividend.STATUS_CHOICES,
    }
    return render(request, 'dividends/balance_dividend_report.html', context)


@login_required
def balance_dividend_cancel(request, pk):
    """Cancel balance dividend"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can cancel dividends.')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    if dividend.status == 'distributed':
        messages.error(request, '❌ Cannot cancel a distributed dividend!')
        return redirect('balance_dividend_detail', pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        try:
            with transaction.atomic():
                # Delete all pending payments
                dividend.payments.filter(status='pending').delete()
                dividend.status = 'cancelled'
                dividend.notes = f"{dividend.notes}\nCancelled: {reason}".strip()
                dividend.save()
                
                messages.success(request, f'❌ Dividend #{dividend.dividend_no} cancelled!')
                return redirect('balance_dividend_list')
                
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('balance_dividend_detail', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
    }
    return render(request, 'dividends/balance_dividend_cancel.html', context)


@login_required
def balance_dividend_delete(request, pk):
    """Delete balance dividend"""
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Access denied! Only superuser can delete dividends.')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    if dividend.status not in ['draft', 'cancelled']:
        messages.error(request, '❌ Only draft or cancelled dividends can be deleted!')
        return redirect('balance_dividend_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            dividend_no = dividend.dividend_no
            dividend.delete()
            messages.success(request, f'🗑️ Dividend #{dividend_no} deleted!')
            return redirect('balance_dividend_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('balance_dividend_detail', pk=pk)
    
    return redirect('balance_dividend_detail', pk=pk)


@login_required
def eligible_shareholders_api(request):
    """API: Get eligible shareholders for balance dividend"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        # Get min balance and min months from request
        min_balance = Decimal(request.GET.get('min_balance', 0))
        min_months = int(request.GET.get('min_months', 0))
        
        # Get eligible shareholders
        eligible = []
        total_balance_used = Decimal('0.00')
        
        for shareholder in Shareholder.objects.filter(status='active'):
            balance_used = get_shareholder_balance_used(shareholder)
            
            # Check min balance requirement
            if balance_used < min_balance:
                continue
            
            # Check min holding period
            if min_months > 0:
                first_share = shareholder.shares.order_by('issue_date').first()
                if not first_share:
                    continue
                months_held = (date.today() - first_share.issue_date).days // 30
                if months_held < min_months:
                    continue
            
            eligible.append({
                'id': shareholder.id,
                'name': shareholder.name,
                'code': shareholder.shareholder_code,
                'balance_used': float(balance_used),
                'total_shares': shareholder.total_shares(),
                'investment': float(shareholder.total_investment()),
            })
            total_balance_used += balance_used
        
        return JsonResponse({
            'success': True,
            'eligible': eligible,
            'count': len(eligible),
            'total_balance_used': float(total_balance_used),
            'min_balance': float(min_balance),
            'min_months': min_months,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def balance_dividend_preview_api(request):
    """API: Preview dividend distribution before creating"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        total_profit = Decimal(request.GET.get('total_profit', 0))
        dividend_percentage = Decimal(request.GET.get('dividend_percentage', 50))
        min_balance = Decimal(request.GET.get('min_balance', 0))
        min_months = int(request.GET.get('min_months', 0))
        
        if total_profit <= 0:
            return JsonResponse({'success': False, 'message': 'Total profit must be greater than zero!'})
        
        amount_to_distribute = total_profit * (dividend_percentage / 100)
        
        # Get eligible shareholders
        eligible = []
        total_balance_used = Decimal('0.00')
        
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
            
            eligible.append({
                'id': shareholder.id,
                'name': shareholder.name,
                'code': shareholder.shareholder_code,
                'balance_used': float(balance_used),
                'total_shares': shareholder.total_shares(),
            })
            total_balance_used += balance_used
        
        # Calculate distribution
        distribution = []
        for item in eligible:
            if total_balance_used > 0:
                percentage = (item['balance_used'] / total_balance_used) * 100
                amount = (item['balance_used'] / total_balance_used) * amount_to_distribute
            else:
                percentage = 0
                amount = 0
            
            distribution.append({
                'shareholder_id': item['id'],
                'name': item['name'],
                'code': item['code'],
                'balance_used': item['balance_used'],
                'percentage': float(percentage),
                'amount': float(amount),
                'total_shares': item['total_shares'],
            })
        
        return JsonResponse({
            'success': True,
            'total_profit': float(total_profit),
            'dividend_percentage': float(dividend_percentage),
            'amount_to_distribute': float(amount_to_distribute),
            'eligible_count': len(distribution),
            'total_balance_used': float(total_balance_used),
            'distribution': distribution,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def balance_dividend_stats_api(request):
    """API: Get balance dividend statistics"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        stats = {
            'total_dividends': BalanceDividend.objects.count(),
            'pending_dividends': BalanceDividend.objects.filter(status__in=['draft', 'declared']).count(),
            'distributed_dividends': BalanceDividend.objects.filter(status='distributed').count(),
            'total_amount': float(BalanceDividend.objects.aggregate(
                total=Sum('total_profit')
            )['total'] or 0),
            'total_paid': float(BalanceDividendPayment.objects.filter(
                status='paid'
            ).aggregate(total=Sum('amount'))['total'] or 0),
            'total_pending': float(BalanceDividendPayment.objects.filter(
                status='pending'
            ).aggregate(total=Sum('amount'))['total'] or 0),
            'eligible_shareholders': get_eligible_shareholders_count(),
            'total_balance_used': float(get_total_balance_used()),
        }
        
        return JsonResponse({'success': True, 'stats': stats})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def balance_dividend_edit(request, pk):
    """Edit balance dividend"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    dividend = get_object_or_404(BalanceDividend, pk=pk)
    
    # Only draft or declared dividends can be edited
    if dividend.status not in ['draft', 'declared']:
        messages.error(request, '❌ Only draft or declared dividends can be edited!')
        return redirect('balance_dividend_detail', pk=pk)
    
    # Check if payments exist
    if dividend.payments.exists():
        messages.error(request, '❌ Cannot edit dividend with existing payments!')
        return redirect('balance_dividend_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            total_profit = Decimal(request.POST.get('total_profit', 0))
            dividend_percentage = Decimal(request.POST.get('dividend_percentage', 50))
            declaration_date = request.POST.get('declaration_date')
            record_date = request.POST.get('record_date')
            distribution_type = request.POST.get('distribution_type', 'balance_used')
            notes = request.POST.get('notes', '')
            
            # Validation
            if total_profit <= 0:
                messages.error(request, 'Total profit must be greater than zero!')
                return redirect('balance_dividend_edit', pk=pk)
            
            if dividend_percentage <= 0 or dividend_percentage > 100:
                messages.error(request, 'Dividend percentage must be between 1 and 100!')
                return redirect('balance_dividend_edit', pk=pk)
            
            # Update dividend
            dividend.total_profit = total_profit
            dividend.dividend_percentage = dividend_percentage
            dividend.declaration_date = declaration_date
            dividend.record_date = record_date
            dividend.distribution_type = distribution_type
            dividend.notes = notes
            dividend.save()
            
            messages.success(request, f'✅ Dividend #{dividend.dividend_no} updated successfully!')
            return redirect('balance_dividend_detail', pk=dividend.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('balance_dividend_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dividend': dividend,
        'distribution_types': [
            ('balance_used', 'Based on Balance Used'),
            ('equal', 'Equal Distribution'),
            ('proportional', 'Proportional by Balance'),
        ],
        'today': date.today().strftime('%Y-%m-%d'),
    }
    return render(request, 'dividends/balance_dividend_edit.html', context)


@login_required
def dividend_profit_api(request):
    """API: Get auto-calculated profit for dividend"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        from_date = request.GET.get('from_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
        to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
        
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        profit_data = BalanceDividend.get_auto_profit(from_date_obj, to_date_obj)
        
        return JsonResponse({
            'success': True,
            'profit': float(profit_data['final_profit']),
            'total_sales_profit': float(profit_data['total_sales_profit']),
            'total_discounts': float(profit_data['total_discounts']),
            'total_expenses': float(profit_data['total_expenses']),
            'from_date': from_date,
            'to_date': to_date,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
