"""Bi models."""
from django.db import models
from django.contrib.auth.models import User

class BIDashboard(models.Model):
    """BI Dashboard configuration"""
    
    DASHBOARD_TYPES = [
        ('sales', '📊 Sales Dashboard'),
        ('financial', '💰 Financial Dashboard'),
        ('inventory', '📦 Inventory Dashboard'),
        ('customer', '👥 Customer Dashboard'),
        ('employee', '👔 Employee Dashboard'),
        ('custom', '🎯 Custom Dashboard'),
    ]
    
    name = models.CharField(max_length=200)
    dashboard_type = models.CharField(max_length=20, choices=DASHBOARD_TYPES)
    description = models.TextField(blank=True, null=True)
    layout = models.JSONField(default=dict, help_text="Dashboard layout configuration")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_dashboards')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI Dashboards"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_dashboard_type_display()})"


class BIWidget(models.Model):
    """BI Dashboard widgets"""
    
    WIDGET_TYPES = [
        ('chart', '📈 Chart'),
        ('kpi', '🎯 KPI'),
        ('table', '📋 Table'),
        ('pie', '🥧 Pie Chart'),
        ('bar', '📊 Bar Chart'),
        ('line', '📉 Line Chart'),
        ('metric', '📊 Metric'),
        ('heatmap', '🔥 Heat Map'),
    ]
    
    dashboard = models.ForeignKey(BIDashboard, on_delete=models.CASCADE, related_name='widgets')
    title = models.CharField(max_length=200)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    data_source = models.CharField(max_length=100, help_text="Model or query name")
    data_query = models.JSONField(default=dict, help_text="Query parameters")
    chart_config = models.JSONField(default=dict, help_text="Chart configuration")
    position = models.JSONField(default=dict, help_text="Widget position")
    size = models.JSONField(default=dict, help_text="Widget size")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI Widgets"
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.title} ({self.get_widget_type_display()})"


class BIReport(models.Model):
    """BI Reports configuration"""
    
    REPORT_TYPES = [
        ('sales', '📊 Sales Report'),
        ('financial', '💰 Financial Report'),
        ('inventory', '📦 Inventory Report'),
        ('customer', '👥 Customer Report'),
        ('employee', '👔 Employee Report'),
        ('custom', '🎯 Custom Report'),
    ]
    
    REPORT_FORMATS = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('html', 'HTML'),
    ]
    
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField(blank=True, null=True)
    format = models.CharField(max_length=10, choices=REPORT_FORMATS, default='pdf')
    data_source = models.CharField(max_length=100)
    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)
    schedule = models.CharField(max_length=50, blank=True, null=True, help_text="Daily, Weekly, Monthly")
    recipients = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "BI Reports"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class BIKPI(models.Model):
    """Key Performance Indicators"""
    
    KPI_CATEGORIES = [
        ('sales', '📊 Sales'),
        ('financial', '💰 Financial'),
        ('customer', '👥 Customer'),
        ('operational', '⚙️ Operational'),
        ('employee', '👔 Employee'),
        ('quality', '✅ Quality'),
    ]
    
    KPI_STATUS = [
        ('on_track', '✅ On Track'),
        ('warning', '⚠️ Warning'),
        ('critical', '🔴 Critical'),
        ('achieved', '🎉 Achieved'),
    ]
    
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=KPI_CATEGORIES)
    description = models.TextField(blank=True, null=True)
    formula = models.TextField(help_text="KPI calculation formula")
    target = models.DecimalField(max_digits=15, decimal_places=2)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unit = models.CharField(max_length=50, default='%')
    status = models.CharField(max_length=20, choices=KPI_STATUS, default='on_track')
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    dashboard = models.ForeignKey(BIDashboard, on_delete=models.SET_NULL, null=True, blank=True, related_name='kpis')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "BI KPIs"
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"
    
    def update_progress(self):
        if self.target > 0:
            self.progress = (self.current_value / self.target) * 100
            if self.progress >= 100:
                self.status = 'achieved'
            elif self.progress >= 80:
                self.status = 'on_track'
            elif self.progress >= 50:
                self.status = 'warning'
            else:
                self.status = 'critical'
        self.save()


class BIAlert(models.Model):
    """BI Alerts and notifications"""
    
    ALERT_TYPES = [
        ('kpi', '📊 KPI Alert'),
        ('trend', '📈 Trend Alert'),
        ('anomaly', '🔍 Anomaly Detection'),
        ('forecast', '🔮 Forecast Alert'),
        ('threshold', '📊 Threshold Alert'),
    ]
    
    name = models.CharField(max_length=200)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    description = models.TextField()
    condition = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    is_triggered = models.BooleanField(default=False)
    triggered_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_alerts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Alerts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_alert_type_display()})"


class BIInsight(models.Model):
    """AI-generated business insights"""
    
    INSIGHT_TYPES = [
        ('opportunity', '💡 Opportunity'),
        ('risk', '⚠️ Risk'),
        ('trend', '📈 Trend'),
        ('anomaly', '🔍 Anomaly'),
        ('recommendation', '🎯 Recommendation'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    data = models.JSONField(default=dict)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_actioned = models.BooleanField(default=False)
    actioned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Insights"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.get_insight_type_display()})"


class BIForecast(models.Model):
    """Business forecasting"""
    
    FORECAST_TYPES = [
        ('sales', '📊 Sales Forecast'),
        ('revenue', '💰 Revenue Forecast'),
        ('demand', '📦 Demand Forecast'),
        ('profit', '💵 Profit Forecast'),
    ]
    
    name = models.CharField(max_length=200)
    forecast_type = models.CharField(max_length=20, choices=FORECAST_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    forecasted_value = models.DecimalField(max_digits=15, decimal_places=2)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    methodology = models.CharField(max_length=100)
    data = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bi_forecasts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "BI Forecasts"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_forecast_type_display()})"
