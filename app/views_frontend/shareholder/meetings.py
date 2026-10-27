"""Frontend views: shareholder/meetings (split from the former shareholders.py)."""
from ...security.permissions import perm_required
from ...models import *
import time
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from datetime import date
from django.contrib import messages
from ...models import Shareholder, ShareholderMeeting, MeetingAttendance, CompanyInfo


@login_required
@perm_required('view_shareholders')
def meeting_list(request):
    """List shareholder meetings"""
    meetings = ShareholderMeeting.objects.all()
    
    status = request.GET.get('status', '')
    if status:
        meetings = meetings.filter(status=status)
    
    meeting_type = request.GET.get('type', '')
    if meeting_type:
        meetings = meetings.filter(meeting_type=meeting_type)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meetings': meetings,
    }
    return render(request, 'shareholders/meeting_list.html', context)


@login_required
@perm_required('manage_shareholders')
def meeting_create(request):
    """Create new shareholder meeting"""
    if request.method == 'POST':
        try:
            meeting_type = request.POST.get('meeting_type')
            title = request.POST.get('title')
            date = request.POST.get('date')
            time = request.POST.get('time') or None
            venue = request.POST.get('venue')
            agenda = request.POST.get('agenda')
            status = request.POST.get('status', 'scheduled')
            notes = request.POST.get('notes', '')
            
            meeting = ShareholderMeeting.objects.create(
                meeting_type=meeting_type,
                title=title,
                date=date,
                time=time,
                venue=venue,
                agenda=agenda,
                status=status,
                notes=notes,
                created_by=request.user
            )
            
            # Add attendees if provided
            attendee_ids = request.POST.getlist('attendees[]')
            if attendee_ids:
                meeting.attendees.set(attendee_ids)
                meeting.total_attendees = len(attendee_ids)
                meeting.save()
            
            messages.success(request, f'✅ Meeting "{meeting.title}" created!')
            return redirect('meeting_detail', pk=meeting.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('meeting_create')
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting_types': ShareholderMeeting.MEETING_TYPES,
        'status_choices': ShareholderMeeting.STATUS_CHOICES,
        'shareholders': Shareholder.objects.filter(status='active'),
    }
    return render(request, 'shareholders/meeting_create.html', context)


@login_required
@perm_required('view_shareholders')
def meeting_detail(request, pk):
    """Meeting detail view"""
    meeting = get_object_or_404(ShareholderMeeting, pk=pk)
    attendance = meeting.attendance_records.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'meeting': meeting,
        'attendance': attendance,
    }
    return render(request, 'shareholders/meeting_detail.html', context)


@login_required
@perm_required('manage_shareholders')
def meeting_mark_attendance(request, pk):
    """Mark attendance for a meeting"""
    meeting = get_object_or_404(ShareholderMeeting, pk=pk)
    
    if request.method == 'POST':
        for shareholder in meeting.attendees.all():
            status = request.POST.get(f'attendance_{shareholder.id}', 'absent')
            MeetingAttendance.objects.update_or_create(
                meeting=meeting,
                shareholder=shareholder,
                defaults={'status': status}
            )
        
        meeting.total_attendees = MeetingAttendance.objects.filter(meeting=meeting, status='present').count()
        meeting.save()
        
        messages.success(request, f'✅ Attendance marked for {meeting.title}!')
        return redirect('meeting_detail', pk=meeting.pk)
    
    return redirect('meeting_detail', pk=meeting.pk)
