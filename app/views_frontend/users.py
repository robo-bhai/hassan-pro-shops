"""Frontend views: users."""
from ..models import *
import json
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils.timezone import now
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.contrib.auth.models import User, Group, Permission
from ..models import CompanyInfo
from django.contrib.auth.hashers import make_password
from reportlab.lib import colors
from django.contrib.contenttypes.models import ContentType


@login_required
def user_create(request):
    """Create new user with role"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can create users.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            full_name = request.POST.get('full_name', '')
            email = request.POST.get('email', '')
            phone = request.POST.get('phone', '')
            role = request.POST.get('role')
            is_active = request.POST.get('is_active') == 'on'
            
            if password != confirm_password:
                messages.error(request, 'Passwords do not match!')
                return redirect('user_create')
            
            if len(password) < 6:
                messages.error(request, 'Password must be at least 6 characters!')
                return redirect('user_create')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists!')
                return redirect('user_create')
            
            # Split full name
            name_parts = full_name.split(' ', 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            user = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active,
                password=make_password(password)
            )
            
            # Add to group based on role
            group_name = {
                'admin': None,
                'owner': 'Owner',
                'salesman': 'Salesman',
                'accountant': 'Accountant',
                'manager': 'Store Manager',
                'warehouse': 'Warehouse Staff'
            }.get(role)
            
            if group_name:
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)
            
            if role == 'admin':
                user.is_superuser = True
                user.is_staff = True
                user.save()
            
            messages.success(request, f'✅ User "{username}" created successfully!')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('user_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'users/user_create.html', context)


@login_required
def user_edit(request, pk):
    """Edit user details"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can edit users.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    # Determine user role
    if user.is_superuser:
        user_role = 'admin'
    elif user.groups.filter(name='Owner').exists():
        user_role = 'owner'
    elif user.groups.filter(name='Salesman').exists():
        user_role = 'salesman'
    elif user.groups.filter(name='Accountant').exists():
        user_role = 'accountant'
    elif user.groups.filter(name='Store Manager').exists():
        user_role = 'manager'
    elif user.groups.filter(name='Warehouse Staff').exists():
        user_role = 'warehouse'
    else:
        user_role = 'staff'
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            full_name = request.POST.get('full_name', '')
            email = request.POST.get('email', '')
            role = request.POST.get('role')
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            
            if User.objects.filter(username=username).exclude(pk=pk).exists():
                messages.error(request, 'Username already exists!')
                return redirect('user_edit', pk=pk)
            
            # Split full name
            name_parts = full_name.split(' ', 1) if full_name else [user.first_name, user.last_name]
            first_name = name_parts[0] if name_parts else user.first_name
            last_name = name_parts[1] if len(name_parts) > 1 else user.last_name
            
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = is_active
            user.is_staff = is_staff
            
            # Update groups
            user.groups.clear()
            group_name = {
                'admin': None,
                'owner': 'Owner',
                'salesman': 'Salesman',
                'accountant': 'Accountant',
                'manager': 'Store Manager',
                'warehouse': 'Warehouse Staff'
            }.get(role)
            
            if group_name:
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)
            
            if role == 'admin':
                user.is_superuser = True
            else:
                user.is_superuser = False
            
            user.save()
            
            messages.success(request, f'✅ User "{username}" updated successfully!')
            return redirect('user_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('user_edit', pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'user': user,
        'user_role': user_role,
    }
    return render(request, 'users/user_edit.html', context)


@login_required
def user_delete(request, pk):
    """Delete user"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can delete users.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    if user.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account!')
        return redirect('user_list')
    
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'🗑️ User "{username}" deleted successfully!')
        return redirect('user_list')
    
    return redirect('user_list')


@login_required
def user_toggle_status(request, pk):
    """Activate/Deactivate user"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can change user status.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    if user.pk == request.user.pk:
        messages.error(request, 'You cannot change your own status!')
        return redirect('user_list')
    
    user.is_active = not user.is_active
    user.save()
    
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'✅ User "{user.username}" has been {status}!')
    return redirect('user_list')


@login_required
def user_reset_password(request, pk):
    """Reset user password"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can reset passwords.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match!')
            return redirect('user_reset_password', pk=pk)
        
        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters!')
            return redirect('user_reset_password', pk=pk)
        
        user.password = make_password(password)
        user.save()
        
        messages.success(request, f'✅ Password reset for "{user.username}" successfully!')
        return redirect('user_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'user': user,
    }
    return render(request, 'users/user_reset_password.html', context)


@login_required
def user_list(request):
    """List all users with role filters - Professional"""
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can view users.')
        return redirect('dashboard')
    
    users = User.objects.select_related().all()
    
    # Add role info to each user
    for user in users:
        if user.is_superuser:
            user.role = 'admin'
            user.role_display = 'Administrator'
            user.role_icon = 'bi-shield-lock'
        elif user.groups.filter(name='Owner').exists():
            user.role = 'owner'
            user.role_display = 'Owner'
            user.role_icon = 'bi-building'
        elif user.groups.filter(name='Salesman').exists():
            user.role = 'salesman'
            user.role_display = 'Salesman'
            user.role_icon = 'bi-person-badge'
        elif user.groups.filter(name='Accountant').exists():
            user.role = 'accountant'
            user.role_display = 'Accountant'
            user.role_icon = 'bi-calculator'
        elif user.groups.filter(name='Store Manager').exists():
            user.role = 'manager'
            user.role_display = 'Store Manager'
            user.role_icon = 'bi-people'
        elif user.groups.filter(name='Warehouse Staff').exists():
            user.role = 'warehouse'
            user.role_display = 'Warehouse Staff'
            user.role_icon = 'bi-box'
        else:
            user.role = 'staff'
            user.role_display = 'Staff'
            user.role_icon = 'bi-person'
    
    # Filters
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    
    if search:
        users = users.filter(Q(username__icontains=search) | Q(email__icontains=search) | Q(first_name__icontains=search))
    if role_filter == 'admin':
        users = users.filter(is_superuser=True)
    elif role_filter == 'owner':
        users = users.filter(groups__name='Owner')
    elif role_filter == 'salesman':
        users = users.filter(groups__name='Salesman')
    elif role_filter == 'accountant':
        users = users.filter(groups__name='Accountant')
    elif role_filter == 'manager':
        users = users.filter(groups__name='Store Manager')
    elif role_filter == 'warehouse':
        users = users.filter(groups__name='Warehouse Staff')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Counts
    total_count = users.count()
    active_count = users.filter(is_active=True).count()
    inactive_count = users.filter(is_active=False).count()
    admin_count = User.objects.filter(is_superuser=True).count()
    
    paginator = Paginator(users, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'admin_count': admin_count,
    }
    return render(request, 'users/list.html', context)


@login_required
def bulk_user_action(request):
    """Bulk action API for users - Activate/Deactivate/Delete"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method!'})
    
    try:
        import json
        data = json.loads(request.body)
        action = data.get('action')
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return JsonResponse({'success': False, 'message': 'No users selected!'})
        
        users = User.objects.filter(id__in=user_ids)
        
        # Exclude current user from deletion
        if action == 'delete':
            users = users.exclude(id=request.user.id)
        
        if not users.exists():
            return JsonResponse({'success': False, 'message': 'No valid users found!'})
        
        with transaction.atomic():
            if action == 'activate':
                count = users.update(is_active=True)
                message = f'{count} user(s) activated successfully!'
            elif action == 'deactivate':
                count = users.update(is_active=False)
                message = f'{count} user(s) deactivated successfully!'
            elif action == 'delete':
                count = users.count()
                users.delete()
                message = f'{count} user(s) deleted successfully!'
            else:
                return JsonResponse({'success': False, 'message': 'Invalid action!'})
        
        return JsonResponse({'success': True, 'message': message})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def quick_view_user(request, user_id):
    """Quick view API for user details"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        user = User.objects.get(id=user_id)
        
        # Determine role
        if user.is_superuser:
            role = 'admin'
            role_display = 'Administrator'
        elif user.groups.filter(name='Owner').exists():
            role = 'owner'
            role_display = 'Owner'
        elif user.groups.filter(name='Salesman').exists():
            role = 'salesman'
            role_display = 'Salesman'
        elif user.groups.filter(name='Accountant').exists():
            role = 'accountant'
            role_display = 'Accountant'
        elif user.groups.filter(name='Store Manager').exists():
            role = 'manager'
            role_display = 'Store Manager'
        elif user.groups.filter(name='Warehouse Staff').exists():
            role = 'warehouse'
            role_display = 'Warehouse Staff'
        else:
            role = 'staff'
            role_display = 'Staff'
        
        # Avatar color based on username
        colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b', '#fa709a', '#fee140', '#f6d365']
        avatar_color = colors[hash(user.username) % len(colors)]
        
        return JsonResponse({
            'success': True,
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'email': user.email,
            'is_active': user.is_active,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never',
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M'),
            'role': role,
            'role_display': role_display,
            'avatar_color': avatar_color,
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def export_users(request):
    """Export users to CSV"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied!')
        return redirect('user_list')
    
    users = User.objects.all()
    
    # Apply filters
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    
    if search:
        users = users.filter(
            Q(username__icontains=search) | 
            Q(email__icontains=search) | 
            Q(first_name__icontains=search)
        )
    
    if role_filter == 'admin':
        users = users.filter(is_superuser=True)
    elif role_filter == 'owner':
        users = users.filter(groups__name='Owner')
    elif role_filter == 'salesman':
        users = users.filter(groups__name='Salesman')
    elif role_filter == 'accountant':
        users = users.filter(groups__name='Accountant')
    elif role_filter == 'manager':
        users = users.filter(groups__name='Store Manager')
    elif role_filter == 'warehouse':
        users = users.filter(groups__name='Warehouse Staff')
    
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="users_export_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Username', 'Full Name', 'Email', 'Role', 'Is Active', 'Last Login', 'Date Joined'])
    
    for user in users:
        if user.is_superuser:
            role = 'Admin'
        elif user.groups.filter(name='Owner').exists():
            role = 'Owner'
        elif user.groups.filter(name='Salesman').exists():
            role = 'Salesman'
        elif user.groups.filter(name='Accountant').exists():
            role = 'Accountant'
        elif user.groups.filter(name='Store Manager').exists():
            role = 'Store Manager'
        elif user.groups.filter(name='Warehouse Staff').exists():
            role = 'Warehouse Staff'
        else:
            role = 'Staff'
        
        writer.writerow([
            user.id,
            user.username,
            user.get_full_name(),
            user.email or '',
            role,
            'Yes' if user.is_active else 'No',
            user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '',
            user.date_joined.strftime('%Y-%m-%d %H:%M'),
        ])
    
    return response


@login_required
def user_activity_stats(request):
    """AJAX API: Get user activity statistics"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        now_date = now().date()
        seven_days_ago = now_date - timedelta(days=7)
        
        active_last_7_days = User.objects.filter(
            last_login__date__gte=seven_days_ago,
            is_active=True
        ).count()
        
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        inactive_users = User.objects.filter(is_active=False).count()
        never_logged_in = User.objects.filter(last_login__isnull=True).count()
        
        return JsonResponse({
            'success': True,
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'active_last_7_days': active_last_7_days,
            'never_logged_in': never_logged_in,
            'active_percent': round((active_users / total_users * 100) if total_users > 0 else 0, 1),
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def permission_matrix(request):
    """Display permission matrix for all roles"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        messages.error(request, 'Access denied! Only administrators can view permission matrix.')
        return redirect('dashboard')
    
    # Define roles with their permissions
    roles = [
        {
            'key': 'admin',
            'name': 'Administrator',
            'icon': 'bi-shield-lock',
            'permissions': ['all'],  # All permissions
            'partial_permissions': [],
            'user_count': User.objects.filter(is_superuser=True).count()
        },
        {
            'key': 'owner',
            'name': 'Owner',
            'icon': 'bi-building',
            'permissions': [
                'view_dashboard', 'view_reports', 'manage_users', 
                'manage_company', 'manage_roles', 'view_all'
            ],
            'partial_permissions': ['delete_users', 'manage_system'],
            'user_count': User.objects.filter(groups__name='Owner').count()
        },
        {
            'key': 'manager',
            'name': 'Store Manager',
            'icon': 'bi-people',
            'permissions': [
                'view_dashboard', 'view_reports', 'manage_inventory',
                'manage_orders', 'approve_purchases', 'manage_warehouse',
                'view_sales', 'manage_employees'
            ],
            'partial_permissions': ['manage_users', 'manage_finance'],
            'user_count': User.objects.filter(groups__name='Store Manager').count()
        },
        {
            'key': 'salesman',
            'name': 'Salesman',
            'icon': 'bi-person-badge',
            'permissions': [
                'view_dashboard', 'create_sales', 'view_customers',
                'view_products', 'create_customers', 'view_inventory'
            ],
            'partial_permissions': ['edit_sales', 'delete_sales'],
            'user_count': User.objects.filter(groups__name='Salesman').count()
        },
        {
            'key': 'accountant',
            'name': 'Accountant',
            'icon': 'bi-calculator',
            'permissions': [
                'view_dashboard', 'view_financials', 'view_reports',
                'view_expenses', 'manage_payments', 'view_invoices'
            ],
            'partial_permissions': ['edit_financials', 'manage_budget'],
            'user_count': User.objects.filter(groups__name='Accountant').count()
        },
        {
            'key': 'warehouse',
            'name': 'Warehouse',
            'icon': 'bi-box',
            'permissions': [
                'view_dashboard', 'manage_inventory', 'manage_stock',
                'receive_goods', 'dispatch_goods', 'view_products'
            ],
            'partial_permissions': ['manage_orders', 'view_sales'],
            'user_count': User.objects.filter(groups__name='Warehouse Staff').count()
        }
    ]
    
    # Define modules and their permissions
    modules = [
        {
            'key': 'dashboard',
            'name': '📊 Dashboard',
            'permissions': [
                {'key': 'view_dashboard', 'name': 'View Dashboard', 'icon': 'bi-speedometer2', 
                 'description': 'Access main dashboard'},
                {'key': 'view_reports', 'name': 'View Reports', 'icon': 'bi-graph-up', 
                 'description': 'View all reports'},
                {'key': 'view_analytics', 'name': 'View Analytics', 'icon': 'bi-bar-chart', 
                 'description': 'View business analytics'},
            ]
        },
        {
            'key': 'sales',
            'name': '🛒 Sales',
            'permissions': [
                {'key': 'view_sales', 'name': 'View Sales', 'icon': 'bi-eye', 
                 'description': 'View sales list'},
                {'key': 'create_sales', 'name': 'Create Sales', 'icon': 'bi-plus-circle', 
                 'description': 'Create new sales'},
                {'key': 'edit_sales', 'name': 'Edit Sales', 'icon': 'bi-pencil', 
                 'description': 'Edit existing sales'},
                {'key': 'delete_sales', 'name': 'Delete Sales', 'icon': 'bi-trash', 
                 'description': 'Delete sales records'},
                {'key': 'manage_orders', 'name': 'Manage Orders', 'icon': 'bi-cart', 
                 'description': 'Manage sale orders'},
            ]
        },
        {
            'key': 'purchase',
            'name': '📥 Purchase',
            'permissions': [
                {'key': 'view_purchases', 'name': 'View Purchases', 'icon': 'bi-eye', 
                 'description': 'View purchase list'},
                {'key': 'create_purchases', 'name': 'Create Purchases', 'icon': 'bi-plus-circle', 
                 'description': 'Create new purchases'},
                {'key': 'edit_purchases', 'name': 'Edit Purchases', 'icon': 'bi-pencil', 
                 'description': 'Edit existing purchases'},
                {'key': 'delete_purchases', 'name': 'Delete Purchases', 'icon': 'bi-trash', 
                 'description': 'Delete purchase records'},
                {'key': 'approve_purchases', 'name': 'Approve Purchases', 'icon': 'bi-check-circle', 
                 'description': 'Approve purchase orders'},
            ]
        },
        {
            'key': 'inventory',
            'name': '📦 Inventory',
            'permissions': [
                {'key': 'view_inventory', 'name': 'View Inventory', 'icon': 'bi-eye', 
                 'description': 'View inventory list'},
                {'key': 'manage_inventory', 'name': 'Manage Inventory', 'icon': 'bi-gear', 
                 'description': 'Manage inventory items'},
                {'key': 'manage_stock', 'name': 'Manage Stock', 'icon': 'bi-box-seam', 
                 'description': 'Manage stock levels'},
                {'key': 'receive_goods', 'name': 'Receive Goods', 'icon': 'bi-arrow-down-circle', 
                 'description': 'Receive incoming goods'},
                {'key': 'dispatch_goods', 'name': 'Dispatch Goods', 'icon': 'bi-arrow-up-circle', 
                 'description': 'Dispatch outgoing goods'},
            ]
        },
        {
            'key': 'customers',
            'name': '👥 Customers',
            'permissions': [
                {'key': 'view_customers', 'name': 'View Customers', 'icon': 'bi-eye', 
                 'description': 'View customer list'},
                {'key': 'create_customers', 'name': 'Create Customers', 'icon': 'bi-person-plus', 
                 'description': 'Create new customers'},
                {'key': 'edit_customers', 'name': 'Edit Customers', 'icon': 'bi-pencil', 
                 'description': 'Edit customer details'},
                {'key': 'delete_customers', 'name': 'Delete Customers', 'icon': 'bi-trash', 
                 'description': 'Delete customers'},
            ]
        },
        {
            'key': 'vendors',
            'name': '🏢 Vendors',
            'permissions': [
                {'key': 'view_vendors', 'name': 'View Vendors', 'icon': 'bi-eye', 
                 'description': 'View vendor list'},
                {'key': 'create_vendors', 'name': 'Create Vendors', 'icon': 'bi-building-add', 
                 'description': 'Create new vendors'},
                {'key': 'edit_vendors', 'name': 'Edit Vendors', 'icon': 'bi-pencil', 
                 'description': 'Edit vendor details'},
                {'key': 'delete_vendors', 'name': 'Delete Vendors', 'icon': 'bi-trash', 
                 'description': 'Delete vendors'},
            ]
        },
        {
            'key': 'finance',
            'name': '💰 Finance',
            'permissions': [
                {'key': 'view_financials', 'name': 'View Financials', 'icon': 'bi-eye', 
                 'description': 'View financial data'},
                {'key': 'edit_financials', 'name': 'Edit Financials', 'icon': 'bi-pencil', 
                 'description': 'Edit financial records'},
                {'key': 'manage_payments', 'name': 'Manage Payments', 'icon': 'bi-credit-card', 
                 'description': 'Manage payments'},
                {'key': 'manage_budget', 'name': 'Manage Budget', 'icon': 'bi-wallet', 
                 'description': 'Manage budgets'},
                {'key': 'view_expenses', 'name': 'View Expenses', 'icon': 'bi-receipt', 
                 'description': 'View expenses'},
            ]
        },
        {
            'key': 'hr',
            'name': '👔 HR',
            'permissions': [
                {'key': 'view_employees', 'name': 'View Employees', 'icon': 'bi-eye', 
                 'description': 'View employee list'},
                {'key': 'manage_employees', 'name': 'Manage Employees', 'icon': 'bi-gear', 
                 'description': 'Manage employees'},
                {'key': 'manage_attendance', 'name': 'Manage Attendance', 'icon': 'bi-calendar-check', 
                 'description': 'Manage attendance'},
                {'key': 'manage_payroll', 'name': 'Manage Payroll', 'icon': 'bi-wallet', 
                 'description': 'Manage payroll'},
                {'key': 'manage_leaves', 'name': 'Manage Leaves', 'icon': 'bi-file-spreadsheet', 
                 'description': 'Manage leave requests'},
            ]
        },
        {
            'key': 'warehouse',
            'name': '🏭 Warehouse',
            'permissions': [
                {'key': 'view_warehouse', 'name': 'View Warehouse', 'icon': 'bi-eye', 
                 'description': 'View warehouse details'},
                {'key': 'manage_warehouse', 'name': 'Manage Warehouse', 'icon': 'bi-gear', 
                 'description': 'Manage warehouses'},
                {'key': 'manage_transfers', 'name': 'Manage Transfers', 'icon': 'bi-arrow-left-right', 
                 'description': 'Manage stock transfers'},
                {'key': 'view_products', 'name': 'View Products', 'icon': 'bi-box', 
                 'description': 'View products'},
            ]
        },
        {
            'key': 'users',
            'name': '👥 Users',
            'permissions': [
                {'key': 'view_users', 'name': 'View Users', 'icon': 'bi-eye', 
                 'description': 'View user list'},
                {'key': 'manage_users', 'name': 'Manage Users', 'icon': 'bi-gear', 
                 'description': 'Manage users'},
                {'key': 'create_users', 'name': 'Create Users', 'icon': 'bi-person-plus', 
                 'description': 'Create new users'},
                {'key': 'delete_users', 'name': 'Delete Users', 'icon': 'bi-trash', 
                 'description': 'Delete users'},
                {'key': 'manage_roles', 'name': 'Manage Roles', 'icon': 'bi-shield', 
                 'description': 'Manage roles and permissions'},
            ]
        },
        {
            'key': 'settings',
            'name': '⚙️ Settings',
            'permissions': [
                {'key': 'view_settings', 'name': 'View Settings', 'icon': 'bi-eye', 
                 'description': 'View system settings'},
                {'key': 'edit_settings', 'name': 'Edit Settings', 'icon': 'bi-pencil', 
                 'description': 'Edit system settings'},
                {'key': 'manage_company', 'name': 'Manage Company', 'icon': 'bi-building', 
                 'description': 'Manage company settings'},
                {'key': 'manage_system', 'name': 'Manage System', 'icon': 'bi-gear', 
                 'description': 'System management'},
            ]
        }
    ]
    
    # Assign permissions to roles
    for role in roles:
        if role['key'] == 'admin':
            # Admin has all permissions
            role['permissions'] = [p['key'] for module in modules for p in module['permissions']]
            role['partial_permissions'] = []
    
    # Calculate total permissions
    total_permissions = sum(len(module['permissions']) for module in modules)
    custom_permissions = len([p for module in modules for p in module['permissions'] if p['key'].startswith('custom_')])
    restricted_permissions = sum(1 for role in roles if len(role['permissions']) < 10)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'roles': roles,
        'modules': modules,
        'total_roles': len(roles),
        'total_permissions': total_permissions,
        'custom_permissions': custom_permissions,
        'restricted_permissions': restricted_permissions,
        'is_admin': request.user.is_superuser,
    }
    return render(request, 'users/permission_matrix.html', context)


@login_required
def permission_matrix_api(request):
    """AJAX API: Get permission matrix data"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        # Build permission data
        roles = []
        modules = []
        
        # Get all groups
        groups = Group.objects.annotate(user_count=Count('user'))
        
        for group in groups:
            permissions = group.permissions.values_list('codename', flat=True)
            roles.append({
                'id': group.id,
                'name': group.name,
                'permissions': list(permissions),
                'user_count': group.user_count
            })
        
        # Get all permissions grouped by content type
        content_types = ContentType.objects.all()
        for ct in content_types:
            perms = Permission.objects.filter(content_type=ct)
            if perms.exists():
                modules.append({
                    'name': ct.app_label.title(),
                    'permissions': [{'key': p.codename, 'name': p.name} for p in perms]
                })
        
        return JsonResponse({
            'success': True,
            'roles': roles,
            'modules': modules,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def permission_matrix_save(request):
    """Save permission matrix changes"""
    
    if not request.user.is_superuser and not request.user.groups.filter(name='Owner').exists():
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method!'})
    
    try:
        data = json.loads(request.body)
        changes = data.get('changes', [])
        
        if not changes:
            return JsonResponse({'success': False, 'message': 'No changes to save!'})
        
        with transaction.atomic():
            saved_count = 0
            
            for change in changes:
                role_key = change.get('role')
                permission_key = change.get('permission')
                new_status = change.get('newStatus')
                
                if not all([role_key, permission_key, new_status]):
                    continue
                
                # Get or create group for this role
                role_name = {
                    'admin': 'Administrator',
                    'owner': 'Owner',
                    'manager': 'Store Manager',
                    'salesman': 'Salesman',
                    'accountant': 'Accountant',
                    'warehouse': 'Warehouse Staff'
                }.get(role_key, role_key.title())
                
                group, _ = Group.objects.get_or_create(name=role_name)
                
                # Find the permission
                # Try to find by codename
                permission = Permission.objects.filter(codename=permission_key).first()
                
                if not permission:
                    # Try to create a custom permission
                    content_type = ContentType.objects.get_for_model(Group)
                    permission, created = Permission.objects.get_or_create(
                        codename=permission_key,
                        content_type=content_type,
                        defaults={'name': permission_key.replace('_', ' ').title()}
                    )
                
                if new_status in ['full', 'partial']:
                    group.permissions.add(permission)
                    saved_count += 1
                else:
                    group.permissions.remove(permission)
                    saved_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Saved {saved_count} permission changes successfully!'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
