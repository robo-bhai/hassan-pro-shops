"""Frontend views: shareholder/support_tickets (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.contrib import messages
from ...models import CompanyInfo
from django.contrib.auth.models import User


@login_required
def shareholder_support_ticket_detail(request, pk):
    """View support ticket detail"""
    
    if not hasattr(request.user, 'shareholder_profile'):
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    shareholder = request.user.shareholder_profile
    ticket = get_object_or_404(ShareholderSupportTicket, pk=pk, shareholder=shareholder)
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            SupportTicketReply.objects.create(
                ticket=ticket,
                message=message,
                is_internal=False,
                created_by=request.user
            )
            
            if ticket.status == 'closed':
                ticket.status = 'in_progress'
                ticket.save()
            
            messages.success(request, '✅ Reply sent successfully!')
            return redirect('shareholder_support_ticket_detail', pk=pk)
    
    replies = ticket.replies.filter(is_internal=False).order_by('created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'ticket': ticket,
        'replies': replies,
    }
    return render(request, 'shareholders/portal/ticket_detail.html', context)


@login_required
@perm_required('view_shareholders')
def admin_support_tickets(request):
    """Admin view all support tickets"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    tickets = ShareholderSupportTicket.objects.select_related('shareholder', 'assigned_to').all()
    
    status = request.GET.get('status', '')
    if status:
        tickets = tickets.filter(status=status)
    
    priority = request.GET.get('priority', '')
    if priority:
        tickets = tickets.filter(priority=priority)
    
    search = request.GET.get('search', '')
    if search:
        tickets = tickets.filter(
            Q(ticket_no__icontains=search) |
            Q(subject__icontains=search) |
            Q(shareholder__name__icontains=search)
        )
    
    total_tickets = tickets.count()
    new_tickets = tickets.filter(status='new').count()
    in_progress = tickets.filter(status='in_progress').count()
    resolved = tickets.filter(status='resolved').count()
    closed = tickets.filter(status='closed').count()
    
    paginator = Paginator(tickets, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'tickets': page_obj,
        'total_tickets': total_tickets,
        'new_tickets': new_tickets,
        'in_progress': in_progress,
        'resolved': resolved,
        'closed': closed,
        'status': status,
        'priority': priority,
        'search': search,
        'status_choices': ShareholderSupportTicket.STATUS_CHOICES,
        'priority_choices': ShareholderSupportTicket.PRIORITY_CHOICES,
    }
    return render(request, 'shareholders/admin/tickets.html', context)


@login_required
@perm_required('view_shareholders', post='manage_shareholders')
def admin_support_ticket_detail(request, pk):
    """Admin view ticket detail"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    ticket = get_object_or_404(ShareholderSupportTicket, pk=pk)
    replies = ticket.replies.all().order_by('created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'reply':
            message = request.POST.get('message')
            is_internal = request.POST.get('is_internal') == 'on'
            
            if message:
                SupportTicketReply.objects.create(
                    ticket=ticket,
                    message=message,
                    is_internal=is_internal,
                    created_by=request.user
                )
                
                if not is_internal:
                    messages.success(request, '✅ Reply sent to shareholder!')
                else:
                    messages.success(request, '✅ Internal note added!')
        
        elif action == 'assign':
            assigned_to_id = request.POST.get('assigned_to')
            if assigned_to_id:
                ticket.assigned_to_id = assigned_to_id
                ticket.status = 'in_progress'
                ticket.save()
                messages.success(request, f'✅ Ticket assigned to {ticket.assigned_to.username}')
        
        elif action == 'resolve':
            ticket.status = 'resolved'
            ticket.resolved_at = now()
            ticket.save()
            messages.success(request, '✅ Ticket resolved!')
        
        elif action == 'close':
            ticket.status = 'closed'
            ticket.save()
            messages.success(request, '✅ Ticket closed!')
        
        return redirect('admin_support_ticket_detail', pk=pk)
    
    users = User.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'ticket': ticket,
        'replies': replies,
        'users': users,
        'status_choices': ShareholderSupportTicket.STATUS_CHOICES,
    }
    return render(request, 'shareholders/admin/ticket_detail.html', context)
