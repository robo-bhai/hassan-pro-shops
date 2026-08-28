from django.contrib import admin
from .models import *

@admin.register(ExecutiveProfile)
class ExecutiveProfileAdmin(admin.ModelAdmin):
    list_display = ('executive_id', 'title', 'executive_type', 'personal_email', 'security_clearance_level')
    search_fields = ('executive_id', 'title', 'personal_email')
    list_filter = ('executive_type', 'security_clearance_level')

@admin.register(StrategicObjective)
class StrategicObjectiveAdmin(admin.ModelAdmin):
    list_display = ('objective', 'quarter', 'year', 'priority', 'status', 'progress_percentage')
    list_filter = ('quarter', 'year', 'priority', 'status')

@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'risk_level', 'risk_score', 'status')
    list_filter = ('category', 'risk_level', 'status')

@admin.register(ExecutiveMeeting)
class ExecutiveMeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting_type', 'meeting_date', 'status')
    list_filter = ('meeting_type', 'status')

@admin.register(ExecutiveBriefing)
class ExecutiveBriefingAdmin(admin.ModelAdmin):
    list_display = ('executive', 'briefing_type', 'period_start', 'is_read')
    list_filter = ('briefing_type', 'is_read')