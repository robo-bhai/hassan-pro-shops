"""Frontend views: audit."""
from ...security.permissions import perm_required
from ...models import *
from reportlab.lib.units import inch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import date
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import HttpResponse
from io import BytesIO
from ...models import CompanyInfo, Employee, Department, AuditPlan, AuditFinding, AuditReport, AuditTrail, InternalControl
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from django.db import models


@login_required
@perm_required('view_audit_log')
def audit_dashboard(request):
    """Audit dashboard"""
    total_plans = AuditPlan.objects.count()
    active_plans = AuditPlan.objects.filter(status__in=['approved', 'in_progress']).count()
    completed_plans = AuditPlan.objects.filter(status='completed').count()
    
    total_findings = AuditFinding.objects.count()
    open_findings = AuditFinding.objects.filter(status='open').count()
    critical_findings = AuditFinding.objects.filter(severity='critical', status='open').count()
    
    controls = InternalControl.objects.count()
    active_controls = InternalControl.objects.filter(status='active').count()
    
    recent_plans = AuditPlan.objects.order_by('-created_at')[:5]
    recent_findings = AuditFinding.objects.order_by('-created_at')[:5]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_plans': total_plans,
        'active_plans': active_plans,
        'completed_plans': completed_plans,
        'total_findings': total_findings,
        'open_findings': open_findings,
        'critical_findings': critical_findings,
        'controls': controls,
        'active_controls': active_controls,
        'recent_plans': recent_plans,
        'recent_findings': recent_findings,
    }
    return render(request, 'audit/dashboard.html', context)


@login_required
@perm_required('view_audit_log')
def audit_plan_list(request):
    """List all audit plans"""
    plans = AuditPlan.objects.select_related('lead_auditor', 'department').all()
    
    search = request.GET.get('search', '')
    if search:
        plans = plans.filter(
            Q(name__icontains=search) |
            Q(plan_no__icontains=search)
        )
    
    type_filter = request.GET.get('type', '')
    if type_filter:
        plans = plans.filter(audit_type=type_filter)
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        plans = plans.filter(status=status_filter)
    
    paginator = Paginator(plans, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'type': type_filter,
        'status': status_filter,
        'audit_types': AuditPlan.AUDIT_TYPES,
        'status_choices': AuditPlan.AUDIT_STATUS,
    }
    return render(request, 'audit/plan_list.html', context)


@login_required
@perm_required('manage_system')
def audit_plan_create(request):
    """Create new audit plan"""
    if request.method == 'POST':
        try:
            plan = AuditPlan.objects.create(
                name=request.POST.get('name'),
                audit_type=request.POST.get('audit_type'),
                description=request.POST.get('description', ''),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                scope=request.POST.get('scope'),
                criteria=request.POST.get('criteria'),
                lead_auditor_id=request.POST.get('lead_auditor') or None,
                department_id=request.POST.get('department') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='draft'
            )
            
            # Add team members
            team_ids = request.POST.getlist('team_members[]')
            if team_ids:
                plan.audit_team.set(team_ids)
            
            messages.success(request, f'✅ Audit Plan "{plan.name}" created!')
            return redirect('audit_plan_detail', pk=plan.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    employees = Employee.objects.filter(status='active')
    departments = Department.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employees': employees,
        'departments': departments,
        'audit_types': AuditPlan.AUDIT_TYPES,
    }
    return render(request, 'audit/plan_create.html', context)


@login_required
@perm_required('view_audit_log')
def audit_plan_detail(request, pk):
    """Audit plan detail"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    checklists = plan.checklists.all()
    findings = plan.findings.all()
    schedules = plan.schedules.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'checklists': checklists,
        'findings': findings,
        'schedules': schedules,
        'progress': plan.get_progress(),
    }
    return render(request, 'audit/plan_detail.html', context)


@login_required
@perm_required('manage_system')
def audit_plan_edit(request, pk):
    """Edit audit plan"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    
    if plan.status != 'draft':
        messages.error(request, '❌ Only draft plans can be edited!')
        return redirect('audit_plan_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            plan.name = request.POST.get('name')
            plan.audit_type = request.POST.get('audit_type')
            plan.description = request.POST.get('description', '')
            plan.start_date = request.POST.get('start_date')
            plan.end_date = request.POST.get('end_date')
            plan.scope = request.POST.get('scope')
            plan.criteria = request.POST.get('criteria')
            plan.lead_auditor_id = request.POST.get('lead_auditor') or None
            plan.department_id = request.POST.get('department') or None
            plan.notes = request.POST.get('notes', '')
            plan.save()
            
            # Update team
            plan.audit_team.clear()
            team_ids = request.POST.getlist('team_members[]')
            if team_ids:
                plan.audit_team.set(team_ids)
            
            messages.success(request, f'✅ Audit Plan "{plan.name}" updated!')
            return redirect('audit_plan_detail', pk=plan.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    employees = Employee.objects.filter(status='active')
    departments = Department.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'employees': employees,
        'departments': departments,
        'audit_types': AuditPlan.AUDIT_TYPES,
    }
    return render(request, 'audit/plan_edit.html', context)


@login_required
@perm_required('manage_system')
def audit_plan_delete(request, pk):
    """Delete audit plan"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    
    if plan.status != 'draft':
        messages.error(request, '❌ Only draft plans can be deleted!')
        return redirect('audit_plan_detail', pk=pk)
    
    if request.method == 'POST':
        plan.delete()
        messages.success(request, f'🗑️ Audit Plan "{plan.name}" deleted!')
        return redirect('audit_plan_list')
    
    return redirect('audit_plan_detail', pk=pk)


@login_required
@perm_required('manage_system')
def audit_plan_start(request, pk):
    """Start audit plan"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    plan.status = 'in_progress'
    plan.actual_start_date = date.today()
    plan.save()
    messages.success(request, f'✅ Audit "{plan.name}" started!')
    return redirect('audit_plan_detail', pk=pk)


@login_required
@perm_required('manage_system')
def audit_plan_complete(request, pk):
    """Complete audit plan"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    plan.status = 'completed'
    plan.actual_end_date = date.today()
    plan.save()
    messages.success(request, f'✅ Audit "{plan.name}" completed!')
    return redirect('audit_plan_detail', pk=pk)


@login_required
@perm_required('view_audit_log', post='manage_system')
def audit_findings(request, pk):
    """View and add findings for audit plan"""
    plan = get_object_or_404(AuditPlan, pk=pk)
    findings = plan.findings.all()
    
    if request.method == 'POST':
        try:
            finding = AuditFinding.objects.create(
                audit_plan=plan,
                title=request.POST.get('title'),
                description=request.POST.get('description'),
                severity=request.POST.get('severity'),
                recommendation=request.POST.get('recommendation'),
                evidence=request.POST.get('evidence', ''),
                assigned_to_id=request.POST.get('assigned_to') or None,
                target_completion_date=request.POST.get('target_completion_date') or None,
                created_by=request.user
            )
            
            if request.FILES.get('attachment'):
                finding.attachment = request.FILES['attachment']
                finding.save()
            
            messages.success(request, f'✅ Finding "{finding.title}" added!')
            return redirect('audit_findings', pk=plan.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    employees = Employee.objects.filter(status='active')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'plan': plan,
        'findings': findings,
        'employees': employees,
        'severity_choices': AuditFinding.SEVERITY_CHOICES,
    }
    return render(request, 'audit/findings.html', context)


@login_required
@perm_required('view_audit_log')
def audit_finding_detail(request, pk):
    """View finding detail"""
    finding = get_object_or_404(AuditFinding, pk=pk)
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'finding': finding,
    }
    return render(request, 'audit/finding_detail.html', context)


@login_required
@perm_required('manage_system')
def audit_finding_resolve(request, pk):
    """Resolve audit finding"""
    finding = get_object_or_404(AuditFinding, pk=pk)
    finding.mark_resolved(request.user)
    messages.success(request, f'✅ Finding "{finding.title}" resolved!')
    return redirect('audit_findings', pk=finding.audit_plan.pk)


@login_required
@perm_required('view_audit_log')
def audit_report_view(request, pk):
    """View audit report"""
    report = get_object_or_404(AuditReport, pk=pk)
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report': report,
    }
    return render(request, 'audit/report_view.html', context)


@login_required
@perm_required('view_audit_log')
def audit_report_pdf(request, pk):
    """Generate audit report PDF"""
    report = get_object_or_404(AuditReport, pk=pk)
    
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    company = CompanyInfo.objects.first()
    company_name = company.name if company else "ERP System"
    
    story.append(Paragraph(f"<b>{company_name}</b>", styles['Heading1']))
    story.append(Paragraph("Audit Report", styles['Heading2']))
    story.append(Paragraph(f"Report No: {report.report_no}", styles['Normal']))
    story.append(Paragraph(f"Title: {report.title}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    story.append(Paragraph("<b>Executive Summary</b>", styles['Heading3']))
    story.append(Paragraph(report.executive_summary, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("<b>Findings Summary</b>", styles['Heading3']))
    story.append(Paragraph(report.findings_summary, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("<b>Recommendations</b>", styles['Heading3']))
    story.append(Paragraph(report.recommendations, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("<b>Conclusion</b>", styles['Heading3']))
    story.append(Paragraph(report.conclusion, styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Audit_Report_{report.report_no}.pdf"'
    return response


@login_required
@perm_required('view_audit_log')
def audit_trails(request):
    """View audit trails"""
    trails = AuditTrail.objects.select_related('user').order_by('-timestamp')
    
    model_name = request.GET.get('model', '')
    if model_name:
        trails = trails.filter(model_name=model_name)
    
    action = request.GET.get('action', '')
    if action:
        trails = trails.filter(action=action)
    
    paginator = Paginator(trails, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Get all unique model names for filter
    models = AuditTrail.objects.values_list('model_name', flat=True).distinct()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'model_name': model_name,
        'action': action,
        'action_choices': AuditTrail.ACTION_TYPES,
        'models': models,
    }
    return render(request, 'audit/trails.html', context)


@login_required
@perm_required('view_audit_log')
def internal_controls(request):
    """View internal controls"""
    controls = InternalControl.objects.select_related('department', 'responsible_person')
    
    search = request.GET.get('search', '')
    if search:
        controls = controls.filter(
            Q(name__icontains=search) |
            Q(control_no__icontains=search)
        )
    
    category = request.GET.get('category', '')
    if category:
        controls = controls.filter(category=category)
    
    status = request.GET.get('status', '')
    if status:
        controls = controls.filter(status=status)
    
    paginator = Paginator(controls, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'category': category,
        'status': status,
        'categories': InternalControl.CONTROL_CATEGORIES,
        'status_choices': InternalControl.CONTROL_STATUS,
        'control_types': InternalControl.CONTROL_TYPES,
    }
    return render(request, 'audit/controls.html', context)


@login_required
@perm_required('manage_system')
def internal_control_create(request):
    """Create internal control"""
    if request.method == 'POST':
        try:
            control = InternalControl.objects.create(
                name=request.POST.get('name'),
                category=request.POST.get('category'),
                control_type=request.POST.get('control_type'),
                description=request.POST.get('description'),
                risk_level=request.POST.get('risk_level'),
                likelihood=request.POST.get('likelihood'),
                impact=request.POST.get('impact'),
                implementation_date=request.POST.get('implementation_date'),
                next_review_date=request.POST.get('next_review_date') or None,
                department_id=request.POST.get('department') or None,
                responsible_person_id=request.POST.get('responsible_person') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='active'
            )
            
            if request.FILES.get('document'):
                control.document = request.FILES['document']
                control.save()
            
            messages.success(request, f'✅ Internal Control "{control.name}" created!')
            return redirect('internal_controls')
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    employees = Employee.objects.filter(status='active')
    departments = Department.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'employees': employees,
        'departments': departments,
        'categories': InternalControl.CONTROL_CATEGORIES,
        'control_types': InternalControl.CONTROL_TYPES,
    }
    return render(request, 'audit/internal_control_create.html', context)


@login_required
@perm_required('view_audit_log')
def internal_control_detail(request, pk):
    """View internal control detail"""
    control = get_object_or_404(InternalControl, pk=pk)
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'control': control,
    }
    return render(request, 'audit/control_detail.html', context)
