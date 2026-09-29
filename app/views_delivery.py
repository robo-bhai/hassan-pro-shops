"""
Delivery Settings Views — Frontend Admin Panel
===============================================
Alag file — views_frontend.py ko bhari karne ke liye

Features:
✅ Delivery settings view (frontend)
✅ Toggle active/inactive
✅ Reset to default
✅ City-wise charges management
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.core.cache import cache
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# ============================================
# DELIVERY SETTINGS VIEWS
# ============================================

@login_required
def delivery_settings_view(request):
    """
    Delivery settings — frontend admin panel se
    Sirf superuser ya staff access kar sakta hai
    """
    from .models import DeliverySettings, CompanyInfo
    
    # Permission check
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can manage delivery settings.')
        return redirect('dashboard')
    
    # ✅ Get or create settings
    settings_obj = DeliverySettings.objects.filter(is_active=True).first()
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if not settings_obj:
                    settings_obj = DeliverySettings()
                
                # STANDARD DELIVERY
                settings_obj.standard_charge = Decimal(
                    request.POST.get('standard_charge', '100.00')
                )
                settings_obj.standard_delivery_time = request.POST.get(
                    'standard_delivery_time', 
                    '2-4 working days'
                )
                
                # EXPRESS DELIVERY
                settings_obj.express_delivery_enabled = (
                    request.POST.get('express_delivery_enabled') == 'on'
                )
                settings_obj.express_charge = Decimal(
                    request.POST.get('express_charge', '300.00')
                )
                settings_obj.express_delivery_time = request.POST.get(
                    'express_delivery_time', 
                    'Same day (within city)'
                )
                
                # STORE PICKUP
                settings_obj.store_pickup_enabled = (
                    request.POST.get('store_pickup_enabled') == 'on'
                )
                
                # FREE DELIVERY
                settings_obj.free_delivery_enabled = (
                    request.POST.get('free_delivery_enabled') == 'on'
                )
                settings_obj.free_delivery_threshold = Decimal(
                    request.POST.get('free_delivery_threshold', '1000.00')
                )
                
                # CITY-WISE CHARGES
                city_charges = {}
                cities = request.POST.getlist('city_name[]')
                charges = request.POST.getlist('city_charge[]')
                
                for i, city in enumerate(cities):
                    city_key = city.strip().lower()
                    if city_key and i < len(charges):
                        try:
                            city_charges[city_key] = float(charges[i])
                        except (ValueError, TypeError):
                            pass
                
                # Default "other" city
                other_charge = request.POST.get('other_city_charge', '200.00')
                try:
                    city_charges['other'] = float(other_charge)
                except (ValueError, TypeError):
                    city_charges['other'] = 200.0
                
                settings_obj.city_charges = city_charges
                settings_obj.is_active = True
                settings_obj.save()
                
                # ✅ Clear cache
                cache.delete('delivery_settings')
                
                messages.success(
                    request, 
                    '✅ Delivery settings updated successfully!'
                )
                return redirect('delivery_settings_view')
        
        except Exception as e:
            logger.error(f"Delivery settings save error: {e}")
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('delivery_settings_view')
    
    # ========================================== #
    # GET — Prepare context                       #
    # ========================================== #
    
    if not settings_obj:
        # Create default if not exists
        settings_obj = DeliverySettings.objects.create(
            standard_charge=Decimal('100.00'),
            express_charge=Decimal('300.00'),
            free_delivery_threshold=Decimal('1000.00'),
            city_charges={
                'karachi': 100,
                'lahore': 120,
                'islamabad': 150,
                'rawalpindi': 150,
                'faisalabad': 130,
                'multan': 140,
                'peshawar': 180,
                'quetta': 250,
                'other': 200,
            }
        )
    
    # Convert city_charges to list for template
    city_charges_list = []
    if settings_obj.city_charges:
        for city, charge in settings_obj.city_charges.items():
            if city != 'other':
                city_charges_list.append({
                    'name': city,
                    'charge': charge,
                })
    
    # Sort alphabetically
    city_charges_list.sort(key=lambda x: x['name'])
    
    # Get "other" charge
    other_charge = (
        settings_obj.city_charges.get('other', 200) 
        if settings_obj.city_charges else 200
    )
    
    company = CompanyInfo.objects.first()
    
    context = {
        'company_name': company.name if company else 'ERP System',
        'settings': settings_obj,
        'city_charges_list': city_charges_list,
        'other_charge': other_charge,
    }
    return render(request, 'settings/delivery_settings.html', context)


@login_required
def delivery_settings_toggle(request):
    """AJAX: Delivery settings toggle active/inactive"""
    from .models import DeliverySettings
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        settings_obj = DeliverySettings.objects.filter(is_active=True).first()
        
        if settings_obj:
            settings_obj.is_active = False
            settings_obj.save()
            cache.delete('delivery_settings')
            
            return JsonResponse({
                'success': True,
                'message': 'Delivery settings disabled',
                'is_active': False,
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No active settings found',
            })
    except Exception as e:
        logger.error(f"Toggle error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def delivery_settings_reset(request):
    """Reset to default delivery settings"""
    from .models import DeliverySettings
    
    if not request.user.is_superuser:
        messages.error(request, '❌ Only superuser can reset settings')
        return redirect('delivery_settings_view')
    
    if request.method != 'POST':
        return redirect('delivery_settings_view')
    
    try:
        with transaction.atomic():
            # Delete existing
            DeliverySettings.objects.all().delete()
            
            # Create new default
            DeliverySettings.objects.create(
                standard_charge=Decimal('100.00'),
                standard_delivery_time='2-4 working days',
                express_delivery_enabled=True,
                express_charge=Decimal('300.00'),
                express_delivery_time='Same day (within city)',
                store_pickup_enabled=True,
                free_delivery_enabled=True,
                free_delivery_threshold=Decimal('1000.00'),
                city_charges={
                    'karachi': 100,
                    'lahore': 120,
                    'islamabad': 150,
                    'rawalpindi': 150,
                    'faisalabad': 130,
                    'multan': 140,
                    'peshawar': 180,
                    'quetta': 250,
                    'other': 200,
                },
                is_active=True,
            )
            
            cache.delete('delivery_settings')
        
        messages.success(request, '✅ Delivery settings reset to default!')
    except Exception as e:
        logger.error(f"Reset error: {e}")
        messages.error(request, f'❌ Error: {str(e)}')
    
    return redirect('delivery_settings_view')