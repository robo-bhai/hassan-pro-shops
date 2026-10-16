"""Frontend views: chat."""
from django.views.decorators.http import require_POST
from ..models import *
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ..models import CompanyInfo, ChatConversation, ChatMessage, ChatTypingStatus


def _is_chat_admin(user):
    """Check karo user chat admin hai ya nahi"""
    if user.is_superuser:
        return True
    if user.is_staff:
        return True
    if user.groups.filter(name__in=['Owner', 'Manager', 'Store Manager', 'Support']).exists():
        return True
    return False


@login_required
def admin_chat_panel(request):
    """Admin chat panel - saari conversations list"""
    
    if not _is_chat_admin(request.user):
        messages.error(request, '❌ Access denied! Only admins can access chat panel.')
        return redirect('dashboard')
    
    # ========================================== #
    # FILTERS                                    #
    # ========================================== #
    status_filter = request.GET.get('status', 'active')
    search = request.GET.get('search', '').strip()
    filter_type = request.GET.get('filter', 'all')
    
    # ========================================== #
    # BASE QUERYSET                              #
    # ========================================== #
    conversations = ChatConversation.objects.select_related(
        'customer', 'assigned_to'
    ).prefetch_related('messages')
    
    # ========================================== #
    # STATUS FILTER                              #
    # ========================================== #
    if status_filter == 'active':
        conversations = conversations.filter(status='active')
    elif status_filter == 'closed':
        conversations = conversations.filter(status='closed')
    # 'all' → no filter
    
    # ========================================== #
    # SEARCH                                     #
    # ========================================== #
    if search:
        conversations = conversations.filter(
            Q(customer__name__icontains=search) |
            Q(customer__customer_code__icontains=search) |
            Q(customer__contact_number__icontains=search) |
            Q(guest_name__icontains=search) |
            Q(guest_phone__icontains=search)
        )
    
    # ========================================== #
    # FILTER TYPE                                #
    # ========================================== #
    if filter_type == 'unread':
        conversations = conversations.filter(admin_unread_count__gt=0)
    elif filter_type == 'mine':
        conversations = conversations.filter(assigned_to=request.user)
    
    conversations = conversations.order_by('-last_message_at')
    
    # ========================================== #
    # STATS                                      #
    # ========================================== #
    total_active = ChatConversation.objects.filter(status='active').count()
    total_unread = ChatConversation.objects.filter(
        admin_unread_count__gt=0, status='active'
    ).count()
    total_closed = ChatConversation.objects.filter(status='closed').count()
    total_all = ChatConversation.objects.count()
    
    # ========================================== #
    # LIVE ADMINS COUNT                          #
    # ========================================== #
    from ..models import AdminPresence
    live_admins_count = AdminPresence.get_live_admins(seconds=60).count()
    
    # ========================================== #
    # PAGINATION                                 #
    # ========================================== #
    paginator = Paginator(conversations, 30)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # ========================================== #
    # ✅ ENRICH CONVERSATIONS (FIXED INDENTATION) #
    # ========================================== #
    for conv in page_obj:
        # Last message info
        last_msg = conv.messages.last()
        conv.last_message_text = last_msg.message[:60] if last_msg else "No messages yet"
        conv.last_message_sender = last_msg.sender_type if last_msg else None
        conv.total_messages = conv.messages.count()
        
        # ✅ URGENT CHECK - 15+ min unread
        if conv.admin_unread_count > 0 and conv.last_message_at:
            delta = now() - conv.last_message_at
            conv.is_urgent = delta.total_seconds() > 900  # 15 minutes
        else:
            conv.is_urgent = False
        
        # Time ago formatting
        if conv.last_message_at:
            delta = now() - conv.last_message_at
            total_seconds = delta.total_seconds()
            
            if delta.days > 0:
                conv.time_ago = f"{delta.days}d ago"
            elif total_seconds > 3600:
                conv.time_ago = f"{int(total_seconds // 3600)}h ago"
            elif total_seconds > 60:
                conv.time_ago = f"{int(total_seconds // 60)}m ago"
            else:
                conv.time_ago = "Just now"
        else:
            conv.time_ago = "-"
    
    # ========================================== #
    # CONTEXT                                    #
    # ========================================== #
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'conversations': page_obj,
        'page_obj': page_obj,
        'total_active': total_active,
        'total_unread': total_unread,
        'total_closed': total_closed,
        'total_all': total_all,
        'live_admins_count': live_admins_count,  # ✅ NEW
        'status_filter': status_filter,
        'filter_type': filter_type,
        'search': search,
        'user': request.user,
    }
    return render(request, 'admin_chat/chat_panel.html', context)


@login_required
def admin_chat_detail(request, pk):
    """Admin chat detail - ek conversation ka full view"""
    
    if not _is_chat_admin(request.user):
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    conversation = get_object_or_404(
        ChatConversation.objects.select_related('customer', 'assigned_to'),
        pk=pk
    )
    
    chat_messages = conversation.messages.all().order_by('created_at')
    
    # Admin ke unread messages ko read mark karo
    unread_admin_msgs = chat_messages.filter(sender_type='customer', is_read=False)
    if unread_admin_msgs.exists():
        unread_admin_msgs.update(is_read=True, read_at=now())
        conversation.admin_unread_count = 0
        conversation.save(update_fields=['admin_unread_count'])
    
    # Display info
    if conversation.customer:
        display_name = conversation.customer.name
        display_phone = conversation.customer.contact_number or 'N/A'
        display_code = conversation.customer.customer_code or 'N/A'
        display_email = conversation.customer.email or 'N/A'
        display_address = conversation.customer.address or 'N/A'
        is_guest = False
    else:
        display_name = conversation.guest_name or f"Guest #{conversation.id}"
        display_phone = conversation.guest_phone or 'N/A'
        display_code = 'Guest'
        display_email = 'N/A'
        display_address = 'N/A'
        is_guest = True
    
    typing, _ = ChatTypingStatus.objects.get_or_create(conversation=conversation)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'conversation': conversation,
        'chat_messages': chat_messages,
        'display_name': display_name,
        'display_phone': display_phone,
        'display_code': display_code,
        'display_email': display_email,
        'display_address': display_address,
        'is_guest': is_guest,
        'is_customer_typing': typing.is_customer_typing,
        'user': request.user,
    }
    return render(request, 'admin_chat/chat_detail.html', context)


@login_required
@require_POST
def admin_chat_send(request):
    """AJAX: Admin reply bheje — Race condition safe + Attachment support"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        data = json.loads(request.body)
        conversation_id = data.get('conversation_id')
        message_text = data.get('message', '').strip()
        
        if not conversation_id:
            return JsonResponse({'success': False, 'message': 'Conversation ID required'})
        
        if not message_text:
            return JsonResponse({'success': False, 'message': 'Message khali hai'})
        
        if len(message_text) > 2000:
            return JsonResponse({'success': False, 'message': 'Message bohot lamba (max 2000 chars)'})
        
        # ✅ Attachment handling
        attachment_file = None
        if request.FILES.get('attachment'):
            attachment_file = request.FILES['attachment']
            if attachment_file.size > 5 * 1024 * 1024:
                return JsonResponse({
                    'success': False, 
                    'message': '❌ File bohot bara! Max 5MB allowed.'
                })
        
        with transaction.atomic():
            # ✅ Lock conversation to prevent race condition
            conversation = ChatConversation.objects.select_for_update().get(
                pk=conversation_id
            )
            
            if conversation.status == 'closed':
                conversation.status = 'active'
                conversation.closed_at = None
            
            chat_message = ChatMessage.objects.create(
                conversation=conversation,
                sender_type='admin',
                sender=request.user,
                message=message_text,
                attachment=attachment_file,  # ✅ ADD
                attachment_name=attachment_file.name if attachment_file else None  # ✅ ADD
            )
            
            conversation.last_message_at = now()
            conversation.last_message_preview = message_text[:100]
            conversation.customer_unread_count += 1
            conversation.assigned_to = request.user
            conversation.save(update_fields=[
                'last_message_at', 'last_message_preview',
                'customer_unread_count', 'assigned_to', 'status', 'closed_at'
            ])
        
        return JsonResponse({
            'success': True,
            'message_id': chat_message.id,
            'timestamp': chat_message.created_at.strftime('%I:%M %p'),
        })
        
    except ChatConversation.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Conversation not found'})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Admin chat send error: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def admin_chat_messages_api(request, pk):
    """AJAX: Admin ke liye naye messages fetch karo (polling) — FIXED"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False, 'messages': []})
    
    try:
        conversation = get_object_or_404(ChatConversation, pk=pk)
        
        after_id = request.GET.get('after_id', 0)
        try:
            after_id = int(after_id)
        except (ValueError, TypeError):
            after_id = 0
        
        messages_qs = conversation.messages.filter(
            id__gt=after_id
        ).order_by('created_at')[:50]
        
        messages_data = []
        unread_ids = []
        
        for msg in messages_qs:
            messages_data.append({
                'id': msg.id,
                'sender_type': msg.sender_type,
                'sender_name': msg.sender.username if msg.sender else 'Support',
                'message': msg.message,
                'attachment_url': msg.attachment.url if msg.attachment else None,
                'attachment_name': msg.attachment_name,
                'created_at': msg.created_at.strftime('%I:%M %p'),
            })
            
            # ✅ Sirf customer messages jo unread hain
            if msg.sender_type == 'customer' and not msg.is_read:
                unread_ids.append(msg.id)
        
        # ✅ Only mark fetched messages as read
        if unread_ids:
            ChatMessage.objects.filter(id__in=unread_ids).update(
                is_read=True, 
                read_at=now()
            )
            
            # ✅ Recalculate unread count
            new_unread = conversation.messages.filter(
                sender_type='customer', 
                is_read=False
            ).count()
            
            conversation.admin_unread_count = new_unread
            conversation.save(update_fields=['admin_unread_count'])
        
        typing, _ = ChatTypingStatus.objects.get_or_create(conversation=conversation)
        
        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'is_customer_typing': typing.is_customer_typing,
            'unread_count': conversation.admin_unread_count,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'messages': [], 'message': str(e)})


@login_required
@require_POST
def admin_chat_typing(request):
    """AJAX: Admin typing indicator bheje"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False})
    
    try:
        data = json.loads(request.body)
        conversation_id = data.get('conversation_id')
        is_typing = data.get('is_typing', False)
        
        conversation = get_object_or_404(ChatConversation, pk=conversation_id)
        
        typing, _ = ChatTypingStatus.objects.get_or_create(conversation=conversation)
        typing.is_admin_typing = bool(is_typing)
        typing.save(update_fields=['is_admin_typing', 'updated_at'])
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@require_POST
def admin_chat_close(request, pk):
    """Admin: Chat close kare"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        conversation = get_object_or_404(ChatConversation, pk=pk)
        conversation.status = 'closed'
        conversation.closed_at = now()
        conversation.save(update_fields=['status', 'closed_at'])
        
        return JsonResponse({'success': True, 'message': 'Chat closed'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@require_POST
def admin_chat_reopen(request, pk):
    """Admin: Closed chat reopen kare"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'})
    
    try:
        conversation = get_object_or_404(ChatConversation, pk=pk)
        conversation.status = 'active'
        conversation.closed_at = None
        conversation.save(update_fields=['status', 'closed_at'])
        
        return JsonResponse({'success': True, 'message': 'Chat reopened'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def admin_chat_stats_api(request):
    """AJAX: Total unread stats"""
    
    if not _is_chat_admin(request.user):
        return JsonResponse({'success': False, 'total_unread': 0})
    
    total_unread = ChatConversation.objects.filter(
        admin_unread_count__gt=0,
        status='active'
    ).aggregate(total=Sum('admin_unread_count'))['total'] or 0
    
    return JsonResponse({
        'success': True,
        'total_unread': total_unread,
        'unread_conversations': ChatConversation.objects.filter(
            admin_unread_count__gt=0, status='active'
        ).count(),
    })
