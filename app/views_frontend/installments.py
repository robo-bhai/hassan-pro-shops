"""Frontend views: installments."""
from ..models import *
import json
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, date as date_today
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from ..models import CompanyInfo, Sale
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


@login_required
def installment_plan_list(request):
    """List all installment plans with stats"""
    plans = InstallmentPlan.objects.all().order_by('-is_active', 'duration_months')
    
    # Count how many times each plan is used
    for plan in plans:
        plan.installment_count = SaleInstallment.objects.filter(plan=plan).count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plans': plans,
        'total_plans': plans.count(),
        'active_plans': plans.filter(is_active=True).count(),
        'inactive_plans': plans.filter(is_active=False).count(),
        'used_in_sales': SaleInstallment.objects.filter(plan__isnull=False).values('plan').distinct().count(),
    }
    return render(request, 'installments/plan_list.html', context)


@login_required
def whatsapp_reminders_view(request):
    """WhatsApp reminders for installment EMIs"""
    from datetime import timedelta
    from ..models import EmiPayment, SaleInstallment
    
    today = date_today.today()
    
    # Get all pending EMIs
    pending_emis = EmiPayment.objects.filter(
        status='pending'
    ).select_related('installment__sale__customer', 'installment__plan')
    
    # Categorize EMIs
    due_today = []
    upcoming = []
    overdue = []
    
    for emi in pending_emis:
        customer = emi.installment.sale.customer
        inst = emi.installment
        
        if customer.contact_number:
            days_left = (emi.due_date - today).days
            
            reminder_data = {
                'customer': customer.name,
                'customer_code': customer.customer_code or '',
                'bill_no': inst.sale.bill_no,
                'emi_no': emi.installment_number,
                'amount': float(emi.remaining_due()),
                'due_date': emi.due_date.strftime('%d-%b-%Y'),
                'phone': customer.contact_number,
                'whatsapp_url': '#',
                'status': ''
            }
            
            if days_left < 0:
                reminder_data['status'] = f'⚠️ Overdue ({abs(days_left)} days)'
                overdue.append(reminder_data)
            elif days_left == 0:
                reminder_data['status'] = '🔔 Due Today'
                due_today.append(reminder_data)
            else:
                reminder_data['status'] = f'📅 Due in {days_left} days'
                upcoming.append(reminder_data)
    
    # Get overdue reports
    overdue_reports = []
    overdue_installments = SaleInstallment.objects.filter(
        status__in=['pending', 'partial'],
        next_due_date__lt=today
    ).select_related('sale__customer', 'plan')
    
    for inst in overdue_installments:
        customer = inst.sale.customer
        if customer.contact_number:
            overdue_emis = inst.emi_payments.filter(status='pending', due_date__lt=today)
            total_overdue = sum(emi.remaining_due() for emi in overdue_emis)
            days_overdue = (today - inst.next_due_date).days if inst.next_due_date else 0
            
            overdue_reports.append({
                'customer': customer.name,
                'bill_no': inst.sale.bill_no,
                'phone': customer.contact_number,
                'days_overdue': days_overdue,
                'total_overdue': float(total_overdue),
                'whatsapp_url': f"https://wa.me/{customer.contact_number.replace('+', '')}"
            })
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'due_today': due_today,
        'upcoming': upcoming,
        'overdue_reminders': overdue,
        'overdue_reports': overdue_reports,
        'total_reminders': len(due_today) + len(upcoming) + len(overdue),
    }
    return render(request, 'installments/whatsapp_reminders.html', context)


@login_required
def whatsapp_emi_reminder(request, installment_id):
    """Send WhatsApp reminder for specific installment"""
    from ..utils.whatsapp_utils import WhatsAppSender
    
    installment = get_object_or_404(SaleInstallment, pk=installment_id)
    customer = installment.sale.customer
    
    if not customer.contact_number:
        messages.error(request, f'❌ Customer {customer.name} has no phone number!')
        return redirect('installment_detail', pk=installment_id)
    
    # Get next pending EMI
    next_emi = installment.next_emi_due()
    
    if not next_emi:
        messages.info(request, f'✅ No pending EMIs for {customer.name}!')
        return redirect('installment_detail', pk=installment_id)
    
    # Generate WhatsApp link
    phone = customer.contact_number.replace('+', '').replace('-', '').strip()
    message = f"🔔 *EMI REMINDER*%0A%0A👤 Customer: {customer.name}%0A📋 Bill No: {installment.sale.bill_no}%0A💰 EMI #{next_emi.installment_number}: Rs. {next_emi.remaining_due():,.2f}%0A📅 Due Date: {next_emi.due_date.strftime('%d-%b-%Y')}%0A📊 Remaining: Rs. {installment.remaining_amount():,.2f}%0A%0A🙏 Please clear your payment on time!"
    
    wa_url = f"https://wa.me/{phone}?text={message}"
    
    messages.success(request, f'✅ WhatsApp reminder link generated for {customer.name}!')
    return redirect(wa_url)


@login_required
def whatsapp_installment_summary(request, installment_id):
    """Send complete installment summary via WhatsApp"""
    installment = get_object_or_404(SaleInstallment, pk=installment_id)
    customer = installment.sale.customer
    
    if not customer.contact_number:
        messages.error(request, f'❌ Customer {customer.name} has no phone number!')
        return redirect('installment_detail', pk=installment_id)
    
    total_emis = installment.emi_payments.count()
    paid_emis = installment.emi_payments.filter(status='paid').count()
    pending_emis = total_emis - paid_emis
    overdue_count = installment.emi_payments.filter(
        status='pending', 
        due_date__lt=date_today.today()
    ).count()
    
    progress = (installment.total_paid() / installment.total_payable * 100) if installment.total_payable > 0 else 0
    
    # Generate WhatsApp link
    phone = customer.contact_number.replace('+', '').replace('-', '').strip()
    message = f"📊 *INSTALLMENT SUMMARY*%0A%0A👤 Customer: {customer.name}%0A📋 Bill No: {installment.sale.bill_no}%0A📦 Plan: {installment.plan.name if installment.plan else 'Installment'}%0A%0A💰 *Financial Summary*%0A├─ Total Payable: Rs. {installment.total_payable:,.2f}%0A├─ Total Paid: Rs. {installment.total_paid():,.2f}%0A├─ Remaining: Rs. {installment.remaining_amount():,.2f}%0A└─ Progress: {progress:.0f}%%0A%0A📅 *Payment Status*%0A├─ Total EMIs: {total_emis}%0A├─ Paid: {paid_emis} ✅%0A├─ Pending: {pending_emis} ⏳%0A└─ Overdue: {overdue_count}%0A%0A📆 Next Due: {installment.next_due_date.strftime('%d-%b-%Y') if installment.next_due_date else 'Completed'}%0A%0AThank you for your business!"
    
    wa_url = f"https://wa.me/{phone}?text={message}"
    
    messages.success(request, f'✅ WhatsApp summary link generated for {customer.name}!')
    return redirect(wa_url)


@login_required
def whatsapp_installment_reminders(request):
    """WhatsApp reminders for installment EMIs"""
    from ..utils.whatsapp_utils import InstallmentWhatsAppSender
    
    reminders = InstallmentWhatsAppSender.generate_all_reminder_links()
    overdue_reports = InstallmentWhatsAppSender.get_overdue_installments()
    
    # Group reminders by type
    due_today = [r for r in reminders if r['type'] == 'due_today']
    upcoming = [r for r in reminders if r['type'] == 'upcoming']
    overdue = [r for r in reminders if r['type'] == 'overdue']
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'due_today': due_today,
        'upcoming': upcoming,
        'overdue_reminders': overdue,
        'overdue_reports': overdue_reports,
        'total_reminders': len(reminders),
    }
    return render(request, 'installments/whatsapp_reminders.html', context)


@login_required
def whatsapp_send_installment_summary(request, installment_id):
    """Send installment summary via WhatsApp"""
    from ..utils.whatsapp_utils import WhatsAppSender
    
    installment = get_object_or_404(SaleInstallment, pk=installment_id)
    customer = installment.sale.customer
    
    if not customer.contact_number:
        messages.error(request, f'❌ Customer {customer.name} has no phone number!')
        return redirect('installment_detail', pk=installment_id)
    
    total_emis = installment.emi_payments.count()
    paid_emis = installment.emi_payments.filter(status='paid').count()
    pending_emis = total_emis - paid_emis
    overdue_count = installment.emi_payments.filter(
        status='pending', due_date__lt=date.today()
    ).count()
    
    result = WhatsAppSender.send_installment_summary(
        customer.contact_number,
        customer.name,
        installment.sale.bill_no,
        installment.plan.name if installment.plan else 'Installment',
        float(installment.total_payable),
        float(installment.total_paid()),
        float(installment.remaining_amount()),
        total_emis,
        paid_emis,
        pending_emis,
        overdue_count,
        installment.start_date,
        installment.end_date,
        installment.next_due_date
    )
    
    if result['success']:
        messages.success(request, f'✅ WhatsApp link generated for {customer.name}!')
        return redirect(result['url'])
    else:
        messages.error(request, f'❌ Error: {result.get("error")}')
        return redirect('installment_detail', pk=installment_id)


@login_required
def installment_plan_edit(request, pk):
    """Edit existing installment plan"""
    plan = get_object_or_404(InstallmentPlan, pk=pk)
    
    # ✅ Calculate down payment amount from percentage (based on Rs. 100,000 sample)
    SAMPLE_AMOUNT = 100000
    down_payment_amount = (plan.down_payment_percent / 100) * SAMPLE_AMOUNT
    
    if request.method == 'POST':
        try:
            plan.name = request.POST.get('name')
            plan.duration_months = int(request.POST.get('duration_months'))
            
            # ✅ Get down payment amount from form
            down_payment_amount_post = Decimal(request.POST.get('down_payment_amount', 0))
            
            # ✅ Calculate percentage from amount
            if SAMPLE_AMOUNT > 0:
                down_payment_percent = (down_payment_amount_post / SAMPLE_AMOUNT) * 100
                plan.down_payment_percent = min(Decimal('100'), max(Decimal('0'), down_payment_percent))
            else:
                plan.down_payment_percent = Decimal('0')
            
            plan.interest_rate = Decimal(request.POST.get('interest_rate', 0))
            plan.late_fee_per_day = Decimal(request.POST.get('late_fee_per_day', 0))
            plan.is_active = request.POST.get('is_active') == 'on'
            plan.save()
            
            messages.success(request, f'✅ Plan "{plan.name}" updated successfully!')
            return redirect('installment_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('installment_plan_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'down_payment_amount': round(down_payment_amount, 2),  # ✅ Pass amount to template
    }
    return render(request, 'installments/edit.html', context)


@login_required
def installment_plan_delete(request, pk):
    """Delete installment plan"""
    plan = get_object_or_404(InstallmentPlan, pk=pk)
    
    if request.method == 'POST':
        try:
            plan_name = plan.name
            plan.delete()
            messages.success(request, f'🗑️ Plan "{plan_name}" deleted successfully!')
            return redirect('installment_list')
        except Exception as e:
            messages.error(request, f'❌ Cannot delete: {str(e)}')
            return redirect('installment_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
    }
    return render(request, 'installments/delete_confirm.html', context)


@login_required
def installment_create(request):
    """Create new installment plan"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            duration_months = int(request.POST.get('duration_months'))
            
            # ✅ NEW: Get down payment amount from form
            down_payment_amount = Decimal(request.POST.get('down_payment_amount', 0))
            
            # ✅ Calculate percentage based on default sample amount (100,000)
            # For saving in database, we store percentage as before
            # But we also store the amount reference
            sample_amount = Decimal('100000')  # Default reference amount
            if sample_amount > 0:
                down_payment_percent = (down_payment_amount / sample_amount) * 100
                down_payment_percent = min(Decimal('100'), max(Decimal('0'), down_payment_percent))
            else:
                down_payment_percent = Decimal('0')
            
            interest_rate = Decimal(request.POST.get('interest_rate', 0))
            late_fee_per_day = Decimal(request.POST.get('late_fee_per_day', 0))
            is_active = request.POST.get('is_active') == 'on'
            
            if not name or duration_months <= 0:
                messages.error(request, 'Please enter valid plan name and duration!')
                return redirect('installment_create')
            
            plan = InstallmentPlan.objects.create(
                name=name,
                duration_months=duration_months,
                down_payment_percent=down_payment_percent,  # Store percentage as before
                interest_rate=interest_rate,
                late_fee_per_day=late_fee_per_day,
                is_active=is_active
            )
            
            messages.success(request, f'✅ Installment plan "{plan.name}" created successfully!')
            return redirect('installment_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('installment_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'installments/create.html', context)


# ✅ NEW CODE
@login_required
def installment_list(request):
    installments = SaleInstallment.objects.select_related(
        'sale',
        'sale__customer',
        'sale__customer__group',
        'plan',
        'created_by'
    ).prefetch_related(
        'emi_payments',
        'sale__saleitem_set__product'
    ).order_by('-created_at')
    
    # Filters
    status = request.GET.get('status', '')
    if status:
        installments = installments.filter(status=status)
    
    plan_id = request.GET.get('plan', '')
    if plan_id:
        installments = installments.filter(plan_id=plan_id)
    
    search = request.GET.get('search', '')
    if search:
        installments = installments.filter(
            Q(sale__bill_no__icontains=search) |
            Q(sale__customer__name__icontains=search) |
            Q(sale__customer__customer_code__icontains=search)
        )
    
    # Summary statistics
    total_installments = installments.count()
    total_amount = sum(i.total_amount for i in installments)
    total_paid = sum(i.total_paid() for i in installments)
    total_outstanding = total_amount - total_paid
    total_defaulted = installments.filter(status='defaulted').count()
    total_active = installments.filter(status__in=['pending', 'partial']).count()
    total_completed = installments.filter(status='paid').count()
    
    # Calculate overdue count
    overdue_count = 0
    for inst in installments:
        if inst.next_due_date and inst.next_due_date < now().date() and inst.status != 'paid':
            overdue_count += 1
    
    # Pagination
    paginator = Paginator(installments, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'today':date.today(),
        'page_obj': page_obj,
        'installments': page_obj,
        'total_installments': total_installments,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'total_active': total_active,
        'total_completed': total_completed,
        'total_defaulted': total_defaulted,
        'overdue_count': overdue_count,
        'selected_status': status,
        'selected_plan': plan_id,
        'search': search,
        'plans': InstallmentPlan.objects.filter(is_active=True),
        'status_choices': SaleInstallment.PAYMENT_STATUS,
    }
    return render(request, 'installments/list.html', context)


@login_required
def installment_detail(request, pk):
    """Installment detail view with EMI schedule"""
    installment = get_object_or_404(
        SaleInstallment.objects.select_related('sale', 'sale__customer', 'plan', 'created_by'),
        pk=pk
    )
    
    # Get EMI payments
    emi_payments = installment.emi_payments.all().order_by('installment_number')
    
    # Calculate statistics
    total_emis = emi_payments.count()
    paid_emis = emi_payments.filter(status='paid').count()
    pending_emis = emi_payments.filter(status='pending').count()
    overdue_emis = emi_payments.filter(status='pending', due_date__lt=now().date()).count()
    
    # Calculate late fee
    late_fee = installment.calculate_late_fee()
    
    # Get payment methods for EMI payment form
    from ..models import PaymentMethod
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    
    # Get payment history
    payment_history = SalePayment.objects.filter(sale=installment.sale).order_by('-payment_date')
    
    # Calculate payment progress for chart
    progress_percent = 0
    if installment.total_payable > 0:
        progress_percent = round((installment.total_paid() / installment.total_payable) * 100, 1)
    
    # Prepare chart data
    months = []
    paid_data = []
    due_data = []
    
    for emi in emi_payments:
        months.append(f"EMI #{emi.installment_number}")
        paid_data.append(float(emi.amount_paid))
        due_data.append(float(emi.amount_due - emi.amount_paid))
    
    import json
    chart_data = {
        'months': months,
        'paid': paid_data,
        'due': due_data,
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'installment': installment,
        'emi_payments': emi_payments,
        'total_emis': total_emis,
        'paid_emis': paid_emis,
        'pending_emis': pending_emis,
        'overdue_emis': overdue_emis,
        'late_fee': late_fee,
        'payment_methods': payment_methods,
        'payment_history': payment_history,
        'progress_percent': progress_percent,
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'installments/detail.html', context)


@login_required
def installment_pdf(request, pk):
    """Generate PDF report for installment"""
    installment = get_object_or_404(SaleInstallment, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP SYSTEM"
    company_address = company.address if company else ""
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
    story.append(Paragraph(company_name, title_style))
    if company_address:
        story.append(Paragraph(company_address, styles['Normal']))
    story.append(Paragraph("INSTALLMENT AGREEMENT", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Header details
    header_data = [
        [Paragraph(f"<b>Bill No:</b> {installment.sale.bill_no}", styles['Normal']),
         Paragraph(f"<b>Date:</b> {installment.sale.sale_date.strftime('%d-%m-%Y')}", styles['Normal'])],
        [Paragraph(f"<b>Customer:</b> {installment.sale.customer.name}", styles['Normal']),
         Paragraph(f"<b>Plan:</b> {installment.plan.name if installment.plan else 'Custom'}", styles['Normal'])],
        [Paragraph(f"<b>Phone:</b> {installment.sale.customer.contact_number or 'N/A'}", styles['Normal']),
         Paragraph(f"<b>Status:</b> {installment.get_status_display()}", styles['Normal'])],
    ]
    
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Amount Summary
    amount_data = [
        ['Description', 'Amount (Rs.)'],
        ['Total Sale Amount', f'{installment.total_amount:,.2f}'],
        ['Down Payment', f'({installment.down_payment_amount:,.2f})'],
        ['Loan Amount', f'{installment.loan_amount:,.2f}'],
        ['Interest', f'{installment.total_interest:,.2f}'],
        ['Total Payable', f'{installment.total_payable:,.2f}'],
        ['', ''],
        ['Total Paid', f'{installment.total_paid():,.2f}'],
        ['Remaining', f'{installment.remaining_amount():,.2f}'],
    ]
    
    amount_table = Table(amount_data, colWidths=[3*inch, 2*inch])
    amount_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 7), (-1, 8), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, 7), (-1, 8), 'Helvetica-Bold'),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 0.3*inch))
    
    # EMI Schedule
    story.append(Paragraph("<b>EMI Payment Schedule</b>", styles['Heading2']))
    
    emi_data = [['#', 'Due Date', 'Amount Due', 'Amount Paid', 'Status', 'Payment Date']]
    
    for emi in installment.emi_payments.all().order_by('installment_number'):
        emi_data.append([
            str(emi.installment_number),
            emi.due_date.strftime('%d-%m-%Y'),
            f"Rs. {emi.amount_due:,.2f}",
            f"Rs. {emi.amount_paid:,.2f}",
            emi.get_status_display(),
            emi.payment_date.strftime('%d-%m-%Y') if emi.payment_date else '-',
        ])
    
    emi_table = Table(emi_data, repeatRows=1)
    emi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (3, -1), 'RIGHT'),
    ]))
    
    story.append(emi_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Late Fee Notice
    if installment.late_fee_accrued > 0:
        story.append(Paragraph(
            f"<b>⚠️ Late Fee Accrued: Rs. {installment.late_fee_accrued:,.2f}</b>",
            styles['Normal']
        ))
    
    # Terms
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("<b>Terms & Conditions:</b>", styles['Normal']))
    story.append(Paragraph("1. EMI must be paid by the due date.", styles['Normal']))
    story.append(Paragraph(f"2. Late payment fee: Rs. {installment.plan.late_fee_per_day}/day after due date.", styles['Normal']))
    story.append(Paragraph("3. Default after 30 days of overdue payment.", styles['Normal']))
    
    # Footer
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated on: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    story.append(Paragraph("This is a computer generated document.", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Installment_{installment.sale.bill_no}.pdf"'
    return response


@login_required
def get_installment_plan(request):
    """AJAX: Get installment plan details and calculate EMI"""
    plan_id = request.GET.get('plan_id')
    total_amount = request.GET.get('total_amount', 0)
    
    if not plan_id:
        return JsonResponse({'success': False, 'message': 'Plan ID required'})
    
    try:
        plan = InstallmentPlan.objects.get(id=plan_id, is_active=True)
        calculation = plan.calculate_emi(Decimal(str(total_amount)))
        
        return JsonResponse({
            'success': True,
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'duration_months': plan.duration_months,
                'down_payment_percent': str(plan.down_payment_percent),
                'interest_rate': str(plan.interest_rate),
                'late_fee_per_day': str(plan.late_fee_per_day),
            },
            'calculation': {
                'down_payment': str(calculation['down_payment']),
                'loan_amount': str(calculation['loan_amount']),
                'emi': str(calculation['emi']),
                'total_payable': str(calculation['total_payable']),
                'total_interest': str(calculation['total_interest']),
                'number_of_emis': plan.duration_months,
            }
        })
    except InstallmentPlan.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Plan not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def create_installment_sale(request):
    """AJAX: Create sale with installment plan"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            sale_id = data.get('sale_id')
            plan_id = data.get('plan_id')
            down_payment = Decimal(str(data.get('down_payment', 0)))
            
            if not sale_id:
                return JsonResponse({'success': False, 'message': 'Sale ID required'})
            if not plan_id:
                return JsonResponse({'success': False, 'message': 'Plan ID required'})
            
            sale = Sale.objects.get(id=sale_id)
            plan = InstallmentPlan.objects.get(id=plan_id, is_active=True)
            
            total_amount = sale.total_amount()
            calculation = plan.calculate_emi(total_amount)
            
            # Check if down payment is sufficient
            if down_payment < calculation['down_payment']:
                return JsonResponse({
                    'success': False, 
                    'message': f'Down payment should be at least Rs. {calculation["down_payment"]:,.2f}',
                    'required_down_payment': str(calculation['down_payment'])
                })
            
            # Create installment record
            installment = SaleInstallment.objects.create(
                sale=sale,
                plan=plan,
                total_amount=total_amount,
                down_payment_amount=calculation['down_payment'],
                down_payment_paid=True,  # Down payment received
                loan_amount=calculation['loan_amount'],
                emi_amount=calculation['emi'],
                total_interest=calculation['total_interest'],
                total_payable=calculation['total_payable'],
                start_date=now().date(),
                created_by=request.user,
                status='partial'  # Down payment received, so partial
            )
            
            # Update sale
            sale.is_installment = True
            sale.installment_plan = plan
            sale.down_payment_received = down_payment
            sale.save()
            
            # Update paid amount in sale
            sale.paid += down_payment
            sale.save()
            
            # Create payment record for down payment
            from ..models import PaymentMethod
            cash_method, _ = PaymentMethod.objects.get_or_create(name='cash', defaults={'is_active': True})
            
            SalePayment.objects.create(
                sale=sale,
                method=cash_method,
                amount=down_payment,
                reference_no=f"DP-{installment.id}",
                created_by=request.user
            )
            
            # Generate EMI schedule
            for i in range(1, plan.duration_months + 1):
                due_date = installment.start_date + timedelta(days=30 * i)
                EmiPayment.objects.create(
                    installment=installment,
                    installment_number=i,
                    due_date=due_date,
                    amount_due=calculation['emi']
                )
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Installment plan created! Monthly EMI: Rs. {calculation["emi"]:,.2f}',
                'installment_id': installment.id,
                'emi_amount': str(calculation['emi']),
                'total_payable': str(calculation['total_payable']),
                'down_payment_received': str(down_payment),
                'number_of_emis': plan.duration_months,
            })
            
        except Sale.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Sale not found'})
        except InstallmentPlan.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Installment plan not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def pay_emi(request):
    """AJAX: Pay an EMI installment with notifications"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            emi_id = data.get('emi_id')
            amount = Decimal(str(data.get('amount', 0)))
            payment_method_id = data.get('payment_method_id')
            reference_no = data.get('reference_no', '')
            
            if not emi_id:
                return JsonResponse({'success': False, 'message': 'EMI ID required'})
            
            emi = EmiPayment.objects.get(id=emi_id)
            
            if emi.status == 'paid':
                return JsonResponse({'success': False, 'message': 'EMI already paid!'})
            
            if amount <= 0:
                return JsonResponse({'success': False, 'message': 'Amount must be greater than 0'})
            
            # Check if amount exceeds due
            if amount > emi.remaining_due():
                return JsonResponse({
                    'success': False, 
                    'message': f'Amount cannot exceed due amount: Rs. {emi.remaining_due():,.2f}'
                })
            
            from ..models import PaymentMethod
            payment_method = None
            if payment_method_id:
                payment_method = PaymentMethod.objects.get(id=payment_method_id)
            else:
                payment_method, _ = PaymentMethod.objects.get_or_create(name='cash', defaults={'is_active': True})
            
            # Get old remaining amount to check if fully paid
            was_fully_paid_before = (emi.remaining_due() - amount) <= 0
            
            # Mark EMI as paid
            emi.mark_paid(amount, payment_method, reference_no, f"EMI #{emi.installment_number} payment", request.user)
            
            # Update sale paid amount
            sale = emi.installment.sale
            sale.paid += amount
            sale.save()
            
            from ..models import Notification
            
            # ✅ Send payment received notification
            Notification.send_payment_notification(request.user, sale, amount)
            
            # ✅ Send installment paid notification (with remaining balance info)
            remaining = emi.installment.remaining_amount()
            if remaining <= 0:
                # Fully paid notification
                Notification.send(
                    user=request.user,
                    title="✅ Installment Completed",
                    message=f"Installment for Bill #{sale.bill_no} has been fully paid! Total paid: Rs. {emi.installment.total_paid():,.2f}",
                    notification_type='success',
                    category='payments',
                    link=f"/installments/{emi.installment.id}/"
                )
            elif was_fully_paid_before:
                # Exactly paid full EMI
                Notification.send(
                    user=request.user,
                    title="💰 EMI Payment Received",
                    message=f"EMI #{emi.installment_number} of Rs. {amount:,.2f} paid for Bill #{sale.bill_no}. Remaining: Rs. {remaining:,.2f}",
                    notification_type='payment',
                    category='payments',
                    link=f"/installments/{emi.installment.id}/"
                )
            
            return JsonResponse({
                'success': True,
                'message': f'✅ EMI #{emi.installment_number} paid successfully!',
                'remaining_amount': str(emi.remaining_due()),
                'status': emi.status,
                'installment_remaining': str(emi.installment.remaining_amount()),
                'installment_status': emi.installment.status,
            })
            
        except EmiPayment.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'EMI not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def get_installment_details(request):
    """AJAX: Get installment details for a sale"""
    sale_id = request.GET.get('sale_id')
    
    if not sale_id:
        return JsonResponse({'success': False, 'message': 'Sale ID required'})
    
    try:
        installment = SaleInstallment.objects.filter(sale_id=sale_id).first()
        
        if not installment:
            return JsonResponse({'success': False, 'message': 'No installment plan found for this sale'})
        
        emis = []
        for emi in installment.emi_payments.all().order_by('installment_number'):
            emis.append({
                'id': emi.id,
                'number': emi.installment_number,
                'due_date': emi.due_date.strftime('%d-%m-%Y'),
                'amount_due': str(emi.amount_due),
                'amount_paid': str(emi.amount_paid),
                'remaining': str(emi.remaining_due()),
                'status': emi.status,
                'is_overdue': emi.is_overdue(),
            })
        
        return JsonResponse({
            'success': True,
            'installment': {
                'id': installment.id,
                'plan_name': installment.plan.name if installment.plan else 'Custom',
                'total_amount': str(installment.total_amount),
                'down_payment': str(installment.down_payment_amount),
                'down_payment_paid': installment.down_payment_paid,
                'emi_amount': str(installment.emi_amount),
                'total_paid': str(installment.total_paid()),
                'remaining': str(installment.remaining_amount()),
                'total_payable': str(installment.total_payable),
                'status': installment.status,
                'start_date': installment.start_date.strftime('%d-%m-%Y'),
                'next_due_date': installment.next_due_date.strftime('%d-%m-%Y') if installment.next_due_date else None,
                'late_fee': str(installment.calculate_late_fee()),
            },
            'emis': emis
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def get_available_plans(request):
    """AJAX: Get all active installment plans"""
    plans = InstallmentPlan.objects.filter(is_active=True).values(
        'id', 'name', 'duration_months', 'down_payment_percent', 'interest_rate', 'late_fee_per_day'
    )
    
    return JsonResponse({
        'success': True,
        'plans': list(plans)
    })
