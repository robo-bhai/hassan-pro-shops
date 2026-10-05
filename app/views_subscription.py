# views_subscription.py - COMPLETE FILE

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Sum, Q
from django.contrib.auth.models import User
from datetime import date, timedelta
from decimal import Decimal
from .models import (
    SubscriptionPlan, Client, SubscriptionPayment,
    SubscriptionHistory, CompanyInfo
)


# ==========================================
# SUPER ADMIN - PLANS
# ==========================================

@login_required
def subscription_plans_list(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    plans = SubscriptionPlan.objects.all().order_by('price')
    
    context = {
        'company_name': 'UQN88 Store',
        'plans': plans,
        'total_plans': plans.count(),
        'active_plans': plans.filter(is_active=True).count(),
    }
    return render(request, 'subscription/plans_list.html', context)


@login_required
def subscription_plan_create(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            # ✅ Saare 27 modules ka dict banao
            enabled_modules = {
                'hr': request.POST.get('module_hr') == 'on',
                'production': request.POST.get('module_production') == 'on',
                'installment': request.POST.get('module_installment') == 'on',
                'reports': request.POST.get('module_reports') == 'on',
                'whatsapp': request.POST.get('module_whatsapp') == 'on',
                'inventory': request.POST.get('module_inventory') == 'on',
                'purchase': request.POST.get('module_purchase') == 'on',
                'sales': request.POST.get('module_sales') == 'on',
                'accounts': request.POST.get('module_accounts') == 'on',
                'backup': request.POST.get('module_backup') == 'on',
                'service': request.POST.get('module_service') == 'on',
                'supply_chain': request.POST.get('module_supply_chain') == 'on',
                'budget': request.POST.get('module_budget') == 'on',
                'expenses': request.POST.get('module_expenses') == 'on',
                'audit': request.POST.get('module_audit') == 'on',
                'shareholder': request.POST.get('module_shareholder') == 'on',
                'loan': request.POST.get('module_loan') == 'on',
                'ai': request.POST.get('module_ai') == 'on',
                'bi': request.POST.get('module_bi') == 'on',
                'document': request.POST.get('module_document') == 'on',
                'security': request.POST.get('module_security') == 'on',
                'testing': request.POST.get('module_testing') == 'on',
                'operations': request.POST.get('module_operations') == 'on',
                'cash': request.POST.get('module_cash') == 'on',
                'warehouse': request.POST.get('module_warehouse') == 'on',
                'returns': request.POST.get('module_returns') == 'on',
                'people': request.POST.get('module_people') == 'on',
            }
            
            plan = SubscriptionPlan.objects.create(
                name=request.POST.get('name'),
                plan_type=request.POST.get('plan_type'),
                description=request.POST.get('description', ''),
                price=Decimal(request.POST.get('price', 0)),
                setup_fee=Decimal(request.POST.get('setup_fee', 0)),
                max_users=int(request.POST.get('max_users', 5)),
                max_products=int(request.POST.get('max_products', 1000)),
                max_customers=int(request.POST.get('max_customers', 500)),
                max_orders_per_month=int(request.POST.get('max_orders_per_month', 1000)),
                has_ai_features=request.POST.get('has_ai_features') == 'on',
                has_whatsapp=request.POST.get('has_whatsapp') == 'on',
                has_live_chat=request.POST.get('has_live_chat') == 'on',
                has_backup=request.POST.get('has_backup') == 'on',
                has_priority_support=request.POST.get('has_priority_support') == 'on',
                has_custom_domain=request.POST.get('has_custom_domain') == 'on',
                enabled_modules=enabled_modules,
            )
            
            messages.success(request, f'✅ Plan "{plan.name}" created!')
            return redirect('subscription_plans_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {'plan_types': SubscriptionPlan.PLAN_TYPES}
    return render(request, 'subscription/plan_create.html', context)


@login_required
def subscription_plan_edit(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    
    if request.method == 'POST':
        try:
            # ✅ Saare 27 modules ka dict banao
            enabled_modules = {
                'hr': request.POST.get('module_hr') == 'on',
                'production': request.POST.get('module_production') == 'on',
                'installment': request.POST.get('module_installment') == 'on',
                'reports': request.POST.get('module_reports') == 'on',
                'whatsapp': request.POST.get('module_whatsapp') == 'on',
                'inventory': request.POST.get('module_inventory') == 'on',
                'purchase': request.POST.get('module_purchase') == 'on',
                'sales': request.POST.get('module_sales') == 'on',
                'accounts': request.POST.get('module_accounts') == 'on',
                'backup': request.POST.get('module_backup') == 'on',
                'service': request.POST.get('module_service') == 'on',
                'supply_chain': request.POST.get('module_supply_chain') == 'on',
                'budget': request.POST.get('module_budget') == 'on',
                'expenses': request.POST.get('module_expenses') == 'on',
                'audit': request.POST.get('module_audit') == 'on',
                'shareholder': request.POST.get('module_shareholder') == 'on',
                'loan': request.POST.get('module_loan') == 'on',
                'ai': request.POST.get('module_ai') == 'on',
                'bi': request.POST.get('module_bi') == 'on',
                'document': request.POST.get('module_document') == 'on',
                'security': request.POST.get('module_security') == 'on',
                'testing': request.POST.get('module_testing') == 'on',
                'operations': request.POST.get('module_operations') == 'on',
                'cash': request.POST.get('module_cash') == 'on',
                'warehouse': request.POST.get('module_warehouse') == 'on',
                'returns': request.POST.get('module_returns') == 'on',
                'people': request.POST.get('module_people') == 'on',
            }
            
            plan.name = request.POST.get('name')
            plan.plan_type = request.POST.get('plan_type')
            plan.description = request.POST.get('description', '')
            plan.price = Decimal(request.POST.get('price', 0))
            plan.setup_fee = Decimal(request.POST.get('setup_fee', 0))
            plan.max_users = int(request.POST.get('max_users', 5))
            plan.max_products = int(request.POST.get('max_products', 1000))
            plan.max_customers = int(request.POST.get('max_customers', 500))
            plan.max_orders_per_month = int(request.POST.get('max_orders_per_month', 1000))
            plan.has_ai_features = request.POST.get('has_ai_features') == 'on'
            plan.has_whatsapp = request.POST.get('has_whatsapp') == 'on'
            plan.has_live_chat = request.POST.get('has_live_chat') == 'on'
            plan.has_backup = request.POST.get('has_backup') == 'on'
            plan.has_priority_support = request.POST.get('has_priority_support') == 'on'
            plan.has_custom_domain = request.POST.get('has_custom_domain') == 'on'
            plan.enabled_modules = enabled_modules
            plan.save()
            
            messages.success(request, '✅ Plan updated!')
            return redirect('subscription_plans_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'plan': plan,
        'plan_types': SubscriptionPlan.PLAN_TYPES,
    }
    return render(request, 'subscription/plan_edit.html', context)




@login_required
def subscription_plan_delete(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    
    if plan.clients.filter(subscription_status='active').exists():
        messages.error(request, '❌ Cannot delete! Active clients use this plan.')
        return redirect('subscription_plans_list')
    
    if request.method == 'POST':
        plan_name = plan.name
        plan.delete()
        messages.success(request, f'🗑️ Plan "{plan_name}" deleted!')
        return redirect('subscription_plans_list')
    
    return redirect('subscription_plans_list')


# ==========================================
# SUPER ADMIN - CLIENTS
# ==========================================

@login_required
def clients_list(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    clients = Client.objects.select_related('current_plan', 'user').all()
    
    status = request.GET.get('status', '')
    if status:
        clients = clients.filter(subscription_status=status)
    
    search = request.GET.get('search', '')
    if search:
        clients = clients.filter(
            Q(business_name__icontains=search) |
            Q(owner_name__icontains=search) |
            Q(email__icontains=search) |
            Q(subdomain__icontains=search)
        )
    
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(subscription_status='active').count()
    trial_clients = Client.objects.filter(subscription_status='trial').count()
    expired_clients = Client.objects.filter(subscription_status='expired').count()
    suspended_clients = Client.objects.filter(subscription_status='suspended').count()
    
    total_revenue = SubscriptionPayment.objects.filter(
        status='paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    monthly_revenue = SubscriptionPayment.objects.filter(
        status='paid',
        payment_date__month=now().month,
        payment_date__year=now().year
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    context = {
        'clients': clients,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'trial_clients': trial_clients,
        'expired_clients': expired_clients,
        'suspended_clients': suspended_clients,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue,
        'selected_status': status,
        'search': search,
    }
    return render(request, 'subscription/clients_list.html', context)


@login_required
def client_create(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                business_name = request.POST.get('business_name')
                owner_name = request.POST.get('owner_name')
                email = request.POST.get('email')
                phone = request.POST.get('phone')
                city = request.POST.get('city')
                address = request.POST.get('address', '')
                subdomain = request.POST.get('subdomain').lower().strip()
                plan_id = request.POST.get('plan')
                duration_months = int(request.POST.get('duration_months', 1))
                username = request.POST.get('username', subdomain).lower().strip()
                password = request.POST.get('password', 'client123')
                
                if not subdomain or len(subdomain) < 3:
                    messages.error(request, '❌ Subdomain min 3 chars!')
                    return redirect('client_create')
                
                if not subdomain.replace('-', '').isalnum():
                    messages.error(request, '❌ Only letters, numbers, hyphens!')
                    return redirect('client_create')
                
                if Client.objects.filter(subdomain=subdomain).exists():
                    messages.error(request, f'❌ "{subdomain}" taken!')
                    return redirect('client_create')
                
                reserved = ['admin', 'www', 'api', 'app', 'mail', 'ftp', 'blog', 'shop', 'store']
                if subdomain in reserved:
                    messages.error(request, f'❌ "{subdomain}" reserved!')
                    return redirect('client_create')
                
                if Client.objects.filter(email=email).exists():
                    messages.error(request, f'❌ Email exists!')
                    return redirect('client_create')
                
                if User.objects.filter(username=username).exists():
                    messages.error(request, f'❌ Username taken!')
                    return redirect('client_create')
                
                plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
                
                start_date = date.today()
                end_date = start_date + timedelta(days=duration_months * 30)
                
                client = Client.objects.create(
                    business_name=business_name,
                    business_type=plan.plan_type,
                    owner_name=owner_name,
                    email=email,
                    phone=phone,
                    city=city,
                    address=address,
                    subdomain=subdomain,
                    current_plan=plan,
                    subscription_start=start_date,
                    subscription_end=end_date,
                    subscription_status='active',
                )
                
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=owner_name.split()[0] if owner_name else '',
                    last_name=' '.join(owner_name.split()[1:]) if len(owner_name.split()) > 1 else ''
                )
                
                client.user = user
                client.save()
                
                total_amount = plan.get_price_for_duration(duration_months)
                SubscriptionPayment.objects.create(
                    client=client,
                    plan=plan,
                    amount=plan.price * duration_months,
                    total_amount=total_amount,
                    period_start=start_date,
                    period_end=end_date,
                    payment_method='cash',
                    status='paid',
                    payment_date=now()
                )
                
                SubscriptionHistory.objects.create(
                    client=client,
                    action='created',
                    new_plan=plan,
                    performed_by=request.user,
                    notes=f'{duration_months} months subscription'
                )
                
                messages.success(
                    request,
                    f'✅ Client "{business_name}" created!\n'
                    f'🌐 URL: https://{subdomain}.uqn88store.com\n'
                    f'👤 Username: {username}\n'
                    f'🔑 Password: {password}'
                )
                
                return redirect('client_detail', pk=client.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {'plans': SubscriptionPlan.objects.filter(is_active=True)}
    return render(request, 'subscription/client_create.html', context)


@login_required
def client_detail(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    payments = client.payments.all().order_by('-created_at')[:20]
    history = client.history.all().order_by('-performed_at')[:20]
    
    context = {
        'client': client,
        'payments': payments,
        'history': history,
        'days_remaining': client.days_remaining(),
        'is_expired': client.is_expired(),
        'is_expiring_soon': client.is_expiring_soon(),
        'modules': client.get_modules(),
    }
    return render(request, 'subscription/client_detail.html', context)


@login_required
def client_edit(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        try:
            client.business_name = request.POST.get('business_name')
            client.owner_name = request.POST.get('owner_name')
            client.email = request.POST.get('email')
            client.phone = request.POST.get('phone')
            client.city = request.POST.get('city')
            client.address = request.POST.get('address', '')
            client.custom_domain = request.POST.get('custom_domain', '') or None
            client.subscription_status = request.POST.get('subscription_status')
            client.notes = request.POST.get('notes', '')
            client.save()
            
            messages.success(request, '✅ Client updated!')
            return redirect('client_detail', pk=client.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {'client': client, 'status_choices': Client.STATUS_CHOICES}
    return render(request, 'subscription/client_edit.html', context)


@login_required
def client_renew(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                plan_id = request.POST.get('plan')
                duration_months = int(request.POST.get('duration_months', 1))
                payment_method = request.POST.get('payment_method', 'bank_transfer')
                
                plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
                
                if client.is_expired():
                    start_date = date.today()
                else:
                    start_date = client.subscription_end + timedelta(days=1)
                
                end_date = start_date + timedelta(days=duration_months * 30)
                
                old_plan = client.current_plan
                client.current_plan = plan
                client.subscription_start = start_date
                client.subscription_end = end_date
                client.subscription_status = 'active'
                client.save()
                
                total_amount = plan.get_price_for_duration(duration_months)
                SubscriptionPayment.objects.create(
                    client=client,
                    plan=plan,
                    amount=plan.price * duration_months,
                    total_amount=total_amount,
                    period_start=start_date,
                    period_end=end_date,
                    payment_method=payment_method,
                    status='paid',
                    payment_date=now()
                )
                
                client.total_paid += total_amount
                client.save()
                
                action = 'upgraded' if (old_plan and plan.price > old_plan.price) else \
                         'downgraded' if (old_plan and plan.price < old_plan.price) else 'renewed'
                
                SubscriptionHistory.objects.create(
                    client=client,
                    action=action,
                    old_plan=old_plan,
                    new_plan=plan,
                    performed_by=request.user,
                    notes=f'{duration_months} months - Rs. {total_amount:,.2f}'
                )
                
                messages.success(
                    request,
                    f'✅ Renewed! Valid until: {end_date} | Amount: Rs. {total_amount:,.2f}'
                )
                return redirect('client_detail', pk=client.pk)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'client': client,
        'plans': SubscriptionPlan.objects.filter(is_active=True),
    }
    return render(request, 'subscription/client_renew.html', context)


@login_required
def client_suspend(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        client.subscription_status = 'suspended'
        client.allow_login = False
        client.save()
        
        if client.user:
            client.user.is_active = False
            client.user.save()
        
        SubscriptionHistory.objects.create(
            client=client,
            action='suspended',
            performed_by=request.user,
        )
        messages.success(request, '⏸️ Client suspended!')
    
    return redirect('client_detail', pk=client.pk)


@login_required
def client_reactivate(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        client.subscription_status = 'active'
        client.allow_login = True
        client.save()
        
        if client.user:
            client.user.is_active = True
            client.user.save()
        
        SubscriptionHistory.objects.create(
            client=client,
            action='reactivated',
            performed_by=request.user,
        )
        messages.success(request, '▶️ Client reactivated!')
    
    return redirect('client_detail', pk=client.pk)


@login_required
def client_delete(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        if client.user:
            user = client.user
            client.user = None
            client.save()
            user.delete()
        
        business_name = client.business_name
        client.delete()
        messages.success(request, f'🗑️ Client "{business_name}" deleted!')
        return redirect('clients_list')
    
    return redirect('client_detail', pk=client.pk)


# ==========================================
# EXPIRED
# ==========================================

@login_required
def subscription_expired(request):
    context = {
        'client': getattr(request, 'tenant', None),
    }
    return render(request, 'subscription/expired.html', context)


# ==========================================
# API
# ==========================================

def check_subdomain_availability(request):
    subdomain = request.GET.get('subdomain', '').lower().strip()
    
    if not subdomain:
        return JsonResponse({'available': False, 'message': 'Subdomain required'})
    
    if len(subdomain) < 3:
        return JsonResponse({'available': False, 'message': 'Min 3 characters'})
    
    if not subdomain.replace('-', '').isalnum():
        return JsonResponse({'available': False, 'message': 'Only letters, numbers, hyphens'})
    
    reserved = ['admin', 'www', 'api', 'app', 'mail', 'ftp', 'blog', 'shop', 'store']
    if subdomain in reserved:
        return JsonResponse({'available': False, 'message': 'Reserved name'})
    
    exists = Client.objects.filter(subdomain=subdomain).exists()
    
    return JsonResponse({
        'available': not exists,
        'subdomain': subdomain,
        'message': 'Available!' if not exists else 'Already taken',
        'url': f"https://{subdomain}.uqn88store.com"
    })


# ==========================================
# SUBSCRIPTION DASHBOARD (Super Admin)
# ==========================================

@login_required
def subscription_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    # Stats
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(subscription_status='active').count()
    trial_clients = Client.objects.filter(subscription_status='trial').count()
    expired_clients = Client.objects.filter(subscription_status='expired').count()
    
    total_revenue = SubscriptionPayment.objects.filter(
        status='paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    monthly_revenue = SubscriptionPayment.objects.filter(
        status='paid',
        payment_date__month=now().month,
        payment_date__year=now().year
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Expiring soon
    expiring_soon = Client.objects.filter(
        subscription_status='active',
        subscription_end__lte=date.today() + timedelta(days=7),
        subscription_end__gte=date.today()
    )
    
    # Recent payments
    recent_payments = SubscriptionPayment.objects.filter(
        status='paid'
    ).select_related('client', 'plan').order_by('-payment_date')[:10]
    
    # Recent clients
    recent_clients = Client.objects.order_by('-created_at')[:10]
    
    context = {
        'total_clients': total_clients,
        'active_clients': active_clients,
        'trial_clients': trial_clients,
        'expired_clients': expired_clients,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue,
        'expiring_soon': expiring_soon,
        'recent_payments': recent_payments,
        'recent_clients': recent_clients,
    }
    return render(request, 'subscription/dashboard.html', context)