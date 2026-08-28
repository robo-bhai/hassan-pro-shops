from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Avg, Q
from django.utils.timezone import now
from datetime import datetime, timedelta, date
from decimal import Decimal
import json

from .models import *
from django.contrib.auth.models import User

# Import your existing models
from app.models import Sale, SaleItem, Purchase, Customer, Vendor, Inventory, Product, CompanyInfo, SaleOrder, Employee, SaleInstallment


def is_executive(user):
    """Check if user has executive privileges"""
    if user.is_superuser:
        return True
    return ExecutiveProfile.objects.filter(user=user).exists()


@login_required
@user_passes_test(is_executive)
def executive_dashboard(request):
    """Main CEO Dashboard"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    # Get today's date
    today = date.today()
    month_start = today.replace(day=1)
    
    # Calculate key metrics
    revenue_today = Sale.objects.filter(sale_date__date=today).aggregate(
        total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
    
    revenue_mtd = Sale.objects.filter(sale_date__date__gte=month_start).aggregate(
        total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
    
    profit_today = SaleItem.objects.filter(sale__sale_date__date=today).aggregate(
        total=Sum('profit'))['total'] or Decimal('0')
    discount_today = Sale.objects.filter(sale_date__date=today).aggregate(
        total=Sum('discount_value'))['total'] or Decimal('0')
    profit_today = profit_today - discount_today
    
    # Customer outstanding
    total_customer_outstanding = Decimal('0')
    for customer in Customer.objects.all():
        total_customer_outstanding += customer.adjusted_outstanding_balance()
    
    # Vendor outstanding
    total_vendor_outstanding = Decimal('0')
    for vendor in Vendor.objects.all():
        total_vendor_outstanding += vendor.outstanding_balance()
    
    # Low stock alert
    low_stock_count = Inventory.objects.filter(stock__lt=10).count()
    
    # Active installments
    active_installments = SaleInstallment.objects.filter(status__in=['pending', 'partial']).count()
    
    # Pending orders
    pending_sale_orders = SaleOrder.objects.filter(status='pending').count()
    
    # Top products (last 30 days)
    top_products = SaleItem.objects.filter(
        sale__sale_date__date__gte=today - timedelta(days=30)
    ).values('product__name').annotate(
        total_sales=Sum('total_amt'),
        total_qty=Sum('qty')
    ).order_by('-total_sales')[:5]
    
    # Recent sales
    recent_sales = Sale.objects.select_related('customer').order_by('-sale_date')[:10]
    
    # Strategic objectives progress
    objectives = StrategicObjective.objects.filter(status__in=['in_progress', 'on_track'])
    avg_progress = objectives.aggregate(Avg('progress_percentage'))['progress_percentage__avg'] or 0
    
    # Monthly sales trend for chart
    monthly_trend = []
    for i in range(11, -1, -1):
        target_month = today - timedelta(days=30 * i)
        month_start_dt = target_month.replace(day=1)
        month_end_dt = (month_start_dt + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_sales = Sale.objects.filter(
            sale_date__date__gte=month_start_dt,
            sale_date__date__lte=month_end_dt
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
        
        monthly_trend.append({
            'month': month_start_dt.strftime('%b %y'),
            'sales': float(month_sales)
        })
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else 'ERP System'
    
    context = {
        'company_name': company_name,
        'executive': executive,
        
        # Key Metrics
        'revenue_today': revenue_today,
        'revenue_mtd': revenue_mtd,
        'profit_today': profit_today,
        'total_customer_outstanding': total_customer_outstanding,
        'total_vendor_outstanding': total_vendor_outstanding,
        'low_stock_count': low_stock_count,
        'active_installments': active_installments,
        'pending_sale_orders': pending_sale_orders,
        
        # Charts & Lists
        'top_products': top_products,
        'recent_sales': recent_sales,
        'monthly_trend': json.dumps(monthly_trend),
        'objective_progress': avg_progress,
    }
    
    return render(request, 'ceo/dashboard/executive_dashboard.html', context)


@login_required
@user_passes_test(is_executive)
def strategic_objectives(request):
    """OKR Management"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_objective':
            StrategicObjective.objects.create(
                objective=request.POST.get('objective'),
                description=request.POST.get('description', ''),
                quarter=request.POST.get('quarter'),
                year=int(request.POST.get('year')),
                priority=request.POST.get('priority'),
                start_date=request.POST.get('start_date'),
                target_date=request.POST.get('target_date'),
                estimated_revenue_impact=Decimal(request.POST.get('estimated_revenue_impact', 0)),
                estimated_cost_saving=Decimal(request.POST.get('estimated_cost_saving', 0)),
                owner=executive
            )
            messages.success(request, '✅ Strategic objective created!')
            
        elif action == 'add_key_result':
            KeyResult.objects.create(
                objective_id=request.POST.get('objective_id'),
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                target_value=Decimal(request.POST.get('target_value')),
                unit=request.POST.get('unit'),
                start_value=Decimal(request.POST.get('start_value', 0))
            )
            messages.success(request, '✅ Key result added!')
        
        elif action == 'update_progress':
            kr = KeyResult.objects.get(id=request.POST.get('kr_id'))
            kr.current_value = Decimal(request.POST.get('current_value'))
            kr.update_notes = request.POST.get('notes', '')
            kr.save()
            
            # Update objective progress
            objective = kr.objective
            total_weight = sum(kr.weight for kr in objective.key_results.all())
            weighted_progress = sum(kr.progress_percentage() * kr.weight for kr in objective.key_results.all())
            objective.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0
            objective.save()
            
            messages.success(request, '✅ Progress updated!')
        
        return redirect('strategic_objectives')
    
    year = request.GET.get('year', date.today().year)
    quarter = request.GET.get('quarter', '')
    
    objectives = StrategicObjective.objects.filter(year=year)
    if quarter:
        objectives = objectives.filter(quarter=quarter)
    
    context = {
        'company_name': 'ERP System',
        'objectives': objectives,
        'quarters': StrategicObjective.QUARTER_CHOICES,
        'priorities': StrategicObjective.PRIORITY_CHOICES,
        'selected_year': int(year),
        'years': range(2020, date.today().year + 2),
        'statuses': StrategicObjective.STATUS_CHOICES,
    }
    return render(request, 'ceo/strategy/objectives.html', context)


@login_required
@user_passes_test(is_executive)
def risk_management(request):
    """Risk Management Dashboard"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        RiskAssessment.objects.create(
            title=request.POST.get('title'),
            description=request.POST.get('description'),
            category=request.POST.get('category'),
            likelihood=int(request.POST.get('likelihood')),
            impact=int(request.POST.get('impact')),
            mitigation_strategy=request.POST.get('mitigation_strategy'),
            mitigation_owner=executive,
            mitigation_deadline=request.POST.get('mitigation_deadline'),
            potential_financial_loss=Decimal(request.POST.get('potential_financial_loss', 0)),
            mitigation_cost=Decimal(request.POST.get('mitigation_cost', 0)),
            identified_by=executive,
            next_review=request.POST.get('next_review')
        )
        messages.success(request, '✅ Risk assessment created!')
        return redirect('risk_management')
    
    risks = RiskAssessment.objects.all()
    
    context = {
        'company_name': 'ERP System',
        'risks': risks,
        'categories': RiskAssessment.RISK_CATEGORIES,
        'risk_levels': RiskAssessment.RISK_LEVELS,
        'total_risk_value': sum(r.potential_financial_loss for r in risks),
        'total_mitigation_cost': sum(r.mitigation_cost for r in risks),
    }
    return render(request, 'ceo/strategy/risk_management.html', context)


@login_required
@user_passes_test(is_executive)
def executive_meetings(request):
    """Meeting Management"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        meeting = ExecutiveMeeting.objects.create(
            title=request.POST.get('title'),
            meeting_type=request.POST.get('meeting_type'),
            meeting_date=request.POST.get('meeting_date'),
            duration_hours=Decimal(request.POST.get('duration_hours', 1)),
            location=request.POST.get('location', ''),
            virtual_link=request.POST.get('virtual_link', ''),
            agenda=request.POST.get('agenda'),
            chairperson=executive
        )
        
        attendee_ids = request.POST.getlist('attendees')
        if attendee_ids:
            meeting.attendees.add(*attendee_ids)
        
        messages.success(request, '✅ Meeting scheduled!')
        return redirect('executive_meetings')
    
    meetings = ExecutiveMeeting.objects.all().order_by('-meeting_date')
    
    context = {
        'company_name': 'ERP System',
        'upcoming': meetings.filter(meeting_date__gte=now(), status='scheduled'),
        'past': meetings.filter(meeting_date__lt=now())[:10],
        'executives': ExecutiveProfile.objects.all(),
        'meeting_types': ExecutiveMeeting.MEETING_TYPES,
    }
    return render(request, 'ceo/operations/meetings.html', context)


@login_required
@user_passes_test(is_executive)
def executive_briefings(request):
    """Executive Briefings"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        today = date.today()
        briefing = ExecutiveBriefing.objects.create(
            executive=executive,
            briefing_type=request.POST.get('briefing_type'),
            period_start=today,
            period_end=today,
            executive_summary="Daily briefing generated.",
            achievements="All systems operational.",
            challenges="No major issues reported.",
            upcoming_priorities="Review Q4 strategy.",
            created_by=executive
        )
        messages.success(request, '✅ Briefing generated!')
        return redirect('executive_briefings')
    
    briefings = ExecutiveBriefing.objects.filter(executive=executive).order_by('-period_start')
    
    context = {
        'company_name': 'ERP System',
        'briefings': briefings,
        'unread_count': briefings.filter(is_read=False).count(),
        'briefing_types': ExecutiveBriefing.BRIEFING_TYPES,
    }
    return render(request, 'ceo/reports/briefings.html', context)


@login_required
@user_passes_test(is_executive)
def financial_analytics(request):
    """Financial Analytics Dashboard"""
    
    period = request.GET.get('period', 'month')
    
    if period == 'week':
        start_date = date.today() - timedelta(days=7)
    elif period == 'month':
        start_date = date.today().replace(day=1)
    elif period == 'quarter':
        quarter_start = (date.today().month - 1) // 3 * 3 + 1
        start_date = date(date.today().year, quarter_start, 1)
    elif period == 'year':
        start_date = date(date.today().year, 1, 1)
    else:
        start_date = date.today().replace(day=1)
    
    sales_data = Sale.objects.filter(sale_date__date__gte=start_date)
    
    # Revenue by category
    revenue_by_category = SaleItem.objects.filter(
        sale__in=sales_data,
        product__category__isnull=False
    ).values('product__category__name').annotate(
        total=Sum('total_amt')
    ).order_by('-total')[:10]
    
    # Daily trend
    daily_trend = []
    for i in range(30):
        d = start_date + timedelta(days=i)
        if d > date.today():
            break
        day_sales = sales_data.filter(sale_date__date=d).aggregate(
            total=Sum('saleitem__total_amt'))['total'] or 0
        daily_trend.append({
            'date': d.strftime('%d %b'),
            'sales': float(day_sales)
        })
    
    total_revenue = sales_data.aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
    total_profit = sales_data.aggregate(total=Sum('saleitem__profit'))['total'] or 0
    gross_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    context = {
        'company_name': 'ERP System',
        'period': period,
        'revenue_by_category': revenue_by_category,
        'daily_trend': json.dumps(daily_trend),
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'gross_margin': gross_margin,
    }
    return render(request, 'ceo/analytics/financial.html', context)


@login_required
@user_passes_test(is_executive)
def ceo_settings(request):
    """CEO Settings"""
    
    executive = ExecutiveProfile.objects.filter(user=request.user).first()
    
    if not executive and request.user.is_superuser:
        # Auto-create for superuser
        executive = ExecutiveProfile.objects.create(
            user=request.user,
            executive_type='ceo',
            title='Chief Executive Officer',
            department='Executive Office',
            office_phone='',
            mobile_phone='',
            personal_email=request.user.email
        )
    
    if request.method == 'POST':
        executive.title = request.POST.get('title')
        executive.office_phone = request.POST.get('office_phone', '')
        executive.mobile_phone = request.POST.get('mobile_phone', '')
        executive.personal_email = request.POST.get('personal_email')
        executive.assistant_email = request.POST.get('assistant_email', '')
        executive.assistant_phone = request.POST.get('assistant_phone', '')
        executive.security_clearance_level = int(request.POST.get('security_clearance_level', 5))
        executive.mfa_enabled = request.POST.get('mfa_enabled') == 'on'
        executive.session_timeout_minutes = int(request.POST.get('session_timeout_minutes', 30))
        executive.email_alerts = request.POST.get('email_alerts') == 'on'
        executive.whatsapp_alerts = request.POST.get('whatsapp_alerts') == 'on'
        executive.slack_webhook = request.POST.get('slack_webhook', '')
        executive.save()
        
        messages.success(request, '✅ Settings updated!')
        return redirect('ceo_settings')
    
    context = {
        'company_name': 'ERP System',
        'executive': executive,
        'security_levels': [(i, f'Level {i}') for i in range(1, 11)],
    }
    return render(request, 'ceo/settings/profile.html', context)


# API Endpoints
@login_required
@user_passes_test(is_executive)
def api_realtime_metrics(request):
    """API for real-time metrics"""
    metrics = RealTimeMetric.objects.all().values('metric_type', 'current_value', 'percentage_change', 'trend')
    return JsonResponse({
        'success': True,
        'metrics': list(metrics),
        'timestamp': now().isoformat()
    })


@login_required
@user_passes_test(is_executive)
def api_audit_logs(request):
    """API for audit logs"""
    limit = int(request.GET.get('limit', 50))
    logs = ExecutiveAuditLog.objects.select_related('executive').order_by('-timestamp')[:limit]
    
    data = [{
        'executive': log.executive.executive_id,
        'action': log.get_action_type_display(),
        'description': log.description,
        'timestamp': log.timestamp.isoformat(),
        'ip': log.ip_address
    } for log in logs]
    
    return JsonResponse({'success': True, 'logs': data})