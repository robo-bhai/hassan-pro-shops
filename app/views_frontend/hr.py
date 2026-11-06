"""Frontend views: hr."""
from ..models import *
import json
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from decimal import Decimal
from django.utils.timezone import now
from datetime import date, timedelta, datetime
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from ..models import CompanyInfo, Sale, Employee, Attendance, LeaveRequest, Payroll, EmployeeSalaryHistory
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


@login_required
def employee_performance_report(request):
    """Employee performance report (sales by employee)"""
    from_date = request.GET.get('from_date', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    
    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    employee_sales = Sale.objects.filter(
        sale_date__date__gte=from_date_obj,
        sale_date__date__lte=to_date_obj,
        created_by__isnull=False
    ).values(
        'created_by__username',
        'created_by__first_name'
    ).annotate(
        total_sales=Sum('saleitem__total_amt'),
        total_profit=Sum('saleitem__profit'),
        sale_count=Count('id'),
        total_discount=Sum('discount_value')
    ).order_by('-total_sales')
    
    for i, emp in enumerate(employee_sales, 1):
        emp['rank'] = i
        net_profit = (emp['total_profit'] or 0) - (emp['total_discount'] or 0)
        emp['net_profit'] = net_profit
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee_sales': employee_sales,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'reports/employee_performance.html', context)


@login_required
def print_salary_slip_html(request, pk):
    """Generate and print salary slip for employee as HTML - BASIC SALARY ONLY"""
    employee = get_object_or_404(Employee, pk=pk)
    company = CompanyInfo.objects.first()
    
    # Current month
    current_month = date.today().replace(day=1)
    WORKING_DAYS = 26
    
    # Get attendance for current month
    first_day = current_month
    if current_month.month == 12:
        last_day = date(current_month.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(current_month.year, current_month.month + 1, 1) - timedelta(days=1)
    
    attendances = Attendance.objects.filter(
        employee=employee,
        date__gte=first_day,
        date__lte=last_day
    )
    
    present_days = attendances.filter(status='present').count()
    absent_days = attendances.filter(status='absent').count()
    
    # Get payroll if exists (for bonus/deductions)
    payroll = Payroll.objects.filter(employee=employee, month=current_month).first()
    
    # Basic Salary ONLY - No allowances
    basic_salary = employee.basic_salary
    total_salary = basic_salary
    
    # Calculations
    per_day = total_salary / WORKING_DAYS if WORKING_DAYS > 0 else 0
    salary_for_present = per_day * present_days
    absence_deduction = per_day * absent_days
    
    # Bonus and deductions from payroll
    bonus = payroll.bonus if payroll else Decimal('0.00')
    tax_deduction = payroll.tax_deduction if payroll else Decimal('0.00')
    loan_deduction = payroll.loan_deduction if payroll else Decimal('0.00')
    other_deduction = payroll.other_deduction if payroll else Decimal('0.00')
    
    total_other_deductions = tax_deduction + loan_deduction + other_deduction
    total_earnings = salary_for_present + bonus
    total_deductions = absence_deduction + total_other_deductions
    net_salary = total_earnings - total_deductions
    
    context = {
        'company_name': company.name if company else 'ERP System',
        'company_address': company.address if company else '',
        'company_phone': company.contact_number if company else '',
        'employee': employee,
        'month': current_month.strftime('%B %Y'),
        'basic_salary': basic_salary,
        'total_salary': total_salary,
        'working_days': WORKING_DAYS,
        'present_days': present_days,
        'absent_days': absent_days,
        'per_day': per_day,
        'salary_for_present': salary_for_present,
        'bonus': bonus,
        'total_earnings': total_earnings,
        'absence_deduction': absence_deduction,
        'tax_deduction': tax_deduction,
        'total_deductions': total_deductions,
        'net_salary': net_salary,
        'current_date': datetime.now().strftime('%d-%m-%Y %I:%M:%S %p'),
    }
    return render(request, 'hr/salary_slip_print.html', context)


@login_required
def employee_list(request):
    """List all employees with filters"""
    # Check permission (only admin, owner, hr can view)
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['Owner', 'HR Manager']).exists():
        messages.error(request, 'Access denied! Only authorized users can view employees.')
        return redirect('dashboard')

    employees = Employee.objects.select_related(
        'created_by'
    ).prefetch_related(
        'attendances',
        'leave_requests',
        'payrolls'
    ).all()
    
    # Filters
    search = request.GET.get('search', '')
    department = request.GET.get('department', '')
    status = request.GET.get('status', '')
    joining_date = request.GET.get('joining_date', '')
    
    if search:
        employees = employees.filter(
            Q(name__icontains=search) |
            Q(employee_id__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search)
        )
    if department:
        employees = employees.filter(department=department)
    if status:
        employees = employees.filter(status=status)
    if joining_date:
        employees = employees.filter(joining_date__gte=joining_date)
    
    # Statistics
    total_employees = employees.count()
    active_employees = employees.filter(status='active').count()
    on_leave = employees.filter(status='on_leave').count()
    total_salary_monthly = sum(emp.total_salary() for emp in employees)
    
    # Pagination
    paginator = Paginator(employees, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'on_leave': on_leave,
        'total_salary_monthly': total_salary_monthly,
        'search': search,
        'department': department,
        'status': status,
        'joining_date': joining_date,
    }
    return render(request, 'hr/employee_list.html', context)


@login_required
def employee_create(request):
    """Create new employee"""
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['Owner', 'HR Manager']).exists():
        messages.error(request, 'Access denied! Only authorized users can create employees.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            # Basic Info
            name = request.POST.get('name')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            dob = request.POST.get('dob') or None
            address = request.POST.get('address', '')
            
            # Employment Info
            department = request.POST.get('department')
            designation = request.POST.get('designation', '')
            joining_date = request.POST.get('joining_date')
            status = request.POST.get('status', 'active')
            
            # Salary Info
            basic_salary = Decimal(request.POST.get('basic_salary', 0))
            house_allowance = Decimal(request.POST.get('house_allowance', 0))
            other_allowance = Decimal(request.POST.get('other_allowance', 0))
            
            # Bank Info
            bank_name = request.POST.get('bank_name', '')
            account_number = request.POST.get('account_number', '')
            
            # Validation
            if not name or not email or not phone:
                messages.error(request, 'Name, Email and Phone are required!')
                return redirect('employee_create')
            
            if Employee.objects.filter(email=email).exists():
                messages.error(request, 'Employee with this email already exists!')
                return redirect('employee_create')
            
            # Create employee
            employee = Employee.objects.create(
                name=name,
                email=email,
                phone=phone,
                dob=dob,
                address=address,
                department=department,
                designation=designation,
                joining_date=joining_date,
                status=status,
                basic_salary=basic_salary,
                house_allowance=house_allowance,
                other_allowance=other_allowance,
                bank_name=bank_name,
                account_number=account_number,
                created_by=request.user
            )
            
            messages.success(request, f'✅ Employee "{employee.name}" created successfully! ID: {employee.employee_id}')
            return redirect('employee_detail', pk=employee.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('employee_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'hr/employee_create.html', context)


@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(
        Employee.objects.select_related('created_by').prefetch_related(
            'attendances',
            'leave_requests',
            'payrolls',
            'salary_history'
        ),
        pk=pk
    )
    
    # ✅ FIX: Variables upar define karo
    today = date.today()
    first_day = today.replace(day=1)
    
    attendances = employee.attendances.filter(
        date__gte=first_day, 
        date__lte=today
    ).select_related('marked_by')
    
    present_days = attendances.filter(status='present').count()
    absent_days = attendances.filter(status='absent').count()
    late_days = attendances.filter(status='late').count()
    half_days = attendances.filter(status='halfday').count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
        'present_days': present_days,
        'absent_days': absent_days,
        'late_days': late_days,
        'half_days': half_days,
    }
    return render(request, 'hr/employee_detail.html', context)


@login_required
def employee_edit(request, pk):
    """Edit employee details"""
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['Owner', 'HR Manager']).exists():
        messages.error(request, 'Access denied! Only authorized users can edit employees.')
        return redirect('dashboard')
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        try:
            # Save old salary for history
            old_basic_salary = employee.basic_salary
            
            # Update fields
            employee.name = request.POST.get('name')
            employee.email = request.POST.get('email')
            employee.phone = request.POST.get('phone')
            employee.dob = request.POST.get('dob') or None
            employee.address = request.POST.get('address', '')
            employee.department = request.POST.get('department')
            employee.designation = request.POST.get('designation', '')
            employee.joining_date = request.POST.get('joining_date')
            employee.status = request.POST.get('status', 'active')
            employee.basic_salary = Decimal(request.POST.get('basic_salary', 0))
            employee.house_allowance = Decimal(request.POST.get('house_allowance', 0))
            employee.other_allowance = Decimal(request.POST.get('other_allowance', 0))
            employee.bank_name = request.POST.get('bank_name', '')
            employee.account_number = request.POST.get('account_number', '')
            employee.save()
            
            # Create salary history if salary changed
            if old_basic_salary != employee.basic_salary:
                EmployeeSalaryHistory.objects.create(
                    employee=employee,
                    old_basic_salary=old_basic_salary,
                    new_basic_salary=employee.basic_salary,
                    reason='Salary revision',
                    changed_by=request.user
                )
            
            messages.success(request, f'✅ Employee "{employee.name}" updated successfully!')
            return redirect('employee_detail', pk=employee.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('employee_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
    }
    return render(request, 'hr/employee_edit.html', context)


@login_required
def employee_delete(request, pk):
    """Delete employee (soft delete - set inactive)"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can delete employees.')
        return redirect('dashboard')
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        employee_name = employee.name
        employee.delete()
        messages.success(request, f'🗑️ Employee "{employee_name}" deleted successfully!')
        return redirect('employee_list')
    
    return redirect('employee_list')


@login_required
def attendance_mark(request):
    """Mark attendance for all employees"""
    today = date.today()
    
    # Check if attendance already marked for today
    existing = Attendance.objects.filter(date=today).first()
    if existing:
        messages.info(request, f'Attendance already marked for today! You can edit it.')
    
    employees = Employee.objects.filter(status='active')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employees': employees,
        'today': today,
    }
    return render(request, 'hr/attendance_mark.html', context)


@login_required
def attendance_save(request):
    """Save attendance via AJAX"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            attendance_data = data.get('attendance', {})
            attendance_date = data.get('date', str(date.today()))
            
            for emp_id, status in attendance_data.items():
                employee = Employee.objects.get(id=emp_id)
                
                # Update or create attendance
                attendance, created = Attendance.objects.update_or_create(
                    employee=employee,
                    date=attendance_date,
                    defaults={
                        'status': status,
                        'marked_by': request.user
                    }
                )
            
            return JsonResponse({'success': True, 'message': 'Attendance saved successfully!'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def attendance_today(request):
    """View today's attendance"""
    today = date.today()
    attendances = Attendance.objects.filter(date=today).select_related('employee')
    
    present = attendances.filter(status='present').count()
    absent = attendances.filter(status='absent').count()
    late = attendances.filter(status='late').count()
    halfday = attendances.filter(status='halfday').count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'attendances': attendances,
        'today': today,
        'present': present,
        'absent': absent,
        'late': late,
        'halfday': halfday,
    }
    return render(request, 'hr/attendance_today.html', context)


@login_required
def attendance_report(request):
    """Attendance report with date range"""
    from_date = request.GET.get('from_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to_date', date.today().strftime('%Y-%m-%d'))
    department = request.GET.get('department', '')
    
    attendances = Attendance.objects.filter(
        date__gte=from_date,
        date__lte=to_date
    ).select_related('employee')
    
    if department:
        attendances = attendances.filter(employee__department=department)
    
    # Group by employee
    employee_summary = {}
    for att in attendances:
        if att.employee.id not in employee_summary:
            employee_summary[att.employee.id] = {
                'employee': att.employee,
                'present': 0,
                'absent': 0,
                'late': 0,
                'halfday': 0,
            }
        employee_summary[att.employee.id][att.status] += 1
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee_summary': employee_summary.values(),
        'from_date': from_date,
        'to_date': to_date,
        'department': department,
        'departments': Employee.DEPARTMENT_CHOICES,
    }
    return render(request, 'hr/attendance_report.html', context)


@login_required
def employee_attendance(request, pk):
    """View attendance for specific employee"""
    employee = get_object_or_404(Employee, pk=pk)
    
    month = request.GET.get('month', date.today().strftime('%Y-%m'))
    year, month_num = map(int, month.split('-'))
    
    first_day = date(year, month_num, 1)
    if month_num == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month_num + 1, 1) - timedelta(days=1)
    
    attendances = Attendance.objects.filter(
        employee=employee,
        date__gte=first_day,
        date__lte=last_day
    ).order_by('date')
    
    # Create calendar data
    calendar_data = []
    for day in range(1, last_day.day + 1):
        current_date = date(year, month_num, day)
        attendance = attendances.filter(date=current_date).first()
        calendar_data.append({
            'date': current_date,
            'day': day,
            'status': attendance.status if attendance else None,
            'is_weekend': current_date.weekday() >= 5  # Saturday=5, Sunday=6
        })
    
    # Statistics
    present = attendances.filter(status='present').count()
    absent = attendances.filter(status='absent').count()
    late = attendances.filter(status='late').count()
    halfday = attendances.filter(status='halfday').count()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
        'calendar_data': calendar_data,
        'month': month,
        'month_name': first_day.strftime('%B %Y'),
        'present': present,
        'absent': absent,
        'late': late,
        'halfday': halfday,
        'total_days': last_day.day,
    }
    return render(request, 'hr/employee_attendance.html', context)


@login_required
def leave_list(request):
    """List all leave requests"""
    leaves = LeaveRequest.objects.select_related('employee', 'approved_by').order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        leaves = leaves.filter(status=status)
    
    paginator = Paginator(leaves, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'pending_count': LeaveRequest.objects.filter(status='pending').count(),
        'approved_count': LeaveRequest.objects.filter(status='approved').count(),
        'rejected_count': LeaveRequest.objects.filter(status='rejected').count(),
    }
    return render(request, 'hr/leave_list.html', context)


@login_required
def leave_request(request, employee_id=None):
    """Request leave (employee self or HR for employee)"""
    if employee_id:
        # HR/Manager requesting leave for an employee
        if not request.user.groups.filter(name__in=['HR Manager', 'Owner']).exists():
            messages.error(request, 'Access denied!')
            return redirect('leave_list')
        employee = get_object_or_404(Employee, pk=employee_id)
    else:
        # Employee requesting leave for themselves
        employee = Employee.objects.filter(email=request.user.email).first()
        if not employee:
            messages.error(request, 'No employee record found for your account!')
            return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            leave_type = request.POST.get('leave_type')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            reason = request.POST.get('reason')
            
            LeaveRequest.objects.create(
                employee=employee,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                status='pending'
            )
            
            messages.success(request, f'✅ Leave request submitted for {employee.name}!')
            return redirect('leave_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('leave_request')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
    }
    return render(request, 'hr/leave_request.html', context)


@login_required
def leave_approve(request, pk):
    """Approve leave request"""
    if not request.user.groups.filter(name__in=['HR Manager', 'Owner']).exists():
        messages.error(request, 'Access denied! Only HR can approve leaves.')
        return redirect('leave_list')
    
    leave = get_object_or_404(LeaveRequest, pk=pk)
    leave.status = 'approved'
    leave.approved_by = request.user
    leave.approved_at = now()
    leave.save()
    
    # Update employee status to on_leave
    if leave.start_date <= date.today() <= leave.end_date:
        leave.employee.status = 'on_leave'
        leave.employee.save()
    
    messages.success(request, f'✅ Leave approved for {leave.employee.name}!')
    return redirect('leave_list')


@login_required
def leave_reject(request, pk):
    """Reject leave request"""
    if not request.user.groups.filter(name__in=['HR Manager', 'Owner']).exists():
        messages.error(request, 'Access denied! Only HR can reject leaves.')
        return redirect('leave_list')
    
    leave = get_object_or_404(LeaveRequest, pk=pk)
    leave.status = 'rejected'
    leave.approved_by = request.user
    leave.approved_at = now()
    leave.save()
    
    messages.success(request, f'❌ Leave rejected for {leave.employee.name}!')
    return redirect('leave_list')


@login_required
def payroll_list(request):
    """List all payroll records"""
    if not request.user.groups.filter(name__in=['HR Manager', 'Accountant', 'Owner']).exists():
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    payrolls = Payroll.objects.select_related('employee').order_by('-month')
    
    month = request.GET.get('month', '')
    if month:
        payrolls = payrolls.filter(month__year=month.split('-')[0], month__month=month.split('-')[1])
    
    paginator = Paginator(payrolls, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    total_net_salary = sum(p.net_salary() for p in payrolls)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'total_net_salary': total_net_salary,
    }
    return render(request, 'hr/payroll_list.html', context)


@login_required
def employee_payroll(request, pk):
    """View payroll for specific employee"""
    employee = get_object_or_404(Employee, pk=pk)
    payrolls = Payroll.objects.filter(employee=employee).order_by('-month')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
        'payrolls': payrolls,
    }
    return render(request, 'hr/employee_payroll.html', context)


@login_required
def payroll_add(request, pk):
    """Add payroll for an employee"""
    if not request.user.groups.filter(name__in=['HR Manager', 'Accountant', 'Owner']).exists():
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        try:
            month = request.POST.get('month')
            bonus = Decimal(request.POST.get('bonus', 0))
            overtime = Decimal(request.POST.get('overtime', 0))
            tax_deduction = Decimal(request.POST.get('tax_deduction', 0))
            loan_deduction = Decimal(request.POST.get('loan_deduction', 0))
            other_deduction = Decimal(request.POST.get('other_deduction', 0))
            
            # Get attendance stats for the month
            year, month_num = map(int, month.split('-'))
            first_day = date(year, month_num, 1)
            if month_num == 12:
                last_day = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(year, month_num + 1, 1) - timedelta(days=1)
            
            attendances = Attendance.objects.filter(
                employee=employee,
                date__gte=first_day,
                date__lte=last_day
            )
            
            total_present = attendances.filter(status='present').count()
            total_absent = attendances.filter(status='absent').count()
            total_late = attendances.filter(status='late').count()
            total_halfday = attendances.filter(status='halfday').count()
            
            # Calculate absence deduction (1 day salary = basic_salary/working_days)
            working_days = 26  # Approximate working days in a month
            per_day_salary = employee.basic_salary / working_days
            absence_deduction = per_day_salary * total_absent
            
            payroll = Payroll.objects.create(
                employee=employee,
                month=first_day,
                basic_salary=employee.basic_salary,
                house_allowance=employee.house_allowance,
                other_allowance=employee.other_allowance,
                bonus=bonus,
                overtime=overtime,
                tax_deduction=tax_deduction,
                loan_deduction=loan_deduction,
                absence_deduction=absence_deduction,
                other_deduction=other_deduction,
                total_present=total_present,
                total_absent=total_absent,
                total_late=total_late,
                total_halfday=total_halfday,
                status='processed',
                created_by=request.user
            )
            
            messages.success(request, f'✅ Payroll created for {employee.name} - {first_day.strftime("%B %Y")}!')
            return redirect('employee_payroll', pk=employee.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('payroll_add', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employee': employee,
        'current_month': date.today().strftime('%Y-%m'),
    }
    return render(request, 'hr/payroll_add.html', context)


@login_required
def payslip_generate(request, pk):
    """Generate payslip PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from django.http import HttpResponse
    
    payroll = get_object_or_404(Payroll, pk=pk)
    employee = payroll.employee
    company = CompanyInfo.objects.first()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER)
    story.append(Paragraph(company.name if company else "ERP SYSTEM", title_style))
    story.append(Paragraph("PAYSLIP", title_style))
    story.append(Paragraph(f"Month: {payroll.month.strftime('%B %Y')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Employee Info
    emp_data = [
        ['Employee Name:', employee.name],
        ['Employee ID:', employee.employee_id],
        ['Department:', employee.get_department_display()],
        ['Designation:', employee.designation or '-'],
        ['Joining Date:', employee.joining_date.strftime('%d-%m-%Y')],
    ]
    
    emp_table = Table(emp_data, colWidths=[2*inch, 4*inch])
    emp_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Earnings Table
    earnings_data = [
        ['EARNINGS', 'Amount (Rs.)'],
        ['Basic Salary', f'{payroll.basic_salary:,.2f}'],
        ['House Allowance', f'{payroll.house_allowance:,.2f}'],
        ['Other Allowance', f'{payroll.other_allowance:,.2f}'],
        ['Bonus', f'{payroll.bonus:,.2f}'],
        ['Overtime', f'{payroll.overtime:,.2f}'],
        ['Total Earnings', f'{payroll.total_earnings():,.2f}'],
    ]
    
    earnings_table = Table(earnings_data, colWidths=[3*inch, 2*inch])
    earnings_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -2), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8ecf4')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(earnings_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Deductions Table
    deductions_data = [
        ['DEDUCTIONS', 'Amount (Rs.)'],
        ['Tax Deduction', f'{payroll.tax_deduction:,.2f}'],
        ['Loan Deduction', f'{payroll.loan_deduction:,.2f}'],
        ['Absence Deduction', f'{payroll.absence_deduction:,.2f}'],
        ['Other Deduction', f'{payroll.other_deduction:,.2f}'],
        ['Total Deductions', f'{payroll.total_deductions():,.2f}'],
    ]
    
    deductions_table = Table(deductions_data, colWidths=[3*inch, 2*inch])
    deductions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (1, -2), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fff3cd')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(deductions_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Net Salary
    net_data = [
        ['NET SALARY', f'Rs. {payroll.net_salary():,.2f}'],
    ]
    net_table = Table(net_data, colWidths=[3*inch, 2*inch])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Attendance Summary
    story.append(Paragraph("<b>Attendance Summary</b>", styles['Heading2']))
    att_data = [
        ['Present', 'Absent', 'Late', 'Half Day'],
        [str(payroll.total_present), str(payroll.total_absent), str(payroll.total_late), str(payroll.total_halfday)],
    ]
    att_table = Table(att_data, colWidths=[1.25*inch]*4)
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1d2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(att_table)
    
    # Footer
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("This is a computer generated payslip.", styles['Normal']))
    story.append(Paragraph(f"Generated on: {now().strftime('%d-%m-%Y %I:%M %p')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Payslip_{employee.employee_id}_{payroll.month.strftime("%B_%Y")}.pdf"'
    return response
