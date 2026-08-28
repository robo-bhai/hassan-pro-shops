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

@login_required
def test_plan_list(request):
    """List test plans"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    plans = TestPlan.objects.select_related('project', 'created_by').all()
    
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
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    # Stats
    total_projects = TestProject.objects.count()
    total_suites = TestSuite.objects.count()
    total_tests = TestCase.objects.count()
    total_bugs = Bug.objects.count()
    
    # Test status breakdown
    passed = TestCase.objects.filter(status='passed').count()
    failed = TestCase.objects.filter(status='failed').count()
    blocked = TestCase.objects.filter(status='blocked').count()
    in_progress = TestCase.objects.filter(status='in_progress').count()
    
    # Bug breakdown
    critical_bugs = Bug.objects.filter(severity='critical').count()
    major_bugs = Bug.objects.filter(severity='major').count()
    open_bugs = Bug.objects.filter(status__in=['new', 'assigned', 'in_progress']).count()
    
    # Recent bugs
    recent_bugs = Bug.objects.order_by('-reported_at')[:10]
    
    # Recent executions
    recent_executions = TestExecution.objects.order_by('-started_at')[:10]
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_projects': total_projects,
        'total_suites': total_suites,
        'total_tests': total_tests,
        'total_bugs': total_bugs,
        'passed': passed,
        'failed': failed,
        'blocked': blocked,
        'in_progress': in_progress,
        'critical_bugs': critical_bugs,
        'major_bugs': major_bugs,
        'open_bugs': open_bugs,
        'recent_bugs': recent_bugs,
        'recent_executions': recent_executions,
    }
    return render(request, 'testing/dashboard.html', context)


@login_required
def test_project_list(request):
    """List test projects"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    projects = TestProject.objects.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'projects': projects,
    }
    return render(request, 'testing/projects.html', context)


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
    """List test cases"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if suite_id:
        suite = get_object_or_404(TestSuite, pk=suite_id)
        cases = suite.cases.all()
    else:
        cases = TestCase.objects.all()
        suite = None
    
    paginator = Paginator(cases, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'suite': suite,
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
        test_case.executed_at = datetime.now()
        test_case.actual_result = request.POST.get('actual_result', '')
        test_case.save()
        
        # If failed, create bug
        if status == 'failed':
            messages.warning(request, '⚠️ Test failed! Please report bug.')
            return redirect('bug_create')
        
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
    """List bugs"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    bugs = Bug.objects.select_related('test_case', 'assigned_to', 'reported_by').all()
    
    status = request.GET.get('status', '')
    if status:
        bugs = bugs.filter(status=status)
    
    severity = request.GET.get('severity', '')
    if severity:
        bugs = bugs.filter(severity=severity)
    
    search = request.GET.get('search', '')
    if search:
        bugs = bugs.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(module__icontains=search)
        )
    
    paginator = Paginator(bugs, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'status': status,
        'severity': severity,
        'search': search,
        'status_choices': Bug.STATUS_CHOICES,
        'severity_choices': Bug.SEVERITY_CHOICES,
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
        'test_cases': TestCase.objects.all(),
        'users': User.objects.filter(is_active=True),
    }
    return render(request, 'testing/bug_create.html', context)


@login_required
def bug_update_status(request, pk):
    """Update bug status"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    bug = get_object_or_404(Bug, pk=pk)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        bug.status = status
        
        if status == 'fixed':
            bug.fixed_at = datetime.now()
        elif status == 'verified':
            bug.verified_at = datetime.now()
        elif status == 'closed':
            bug.closed_at = datetime.now()
        
        bug.save()
        messages.success(request, f'✅ Bug status updated to: {bug.get_status_display()}')
        return redirect('bug_list')
    
    return redirect('bug_list')


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