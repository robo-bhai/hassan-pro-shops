from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Avg
from decimal import Decimal
import json
from datetime import datetime, timedelta, date
from app.models import CompanyInfo, BIDashboard, BIWidget, BIReport, BIKPI, BIAlert, BIInsight, BIForecast
from app.utils.bi import (
    get_sales_data, get_financial_data, get_customer_data,
    get_inventory_data, get_employee_data, calculate_kpi
)


@login_required
def bi_dashboard(request):
    """Business Intelligence Dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    # Get default dashboard or first active
    dashboard = BIDashboard.objects.filter(is_active=True, is_default=True).first()
    if not dashboard:
        dashboard = BIDashboard.objects.filter(is_active=True).first()
    
    # Get data
    sales_data = get_sales_data(30)
    financial_data = get_financial_data()
    customer_data = get_customer_data(30)
    inventory_data = get_inventory_data()
    employee_data = get_employee_data()
    
    # Get KPIs
    kpis = BIKPI.objects.filter(is_active=True)[:6]
    for kpi in kpis:
        calculate_kpi(kpi)
    
    # Get insights
    insights = BIInsight.objects.order_by('-created_at')[:5]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dashboard': dashboard,
        'sales_data': sales_data,
        'financial_data': financial_data,
        'customer_data': customer_data,
        'inventory_data': inventory_data,
        'employee_data': employee_data,
        'kpis': kpis,
        'insights': insights,
    }
    return render(request, 'bi/dashboard.html', context)


@login_required
def bi_dashboards_list(request):
    """List all dashboards"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    dashboards = BIDashboard.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dashboards': dashboards,
    }
    return render(request, 'bi/dashboards_list.html', context)


@login_required
def bi_dashboard_create(request):
    """Create BI dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            dashboard = BIDashboard.objects.create(
                name=request.POST.get('name'),
                dashboard_type=request.POST.get('dashboard_type'),
                description=request.POST.get('description', ''),
                layout={'widgets': []},
                is_default=request.POST.get('is_default') == 'on',
                created_by=request.user
            )
            
            if dashboard.is_default:
                BIDashboard.objects.exclude(id=dashboard.id).update(is_default=False)
            
            messages.success(request, f'✅ Dashboard "{dashboard.name}" created!')
            return redirect('bi_dashboard_edit', pk=dashboard.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dashboard_types': BIDashboard.DASHBOARD_TYPES,
    }
    return render(request, 'bi/dashboard_create.html', context)


@login_required
def bi_dashboard_edit(request, pk):
    """Edit BI dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    dashboard = get_object_or_404(BIDashboard, pk=pk)
    widgets = dashboard.widgets.all()
    
    if request.method == 'POST':
        try:
            dashboard.name = request.POST.get('name')
            dashboard.dashboard_type = request.POST.get('dashboard_type')
            dashboard.description = request.POST.get('description', '')
            dashboard.is_default = request.POST.get('is_default') == 'on'
            dashboard.save()
            
            if dashboard.is_default:
                BIDashboard.objects.exclude(id=dashboard.id).update(is_default=False)
            
            messages.success(request, f'✅ Dashboard "{dashboard.name}" updated!')
            return redirect('bi_dashboards_list')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dashboard': dashboard,
        'widgets': widgets,
        'widget_types': BIWidget.WIDGET_TYPES,
    }
    return render(request, 'bi/dashboard_edit.html', context)


@login_required
def bi_widget_create(request, dashboard_id):
    """Create BI widget"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    dashboard = get_object_or_404(BIDashboard, pk=dashboard_id)
    
    if request.method == 'POST':
        try:
            widget = BIWidget.objects.create(
                dashboard=dashboard,
                title=request.POST.get('title'),
                widget_type=request.POST.get('widget_type'),
                data_source=request.POST.get('data_source'),
                data_query={'field': request.POST.get('field', '')},
                chart_config={'type': request.POST.get('chart_type', '')},
                position={'x': 0, 'y': 0},
                size={'width': 2, 'height': 2},
                is_active=True
            )
            
            messages.success(request, f'✅ Widget "{widget.title}" created!')
            return redirect('bi_dashboard_edit', pk=dashboard.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'dashboard': dashboard,
        'widget_types': BIWidget.WIDGET_TYPES,
        'data_sources': ['sales', 'purchases', 'products', 'customers', 'inventory', 'expenses', 'budgets'],
    }
    return render(request, 'bi/widget_create.html', context)


@login_required
def bi_kpi_dashboard(request):
    """KPI Dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    kpis = BIKPI.objects.filter(is_active=True)
    for kpi in kpis:
        calculate_kpi(kpi)
    
    categories = BIKPI.KPI_CATEGORIES
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'kpis': kpis,
        'categories': categories,
    }
    return render(request, 'bi/kpi_dashboard.html', context)


@login_required
def bi_kpi_create(request):
    """Create KPI"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            kpi = BIKPI.objects.create(
                name=request.POST.get('name'),
                category=request.POST.get('category'),
                description=request.POST.get('description', ''),
                formula=request.POST.get('formula'),
                target=Decimal(request.POST.get('target', 0)),
                unit=request.POST.get('unit', '%'),
                created_by=request.user
            )
            
            messages.success(request, f'✅ KPI "{kpi.name}" created!')
            return redirect('bi_kpi_dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': BIKPI.KPI_CATEGORIES,
    }
    return render(request, 'bi/kpi_create.html', context)


@login_required
def bi_reports(request):
    """BI Reports list"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    reports = BIReport.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'reports': reports,
    }
    return render(request, 'bi/reports.html', context)


@login_required
def bi_report_generate(request, pk):
    """Generate BI report"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    report = get_object_or_404(BIReport, pk=pk)
    report.last_run = datetime.now()
    report.save()
    
    # Generate report data based on type
    if report.report_type == 'sales':
        data = get_sales_data(30)
    elif report.report_type == 'financial':
        data = get_financial_data()
    elif report.report_type == 'customer':
        data = get_customer_data(30)
    elif report.report_type == 'inventory':
        data = get_inventory_data()
    else:
        data = {'message': 'Report type not implemented yet'}
    
    messages.success(request, f'✅ Report "{report.name}" generated!')
    return redirect('bi_reports')


@login_required
def bi_analytics_api(request):
    """API endpoint for BI data"""
    data_type = request.GET.get('type', 'sales')
    days = int(request.GET.get('days', 30))
    
    if data_type == 'sales':
        data = get_sales_data(days)
    elif data_type == 'financial':
        data = get_financial_data()
    elif data_type == 'customer':
        data = get_customer_data(days)
    elif data_type == 'inventory':
        data = get_inventory_data()
    else:
        data = {'error': 'Invalid data type'}
    
    return JsonResponse({'success': True, 'data': data})


@login_required
def bi_insights(request):
    """View BI insights"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    insights = BIInsight.objects.all().order_by('-created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'insights': insights,
    }
    return render(request, 'bi/insights.html', context)


@login_required
def bi_forecast(request):
    """View forecasts"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    forecasts = BIForecast.objects.all().order_by('-created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'forecasts': forecasts,
    }
    return render(request, 'bi/forecast.html', context)