"""Hr models."""
from django.db import models
from datetime import date
from django.contrib.auth.models import User

class Employee(models.Model):
    DEPARTMENT_CHOICES = [
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('accounts', 'Accounts'),
        ('warehouse', 'Warehouse'),
        ('admin', 'Admin'),
        ('hr', 'Human Resources'),
        ('it', 'IT'),
        ('marketing', 'Marketing'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('inactive', 'Inactive'),
        ('terminated', 'Terminated'),
    ]
    
    # Personal Information
    employee_id = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)
    dob = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    profile_pic = models.ImageField(upload_to='employee_profiles/', null=True, blank=True)
    
    # Employment Information
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Salary Information
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    house_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Bank Information
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Documents
    cv = models.FileField(upload_to='employee_cv/', null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_employees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "HR - Employees"
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['department', 'status']),
        ]
    
    def __str__(self):
        return f"{self.employee_id} - {self.name}"
    
    def total_salary(self):
        """Calculate total monthly salary"""
        return self.basic_salary + self.house_allowance + self.other_allowance
    
    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_emp = Employee.objects.order_by('-id').first()
            if last_emp and last_emp.employee_id:
                try:
                    last_num = int(last_emp.employee_id.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.employee_id = f'EMP-{new_num}'
        super().save(*args, **kwargs)


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('halfday', 'Half Day'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "HR - Attendance"
        unique_together = ['employee', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['employee', 'date']),
        ]
    
    def __str__(self):
        return f"{self.employee.name} - {self.date} - {self.get_status_display()}"


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('casual', 'Casual Leave'),
        ('sick', 'Sick Leave'),
        ('annual', 'Annual Leave'),
        ('unpaid', 'Unpaid Leave'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=10, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_leaves')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "HR - Leave Requests"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.name} - {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"
    
    def total_days(self):
        delta = self.end_date - self.start_date
        return delta.days + 1


class Payroll(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    month = models.DateField(help_text="First day of the month")
    
    # Earnings
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    house_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Deductions
    tax_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    loan_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Attendance Summary
    total_present = models.IntegerField(default=0)
    total_absent = models.IntegerField(default=0)
    total_late = models.IntegerField(default=0)
    total_halfday = models.IntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "HR - Payroll"
        unique_together = ['employee', 'month']
        ordering = ['-month']
    
    def __str__(self):
        return f"{self.employee.name} - {self.month.strftime('%B %Y')}"
    
    def total_earnings(self):
        return self.basic_salary + self.house_allowance + self.other_allowance + self.bonus + self.overtime
    
    def total_deductions(self):
        return self.tax_deduction + self.loan_deduction + self.absence_deduction + self.other_deduction
    
    def net_salary(self):
        return self.total_earnings() - self.total_deductions()


class EmployeeSalaryHistory(models.Model):
    """Track salary changes history"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_history')
    old_basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    new_basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    change_date = models.DateField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name_plural = "HR - Salary History"
        ordering = ['-change_date']
    
    def __str__(self):
        return f"{self.employee.name} - {self.change_date}: {self.old_basic_salary} → {self.new_basic_salary}"
