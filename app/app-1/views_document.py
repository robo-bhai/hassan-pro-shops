from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
import os
from datetime import datetime
from app.models import CompanyInfo, Document, DocumentCategory, DocumentFolder, DocumentVersion, DocumentShare, DocumentApproval
from app.models import Sale, Purchase, Customer, Vendor, Employee, Shareholder


@login_required
def document_dashboard(request):
    """Document Management Dashboard"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    total_documents = Document.objects.count()
    recent_documents = Document.objects.order_by('-uploaded_at')[:10]
    categories = DocumentCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'total_documents': total_documents,
        'recent_documents': recent_documents,
        'categories': categories,
        'pending_approvals': DocumentApproval.objects.filter(status='pending', approver=request.user).count(),
    }
    return render(request, 'document/dashboard.html', context)


@login_required
def document_list(request):
    """List all documents"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    documents = Document.objects.select_related('category', 'uploaded_by').all()
    
    search = request.GET.get('search', '')
    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(document_no__icontains=search) |
            Q(description__icontains=search) |
            Q(keywords__icontains=search)
        )
    
    category = request.GET.get('category', '')
    if category:
        documents = documents.filter(category_id=category)
    
    status = request.GET.get('status', '')
    if status:
        documents = documents.filter(status=status)
    
    paginator = Paginator(documents, 25)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj,
        'search': search,
        'category': category,
        'status': status,
        'categories': DocumentCategory.objects.filter(is_active=True),
        'status_choices': Document.DOCUMENT_STATUS,
    }
    return render(request, 'document/list.html', context)


@login_required
def document_upload(request):
    """Upload new document"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            file = request.FILES.get('file')
            if not file:
                messages.error(request, 'Please select a file!')
                return redirect('document_upload')
            
            document = Document.objects.create(
                title=request.POST.get('title'),
                description=request.POST.get('description', ''),
                category_id=request.POST.get('category') or None,
                document_type=request.POST.get('document_type', ''),
                file=file,
                file_size=file.size,
                file_type=file.content_type,
                visibility=request.POST.get('visibility', 'private'),
                status=request.POST.get('status', 'draft'),
                keywords=request.POST.get('keywords', ''),
                notes=request.POST.get('notes', ''),
                uploaded_by=request.user,
                uploaded_at=datetime.now()
            )
            
            # Link to related module
            module_type = request.POST.get('module_type')
            module_id = request.POST.get('module_id')
            if module_type and module_id:
                if module_type == 'sale':
                    document.sale_id = module_id
                elif module_type == 'purchase':
                    document.purchase_id = module_id
                elif module_type == 'customer':
                    document.customer_id = module_id
                elif module_type == 'vendor':
                    document.vendor_id = module_id
                elif module_type == 'employee':
                    document.employee_id = module_id
                elif module_type == 'shareholder':
                    document.shareholder_id = module_id
                elif module_type == 'loan':
                    document.loan_id = module_id
                document.save()
            
            messages.success(request, f'✅ Document "{document.title}" uploaded!')
            return redirect('document_detail', pk=document.pk)
            
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    
    categories = DocumentCategory.objects.filter(is_active=True)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'categories': categories,
        'visibility_choices': Document.DOCUMENT_VISIBILITY,
        'status_choices': Document.DOCUMENT_STATUS,
        'module_types': [
            ('sale', 'Sales'),
            ('purchase', 'Purchase'),
            ('customer', 'Customer'),
            ('vendor', 'Vendor'),
            ('employee', 'Employee'),
            ('shareholder', 'Shareholder'),
            ('loan', 'Loan'),
        ],
    }
    return render(request, 'document/upload.html', context)


@login_required
def document_detail(request, pk):
    """Document detail view"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    document = get_object_or_404(Document, pk=pk)
    versions = document.versions.all()
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'document': document,
        'versions': versions,
    }
    return render(request, 'document/detail.html', context)


@login_required
def document_download(request, pk):
    """Download document"""
    document = get_object_or_404(Document, pk=pk)
    response = HttpResponse(document.file, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{document.file.name.split("/")[-1]}"'
    return response


@login_required
def document_preview(request, pk):
    """Preview document (for PDFs and images)"""
    document = get_object_or_404(Document, pk=pk)
    return render(request, 'document/preview.html', {'document': document})


@login_required
def document_delete(request, pk):
    """Delete document"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied!')
        return redirect('dashboard')
    
    document = get_object_or_404(Document, pk=pk)
    
    if request.method == 'POST':
        title = document.title
        document.delete()
        messages.success(request, f'🗑️ Document "{title}" deleted!')
        return redirect('document_list')
    
    return redirect('document_detail', pk=pk)