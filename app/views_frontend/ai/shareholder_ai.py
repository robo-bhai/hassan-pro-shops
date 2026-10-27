"""Frontend views: ai/shareholder_ai (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.views.decorators.http import require_POST
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils.timezone import now
from django.contrib import messages
from ...models import Shareholder, CompanyInfo
from ...ai.ai_shareholder_engine import AIShareholderEngine


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_shareholder_dashboard(request):
    """AI Shareholder Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import (
        AIShareholderScore, AIShareholderChurn,
        AIDividendRecommendation, AIShareholderAlert,
        AIShareholderForecast
    )
    
    # Run analysis if requested
    if request.GET.get('run') == 'true':
        try:
            engine = AIShareholderEngine()
            results = engine.run_full_analysis()
            
            messages.success(
                request,
                f"🤖 AI Analysis Complete! "
                f"Scored: {results['scores_calculated']} | "
                f"Churn: {results['churn_predictions']} | "
                f"Fraud: {results['fraud_alerts']}"
            )
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_shareholder_dashboard')
    
    # Get data
    top_shareholders = AIShareholderScore.objects.select_related(
        'shareholder'
    ).order_by('-overall_score')[:10]
    
    at_risk_shareholders = AIShareholderChurn.objects.select_related(
        'shareholder'
    ).filter(
        risk_level__in=['high', 'critical']
    ).order_by('-churn_probability')[:10]
    
    recent_alerts = AIShareholderAlert.objects.select_related(
        'shareholder'
    ).filter(
        is_resolved=False
    ).order_by('-created_at')[:10]
    
    dividend_recommendation = AIDividendRecommendation.objects.filter(
        status='pending'
    ).order_by('-created_at').first()
    
    forecast = AIShareholderForecast.objects.order_by('-forecast_date').first()
    
    # Stats
    total_shareholders = Shareholder.objects.filter(status='active').count()
    scored_shareholders = AIShareholderScore.objects.count()
    critical_risk = AIShareholderChurn.objects.filter(
        risk_level='critical'
    ).count()
    investment_at_risk = AIShareholderChurn.objects.filter(
        risk_level__in=['high', 'critical']
    ).aggregate(
        total=Sum('investment_at_risk')
    )['total'] or 0
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'top_shareholders': top_shareholders,
        'at_risk_shareholders': at_risk_shareholders,
        'recent_alerts': recent_alerts,
        'dividend_recommendation': dividend_recommendation,
        'forecast': forecast,
        'total_shareholders': total_shareholders,
        'scored_shareholders': scored_shareholders,
        'critical_risk': critical_risk,
        'investment_at_risk': investment_at_risk,
        'total_alerts': recent_alerts.count(),
    }
    return render(request, 'ai/shareholder_dashboard.html', context)


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_shareholder_scores(request):
    """View all shareholder scores"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIShareholderScore
    
    scores = AIShareholderScore.objects.select_related('shareholder').all()
    
    # Filter
    risk_level = request.GET.get('level', '')
    if risk_level:
        scores = scores.filter(risk_level=risk_level)
    
    # Stats
    stats = {
        'total': scores.count(),
        'excellent': scores.filter(risk_level='excellent').count(),
        'good': scores.filter(risk_level='good').count(),
        'warning': scores.filter(risk_level='warning').count(),
        'critical': scores.filter(risk_level='critical').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'scores': scores,
        'stats': stats,
        'selected_level': risk_level,
    }
    return render(request, 'ai/shareholder_scores.html', context)


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_shareholder_churn(request):
    """View churn predictions"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIShareholderChurn
    
    churn_data = AIShareholderChurn.objects.select_related('shareholder').all()
    
    risk_level = request.GET.get('level', '')
    if risk_level:
        churn_data = churn_data.filter(risk_level=risk_level)
    
    stats = {
        'total': churn_data.count(),
        'low': churn_data.filter(risk_level='low').count(),
        'medium': churn_data.filter(risk_level='medium').count(),
        'high': churn_data.filter(risk_level='high').count(),
        'critical': churn_data.filter(risk_level='critical').count(),
        'at_risk_amount': churn_data.filter(
            risk_level__in=['high', 'critical']
        ).aggregate(total=Sum('investment_at_risk'))['total'] or 0,
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'churn_data': churn_data,
        'stats': stats,
        'selected_level': risk_level,
    }
    return render(request, 'ai/shareholder_churn.html', context)


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_dividend_recommendation(request):
    """View dividend recommendations"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIDividendRecommendation
    
    # Get latest recommendation
    recommendations = AIDividendRecommendation.objects.all().order_by('-created_at')
    latest = recommendations.first()
    
    # Generate new if requested
    if request.GET.get('generate') == 'true':
        engine = AIShareholderEngine()
        new_rec = engine.recommend_dividend()
        
        if new_rec:
            messages.success(request, f"✅ New recommendation: {new_rec.recommended_percentage}%")
        else:
            messages.warning(request, "⚠️ Cannot generate recommendation (no profit)")
        
        return redirect('ai_dividend_recommendation')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'recommendations': recommendations,
        'latest': latest,
    }
    return render(request, 'ai/dividend_recommendation.html', context)


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_shareholder_alerts(request):
    """View all shareholder AI alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIShareholderAlert
    
    alerts = AIShareholderAlert.objects.select_related('shareholder').all()
    
    alert_type = request.GET.get('type', '')
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'medium': alerts.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts,
        'stats': stats,
        'selected_type': alert_type,
        'selected_severity': severity,
        'selected_status': status,
        'alert_types': AIShareholderAlert.ALERT_TYPES,
        'severity_levels': AIShareholderAlert.SEVERITY,
    }
    return render(request, 'ai/shareholder_alerts.html', context)


@login_required
@perm_required('use_ai', 'view_shareholders')
def ai_shareholder_forecast(request):
    """6-Month Shareholder Forecast"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIShareholderForecast
    import json
    
    forecast = AIShareholderForecast.objects.order_by('-forecast_date').first()
    
    if request.GET.get('generate') == 'true':
        engine = AIShareholderEngine()
        forecast = engine.generate_forecast()
        messages.success(request, "✅ New forecast generated!")
        return redirect('ai_shareholder_forecast')
    
    # Chart data
    chart_labels = []
    chart_values = []
    
    if forecast and forecast.monthly_forecast:
        for m in forecast.monthly_forecast:
            chart_labels.append(m['month'])
            chart_values.append(m['expected_shareholders'])
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'forecast': forecast,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
    }
    return render(request, 'ai/shareholder_forecast.html', context)


@login_required
@perm_required('manage_ai_ops')
@require_POST
def ai_shareholder_alert_resolve(request, pk):
    """Resolve a shareholder alert"""
    
    from ...models import AIShareholderAlert
    alert = get_object_or_404(AIShareholderAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_shareholder_alerts')
