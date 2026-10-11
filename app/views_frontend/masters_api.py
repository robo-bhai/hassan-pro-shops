"""Frontend views: masters api."""
from ..models import *
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from ..models import Category, Brand, Unit, Location, Types


@login_required
def api_create_category(request):
    """API to create new category inline"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Category name is required!'})
            
            existing = Category.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True, 
                    'id': existing.id, 
                    'name': existing.name,
                    'message': 'Category already exists, selected!'
                })
            
            category = Category.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'id': category.id,
                'name': category.name,
                'message': f'Category "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required

def api_create_brand(request):
    """API to create new brand inline"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Brand name is required!'})
            
            existing = Brand.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True, 
                    'id': existing.id, 
                    'name': existing.name,
                    'message': 'Brand already exists, selected!'
                })
            
            brand = Brand.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'id': brand.id,
                'name': brand.name,
                'message': f'Brand "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def api_create_unit(request):
    """API to create new unit inline"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Unit name is required!'})
            
            existing = Unit.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True, 
                    'id': existing.id, 
                    'name': existing.name,
                    'message': 'Unit already exists, selected!'
                })
            
            unit = Unit.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'id': unit.id,
                'name': unit.name,
                'message': f'Unit "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def api_create_location(request):
    """API to create new location inline"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Location name is required!'})
            
            existing = Location.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True, 
                    'id': existing.id, 
                    'name': existing.name,
                    'message': 'Location already exists, selected!'
                })
            
            location = Location.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'id': location.id,
                'name': location.name,
                'message': f'Location "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def api_create_type(request):
    """API to create new type inline"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Type name is required!'})
            
            existing = Types.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True, 
                    'id': existing.id, 
                    'name': existing.name,
                    'message': 'Type already exists, selected!'
                })
            
            type_obj = Types.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'id': type_obj.id,
                'name': type_obj.name,
                'message': f'Type "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@login_required
def api_create_warehouse(request):
    """API: Create new warehouse inline from purchase form"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            location_id = data.get('location_id') or None
            description = data.get('description', '').strip()
            
            if not name:
                return JsonResponse({'success': False, 'message': 'Warehouse name is required!'})
            
            # Check duplicate
            existing = Warehouse.objects.filter(name__iexact=name).first()
            if existing:
                return JsonResponse({
                    'success': True,
                    'id': existing.id,
                    'name': existing.name,
                    'message': 'Warehouse already exists, selected!'
                })
            
            # Create new warehouse
            warehouse = Warehouse.objects.create(
                name=name,
                location_id=location_id,
                description=description
            )
            
            return JsonResponse({
                'success': True,
                'id': warehouse.id,
                'name': warehouse.name,
                'message': f'✅ Warehouse "{name}" created successfully!'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})
