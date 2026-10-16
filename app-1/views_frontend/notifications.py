"""Frontend views: notifications."""
from ..models import *
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from ..models import CompanyInfo
from django.db import models


@login_required
def get_notifications_api(request):
    """Get all notifications for current user with category filter"""
    category = request.GET.get('category', 'all')
    
    notifications = Notification.objects.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True)
    )
    
    # Filter by category
    if category != 'all':
        notifications = notifications.filter(category=category)
    
    notifications = notifications.order_by('-created_at')[:50]
    
    data = []
    for notif in notifications:
        from django.utils import timezone
        time_diff = timezone.now() - notif.created_at
        if time_diff.days > 0:
            time_ago = f"{time_diff.days} days ago"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            time_ago = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            time_ago = "Just now"
        
        data.append({
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'notification_type': notif.notification_type,
            'category': notif.category,
            'is_read': notif.is_read,
            'link': notif.link,
            'time_ago': time_ago,
            'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    # Get category counts
    category_counts = {
        'all': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True)).count(),
        'sales': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='sales').count(),
        'payments': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='payments').count(),
        'installments': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='installments').count(),
        'stock': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='stock').count(),
        'system': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='system').count(),
    }
    
    unread_count = Notification.objects.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True),
        is_read=False
    ).count()
    
    return JsonResponse({
        'success': True,
        'notifications': data,
        'unread_count': unread_count,
        'category_counts': category_counts,
        'current_category': category,
        'total': len(data)
    })


@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read"""
    try:
        notification = Notification.objects.get(pk=pk)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Notification not found'})


@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True),
        is_read=False
    ).update(is_read=True)
    return JsonResponse({'success': True})


@login_required
def mark_category_read(request):
    """Mark all notifications in a category as read"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        category = data.get('category', '')
        
        if category and category != 'all':
            Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True),
                category=category,
                is_read=False
            ).update(is_read=True)
        elif category == 'all':
            Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True),
                is_read=False
            ).update(is_read=True)
        
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


@login_required
def get_unread_count(request):
    """Get unread notification count"""
    count = Notification.objects.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True),
        is_read=False
    ).count()
    return JsonResponse({'unread_count': count})


@login_required
def get_notification_categories(request):
    """Get notification categories with counts"""
    categories = [
        {'id': 'all', 'name': 'All Notifications', 'icon': 'bi-bell', 'color': '#667eea'},
        {'id': 'sales', 'name': 'Sales', 'icon': 'bi-cart', 'color': '#28a745'},
        {'id': 'payments', 'name': 'Payments', 'icon': 'bi-currency-rupee', 'color': '#17a2b8'},
        {'id': 'installments', 'name': 'Installments', 'icon': 'bi-calendar', 'color': '#ffc107'},
        {'id': 'stock', 'name': 'Stock Alerts', 'icon': 'bi-box', 'color': '#fd7e14'},
        {'id': 'system', 'name': 'System', 'icon': 'bi-gear', 'color': '#6c757d'},
    ]
    
    for cat in categories:
        if cat['id'] == 'all':
            cat['count'] = Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True)
            ).count()
        else:
            cat['count'] = Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True),
                category=cat['id']
            ).count()
    
    return JsonResponse({'success': True, 'categories': categories})


@login_required
def notification_list_page(request):
    """Full notifications page with category filter"""
    category = request.GET.get('category', 'all')
    
    notifications = Notification.objects.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True)
    )
    
    if category != 'all':
        notifications = notifications.filter(category=category)
    
    notifications = notifications.order_by('-created_at')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(notifications, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Get category counts for sidebar
    categories = [
        {'id': 'all', 'name': 'All', 'icon': 'bi-bell', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True)).count()},
        {'id': 'sales', 'name': 'Sales', 'icon': 'bi-cart', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='sales').count()},
        {'id': 'payments', 'name': 'Payments', 'icon': 'bi-currency-rupee', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='payments').count()},
        {'id': 'installments', 'name': 'Installments', 'icon': 'bi-calendar', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='installments').count()},
        {'id': 'stock', 'name': 'Stock', 'icon': 'bi-box', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='stock').count()},
        {'id': 'system', 'name': 'System', 'icon': 'bi-gear', 'count': Notification.objects.filter(models.Q(user=request.user) | models.Q(user__isnull=True), category='system').count()},
    ]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'notifications': page_obj,
        'categories': categories,
        'current_category': category,
    }
    return render(request, 'notifications/list.html', context)


@login_required
def delete_notification(request, pk):
    """Delete a notification"""
    if request.method == 'POST':
        try:
            notification = Notification.objects.get(pk=pk)
            notification.delete()
            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Notification not found'})
    return JsonResponse({'success': False})


@login_required
def delete_all_notifications(request):
    """Delete all notifications for current user"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        category = data.get('category', 'all')
        
        if category != 'all':
            Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True),
                category=category
            ).delete()
        else:
            Notification.objects.filter(
                models.Q(user=request.user) | models.Q(user__isnull=True)
            ).delete()
        
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})
