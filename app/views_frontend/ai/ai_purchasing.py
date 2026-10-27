"""Frontend views: ai/ai_purchasing (split from the former ai_ops.py)."""
from ...security.permissions import perm_required
from django.utils.timezone import localdate
from ...models import *
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from datetime import timedelta
from django.contrib import messages
from django.http import JsonResponse
from ...models import CompanyInfo, Product
from ...ai.ai_purchase_planner import AIPurchasePlanner
logger = logging.getLogger(__name__)


@login_required
@perm_required('use_ai')
def ai_purchase_analysis(request):
    """API: Get AI analysis for a product"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        product_id = request.GET.get('product_id')
        warehouse_id = request.GET.get('warehouse_id')
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'message': 'Product ID required'
            })
        
        product = get_object_or_404(Product, pk=product_id)
        warehouse = None
        
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Run AI analysis
        planner = AIPurchasePlanner(product, warehouse)
        result = planner.analyze()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"AI analysis API error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
@perm_required('manage_ai_ops')
def ai_bulk_analysis(request):
    """API: Get AI analysis for multiple products"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    try:
        warehouse_id = request.GET.get('warehouse_id')
        warehouse = None
        
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        
        # Get products with sales activity
        from django.db.models import Sum
        from datetime import timedelta
        
        last_90 = localdate() - timedelta(days=90)
        
        active_products = Product.objects.filter(
            is_active=True,
            saleitem__sale__sale_date__date__gte=last_90
        ).distinct()[:20]
        
        results = []
        for product in active_products:
            try:
                planner = AIPurchasePlanner(product, warehouse)
                result = planner.analyze()
                
                if result['success']:
                    results.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'suggested_quantity': result['suggested_quantity'],
                        'confidence_score': result['confidence_score'],
                        'confidence_level': result['confidence_level'],
                        'risk_level': result['risk_level'],
                        'estimated_cost': result['estimated_cost'],
                        'is_urgent': result.get('is_urgent', False),
                        'current_stock': result['current_stock'],
                        'stock_coverage_days': result['stock_coverage_days'],
                    })
            except Exception as e:
                logger.warning(f"Failed for {product.name}: {e}")
                continue
        
        # Sort by urgency and confidence
        results.sort(
            key=lambda x: (
                not x['is_urgent'],
                -x['confidence_score'],
                -x['estimated_cost']
            )
        )
        
        return JsonResponse({
            'success': True,
            'analyses': results,
            'total': len(results),
        })
        
    except Exception as e:
        logger.error(f"Bulk analysis error: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
@perm_required('use_ai')
def ai_purchase_planner_dashboard(request):
    """AI Purchase Planner Dashboard"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, '❌ Access denied!')
        return redirect('dashboard')
    
    from ...models import AIPurchaseAnalysis, AIPurchaseInsight
    
    # Recent analyses
    recent_analyses = AIPurchaseAnalysis.objects.select_related(
        'product', 'warehouse'
    ).order_by('-created_at')[:20]
    
    # ✅ FIX: Python-level filter instead of JSON contains
    all_analyses = AIPurchaseAnalysis.objects.filter(
        user_accepted__isnull=True
    ).select_related('product', 'warehouse').order_by('-created_at')[:50]
    
    urgent_items = []
    for analysis in all_analyses:
        # Check in Python
        risk_factors = analysis.risk_factors or []
        if 'urgent' in risk_factors or analysis.risk_level == 'danger':
            urgent_items.append(analysis)
            if len(urgent_items) >= 10:
                break
    
    # Stats
    stats = {
        'total_analyses': AIPurchaseAnalysis.objects.count(),
        'high_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='high'
        ).count(),
        'medium_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='medium'
        ).count(),
        'low_confidence': AIPurchaseAnalysis.objects.filter(
            confidence_level='low'
        ).count(),
        'danger_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='danger'
        ).count(),
        'warning_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='warning'
        ).count(),
        'safe_risk': AIPurchaseAnalysis.objects.filter(
            risk_level='safe'
        ).count(),
    }
    
    # Insights
    insights = AIPurchaseInsight.objects.filter(
        is_resolved=False
    ).order_by('-impact_score')[:10]
    
    # --- Decision queue: suggestions that nobody has accepted or rejected yet ---------------
    from django.db.models import Sum as _Sum
    pending_qs = AIPurchaseAnalysis.objects.filter(user_accepted__isnull=True)
    pending_total = pending_qs.count()
    pending_cost = pending_qs.aggregate(t=_Sum('estimated_cost'))['t'] or 0
    risk_rank = {'danger': 0, 'warning': 1, 'safe': 2}
    pending_items = sorted(
        pending_qs.select_related('product', 'warehouse').order_by('-created_at')[:80],
        key=lambda a: (risk_rank.get(a.risk_level, 3), -(a.confidence_score or 0))
    )[:25]
    accepted_count = AIPurchaseAnalysis.objects.filter(user_accepted=True).count()
    rejected_count = AIPurchaseAnalysis.objects.filter(user_accepted=False).count()
    decided = accepted_count + rejected_count
    total = stats['total_analyses'] or 0

    def _pct(n):
        return int(round(n * 100 / total)) if total else 0

    stats.update({
        'pending_total': pending_total,
        'pending_cost': pending_cost,
        'accepted_count': accepted_count,
        'rejected_count': rejected_count,
        'accept_rate': int(round(accepted_count * 100 / decided)) if decided else 0,
        'danger_pct': _pct(stats['danger_risk']),
        'warning_pct': _pct(stats['warning_risk']),
        'safe_pct': _pct(stats['safe_risk']),
        'high_pct': _pct(stats['high_confidence']),
        'medium_pct': _pct(stats['medium_confidence']),
        'low_pct': _pct(stats['low_confidence']),
    })

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'recent_analyses': recent_analyses,
        'urgent_items': urgent_items,
        'pending_items': pending_items,
        'stats': stats,
        'insights': insights,
        'now': now(),
    }
    return render(request, 'ai/purchase_planner_dashboard.html', context)


@login_required
@perm_required('approve_purchases')
def ai_accept_suggestion(request, pk):
    """Accept AI suggestion and apply to plan"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})
    
    try:
        import json
        data = json.loads(request.body)
        
        analysis = get_object_or_404(AIPurchaseAnalysis, pk=pk)
        modified_qty = data.get('quantity')
        
        analysis.user_accepted = True
        analysis.user_modified_quantity = modified_qty
        analysis.user_notes = data.get('notes', '')
        analysis.save()
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Suggestion accepted! Quantity: {modified_qty or analysis.suggested_quantity}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@perm_required('approve_purchases')
def ai_reject_suggestion(request, pk):
    """Reject AI suggestion"""
    
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'})

    analysis = get_object_or_404(AIPurchaseAnalysis, pk=pk)
    analysis.user_accepted = False
    analysis.save()
    
    return JsonResponse({'success': True, 'message': '❌ Suggestion rejected'})
