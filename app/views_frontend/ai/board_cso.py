"""Frontend views: ai/board_cso (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST
from ...models import *
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils.timezone import now
from django.contrib import messages
from ...models import CompanyInfo
from ...ai.ai_board_room import AIBoardRoom
from ...ai.ai_cso_tech import AICSOTechEngine


@login_required
@perm_required('view_board_room')
def ai_board_room_dashboard(request):
    """Main AI Board Room Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBoardMeeting, AIBoardMember, AIBoardAlert, AIBoardKPI
    
    # Run meeting if requested
    if request.GET.get('run') == 'true':
        try:
            board = AIBoardRoom()
            results = board.run_full_board_meeting()
            
            if results['success']:
                messages.success(
                    request,
                    f"🏢 Board Meeting Complete! "
                    f"Health: {results['overall_health']}/100 | "
                    f"Alerts: {results['alerts_created']} | "
                    f"Impact: Rs. {results['total_savings'] + results['total_revenue']:,.0f}"
                )
            else:
                messages.error(request, f"❌ Error: {results.get('error', 'Unknown')}")
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_board_room_dashboard')
    
    # Get latest meeting
    latest_meeting = AIBoardMeeting.objects.order_by('-meeting_date', '-created_at').first()
    
    # Get all members for latest
    if latest_meeting:
        members = latest_meeting.board_members.all().order_by('member_type')
    else:
        members = []
    
    # ==========================================
    # ✅ FIX: Base queryset PEHLE banao
    # ==========================================
    base_alerts = AIBoardAlert.objects.filter(is_resolved=False)
    
    # ✅ Stats from the FULL queryset (BEFORE the slice)
    total_alerts = base_alerts.count()
    critical_alerts = base_alerts.filter(severity='critical').count()
    high_alerts = base_alerts.filter(severity='high').count()
    medium_alerts = base_alerts.filter(severity='medium').count()
    
    # ✅ Now slice for display
    alerts = base_alerts.order_by('-created_at')[:15]
    
    # KPI history
    kpis = AIBoardKPI.objects.order_by('-date')[:30]
    
    # Chart data
    kpi_labels = [k.date.strftime('%d-%b') for k in reversed(list(kpis))]
    kpi_health = [k.overall_health for k in reversed(list(kpis))]
    kpi_revenue = [float(k.revenue) for k in reversed(list(kpis))]
    
    # Stats
    stats = {
        'total_meetings': AIBoardMeeting.objects.count(),
        'active_alerts': total_alerts,       # ✅ From base
        'critical_alerts': critical_alerts,  # ✅ From base
        'high_alerts': high_alerts,          # ✅ From base
        'medium_alerts': medium_alerts,      # ✅ From base
        'total_savings': AIBoardMeeting.objects.aggregate(
            total=Sum('total_potential_savings')
        )['total'] or 0,
        'total_revenue': AIBoardMeeting.objects.aggregate(
            total=Sum('total_potential_revenue')
        )['total'] or 0,
    }
    
    import json
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': latest_meeting,
        'members': members,
        'alerts': alerts,                # ✅ Sliced list for display
        'stats': stats,
        'kpi_labels': json.dumps(kpi_labels),
        'kpi_health': json.dumps(kpi_health),
        'kpi_revenue': json.dumps(kpi_revenue),
        'today': localdate(),
    }
    return render(request, 'ai/board_room_dashboard.html', context)


@login_required
@perm_required('view_board_room')
def ai_board_member_detail(request, member_type):
    """View individual board member report"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBoardMember
    
    # Get latest report for this member
    member = AIBoardMember.objects.filter(
        member_type=member_type
    ).order_by('-report_date', '-created_at').first()
    
    if not member:
        messages.warning(request, f"No report found for {member_type}. Run board meeting first.")
        return redirect('ai_board_room_dashboard')
    
    # History
    history = AIBoardMember.objects.filter(
        member_type=member_type
    ).order_by('-report_date')[:30]
    
    import json
    chart_labels = [h.report_date.strftime('%d-%b') for h in reversed(list(history))]
    chart_scores = [h.health_score for h in reversed(list(history))]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'member': member,
        'history': history,
        'chart_labels': json.dumps(chart_labels),
        'chart_scores': json.dumps(chart_scores),
    }
    return render(request, 'ai/board_member_detail.html', context)


@login_required
@perm_required('view_board_room')
def ai_board_meetings_list(request):
    """List all board meetings"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBoardMeeting
    
    meetings = AIBoardMeeting.objects.order_by('-meeting_date', '-created_at')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meetings': meetings,
    }
    return render(request, 'ai/board_meetings_list.html', context)


@login_required
@perm_required('view_board_room')
def ai_board_meeting_detail(request, pk):
    """View detailed board meeting"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBoardMeeting
    
    meeting = get_object_or_404(AIBoardMeeting, pk=pk)
    members = meeting.board_members.all().order_by('member_type')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': meeting,
        'members': members,
    }
    return render(request, 'ai/board_meeting_detail.html', context)


@login_required
@perm_required('view_board_room')
def ai_board_alerts(request):
    """View all board alerts"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBoardAlert
    
    alerts = AIBoardAlert.objects.all().order_by('-created_at')
    
    # Filters
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    source = request.GET.get('source', '')
    if source:
        alerts = alerts.filter(source=source)
    
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
        'selected_severity': severity,
        'selected_source': source,
        'selected_status': status,
    }
    return render(request, 'ai/board_alerts.html', context)


@login_required
@perm_required('view_board_room')
@require_POST
def ai_board_alert_resolve(request, pk):
    """Resolve a board alert"""
    
    from ...models import AIBoardAlert
    alert = get_object_or_404(AIBoardAlert, pk=pk)
    
    alert.is_resolved = True
    alert.resolved_at = now()
    alert.resolved_by = request.user
    alert.save()
    
    messages.success(request, '✅ Alert resolved!')
    return redirect('ai_board_alerts')


@login_required
@perm_required('view_board_room')
def ai_cso_tech_dashboard(request):
    """CSO Tech Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import (
        AIBugReport, AIPerformanceIssue, AIFeatureSuggestion,
        AISystemHealth, AISecurityLog
    )
    
    # Run analysis if requested
    if request.GET.get('run') == 'true':
        try:
            engine = AICSOTechEngine()
            report = engine.run_full_analysis()
            
            messages.success(
                request,
                f"💻 CSO Tech Analysis Complete! "
                f"Health: {report['health_score']}/100 | "
                f"Warnings: {len(report['warnings'])}"
            )
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
        
        return redirect('ai_cso_tech_dashboard')
    
    # Get latest system health
    latest_health = AISystemHealth.objects.order_by('-date').first()
    
    # Stats
    active_bugs = AIBugReport.objects.filter(status__in=['new', 'investigating'])
    performance_issues = AIPerformanceIssue.objects.filter(is_resolved=False)
    pending_features = AIFeatureSuggestion.objects.filter(status='pending')
    security_alerts = AISecurityLog.objects.filter(is_resolved=False)
    
    stats = {
        'system_health': latest_health.health_score if latest_health else 100,
        'active_bugs': active_bugs.count(),
        'critical_bugs': active_bugs.filter(severity='critical').count(),
        'performance_issues': performance_issues.count(),
        'pending_features': pending_features.count(),
        'security_alerts': security_alerts.count(),
    }
    
    # Recent items
    recent_bugs = active_bugs.order_by('-frequency')[:5]
    recent_issues = performance_issues.order_by('-priority')[:5]
    recent_features = pending_features.order_by('-roi_score')[:5]
    recent_security = security_alerts.order_by('-created_at')[:5]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'stats': stats,
        'latest_health': latest_health,
        'recent_bugs': recent_bugs,
        'recent_issues': recent_issues,
        'recent_features': recent_features,
        'recent_security': recent_security,
    }
    return render(request, 'ai/cso_tech_dashboard.html', context)


@login_required
@perm_required('view_board_room')
def ai_cso_tech_security(request):
    """Security Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AISecurityLog
    
    alerts = AISecurityLog.objects.all().order_by('-created_at')
    
    severity = request.GET.get('severity', '')
    if severity:
        alerts = alerts.filter(severity=severity)
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        alerts = alerts.filter(is_resolved=False)
    elif status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    
    # Stats - BEFORE slice
    stats = {
        'total': alerts.count(),
        'critical': alerts.filter(severity='critical').count(),
        'high': alerts.filter(severity='high').count(),
        'medium': alerts.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'alerts': alerts[:50],
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_security.html', context)


@login_required
@perm_required('view_board_room')
def ai_cso_tech_performance(request):
    """Performance Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIPerformanceIssue, AISystemHealth
    
    issues = AIPerformanceIssue.objects.all().order_by('-priority', '-created_at')
    health_records = AISystemHealth.objects.order_by('-date')[:30]
    
    # Stats
    stats = {
        'total_issues': issues.count(),
        'unresolved': issues.filter(is_resolved=False).count(),
        'critical': issues.filter(priority__gte=8, is_resolved=False).count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'issues': issues,
        'health_records': health_records,
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_performance.html', context)


@login_required
@perm_required('view_board_room')
def ai_cso_tech_bugs(request):
    """Bugs Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIBugReport
    
    bugs = AIBugReport.objects.all().order_by('-frequency', '-last_seen')
    
    status = request.GET.get('status', 'active')
    if status == 'active':
        bugs = bugs.filter(status__in=['new', 'investigating'])
    elif status == 'fixed':
        bugs = bugs.filter(status__in=['fixed', 'closed'])
    
    # Stats BEFORE slice
    stats = {
        'total': bugs.count(),
        'critical': bugs.filter(severity='critical').count(),
        'high': bugs.filter(severity='high').count(),
        'medium': bugs.filter(severity='medium').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'bugs': bugs[:50],
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_bugs.html', context)


@login_required
@perm_required('view_board_room')
def ai_cso_tech_features(request):
    """Feature Suggestions Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIFeatureSuggestion
    
    features = AIFeatureSuggestion.objects.all().order_by('-roi_score', '-created_at')
    
    status = request.GET.get('status', 'pending')
    if status:
        features = features.filter(status=status)
    
    stats = {
        'total': features.count(),
        'pending': features.filter(status='pending').count(),
        'in_progress': features.filter(status='in_progress').count(),
        'completed': features.filter(status='completed').count(),
    }
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'features': features,
        'stats': stats,
    }
    return render(request, 'ai/cso_tech_features.html', context)


@login_required
@perm_required('view_board_room')
def ai_cso_tech_system(request):
    """System Health Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AISystemHealth
    import json
    
    health_records = AISystemHealth.objects.order_by('-date')[:60]
    
    # Chart data
    labels = [h.date.strftime('%d-%b %I:%M %p') for h in reversed(list(health_records))]
    scores = [h.health_score for h in reversed(list(health_records))]
    memory = [float(h.memory_usage) for h in reversed(list(health_records))]
    disk = [float(h.disk_usage) for h in reversed(list(health_records))]
    
    # Latest
    latest = health_records.first()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'latest': latest,
        'records': health_records,
        'chart_labels': json.dumps(labels),
        'chart_scores': json.dumps(scores),
        'chart_memory': json.dumps(memory),
        'chart_disk': json.dumps(disk),
    }
    return render(request, 'ai/cso_tech_system.html', context)
