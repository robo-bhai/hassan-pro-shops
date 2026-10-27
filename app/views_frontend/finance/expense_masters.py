"""Frontend views: finance/expense_masters (split from the former expenses_budget.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ...models import CompanyInfo, Department, Project


@login_required
@perm_required('view_expenses')
def expense_category_list(request):
    """List all expense categories"""
    categories = ExpenseCategory.objects.filter(is_active=True)
    
    search = request.GET.get('search', '')
    if search:
        categories = categories.filter(name__icontains=search)
    
    category_type = request.GET.get('type', '')
    if category_type:
        categories = categories.filter(category_type=category_type)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': categories,
        'search': search,
        'category_type': category_type,
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'total_categories': categories.count(),
        'active_categories': categories.filter(is_active=True).count(),
    }
    return render(request, 'expenses/category_list.html', context)


@login_required
@perm_required('manage_expenses')
def expense_category_create(request):
    """Create new expense category from frontend"""
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            category_type = request.POST.get('category_type')
            parent_id = request.POST.get('parent') or None
            description = request.POST.get('description', '')
            is_active = request.POST.get('is_active') == 'on'
            
            if not name:
                messages.error(request, 'Category name is required!')
                return redirect('expense_category_create')
            
            # Check duplicate
            if ExpenseCategory.objects.filter(name__iexact=name).exists():
                messages.error(request, f'Category "{name}" already exists!')
                return redirect('expense_category_create')
            
            category = ExpenseCategory.objects.create(
                name=name,
                category_type=category_type,
                parent_id=parent_id,
                description=description,
                is_active=is_active
            )
            
            messages.success(request, f'✅ Category "{category.name}" created successfully!')
            return redirect('expense_category_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_category_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'parent_categories': ExpenseCategory.objects.filter(parent__isnull=True, is_active=True),
    }
    return render(request, 'expenses/category_create.html', context)


@login_required
@perm_required('manage_expenses')
def expense_category_edit(request, pk):
    """Edit expense category"""
    
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        try:
            category.name = request.POST.get('name', '').strip()
            category.category_type = request.POST.get('category_type')
            category.parent_id = request.POST.get('parent') or None
            category.description = request.POST.get('description', '')
            category.is_active = request.POST.get('is_active') == 'on'
            category.save()
            
            messages.success(request, f'✅ Category "{category.name}" updated!')
            return redirect('expense_category_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('expense_category_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category': category,
        'category_types': ExpenseCategory.CATEGORY_TYPES,
        'parent_categories': ExpenseCategory.objects.filter(parent__isnull=True, is_active=True).exclude(pk=pk),
    }
    return render(request, 'expenses/category_edit.html', context)


@login_required
@perm_required('manage_expenses')
def expense_category_delete(request, pk):
    """Delete expense category"""
    
    category = get_object_or_404(ExpenseCategory, pk=pk)
    
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'🗑️ Category "{name}" deleted!')
        return redirect('expense_category_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'category': category,
    }
    return render(request, 'expenses/category_delete.html', context)


@login_required
@perm_required('view_expenses')
def department_list(request):
    """List all departments"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    departments = Department.objects.all().order_by('name')
    
    search = request.GET.get('search', '')
    if search:
        departments = departments.filter(name__icontains=search)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'departments': departments,
        'search': search,
    }
    return render(request, 'departments/list.html', context)


@login_required
@perm_required('manage_expenses')
def department_create(request):
    """Create new department"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Department name is required!')
            return redirect('department_create')
        
        department = Department.objects.create(
            name=name,
            code=code if code else name[:3].upper(),
            description=description,
            is_active=is_active
        )
        
        messages.success(request, f'✅ Department "{department.name}" created successfully!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'departments/create.html', context)


@login_required
@perm_required('manage_expenses')
def department_edit(request, pk):
    """Edit department"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        department.name = request.POST.get('name', '').strip()
        department.code = request.POST.get('code', '').strip()
        department.description = request.POST.get('description', '')
        department.is_active = request.POST.get('is_active') == 'on'
        department.save()
        
        messages.success(request, f'✅ Department "{department.name}" updated!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'department': department,
    }
    return render(request, 'departments/edit.html', context)


@login_required
@perm_required('manage_expenses')
def department_delete(request, pk):
    """Delete department"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can delete departments.')
        return redirect('department_list')
    
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        name = department.name
        department.delete()
        messages.success(request, f'🗑️ Department "{name}" deleted!')
        return redirect('department_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'department': department,
    }
    return render(request, 'departments/delete.html', context)


@login_required
@perm_required('view_expenses')
def project_list(request):
    """List all projects"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    projects = Project.objects.select_related('department', 'manager').all().order_by('-start_date')
    
    search = request.GET.get('search', '')
    if search:
        projects = projects.filter(name__icontains=search)
    
    status = request.GET.get('status', '')
    if status:
        projects = projects.filter(status=status)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
        'search': search,
        'status': status,
    }
    return render(request, 'projects/list.html', context)


@login_required
@perm_required('manage_expenses')
def project_create(request):
    """Create new project"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        description = request.POST.get('description', '')
        department_id = request.POST.get('department')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        budget = request.POST.get('budget', 0)
        status = request.POST.get('status', 'active')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Project name is required!')
            return redirect('project_create')
        
        project = Project.objects.create(
            name=name,
            code=code if code else f'PRJ-{Project.objects.count() + 1:04d}',
            description=description,
            department_id=department_id if department_id else None,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            status=status,
            is_active=is_active
        )
        
        messages.success(request, f'✅ Project "{project.name}" created successfully!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'departments': Department.objects.filter(is_active=True),
    }
    return render(request, 'projects/create.html', context)


@login_required
@perm_required('manage_expenses')
def project_edit(request, pk):
    """Edit project"""
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    project = get_object_or_404(Project, pk=pk)
    
    if request.method == 'POST':
        project.name = request.POST.get('name', '').strip()
        project.code = request.POST.get('code', '').strip()
        project.description = request.POST.get('description', '')
        project.department_id = request.POST.get('department') if request.POST.get('department') else None
        project.start_date = request.POST.get('start_date')
        project.end_date = request.POST.get('end_date')
        project.budget = request.POST.get('budget', 0)
        project.status = request.POST.get('status', 'active')
        project.is_active = request.POST.get('is_active') == 'on'
        project.save()
        
        messages.success(request, f'✅ Project "{project.name}" updated!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'project': project,
        'departments': Department.objects.filter(is_active=True),
    }
    return render(request, 'projects/edit.html', context)


@login_required
@perm_required('manage_expenses')
def project_delete(request, pk):
    """Delete project"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can delete projects.')
        return redirect('project_list')
    
    project = get_object_or_404(Project, pk=pk)
    
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'🗑️ Project "{name}" deleted!')
        return redirect('project_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'project': project,
    }
    return render(request, 'projects/delete.html', context)
