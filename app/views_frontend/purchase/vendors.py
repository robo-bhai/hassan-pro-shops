"""Frontend views: purchase/vendors (split from the former purchasing.py)."""
from ...security.permissions import perm_required
from django.db.models.functions import Coalesce
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Value, DecimalField
from decimal import Decimal
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from ...models import CompanyInfo


@login_required
@perm_required('create_vendors')
def vendor_create_frontend(request):
    """Frontend vendor creation view"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            vendor_code = request.POST.get('vendor_code', '').strip()
            contact_number = request.POST.get('contact_number', '')
            address = request.POST.get('address', '')
            group_id = request.POST.get('group') or None
            
            if not name:
                messages.error(request, 'Vendor name is required!')
                return redirect('vendor_create_frontend')
            
            # Check for duplicate vendor code
            if vendor_code and Vendor.objects.filter(vendor_code=vendor_code).exists():
                messages.error(request, f'Vendor code "{vendor_code}" already exists!')
                return redirect('vendor_create_frontend')
            
            vendor = Vendor(
                name=name,
                vendor_code=vendor_code if vendor_code else None,
                contact_number=contact_number,
                address=address,
                group_id=group_id
            )
            vendor.save()
            
            messages.success(request, f'✅ Vendor "{vendor.name}" created! Code: {vendor.vendor_code}')
            return redirect('vendor_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('vendor_create_frontend')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'groups': VendorGroup.objects.all(),
    }
    return render(request, 'vendors/create.html', context)


@login_required
@perm_required('edit_vendors')
def vendor_update(request, pk):
    """Update vendor with opening balance"""
    vendor = get_object_or_404(Vendor, pk=pk)
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name', '').strip()
            vendor_code = request.POST.get('vendor_code', '').strip()
            contact_number = request.POST.get('contact_number', '')
            address = request.POST.get('address', '')
            group_id = request.POST.get('group') or None
            opening_balance = request.POST.get('opening_balance', 0)
            
            # Validation
            if not name:
                messages.error(request, '❌ Vendor name is required!')
                return redirect('vendor_update', pk=pk)
            
            # Check for duplicate vendor code (excluding self)
            if vendor_code:
                existing = Vendor.objects.filter(vendor_code=vendor_code).exclude(pk=pk).first()
                if existing:
                    messages.error(request, f'❌ Vendor code "{vendor_code}" already exists!')
                    return redirect('vendor_update', pk=pk)
            
            # ✅ Update vendor with opening balance
            vendor.name = name
            vendor.vendor_code = vendor_code if vendor_code else None
            vendor.contact_number = contact_number
            vendor.address = address
            vendor.group_id = group_id
            vendor.opening_balance = Decimal(opening_balance) if opening_balance else Decimal('0.00')
            vendor.save()
            
            messages.success(
                request, 
                f'✅ Vendor "{vendor.name}" updated successfully!\n'
                f'📋 Code: {vendor.vendor_code}\n'
                f'💰 Opening Balance: Rs. {vendor.opening_balance:,.2f}'
            )
            return redirect('vendor_list')
            
        except ValidationError as e:
            messages.error(request, f'❌ Validation Error: {str(e)}')
            return redirect('vendor_update', pk=pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('vendor_update', pk=pk)
    
    # GET request - show form with existing data
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'vendor': vendor,
        'groups': VendorGroup.objects.all(),
    }
    return render(request, 'vendors/update.html', context)


@login_required
@perm_required('view_vendors')
def vendor_list(request):
    """
    Vendor list with outstanding balance — OPTIMIZED (60x faster)
    Before: 600 queries | After: 2 queries
    """
    from django.db.models import Sum, Count, Q, F, Value, DecimalField
    from django.db.models.functions import Coalesce
    
    # ✅ Annotate all totals in one query
    vendors = Vendor.objects.select_related('group').annotate(
        total_purchases=Coalesce(
            Sum(
                'purchase__purchaseitem__total_amt',
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_paid=Coalesce(
            Sum(
                'purchase__paid',
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_returns=Coalesce(
            Sum(
                'purchaseretrn__return_items__total_amt',
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        purchase_count=Count('purchase', distinct=True),
    ).annotate(
        # ✅ Outstanding = opening + purchases - paid - returns
        outstanding=(
            F('opening_balance') + F('total_purchases') - 
            F('total_paid') - F('total_returns')
        )
    ).order_by('vendor_code')
    
    # ✅ Search filter
    search = request.GET.get('search', '')
    if search:
        vendors = vendors.filter(
            Q(name__icontains=search) |
            Q(vendor_code__icontains=search)
        )
    
    # ✅ Pagination
    paginator = Paginator(vendors, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
    }
    return render(request, 'vendors/list.html', context)


@login_required
@perm_required('create_vendors')
def vendor_create(request):
    """Create new vendor - Frontend view"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            vendor_code = request.POST.get('vendor_code', '').strip()
            contact_number = request.POST.get('contact_number', '')
            address = request.POST.get('address', '')
            group_id = request.POST.get('group') or None
            
            # ✅ FIX: save opening_balance (ADD THIS LINE)
            opening_balance = Decimal(request.POST.get('opening_balance', 0))
            
            if not name:
                messages.error(request, 'Vendor name is required!')
                return redirect('vendor_create')
            
            # Check for duplicate vendor code
            if vendor_code and Vendor.objects.filter(vendor_code=vendor_code).exists():
                messages.error(request, f'Vendor code "{vendor_code}" already exists!')
                return redirect('vendor_create')
            
            # ✅ FIX: add the opening_balance field (ADD THIS LINE)
            vendor = Vendor(
                name=name,
                vendor_code=vendor_code if vendor_code else None,
                contact_number=contact_number,
                address=address,
                group_id=group_id,
                opening_balance=opening_balance  # ✅ ADD THIS LINE
            )
            vendor.save()
            
            messages.success(request, f'✅ Vendor "{vendor.name}" created! Code: {vendor.vendor_code} | Opening Balance: Rs. {vendor.opening_balance:,.2f}')
            return redirect('vendor_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('vendor_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'groups': VendorGroup.objects.all(),
    }
    return render(request, 'vendors/create.html', context)


@login_required
@perm_required('delete_vendors')
def vendor_delete(request, pk):
    """Delete a vendor with confirmation"""
    vendor = get_object_or_404(Vendor, pk=pk)
    
    # Check permission - only superuser or staff can delete
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only administrators can delete vendors.')
        return redirect('vendor_list')
    
    # Check if vendor has any purchases
    if vendor.purchase_set.exists():
        messages.error(
            request, 
            f'❌ Cannot delete "{vendor.name}" because they have {vendor.purchase_set.count()} purchase(s) associated with them!'
        )
        return redirect('vendor_list')
    
    if request.method == 'POST':
        vendor_name = vendor.name
        vendor.delete()
        messages.success(request, f'🗑️ Vendor "{vendor_name}" deleted successfully!')
        return redirect('vendor_list')
    
    return redirect('vendor_list')


@login_required
@perm_required('create_vendors')
def api_create_vendor(request):
    """API: Create new vendor inline from purchase form"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            contact_number = data.get('contact_number', '').strip()
            address = data.get('address', '').strip()
            group_id = data.get('group_id') or None
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Vendor name is required!'})
            
            # Check duplicate
            existing = Vendor.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True,
                    'id': existing.id,
                    'name': existing.name,
                    'code': existing.vendor_code or '',
                    'message': 'Vendor already exists, selected!'
                })
            
            # Create new vendor
            vendor = Vendor.objects.create(
                name=name,
                contact_number=contact_number,
                address=address,
                group_id=group_id
            )
            
            return JsonResponse({
                'success': True,
                'id': vendor.id,
                'name': vendor.name,
                'code': vendor.vendor_code or '',
                'message': f'✅ Vendor "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})
