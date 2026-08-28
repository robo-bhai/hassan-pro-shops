from django.urls import path
from . import views

app_name = 'ceo'

urlpatterns = [
    # Dashboard
    path('', views.executive_dashboard, name='dashboard'),
    path('dashboard/', views.executive_dashboard, name='executive_dashboard'),
    
    # Strategy
    path('strategy/objectives/', views.strategic_objectives, name='strategic_objectives'),
    path('strategy/risk/', views.risk_management, name='risk_management'),
    
    # Operations
    path('meetings/', views.executive_meetings, name='executive_meetings'),
    
    # Reports
    path('briefings/', views.executive_briefings, name='executive_briefings'),
    path('analytics/financial/', views.financial_analytics, name='financial_analytics'),
    
    # Settings
    path('settings/', views.ceo_settings, name='ceo_settings'),
    
    # API
    path('api/metrics/', views.api_realtime_metrics, name='api_metrics'),
    path('api/audit-logs/', views.api_audit_logs, name='api_audit_logs'),
]