from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, Avg
from datetime import datetime, timedelta
from app.models import (
    CompanyInfo, TestProject, TestSuite, TestCase,
    TestExecution, Bug, TestPlan, TestReport
)
from django.contrib.auth.models import User  # ✅ ADD THIS

import re
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme


# ----------------------------------------------------------------------------
# UI helpers (labels without emoji, chart data)
# ----------------------------------------------------------------------------
def _label(display):
    """'🔴 Critical' -> 'Critical' (drops the leading emoji for a cleaner UI)."""
    return re.sub(r'^[^\w]+', '', str(display)).strip()


def _clean_choices(choices):
    return [(k, _label(v)) for k, v in choices]


def _pct(part, whole):
    return round(part * 100 / whole) if whole else 0


def _donut(segments):
    """[(value, '#hex'), ...] -> CSS conic-gradient string (grey ring when empty)."""
    total = sum(v for v, _ in segments)
    if not total:
        return 'conic-gradient(#e9ecef 0 100%)'
    parts, start = [], 0.0
    for value, color in segments:
        if not value:
            continue
        end = start + value * 100.0 / total
        parts.append('%s %.2f%% %.2f%%' % (color, start, end))
        start = end
    return 'conic-gradient(' + ', '.join(parts) + ')'


def _count_by(qs, field):
    """{value: count} for one field (ignores the model's default ordering)."""
    return dict(qs.order_by().values_list(field).annotate(n=Count('id')))


def _decorate_bug(b):
    b.sev_label = _label(b.get_severity_display())
    b.status_label = _label(b.get_status_display())
    return b


def _decorate_case(c):
    c.type_label = _label(c.get_test_type_display())
    c.priority_label = _label(c.get_priority_display())
    c.status_label = _label(c.get_status_display())
    return c


def _query_string(request):
    qs = request.GET.copy()
    qs.pop('page', None)
    return qs.urlencode()


def _deny(request):
    messages.error(request, 'Access denied!')
    return redirect('dashboard')


@login_required
def test_plan_list(request):
    """List test plans"""
    if not request.user.is_superuser:
        return _deny(request)

    plans = list(TestPlan.objects.select_related('project', 'created_by').order_by('-created_at', '-id'))
    for p in plans:
        p.status_label = _label(p.get_status_display())

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'test_plans': plans,
    }
    return render(request, 'testing/test_plan.html', context)


@login_required
def test_plan_create(request):
    """Create test plan"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            plan = TestPlan.objects.create(
                name=request.POST.get('name'),
                project_id=request.POST.get('project'),
                description=request.POST.get('description'),
                test_scope=request.POST.get('test_scope'),
                test_strategy=request.POST.get('test_strategy'),
                resources=request.POST.get('resources', ''),
                schedule=request.POST.get('schedule', ''),
                status=request.POST.get('status', 'draft'),
                created_by=request.user
            )
            messages.success(request, f'✅ Test plan "{plan.name}" created!')
            return redirect('test_plan_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    projects = TestProject.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
        'status_choices': TestPlan.STATUS_CHOICES,
    }
    return render(request, 'testing/test_plan_create.html', context)


@login_required
def test_plan_detail(request, pk):
    """Test plan detail"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    plan = get_object_or_404(TestPlan, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'test_plan': plan,
    }
    return render(request, 'testing/test_plan_detail.html', context)


@login_required
def test_dashboard(request):
    """Testing dashboard"""
    if not request.user.is_superuser:
        return _deny(request)

    tc = _count_by(TestCase.objects, 'status')
    bs = _count_by(Bug.objects, 'status')
    bsev = _count_by(Bug.objects, 'severity')

    total_tests = sum(tc.values())
    passed, failed = tc.get('passed', 0), tc.get('failed', 0)
    blocked, in_progress = tc.get('blocked', 0), tc.get('in_progress', 0)
    other = max(total_tests - passed - failed - blocked - in_progress, 0)
    executed = passed + failed + blocked
    pass_rate = _pct(passed, executed)

    total_bugs = sum(bs.values())
    b_open = bs.get('new', 0) + bs.get('assigned', 0) + bs.get('reopened', 0)
    b_prog = bs.get('in_progress', 0)
    b_resolved = bs.get('fixed', 0) + bs.get('verified', 0)
    b_closed = bs.get('closed', 0) + bs.get('duplicate', 0) + bs.get('won_fix', 0)
    open_bugs = b_open + b_prog
    resolved_bugs = b_resolved + b_closed

    test_groups = [
        {'label': 'Passed', 'n': passed, 'color': '#2f9e44'},
        {'label': 'Failed', 'n': failed, 'color': '#e03131'},
        {'label': 'Blocked', 'n': blocked, 'color': '#f08c00'},
        {'label': 'In progress', 'n': in_progress, 'color': '#1c7ed6'},
        {'label': 'Not run', 'n': other, 'color': '#ced4da'},
    ]
    bug_groups = [
        {'label': 'Open', 'n': b_open, 'color': '#e03131'},
        {'label': 'In progress', 'n': b_prog, 'color': '#1c7ed6'},
        {'label': 'Fixed / verified', 'n': b_resolved, 'color': '#7048e8'},
        {'label': 'Closed', 'n': b_closed, 'color': '#2f9e44'},
    ]
    severity_groups = [
        {'label': 'Critical', 'n': bsev.get('critical', 0), 'color': '#c2255c'},
        {'label': 'Major', 'n': bsev.get('major', 0), 'color': '#f08c00'},
        {'label': 'Minor', 'n': bsev.get('minor', 0), 'color': '#1c7ed6'},
        {'label': 'Trivial', 'n': bsev.get('trivial', 0), 'color': '#868e96'},
    ]
    for g in severity_groups:
        g['pct'] = _pct(g['n'], total_bugs)

    # bugs reported per day, last 7 days
    today = datetime.now().date()
    start = today - timedelta(days=6)
    rows = (Bug.objects.filter(reported_at__date__gte=start)
            .annotate(d=TruncDate('reported_at')).order_by().values('d').annotate(n=Count('id')))
    by_day = {r['d']: r['n'] for r in rows}
    peak = max(by_day.values(), default=0)
    bug_trend = []
    for i in range(7):
        d = start + timedelta(days=i)
        n = by_day.get(d, 0)
        bug_trend.append({'label': d.strftime('%a'), 'n': n,
                          'h': max(6, round(n * 100 / peak)) if peak else 6})

    recent_bugs = [_decorate_bug(b) for b in Bug.objects.select_related('reported_by').order_by('-reported_at')[:8]]
    recent_executions = list(TestExecution.objects.select_related('test_case', 'executed_by').order_by('-started_at')[:8])
    for e in recent_executions:
        e.status_label = _label(e.get_status_display())

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_projects': TestProject.objects.count(),
        'total_suites': TestSuite.objects.count(),
        'total_tests': total_tests, 'total_bugs': total_bugs,
        'passed': passed, 'failed': failed, 'blocked': blocked, 'in_progress': in_progress,
        'executed': executed, 'pass_rate': pass_rate,
        'critical_bugs': bsev.get('critical', 0), 'major_bugs': bsev.get('major', 0),
        'minor_bugs': bsev.get('minor', 0), 'trivial_bugs': bsev.get('trivial', 0),
        'open_bugs': open_bugs, 'resolved_bugs': resolved_bugs, 'resolve_rate': _pct(resolved_bugs, total_bugs),
        'test_groups': test_groups, 'bug_groups': bug_groups, 'severity_groups': severity_groups,
        'test_donut': _donut([(g['n'], g['color']) for g in test_groups]),
        'bug_donut': _donut([(g['n'], g['color']) for g in bug_groups]),
        'bug_trend': bug_trend,
        'recent_bugs': recent_bugs, 'recent_executions': recent_executions,
    }
    return render(request, 'testing/dashboard.html', context)


@login_required
def test_project_list(request):
    """List test projects (with per-project pass rate)"""
    if not request.user.is_superuser:
        return _deny(request)

    projects = list(TestProject.objects.annotate(
        suite_count=Count('suites', distinct=True),
        case_count=Count('suites__cases', distinct=True),
        passed_count=Count('suites__cases', filter=Q(suites__cases__status='passed'), distinct=True),
        failed_count=Count('suites__cases', filter=Q(suites__cases__status='failed'), distinct=True),
    ).order_by('-created_at', '-id'))
    for p in projects:
        p.pass_rate = _pct(p.passed_count, p.case_count)
        p.fail_rate = _pct(p.failed_count, p.case_count)
        p.suite_list = list(p.suites.all().order_by('name')[:5])

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
    }
    return render(request, 'testing/projects.html', context)


@login_required
def test_suite_detail(request, pk):
    """Suite overview with its test cases"""
    if not request.user.is_superuser:
        return _deny(request)

    suite = get_object_or_404(TestSuite.objects.select_related('project'), pk=pk)
    cases = [_decorate_case(c) for c in suite.cases.order_by('-created_at', '-id')]
    total = len(cases)
    passed = sum(1 for c in cases if c.status == 'passed')
    failed = sum(1 for c in cases if c.status == 'failed')
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suite': suite, 'cases': cases,
        'stats': {'total': total, 'passed': passed, 'failed': failed, 'pass_rate': _pct(passed, total)},
    }
    return render(request, 'testing/suite_detail.html', context)


@login_required
def test_project_create(request):
    """Create test project"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            project = TestProject.objects.create(
                name=request.POST.get('name'),
                description=request.POST.get('description', ''),
                version=request.POST.get('version'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date') or None,
                created_by=request.user
            )
            messages.success(request, f'✅ Test project "{project.name}" created!')
            return redirect('test_project_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
    }
    return render(request, 'testing/project_create.html', context)


@login_required
def test_suite_create(request, project_id):
    """Create test suite"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    project = get_object_or_404(TestProject, pk=project_id)
    
    if request.method == 'POST':
        try:
            suite = TestSuite.objects.create(
                project=project,
                name=request.POST.get('name'),
                description=request.POST.get('description', '')
            )
            messages.success(request, f'✅ Test suite "{suite.name}" created!')
            return redirect('test_project_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'project': project,
    }
    return render(request, 'testing/suite_create.html', context)


@login_required
def test_case_list(request, suite_id=None):
    """List test cases (filters + KPI strip)"""
    if not request.user.is_superuser:
        return _deny(request)

    if suite_id:
        suite = get_object_or_404(TestSuite.objects.select_related('project'), pk=suite_id)
        base = suite.cases.all()
    else:
        suite = None
        base = TestCase.objects.all()

    sc = _count_by(base, 'status')
    total = sum(sc.values())
    kpi = {'total': total, 'passed': sc.get('passed', 0), 'failed': sc.get('failed', 0),
           'blocked': sc.get('blocked', 0)}
    kpi['pass_rate'] = _pct(kpi['passed'], total)

    cases = base.select_related('suite', 'suite__project', 'executed_by').order_by('-created_at', '-id')
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    test_type = request.GET.get('type', '')
    if search:
        cases = cases.filter(Q(title__icontains=search) | Q(description__icontains=search))
    if status:
        cases = cases.filter(status=status)
    if priority:
        cases = cases.filter(priority=priority)
    if test_type:
        cases = cases.filter(test_type=test_type)

    paginator = Paginator(cases, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    for c in page_obj:
        _decorate_case(c)

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj, 'suite': suite, 'kpi': kpi, 'total_count': paginator.count,
        'search': search, 'status': status, 'priority': priority, 'test_type': test_type,
        'status_choices': _clean_choices(TestCase.STATUS_CHOICES),
        'priority_choices': _clean_choices(TestCase.PRIORITY_CHOICES),
        'type_choices': _clean_choices(TestCase.TYPE_CHOICES),
        'query_string': _query_string(request),
    }
    return render(request, 'testing/cases.html', context)


@login_required
def test_case_create(request, suite_id):
    """Create test case"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    suite = get_object_or_404(TestSuite, pk=suite_id)
    
    if request.method == 'POST':
        try:
            test_case = TestCase.objects.create(
                suite=suite,
                title=request.POST.get('title'),
                description=request.POST.get('description'),
                test_type=request.POST.get('test_type'),
                priority=request.POST.get('priority'),
                pre_conditions=request.POST.get('pre_conditions', ''),
                test_steps=request.POST.getlist('steps[]'),
                expected_result=request.POST.get('expected_result'),
                is_automated=request.POST.get('is_automated') == 'on',
                created_by=request.user,
                status='draft'
            )
            messages.success(request, f'✅ Test case "{test_case.title}" created!')
            return redirect('test_case_list', suite_id=suite.id)
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'suite': suite,
        'test_types': TestCase.TYPE_CHOICES,
        'priority_choices': TestCase.PRIORITY_CHOICES,
    }
    return render(request, 'testing/case_create.html', context)


@login_required
def test_case_execute(request, pk):
    """Execute test case"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    test_case = get_object_or_404(TestCase, pk=pk)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        execution = TestExecution.objects.create(
            test_case=test_case,
            executed_by=request.user,
            status=status,
            notes=notes,
            results={'steps': request.POST.getlist('step_results[]')}
        )
        
        # Update test case status
        test_case.status = status
        test_case.executed_by = request.user
        test_case.executed_at = timezone.now()
        test_case.actual_result = request.POST.get('actual_result', '')
        test_case.save()
        
        # If failed, create bug
        if status == 'failed':
            messages.warning(request, '⚠️ Test failed! Please report the bug.')
            return redirect('%s?test_case=%s' % (reverse('bug_create'), test_case.pk))
        
        messages.success(request, f'✅ Test case executed with status: {status}')
        return redirect('test_case_list')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'test_case': test_case,
        'status_choices': TestCase.STATUS_CHOICES,
    }
    return render(request, 'testing/case_execute.html', context)


@login_required
def bug_list(request):
    """List bugs (KPI strip, filters, detail sheet)"""
    if not request.user.is_superuser:
        return _deny(request)

    bs = _count_by(Bug.objects, 'status')
    sev = _count_by(Bug.objects, 'severity')
    kpi = {k: bs.get(k, 0) for k in ('new', 'in_progress', 'reopened', 'fixed', 'closed')}
    kpi['critical'] = sev.get('critical', 0)

    bugs = Bug.objects.select_related('test_case', 'assigned_to', 'reported_by').order_by('-reported_at', '-id')

    status = request.GET.get('status', '')
    if status:
        bugs = bugs.filter(status=status)
    severity = request.GET.get('severity', '')
    if severity:
        bugs = bugs.filter(severity=severity)
    search = request.GET.get('search', '').strip()
    if search:
        q = Q(title__icontains=search) | Q(description__icontains=search) | Q(module__icontains=search)
        if search.lstrip('#').isdigit():
            q |= Q(pk=int(search.lstrip('#')))
        bugs = bugs.filter(q)

    paginator = Paginator(bugs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    for b in page_obj:
        _decorate_bug(b)

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj, 'total_count': paginator.count, 'kpi': kpi,
        'status': status, 'severity': severity, 'search': search,
        'status_choices': _clean_choices(Bug.STATUS_CHOICES),
        'severity_choices': _clean_choices(Bug.SEVERITY_CHOICES),
        'query_string': _query_string(request),
    }
    return render(request, 'testing/bugs.html', context)


@login_required
def bug_create(request):
    """Create bug report"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            bug = Bug.objects.create(
                title=request.POST.get('title'),
                description=request.POST.get('description'),
                severity=request.POST.get('severity'),
                module=request.POST.get('module', ''),
                steps_to_reproduce=request.POST.get('steps_to_reproduce'),
                actual_result=request.POST.get('actual_result'),
                expected_result=request.POST.get('expected_result'),
                browser=request.POST.get('browser', ''),
                os=request.POST.get('os', ''),
                device=request.POST.get('device', ''),
                assigned_to_id=request.POST.get('assigned_to') or None,
                reported_by=request.user,
                test_case_id=request.POST.get('test_case') or None,
                status='new'
            )
            
            if request.FILES.get('screenshot'):
                bug.screenshot = request.FILES['screenshot']
                bug.save()
            if request.FILES.get('attachment'):
                bug.attachment = request.FILES['attachment']
                bug.save()
            
            messages.success(request, f'✅ Bug reported: {bug.title}')
            return redirect('bug_list')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'severity_choices': Bug.SEVERITY_CHOICES,
        'test_cases': TestCase.objects.order_by('title'),
        'users': User.objects.filter(is_active=True).order_by('username'),
        'selected_case': request.GET.get('test_case', ''),
    }
    return render(request, 'testing/bug_create.html', context)


@login_required
def bug_update_status(request, pk):
    """Update bug status (POST only; returns to the page the user came from)"""
    if not request.user.is_superuser:
        return _deny(request)

    bug = get_object_or_404(Bug, pk=pk)
    back = request.META.get('HTTP_REFERER')
    if not back or not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = reverse('bug_list')

    if request.method != 'POST':
        return redirect(back)

    status = request.POST.get('status')
    if status not in dict(Bug.STATUS_CHOICES):
        messages.error(request, 'Invalid status.')
        return redirect(back)

    bug.status = status
    now = timezone.now()
    if status == 'fixed':
        bug.fixed_at = now
    elif status == 'verified':
        bug.verified_at = now
    elif status == 'closed':
        bug.closed_at = now
    elif status == 'reopened':
        bug.closed_at = None
    bug.save()
    messages.success(request, 'Bug #%s is now "%s".' % (bug.pk, _label(bug.get_status_display())))
    return redirect(back)


@login_required
def test_report_generate(request):
    """Generate test report"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        project_id = request.POST.get('project')
        project = get_object_or_404(TestProject, pk=project_id)
        
        # Get all test cases in project
        cases = TestCase.objects.filter(suite__project=project)
        
        total = cases.count()
        passed = cases.filter(status='passed').count()
        failed = cases.filter(status='failed').count()
        blocked = cases.filter(status='blocked').count()
        skipped = cases.filter(status__in=['draft', 'ready']).count()
        
        # Bugs
        bugs = Bug.objects.filter(module__icontains=project.name)
        total_bugs = bugs.count()
        critical_bugs = bugs.filter(severity='critical').count()
        major_bugs = bugs.filter(severity='major').count()
        minor_bugs = bugs.filter(severity='minor').count()
        
        report = TestReport.objects.create(
            project=project,
            name=f"Test Report - {project.name}",
            description=f"Test report generated on {datetime.now().strftime('%d-%m-%Y')}",
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            blocked_tests=blocked,
            skipped_tests=skipped,
            total_bugs=total_bugs,
            critical_bugs=critical_bugs,
            major_bugs=major_bugs,
            minor_bugs=minor_bugs,
            generated_by=request.user
        )
        report.calculate_metrics()
        report.save()
        
        messages.success(request, f'✅ Test report generated!')
        return redirect('test_report_view', pk=report.pk)
    
    projects = TestProject.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
    }
    return render(request, 'testing/report_generate.html', context)


@login_required
def test_report_view(request, pk):
    """View test report"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    report = get_object_or_404(TestReport, pk=pk)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'report': report,
    }
    return render(request, 'testing/report_view.html', context)


@login_required
def test_run_auto(request):
    """Start the automatic system tester in the background (dashboard button)."""
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not request.user.is_superuser:
        if is_ajax:
            return JsonResponse({'ok': False, 'message': 'Access denied'}, status=403)
        messages.error(request, 'Access denied!')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('test_dashboard')

    from app.testing_qa import auto_tester
    started = auto_tester.start_background(
        request.user, request.get_host(),
        include_pages=request.POST.get('pages', '1') != '0',
    )
    if is_ajax:
        return JsonResponse({'ok': True, 'started': started,
                             'message': 'Started' if started else 'A test is already running'})
    if started:
        messages.info(request, '⏳ Auto test started. Progress is shown on this page.')
    else:
        messages.warning(request, 'An auto test is already running.')
    return redirect('test_dashboard')


@login_required
def test_auto_status(request):
    """Progress of the background auto test (polled by the dashboard)."""
    if not request.user.is_superuser:
        return JsonResponse({'state': 'denied'}, status=403)
    from app.testing_qa import auto_tester
    return JsonResponse(auto_tester.get_status())


@login_required
def test_auto_stop(request):
    """Stop the running background auto test (Stop button on the dashboard)."""
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not request.user.is_superuser:
        if is_ajax:
            return JsonResponse({'ok': False, 'message': 'Access denied'}, status=403)
        messages.error(request, 'Access denied!')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('test_dashboard')

    from app.testing_qa import auto_tester
    stopping = auto_tester.request_stop()
    if is_ajax:
        return JsonResponse({'ok': True, 'stopping': stopping,
                             'message': 'Stopping...' if stopping else 'No auto test is running'})
    if stopping:
        messages.info(request, 'Stopping the auto test...')
    else:
        messages.warning(request, 'No auto test is running.')
    return redirect('test_dashboard')
