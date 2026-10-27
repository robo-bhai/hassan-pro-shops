"""Frontend views: ai/ai_insights (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST
from ...models import *
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, F
from decimal import Decimal
from django.utils.timezone import now
from datetime import timedelta
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from ...models import (
    CashBalance,
    CompanyInfo,
    Product,
    AIInsight,
    AIHealthScore,
    AIAnomalyDetection,
    AIPrediction,
)
from ...ai.ai_engine import AIEngine
from ...ai.ai_operations_engine import AIOperationsEngine
from ...ai.chatbot_engine import BusinessChatbot
logger = logging.getLogger(__name__)


@login_required
def risk_assessment_api(request):
    """API: Calculate risk assessment for a purchase"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        from ...risk_calculator import RiskCalculator
        
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        sale_qty = int(request.GET.get('sale_qty', 0))
        purchase_qty = int(request.GET.get('purchase_qty', 0))
        unit_price = Decimal(request.GET.get('unit_price', 0))
        
        if not product_id or not warehouse_id:
            return JsonResponse({'success': False, 'message': 'Product and Warehouse required!'})
        
        if purchase_qty <= 0:
            return JsonResponse({
                'success': True,
                'score': 0,
                'category': 'NO PURCHASE NEEDED',
                'color': 'success',
                'factors': {},
                'alerts': [],
                'positives': ['Stock sufficient - no purchase needed'],
                'recommendation': {
                    'action': 'SKIP',
                    'title': '✅ NO PURCHASE NEEDED',
                    'message': 'Available stock is enough. There is no need to buy anything.',
                    'suggested_qty': 0,
                    'steps': ['Stock is sufficient', 'Keep monitoring'],
                },
            })
        
        product = get_object_or_404(Product, pk=product_id)
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Calculate risk
        calculator = RiskCalculator(
            product=product,
            warehouse=warehouse,
            sale_qty=sale_qty,
            purchase_qty=purchase_qty,
            unit_price=unit_price,
        )
        
        result = calculator.calculate()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Risk assessment error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e),
        })


@login_required
@perm_required('use_ai')
def ai_dashboard(request):
    """AI Self-Diagnostic Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied! Only admins can access AI Dashboard.')
        return redirect('dashboard')
    
    # Run AI analysis on-demand
    run_analysis = request.GET.get('run', 'false') == 'true'
    
    if run_analysis:
        with transaction.atomic():
            engine = AIEngine()
            result = engine.run_full_analysis()
            
            # Save health score
            today = now().date()
            health_score, created = AIHealthScore.objects.get_or_create(
                date=today,
                defaults={
                    'overall_score': result['health_score'],
                }
            )
            
            if not created:
                health_score.overall_score = result['health_score']
                health_score.save()
            
            messages.success(
                request, 
                f"🤖 AI Analysis complete! "
                f"{result['insights_count']} new insights. "
                f"Health Score: {result['health_score']}/100"
            )
    
    # Get all insights
    insights = AIInsight.objects.filter(is_ignored=False).order_by('-detected_at')
    
    # Stats
    total_insights = insights.count()
    critical_count = insights.filter(severity='critical', is_resolved=False).count()
    high_count = insights.filter(severity='high', is_resolved=False).count()
    medium_count = insights.filter(severity='medium', is_resolved=False).count()
    low_count = insights.filter(severity='low', is_resolved=False).count()
    
    # Category breakdown
    categories = insights.values('category').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Health score
    latest_score = AIHealthScore.objects.order_by('-date').first()
    
    # Anomalies
    anomalies = AIAnomalyDetection.objects.filter(
        is_resolved=False
    ).order_by('-detected_at')[:10]
    
    # Predictions
    predictions = AIPrediction.objects.order_by('-created_at')[:10]
    
    # Filter by category
    category_filter = request.GET.get('category', '')
    if category_filter:
        insights = insights.filter(category=category_filter)
    
    # Filter by severity
    severity_filter = request.GET.get('severity', '')
    if severity_filter:
        insights = insights.filter(severity=severity_filter)
    
    # Pagination
    paginator = Paginator(insights, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'insights': page_obj,
        'total_insights': total_insights,
        'critical_count': critical_count,
        'high_count': high_count,
        'medium_count': medium_count,
        'low_count': low_count,
        'categories': categories,
        'latest_score': latest_score,
        'anomalies': anomalies,
        'predictions': predictions,
        'category_filter': category_filter,
        'severity_filter': severity_filter,
        'insight_categories': AIInsight.CATEGORIES,
        'severity_levels': AIInsight.SEVERITY_LEVELS,
    }
    return render(request, 'ai/dashboard.html', context)


@login_required
@perm_required('use_ai')
def ai_run_analysis(request):
    """Run AI analysis via AJAX"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        engine = AIEngine()
        result = engine.run_full_analysis()
        
        return JsonResponse({
            'success': True,
            'insights_count': result['insights_count'],
            'health_score': result['health_score'],
            'message': f"✅ Analysis complete! {result['insights_count']} new insights found."
        })
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
@perm_required('use_ai')
def ai_insight_detail(request, pk):
    """View AI insight detail"""
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    # Track view
    if request.user.is_authenticated:
        from ...models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='viewed',
            user=request.user,
        )
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'insight': insight,
    }
    return render(request, 'ai/insight_detail.html', context)


@login_required
@perm_required('use_ai')
def ai_resolve_insight(request, pk):
    """Mark insight as resolved"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    if request.method == 'POST':
        insight.is_resolved = True
        insight.resolved_at = now()
        insight.resolved_by = request.user
        insight.save()
        
        # Track action
        from ...models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='fixed',
            user=request.user,
        )
        
        messages.success(request, f'✅ Insight marked as resolved!')
    
    return redirect('ai_dashboard')


@login_required
@perm_required('use_ai')
def ai_ignore_insight(request, pk):
    """Ignore an insight"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    insight = get_object_or_404(AIInsight, pk=pk)
    
    if request.method == 'POST':
        insight.is_ignored = True
        insight.save()
        
        # Track action
        from ...models import AILearningData
        AILearningData.objects.create(
            insight=insight,
            action='ignored',
            user=request.user,
        )
        
        messages.success(request, f'🔇 Insight ignored!')
    
    return redirect('ai_dashboard')


@login_required
@perm_required('use_ai')
def ai_insights_list(request):
    """View all AI insights"""
    
    insights = AIOperationsInsight.objects.filter(is_ignored=False).order_by('-detected_at')
    
    # Filters
    insight_type = request.GET.get('type', '')
    if insight_type:
        insights = insights.filter(insight_type=insight_type)
    
    severity = request.GET.get('severity', '')
    if severity:
        insights = insights.filter(severity=severity)
    
    status = request.GET.get('status', '')
    if status == 'resolved':
        insights = insights.filter(is_resolved=True)
    elif status == 'unresolved':
        insights = insights.filter(is_resolved=False)
    
    # Stats
    stats = {
        'total': insights.count(),
        'critical': insights.filter(severity='critical', is_resolved=False).count(),
        'high': insights.filter(severity='high', is_resolved=False).count(),
        'medium': insights.filter(severity='medium', is_resolved=False).count(),
        'low': insights.filter(severity='low', is_resolved=False).count(),
    }
    
    paginator = Paginator(insights, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'insights': page_obj,
        'stats': stats,
        'insight_types': AIOperationsInsight.INSIGHT_TYPES,
        'severities': AIOperationsInsight.SEVERITY,
        'selected_type': insight_type,
        'selected_severity': severity,
        'selected_status': status,
    }
    return render(request, 'operations/ai_insights.html', context)


@login_required
@perm_required('use_ai')
@require_POST
def ai_insight_resolve(request, pk):
    """Mark AI insight as resolved"""
    insight = get_object_or_404(AIOperationsInsight, pk=pk)
    insight.is_resolved = True
    insight.resolved_at = now()
    insight.resolved_by = request.user
    insight.save()
    
    messages.success(request, '✅ Insight resolved!')
    return redirect('ai_insights_list')


@login_required
@perm_required('use_ai')
@require_POST
def ai_insight_ignore(request, pk):
    """Ignore AI insight"""
    insight = get_object_or_404(AIOperationsInsight, pk=pk)
    insight.is_ignored = True
    insight.save()
    
    messages.success(request, '🔇 Insight ignored!')
    return redirect('ai_insights_list')


@login_required
@perm_required('use_ai')
def ai_task_suggestions(request):
    """View AI task suggestions"""
    
    suggestions = AITaskSuggestion.objects.filter(
        status='pending'
    ).order_by('-generated_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suggestions': suggestions,
        'total': suggestions.count(),
    }
    return render(request, 'operations/ai_suggestions.html', context)


@login_required
@perm_required('use_ai')
def ai_suggestion_accept(request, pk):
    """Accept AI suggestion and create task"""
    
    suggestion = get_object_or_404(AITaskSuggestion, pk=pk)
    
    if request.method == 'POST':
        try:
            # Get or create a default plan
            plan, _ = BusinessOperationPlan.objects.get_or_create(
                title=f"AI Suggested Tasks - {localdate()}",
                defaults={
                    'description': 'Tasks created from AI suggestions',
                    'plan_type': 'daily',
                    'department': suggestion.department,
                    'start_date': localdate(),
                    'end_date': localdate() + timedelta(days=7),
                    'created_by': request.user,
                    'status': 'active',
                }
            )
            
            # Create task
            task = OperationTask.objects.create(
                plan=plan,
                title=suggestion.title,
                description=suggestion.description,
                priority=suggestion.suggested_priority,
                assigned_to=suggestion.suggested_assignee,
                assigned_by=request.user,
                due_date=now() + timedelta(days=1),
                notes=f"Created from AI suggestion. Reason: {suggestion.reason}",
                created_by=request.user,
                ai_suggested=True,
            )
            
            suggestion.status = 'accepted'
            suggestion.created_task = task
            suggestion.processed_at = now()
            suggestion.processed_by = request.user
            suggestion.save()
            
            messages.success(request, f'✅ Task created: {task.task_no}')
            return redirect('task_detail', pk=task.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('ai_task_suggestions')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suggestion': suggestion,
    }
    return render(request, 'operations/ai_suggestion_accept.html', context)


@login_required
@perm_required('use_ai')
@require_POST
def ai_suggestion_reject(request, pk):
    """Reject AI suggestion"""
    suggestion = get_object_or_404(AITaskSuggestion, pk=pk)
    suggestion.status = 'rejected'
    suggestion.processed_at = now()
    suggestion.processed_by = request.user
    suggestion.save()
    
    messages.success(request, '❌ Suggestion rejected!')
    return redirect('ai_task_suggestions')


@login_required
@perm_required('use_ai')
def run_ai_analysis(request):
    """Run AI analysis via AJAX"""
    
    if not request.user.is_superuser and not can_manage_operations(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        engine = AIOperationsEngine()
        result = engine.run_full_analysis()
        
        return JsonResponse({
            'success': True,
            'insights_created': result['insights_created'],
            'alerts_created': result['alerts_created'],
            'task_suggestions': result['task_suggestions'],
            'health_score': result['health_score'],
            'details': result['details'],
            'message': f"✅ AI Analysis Complete! Health: {result['health_score']}/100"
        })
    except Exception as e:
        logger.error(f"AI Analysis Error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def chatbot_api(request):
    """Chatbot API - Handles all queries"""
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        
        if not question:
            return JsonResponse({
                'success': False,
                'message': 'Question required'
            })
        
        # Get response from chatbot
        chatbot = BusinessChatbot(user=request.user)
        answer = chatbot.get_response(question)
        
        return JsonResponse({
            'success': True,
            'answer': answer,
            'question': question,
            'timestamp': now().isoformat(),
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON'
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Chatbot error: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Server error'
        })


@login_required
def announce_alerts_api(request):
    """API: Get alerts that need voice announcement"""
    
    try:
        alerts = []
        
        # ==========================================
        # 1. LOW STOCK ALERTS
        # ==========================================
        low_stock_items = Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).select_related('product')[:5]
        
        for item in low_stock_items:
            alerts.append({
                'id': f'lowstock_{item.id}',
                'type': 'low_stock',
                'product_name': item.product.name,
                'units': int(item.stock),
                'priority': 'high',
                'severity': 'warning',
            })
        
        # ==========================================
        # 2. OVERDUE TASKS
        # ==========================================
        try:
            from ...models import OperationTask
            from django.utils.timezone import now
            
            overdue_count = OperationTask.objects.filter(
                due_date__lt=now(),
                status__in=['pending', 'in_progress']
            ).count()
            
            if overdue_count > 0:
                alerts.append({
                    'id': f'overdue_{overdue_count}',
                    'type': 'overdue_task',
                    'count': overdue_count,
                    'priority': 'critical',
                    'severity': 'danger',
                })
        except:
            pass
        
        # ==========================================
        # 3. EMI DUE TODAY
        # ==========================================
        try:
            from ...models import SaleInstallment
            from django.utils.timezone import now
            
            today = now().date()
            
            due_emis = SaleInstallment.objects.filter(
                status__in=['pending', 'partial'],
                next_due_date=today
            ).select_related('sale__customer')[:3]
            
            for inst in due_emis:
                alerts.append({
                    'id': f'emi_{inst.id}',
                    'type': 'emi_due',
                    'customer_name': inst.sale.customer.name,
                    'amount': float(inst.remaining_amount()),
                    'priority': 'medium',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 4. LOW CASH BALANCE
        # ==========================================
        try:
            balance = CashBalance.get_balance()
            
            if balance < 10000:  # Rs. 10,000 se kam
                alerts.append({
                    'id': f'cash_low_{int(balance)}',
                    'type': 'cash_low',
                    'balance': float(balance),
                    'priority': 'high',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 5. OVERDUE PAYMENTS (Customer)
        # ==========================================
        try:
            from ...models import Customer
            
            overdue_customers = []
            for customer in Customer.objects.all()[:100]:
                balance = customer.adjusted_outstanding_balance()
                if balance > 50000:  # Rs. 50,000 se zyada
                    overdue_customers.append(customer)
                    if len(overdue_customers) >= 3:
                        break
            
            for customer in overdue_customers:
                alerts.append({
                    'id': f'payment_{customer.id}',
                    'type': 'payment_overdue',
                    'customer_name': customer.name,
                    'amount': float(customer.adjusted_outstanding_balance()),
                    'priority': 'medium',
                    'severity': 'warning',
                })
        except:
            pass
        
        # ==========================================
        # 6. NEW WHATSAPP MESSAGES
        # ==========================================
        try:
            from ...models import Notification
            
            new_whatsapp = Notification.objects.filter(
                Q(user=request.user) | Q(user__isnull=True),
                category='whatsapp',
                is_read=False
            ).count()
            
            if new_whatsapp > 0:
                alerts.append({
                    'id': f'whatsapp_{new_whatsapp}',
                    'type': 'whatsapp',
                    'count': new_whatsapp,
                    'priority': 'low',
                    'severity': 'info',
                })
        except:
            pass
        
        # Return top 5 alerts by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        alerts.sort(key=lambda x: priority_order.get(x.get('priority', 'medium'), 2))
        
        return JsonResponse({
            'success': True,
            'alerts': alerts[:5],
            'total': len(alerts),
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Announce alerts error: {e}")
        return JsonResponse({
            'success': False,
            'alerts': [],
            'error': str(e),
        })


@login_required
def voice_announcement_settings(request):
    """Voice Announcement Settings Page"""
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_title': '🔊 Voice Announcement Settings',
    }
    return render(request, 'settings/voice_announcement.html', context)
