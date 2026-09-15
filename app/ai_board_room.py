"""
AI Board Room Engine
Complete C-Suite AI System with 7 Experts

Experts:
👑 CEO      - Chief Executive Officer
💰 CFO      - Chief Financial Officer
📊 CA       - Chartered Accountant
⚙️ COO      - Chief Operating Officer
🎯 CSO      - Chief Strategy Officer
👥 CSHO     - Chief Shareholder Officer
💻 CSO Tech - Chief Software Officer
"""

from django.db.models import Sum, Avg, Count, F, Q, Max, Min
from django.utils.timezone import now, localdate
from datetime import timedelta, date, datetime
from decimal import Decimal
from collections import defaultdict
import logging
import json

logger = logging.getLogger(__name__)


class AIBoardRoom:
    """
    AI Board Room - Manages 7 AI Experts
    
    Experts:
    👑 CEO      - Overall Business Vision & Strategy
    💰 CFO      - Financial Control & Cash Management
    📊 CA       - Tax, Compliance & Accounting
    ⚙️ COO      - Operations & Efficiency
    🎯 CSO      - Strategy, Sales & Marketing
    👥 CSHO     - Shareholder Relations & Protection
    💻 CSO Tech - Software & Technology Management
    """
    
    def __init__(self):
        self.today = localdate()
        self.reports = {}
        self.meeting = None
        
        # Import all models
        from .models import (
            Sale, Purchase, Expense, Product, Inventory,
            Customer, Vendor, Employee, Shareholder, CashBalance,
            SaleInstallment, BalanceDividend, Dividend,
            SaleOrder, PurchaseOrder, OperationTask,
            ShareholderWithdrawalRequest, ShareholderDepositRequest
        )
        
        self.Sale = Sale
        self.Purchase = Purchase
        self.Expense = Expense
        self.Product = Product
        self.Inventory = Inventory
        self.Customer = Customer
        self.Vendor = Vendor
        self.Employee = Employee
        self.Shareholder = Shareholder
        self.CashBalance = CashBalance
        self.SaleInstallment = SaleInstallment
        self.BalanceDividend = BalanceDividend
        self.Dividend = Dividend
        self.SaleOrder = SaleOrder
        self.PurchaseOrder = PurchaseOrder
        self.OperationTask = OperationTask
        self.ShareholderWithdrawalRequest = ShareholderWithdrawalRequest
        self.ShareholderDepositRequest = ShareholderDepositRequest
    
    # ==========================================
    # MAIN - RUN COMPLETE BOARD MEETING (7 EXPERTS)
    # ==========================================
    
    def run_full_board_meeting(self, title=None):
        """Run complete board meeting with all 7 experts"""
        
        logger.info("🏢 Starting AI Board Meeting (7 experts)...")
        
        if not title:
            title = f"Board Meeting - {self.today.strftime('%d %b %Y')}"
        
        results = {
            'success': True,
            'meeting_id': None,
            'reports_generated': 0,
            'alerts_created': 0,
            'overall_health': 0,
            'total_savings': 0,
            'total_revenue': 0,
        }
        
        try:
            # 1. Run all 7 expert reports
            logger.info("📊 Running all 7 expert reports...")
            
            self.reports['ceo'] = self.run_ceo_analysis()
            self.reports['cfo'] = self.run_cfo_analysis()
            self.reports['ca'] = self.run_ca_analysis()
            self.reports['coo'] = self.run_coo_analysis()
            self.reports['cso'] = self.run_cso_analysis()
            self.reports['csho'] = self.run_csho_analysis()
            self.reports['cso_tech'] = self.run_cso_tech_analysis()
            
            # 2. Save individual reports
            from .models import AIBoardMember
            
            saved_reports = []
            for member_type, report in self.reports.items():
                member, created = AIBoardMember.objects.update_or_create(
                    member_type=member_type,
                    report_date=self.today,
                    defaults={
                        'health_score': report['health_score'],
                        'status': report['status'],
                        'summary': report['summary'],
                        'key_metrics': report['key_metrics'],
                        'findings': report['findings'],
                        'recommendations': report['recommendations'],
                        'warnings': report['warnings'],
                        'opportunities': report['opportunities'],
                        'potential_savings': Decimal(str(report.get('potential_savings', 0))),
                        'potential_revenue': Decimal(str(report.get('potential_revenue', 0))),
                        'confidence_score': Decimal(str(report.get('confidence', 80))),
                        'data_snapshot': report.get('data_snapshot', {}),
                    }
                )
                saved_reports.append(member)
            
            results['reports_generated'] = len(saved_reports)
            
            # 3. Create unified board meeting
            self.meeting = self.create_board_meeting(saved_reports, title)
            results['meeting_id'] = self.meeting.id
            results['overall_health'] = self.meeting.overall_health_score
            results['total_savings'] = float(self.meeting.total_potential_savings)
            results['total_revenue'] = float(self.meeting.total_potential_revenue)
            
            # 4. Create alerts
            alerts_count = self.create_board_alerts()
            results['alerts_created'] = alerts_count
            
            # 5. Save KPIs
            self.save_kpis()
            
            logger.info(f"✅ Board Meeting Complete: {results}")
            
        except Exception as e:
            logger.error(f"❌ Board Meeting failed: {e}")
            import traceback
            traceback.print_exc()
            results['success'] = False
            results['error'] = str(e)
        
        return results
    
    # ==========================================
    # 👑 CEO - CHIEF EXECUTIVE OFFICER
    # ==========================================
    
    def run_ceo_analysis(self):
        """CEO AI - Overall Business Vision & Strategy"""
        
        logger.info("👑 Running CEO Analysis...")
        
        # METRICS
        last_30 = self.today - timedelta(days=30)
        prev_30 = last_30 - timedelta(days=30)
        
        current_sales = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        prev_sales = self.Sale.objects.filter(
            sale_date__date__gte=prev_30,
            sale_date__date__lt=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        growth_rate = 0
        if prev_sales > 0:
            growth_rate = float((current_sales - prev_sales) / prev_sales * 100)
        
        total_products = self.Product.objects.filter(is_active=True).count()
        total_customers = self.Customer.objects.count()
        total_employees = self.Employee.objects.filter(status='active').count()
        total_shareholders = self.Shareholder.objects.filter(status='active').count()
        
        total_revenue = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        total_profit = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__profit'))['total'] or Decimal('0')
        
        profit_margin = (float(total_profit) / float(total_revenue) * 100) if total_revenue > 0 else 0
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if growth_rate > 20:
            findings.append(f"🚀 Strong growth: {growth_rate:.1f}% MoM")
            opportunities.append({
                'title': 'Scale up operations',
                'description': 'Growth is strong. Consider expansion.',
                'priority': 'high',
                'impact': 'Revenue +30%'
            })
        elif growth_rate > 5:
            findings.append(f"✅ Healthy growth: {growth_rate:.1f}% MoM")
        elif growth_rate > -5:
            findings.append(f"➡️ Stable business: {growth_rate:.1f}% MoM")
        else:
            findings.append(f"📉 Declining: {growth_rate:.1f}% MoM")
            warnings.append({
                'title': 'Business decline detected',
                'message': f'Sales dropped {abs(growth_rate):.1f}%. Need strategy change.',
                'severity': 'high'
            })
            recommendations.append({
                'title': 'Marketing push needed',
                'description': 'Increase marketing to reverse decline',
                'priority': 'urgent'
            })
        
        if profit_margin > 25:
            findings.append(f"💎 Excellent margins: {profit_margin:.1f}%")
        elif profit_margin > 15:
            findings.append(f"✅ Good margins: {profit_margin:.1f}%")
        elif profit_margin > 10:
            findings.append(f"⚠️ Thin margins: {profit_margin:.1f}%")
            warnings.append({
                'title': 'Margins are thin',
                'message': 'Consider price optimization',
                'severity': 'medium'
            })
        else:
            findings.append(f"🔴 Poor margins: {profit_margin:.1f}%")
            warnings.append({
                'title': 'Critical: Low margins',
                'message': 'Immediate action needed',
                'severity': 'critical'
            })
        
        if total_products < 20:
            recommendations.append({
                'title': 'Expand product range',
                'description': f'Only {total_products} products. Add more for stability.',
                'priority': 'medium'
            })
        
        if total_customers < 50:
            recommendations.append({
                'title': 'Grow customer base',
                'description': 'Focus on customer acquisition',
                'priority': 'high'
            })
        
        opportunities.append({
            'title': 'Market expansion',
            'description': 'Explore new geographic markets',
            'priority': 'medium',
            'impact': 'Revenue +20%'
        })
        
        # Score
        score = 50
        if growth_rate > 20:
            score += 25
        elif growth_rate > 10:
            score += 15
        elif growth_rate > 0:
            score += 10
        elif growth_rate > -10:
            score += 0
        else:
            score -= 15
        
        if profit_margin > 25:
            score += 25
        elif profit_margin > 15:
            score += 15
        elif profit_margin > 10:
            score += 5
        else:
            score -= 10
        
        score = max(0, min(100, score))
        
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"Business is {'thriving' if score >= 80 else 'growing' if score >= 60 else 'stable' if score >= 40 else 'declining'}. "
                      f"Revenue: Rs. {float(total_revenue):,.0f}, "
                      f"Growth: {growth_rate:+.1f}%, "
                      f"Margin: {profit_margin:.1f}%.",
            'key_metrics': {
                'revenue': float(total_revenue),
                'profit': float(total_profit),
                'profit_margin': round(profit_margin, 1),
                'growth_rate': round(growth_rate, 1),
                'products': total_products,
                'customers': total_customers,
                'employees': total_employees,
                'shareholders': total_shareholders,
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': 0,
            'potential_revenue': float(total_revenue) * 0.3,
            'confidence': 85,
            'data_snapshot': {
                'growth_rate': growth_rate,
                'profit_margin': profit_margin,
            }
        }
    
    # ==========================================
    # 💰 CFO - CHIEF FINANCIAL OFFICER
    # ==========================================
    
    def run_cfo_analysis(self):
        """CFO AI - Financial Control & Cash Management"""
        
        logger.info("💰 Running CFO Analysis...")
        
        last_30 = self.today - timedelta(days=30)
        
        current_cash = Decimal(str(self.CashBalance.get_balance()))
        
        cash_inflow = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        
        cash_outflow = self.Purchase.objects.filter(
            pur_date__date__gte=last_30
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        
        net_cash_flow = cash_inflow - cash_outflow
        
        # Receivables
        total_receivables = Decimal('0')
        for customer in self.Customer.objects.all()[:200]:
            balance = customer.adjusted_outstanding_balance()
            if balance > 0:
                total_receivables += balance
        
        # Payables
        total_payables = Decimal('0')
        for vendor in self.Vendor.objects.all()[:100]:
            balance = vendor.outstanding_balance()
            if balance > 0:
                total_payables += balance
        
        # Liquidity
        if total_payables > 0:
            liquidity_ratio = float(current_cash) / float(total_payables)
        else:
            liquidity_ratio = 10.0
        
        # Burn rate
        monthly_expense = self.Expense.objects.filter(
            expense_date__gte=last_30
        ).aggregate(total=Sum('amount'))['total'] or Decimal('100000')
        
        daily_burn = float(monthly_expense) / 30
        days_runway = float(current_cash) / daily_burn if daily_burn > 0 else 999
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if days_runway >= 90:
            findings.append(f"💰 Excellent cash: {int(days_runway)} days runway")
        elif days_runway >= 60:
            findings.append(f"✅ Healthy cash: {int(days_runway)} days runway")
        elif days_runway >= 30:
            findings.append(f"⚠️ Moderate cash: {int(days_runway)} days runway")
            warnings.append({
                'title': 'Cash position moderate',
                'message': f'Only {int(days_runway)} days of cash remaining',
                'severity': 'medium'
            })
        else:
            findings.append(f"🚨 Critical cash: {int(days_runway)} days")
            warnings.append({
                'title': 'CRITICAL: Cash running out!',
                'message': f'Only {int(days_runway)} days runway. Act NOW!',
                'severity': 'critical'
            })
            recommendations.append({
                'title': 'Emergency cash management',
                'description': 'Urgent: Increase collections and reduce expenses',
                'priority': 'urgent'
            })
        
        if liquidity_ratio >= 2:
            findings.append(f"✅ Strong liquidity: {liquidity_ratio:.2f}")
        elif liquidity_ratio >= 1:
            findings.append(f"⚠️ Tight liquidity: {liquidity_ratio:.2f}")
        else:
            findings.append(f"🔴 Poor liquidity: {liquidity_ratio:.2f}")
            warnings.append({
                'title': 'Liquidity crisis',
                'message': 'Payables exceed cash reserves',
                'severity': 'critical'
            })
        
        if net_cash_flow > 0:
            findings.append(f"✅ Positive cash flow: Rs. {float(net_cash_flow):,.0f}/month")
        else:
            findings.append(f"⚠️ Negative cash flow: Rs. {float(net_cash_flow):,.0f}/month")
            warnings.append({
                'title': 'Negative cash flow',
                'message': 'More money going out than coming in',
                'severity': 'high'
            })
        
        if total_receivables > 0:
            if current_cash > 0 and float(total_receivables) / float(current_cash) > 2:
                warnings.append({
                    'title': 'High receivables',
                    'message': f'Rs. {float(total_receivables):,.0f} outstanding',
                    'severity': 'medium'
                })
                opportunities.append({
                    'title': 'Collection drive',
                    'description': f'Rs. {float(total_receivables):,.0f} can be collected',
                    'priority': 'high',
                    'impact': f'Cash +{float(total_receivables):,.0f}'
                })
        
        recommendations.append({
            'title': 'Optimize cash management',
            'description': 'Maintain 3-month cash reserve',
            'priority': 'medium'
        })
        
        recommendations.append({
            'title': 'Review expenses',
            'description': 'Find cost-cutting opportunities',
            'priority': 'medium'
        })
        
        # Score
        score = 50
        if days_runway >= 90:
            score += 25
        elif days_runway >= 60:
            score += 15
        elif days_runway >= 30:
            score += 5
        else:
            score -= 20
        
        if liquidity_ratio >= 2:
            score += 15
        elif liquidity_ratio >= 1:
            score += 5
        else:
            score -= 15
        
        if net_cash_flow > 0:
            score += 10
        else:
            score -= 10
        
        score = max(0, min(100, score))
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        potential_savings = float(monthly_expense) * 0.2
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"Cash: Rs. {float(current_cash):,.0f} ({int(days_runway)} days). "
                      f"Receivables: Rs. {float(total_receivables):,.0f}. "
                      f"Payables: Rs. {float(total_payables):,.0f}.",
            'key_metrics': {
                'cash_balance': float(current_cash),
                'cash_inflow': float(cash_inflow),
                'cash_outflow': float(cash_outflow),
                'net_cash_flow': float(net_cash_flow),
                'receivables': float(total_receivables),
                'payables': float(total_payables),
                'liquidity_ratio': round(liquidity_ratio, 2),
                'days_runway': int(days_runway),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': potential_savings,
            'potential_revenue': float(total_receivables) * 0.3,
            'confidence': 88,
            'data_snapshot': {
                'cash': float(current_cash),
                'days_runway': days_runway,
            }
        }
    
    # ==========================================
    # 📊 CA - CHARTERED ACCOUNTANT
    # ==========================================
    
    def run_ca_analysis(self):
        """CA AI - Tax, Compliance & Accounting"""
        
        logger.info("📊 Running CA Analysis...")
        
        # Financial year
        fy_start = self.today.replace(month=7, day=1) if self.today.month >= 7 else self.today.replace(year=self.today.year-1, month=7, day=1)
        
        ytd_revenue = self.Sale.objects.filter(
            sale_date__date__gte=fy_start
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        ytd_expenses = self.Expense.objects.filter(
            expense_date__gte=fy_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        ytd_purchases = self.Purchase.objects.filter(
            pur_date__date__gte=fy_start
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        estimated_profit = ytd_revenue - ytd_purchases - ytd_expenses
        estimated_tax = estimated_profit * Decimal('0.17') if estimated_profit > 0 else Decimal('0')
        
        next_quarter_end = self.today.replace(day=1) + timedelta(days=90)
        days_to_next_quarter = (next_quarter_end - self.today).days
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if estimated_profit > 0:
            findings.append(f"📊 YTD Profit: Rs. {float(estimated_profit):,.0f}")
            findings.append(f"💰 Estimated Tax: Rs. {float(estimated_tax):,.0f}")
        else:
            findings.append(f"📉 YTD Loss: Rs. {float(abs(estimated_profit)):,.0f}")
            findings.append("💡 No tax liability (loss year)")
        
        recommendations.append({
            'title': 'Maximize tax deductions',
            'description': 'Utilize all available expense deductions',
            'priority': 'medium',
            'impact': f'Potential saving: Rs. {float(estimated_tax * Decimal("0.15")):,.0f}'
        })
        
        recommendations.append({
            'title': 'Maintain proper records',
            'description': 'Keep all invoices, bills, receipts organized',
            'priority': 'medium'
        })
        
        recommendations.append({
            'title': 'Advance tax planning',
            'description': f'Next quarter in {days_to_next_quarter} days',
            'priority': 'high' if days_to_next_quarter < 30 else 'medium'
        })
        
        if days_to_next_quarter < 30:
            warnings.append({
                'title': 'Quarterly tax filing due',
                'message': f'Only {days_to_next_quarter} days left',
                'severity': 'high'
            })
        
        opportunities.append({
            'title': 'Tax optimization strategies',
            'description': 'Review business structure for tax efficiency',
            'priority': 'medium',
            'impact': f'Save up to Rs. {float(estimated_tax * Decimal("0.2")):,.0f}'
        })
        
        # Score
        score = 75
        if estimated_profit > 0:
            score += 10
        if days_to_next_quarter > 60:
            score += 10
        elif days_to_next_quarter > 30:
            score += 5
        else:
            score -= 10
        
        score = max(0, min(100, score))
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"YTD Revenue: Rs. {float(ytd_revenue):,.0f}, "
                      f"Expenses: Rs. {float(ytd_expenses):,.0f}, "
                      f"Tax Liability: Rs. {float(estimated_tax):,.0f}. "
                      f"Next filing: {days_to_next_quarter} days.",
            'key_metrics': {
                'ytd_revenue': float(ytd_revenue),
                'ytd_expenses': float(ytd_expenses),
                'ytd_purchases': float(ytd_purchases),
                'estimated_profit': float(estimated_profit),
                'estimated_tax': float(estimated_tax),
                'days_to_next_quarter': days_to_next_quarter,
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': float(estimated_tax) * 0.2,
            'potential_revenue': 0,
            'confidence': 82,
            'data_snapshot': {
                'estimated_tax': float(estimated_tax),
            }
        }
    
    # ==========================================
    # ⚙️ COO - CHIEF OPERATING OFFICER
    # ==========================================
    
    def run_coo_analysis(self):
        """COO AI - Operations & Efficiency"""
        
        logger.info("⚙️ Running COO Analysis...")
        
        total_products = self.Product.objects.filter(is_active=True).count()
        
        low_stock_count = self.Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).count()
        
        out_of_stock = self.Inventory.objects.filter(stock__lte=0).count()
        
        total_inventory_value = Decimal('0')
        for inv in self.Inventory.objects.all()[:500]:
            total_inventory_value += inv.stock_value()
        
        pending_orders = self.SaleOrder.objects.filter(status='pending').count()
        processing_orders = self.SaleOrder.objects.filter(status='processing').count()
        
        pending_pos = self.PurchaseOrder.objects.filter(
            status__in=['pending', 'confirmed', 'processing']
        ).count()
        
        total_tasks = self.OperationTask.objects.filter(
            created_at__date__gte=self.today - timedelta(days=30)
        ).count()
        
        completed_tasks = self.OperationTask.objects.filter(
            created_at__date__gte=self.today - timedelta(days=30),
            status='completed'
        ).count()
        
        task_completion = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 100
        efficiency = 100 - (out_of_stock / max(1, total_products) * 100)
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if low_stock_count > 0:
            findings.append(f"⚠️ {low_stock_count} products low stock")
            warnings.append({
                'title': f'{low_stock_count} products need restocking',
                'message': 'Low stock may lead to stockouts',
                'severity': 'high' if low_stock_count > 10 else 'medium'
            })
            recommendations.append({
                'title': 'Restock low-inventory products',
                'description': f'Order {low_stock_count} products immediately',
                'priority': 'high'
            })
        
        if out_of_stock > 0:
            findings.append(f"🚨 {out_of_stock} products OUT OF STOCK")
            warnings.append({
                'title': f'{out_of_stock} products out of stock!',
                'message': 'Lost sales and unhappy customers',
                'severity': 'critical'
            })
        
        if task_completion >= 90:
            findings.append(f"✅ Excellent task completion: {task_completion:.1f}%")
        elif task_completion >= 70:
            findings.append(f"✅ Good task completion: {task_completion:.1f}%")
        else:
            findings.append(f"⚠️ Low task completion: {task_completion:.1f}%")
            warnings.append({
                'title': 'Low task completion rate',
                'message': f'Only {task_completion:.1f}% tasks completed',
                'severity': 'medium'
            })
        
        if pending_orders > 10:
            findings.append(f"⚠️ {pending_orders} pending sale orders")
            recommendations.append({
                'title': 'Process pending orders',
                'description': f'Clear backlog of {pending_orders} orders',
                'priority': 'high'
            })
        
        if pending_pos > 10:
            findings.append(f"⚠️ {pending_pos} pending purchase orders")
        
        if efficiency >= 95:
            findings.append(f"✅ Excellent efficiency: {efficiency:.1f}%")
        elif efficiency >= 85:
            findings.append(f"✅ Good efficiency: {efficiency:.1f}%")
        else:
            findings.append(f"⚠️ Efficiency: {efficiency:.1f}%")
        
        recommendations.append({
            'title': 'Automate repetitive tasks',
            'description': 'Reduce manual work through automation',
            'priority': 'medium'
        })
        
        recommendations.append({
            'title': 'Regular inventory audit',
            'description': 'Monthly stock reconciliation',
            'priority': 'medium'
        })
        
        if low_stock_count > 5:
            opportunities.append({
                'title': 'Prevent stockouts',
                'description': f'Restock {low_stock_count} products to avoid lost sales',
                'priority': 'high',
                'impact': 'Prevent revenue loss'
            })
        
        # Score
        score = 50
        if out_of_stock == 0 and low_stock_count == 0:
            score += 20
        elif out_of_stock == 0:
            score += 10
        elif low_stock_count > 10:
            score -= 10
        
        if task_completion >= 90:
            score += 15
        elif task_completion >= 70:
            score += 8
        else:
            score -= 5
        
        if pending_orders < 5:
            score += 15
        elif pending_orders < 15:
            score += 8
        else:
            score -= 5
        
        score = max(0, min(100, score))
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"Ops efficiency: {efficiency:.1f}%. "
                      f"Tasks: {task_completion:.1f}% complete. "
                      f"Low stock: {low_stock_count}, Out of stock: {out_of_stock}.",
            'key_metrics': {
                'total_products': total_products,
                'low_stock_count': low_stock_count,
                'out_of_stock': out_of_stock,
                'inventory_value': float(total_inventory_value),
                'pending_orders': pending_orders,
                'pending_pos': pending_pos,
                'task_completion': round(task_completion, 1),
                'efficiency': round(efficiency, 1),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': float(total_inventory_value) * 0.1,
            'potential_revenue': 0,
            'confidence': 85,
            'data_snapshot': {
                'efficiency': efficiency,
                'task_completion': task_completion,
            }
        }
    
    # ==========================================
    # 🎯 CSO - CHIEF STRATEGY OFFICER
    # ==========================================
    
    def run_cso_analysis(self):
        """CSO AI - Strategy, Sales & Marketing"""
        
        logger.info("🎯 Running CSO Analysis...")
        
        last_30 = self.today - timedelta(days=30)
        last_60 = self.today - timedelta(days=60)
        
        current_customers = self.Customer.objects.filter(
            created_at__date__gte=last_30
        ).count() if hasattr(self.Customer, 'created_at') else 0
        
        total_customers = self.Customer.objects.count()
        
        current_sales = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        prev_sales = self.Sale.objects.filter(
            sale_date__date__gte=last_60,
            sale_date__date__lt=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        sales_growth = 0
        if prev_sales > 0:
            sales_growth = float((current_sales - prev_sales) / prev_sales * 100)
        
        top_products = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).values('saleitem__product__name').annotate(
            total=Sum('saleitem__total_amt')
        ).order_by('-total')[:5]
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if sales_growth > 20:
            findings.append(f"🚀 Excellent sales growth: {sales_growth:+.1f}%")
        elif sales_growth > 5:
            findings.append(f"✅ Good sales growth: {sales_growth:+.1f}%")
        elif sales_growth > -5:
            findings.append(f"➡️ Stable sales: {sales_growth:+.1f}%")
        else:
            findings.append(f"📉 Sales declining: {sales_growth:+.1f}%")
            warnings.append({
                'title': 'Sales decline detected',
                'message': f'Sales dropped {abs(sales_growth):.1f}%',
                'severity': 'high'
            })
        
        if total_customers > 100:
            findings.append(f"✅ Strong customer base: {total_customers}")
        elif total_customers > 50:
            findings.append(f"✅ Good customer base: {total_customers}")
        else:
            findings.append(f"⚠️ Small customer base: {total_customers}")
            recommendations.append({
                'title': 'Customer acquisition campaign',
                'description': 'Focus on growing customer base',
                'priority': 'high'
            })
        
        if top_products:
            top_product = top_products[0]
            findings.append(f"🏆 Top product: {top_product['saleitem__product__name']}")
        
        recommendations.append({
            'title': 'Market expansion strategy',
            'description': 'Explore new markets and demographics',
            'priority': 'medium'
        })
        
        recommendations.append({
            'title': 'Competitor analysis',
            'description': 'Regular competitor review',
            'priority': 'medium'
        })
        
        opportunities.append({
            'title': 'Cross-sell opportunities',
            'description': 'Analyze customer buying patterns',
            'priority': 'medium',
            'impact': 'Revenue +15%'
        })
        
        opportunities.append({
            'title': 'Digital marketing',
            'description': 'Expand online presence',
            'priority': 'medium',
            'impact': 'New customers +30%'
        })
        
        # Score
        score = 50
        if sales_growth > 20:
            score += 25
        elif sales_growth > 10:
            score += 15
        elif sales_growth > 0:
            score += 10
        elif sales_growth > -10:
            score += 0
        else:
            score -= 15
        
        if total_customers > 100:
            score += 15
        elif total_customers > 50:
            score += 10
        elif total_customers > 20:
            score += 5
        
        score = max(0, min(100, score))
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"Sales growth: {sales_growth:+.1f}%. "
                      f"Total customers: {total_customers}. "
                      f"Strategy focused on growth & retention.",
            'key_metrics': {
                'sales_growth': round(sales_growth, 1),
                'total_customers': total_customers,
                'new_customers': current_customers,
                'top_products_count': len(top_products),
                'current_sales': float(current_sales),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': 0,
            'potential_revenue': float(current_sales) * 0.2,
            'confidence': 78,
            'data_snapshot': {
                'sales_growth': sales_growth,
            }
        }
    
    # ==========================================
    # 👥 CSHO - CHIEF SHAREHOLDER OFFICER
    # ==========================================
    
    def run_csho_analysis(self):
        """CSHO AI - Shareholder Relations & Protection"""
        
        logger.info("👥 Running CSHO Analysis...")
        
        last_30 = self.today - timedelta(days=30)
        last_90 = self.today - timedelta(days=90)
        
        total_shareholders = self.Shareholder.objects.filter(status='active').count()
        
        total_investment = Decimal('0')
        for sh in self.Shareholder.objects.filter(status='active'):
            total_investment += sh.total_investment()
        
        total_balance = Decimal('0')
        for sh in self.Shareholder.objects.filter(status='active'):
            total_balance += sh.get_balance()
        
        recent_dividends = self.BalanceDividend.objects.filter(
            declaration_date__gte=last_90
        )
        total_dividends = sum(d.amount_to_distribute for d in recent_dividends)
        
        pending_withdrawals = self.ShareholderWithdrawalRequest.objects.filter(
            status='pending'
        ).count()
        
        pending_deposits = self.ShareholderDepositRequest.objects.filter(
            status='pending'
        ).count()
        
        # Count inactive
        inactive_count = 0
        for sh in self.Shareholder.objects.filter(status='active'):
            last_transaction = sh.cash_transactions.order_by('-created_at').first()
            if last_transaction:
                days_since = (self.today - last_transaction.created_at.date()).days
                if days_since > 90:
                    inactive_count += 1
        
        # ANALYSIS
        findings = []
        recommendations = []
        warnings = []
        opportunities = []
        
        if total_shareholders >= 50:
            findings.append(f"✅ Strong shareholder base: {total_shareholders}")
        elif total_shareholders >= 20:
            findings.append(f"✅ Good shareholder base: {total_shareholders}")
        else:
            findings.append(f"⚠️ Small shareholder base: {total_shareholders}")
            recommendations.append({
                'title': 'Recruit more shareholders',
                'description': 'Target 20+ active shareholders',
                'priority': 'high'
            })
        
        findings.append(f"💰 Total investment: Rs. {float(total_investment):,.0f}")
        findings.append(f"💵 Cash balances: Rs. {float(total_balance):,.0f}")
        
        if recent_dividends.exists():
            findings.append(f"💵 Dividends paid (90d): Rs. {float(total_dividends):,.0f}")
        else:
            findings.append("⚠️ No dividends in last 90 days")
            recommendations.append({
                'title': 'Consider dividend distribution',
                'description': 'Shareholders may expect regular dividends',
                'priority': 'medium'
            })
        
        if pending_withdrawals > 3:
            warnings.append({
                'title': f'{pending_withdrawals} pending withdrawals',
                'message': 'Process soon to maintain trust',
                'severity': 'medium'
            })
            recommendations.append({
                'title': 'Process withdrawal requests',
                'description': f'Clear {pending_withdrawals} pending requests',
                'priority': 'high'
            })
        
        if pending_deposits > 3:
            recommendations.append({
                'title': 'Approve deposit requests',
                'description': f'Fast-track {pending_deposits} deposits',
                'priority': 'medium'
            })
        
        if inactive_count > 5:
            warnings.append({
                'title': f'{inactive_count} inactive shareholders',
                'message': 'May churn if not engaged',
                'severity': 'medium'
            })
            recommendations.append({
                'title': 'Re-engagement campaign',
                'description': f'Contact {inactive_count} inactive shareholders',
                'priority': 'high'
            })
        
        recommendations.append({
            'title': 'Regular communication',
            'description': 'Monthly updates to all shareholders',
            'priority': 'medium'
        })
        
        recommendations.append({
            'title': 'Shareholder meeting',
            'description': 'Quarterly business review meetings',
            'priority': 'medium'
        })
        
        opportunities.append({
            'title': 'Idle balance activation',
            'description': f'Rs. {float(total_balance):,.0f} in idle balances',
            'priority': 'medium',
            'impact': 'Improve utilization'
        })
        
        # Score
        score = 60
        if total_shareholders >= 50:
            score += 15
        elif total_shareholders >= 20:
            score += 10
        elif total_shareholders >= 10:
            score += 5
        else:
            score -= 5
        
        if total_investment > Decimal('10000000'):
            score += 15
        elif total_investment > Decimal('5000000'):
            score += 10
        elif total_investment > Decimal('1000000'):
            score += 5
        
        if pending_withdrawals == 0:
            score += 5
        elif pending_withdrawals > 5:
            score -= 5
        
        if inactive_count < 5:
            score += 10
        elif inactive_count < 15:
            score += 5
        else:
            score -= 5
        
        score = max(0, min(100, score))
        status = 'excellent' if score >= 80 else 'good' if score >= 60 else 'warning' if score >= 40 else 'critical'
        
        return {
            'health_score': score,
            'status': status,
            'summary': f"Shareholders: {total_shareholders}. "
                      f"Investment: Rs. {float(total_investment):,.0f}. "
                      f"Balances: Rs. {float(total_balance):,.0f}. "
                      f"Inactive: {inactive_count}.",
            'key_metrics': {
                'total_shareholders': total_shareholders,
                'total_investment': float(total_investment),
                'total_balance': float(total_balance),
                'recent_dividends': float(total_dividends),
                'pending_withdrawals': pending_withdrawals,
                'pending_deposits': pending_deposits,
                'inactive_shareholders': inactive_count,
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': warnings,
            'opportunities': opportunities,
            'potential_savings': 0,
            'potential_revenue': float(total_balance) * 0.15,
            'confidence': 85,
            'data_snapshot': {
                'shareholders': total_shareholders,
                'investment': float(total_investment),
            }
        }
    
    # ==========================================
    # 💻 CSO TECH - CHIEF SOFTWARE OFFICER
    # ==========================================
    
    def run_cso_tech_analysis(self):
        """CSO Tech AI - Software & Technology Management"""
        
        logger.info("💻 Running CSO Tech Analysis...")
        
        try:
            from .ai_cso_tech import AICSOTechEngine
            
            engine = AICSOTechEngine()
            report = engine.run_full_analysis()
            
            return report
            
        except Exception as e:
            logger.error(f"CSO Tech analysis failed: {e}")
            
            # Fallback report
            return {
                'health_score': 75,
                'status': 'good',
                'summary': f"Software ecosystem analysis: {str(e)[:100]}",
                'key_metrics': {},
                'findings': [],
                'recommendations': [],
                'warnings': [],
                'opportunities': [],
                'potential_savings': 0,
                'potential_revenue': 0,
                'confidence': 50,
                'data_snapshot': {},
            }
    
    # ==========================================
    # CREATE BOARD MEETING (7 EXPERTS)
    # ==========================================
    
    def create_board_meeting(self, board_members, title):
        """Create unified board meeting with 7 experts"""
        
        from .models import AIBoardMeeting
        
        # Calculate scores (7 experts)
        scores = {
            'ceo': self.reports['ceo']['health_score'],
            'cfo': self.reports['cfo']['health_score'],
            'ca': self.reports['ca']['health_score'],
            'coo': self.reports['coo']['health_score'],
            'cso': self.reports['cso']['health_score'],
            'csho': self.reports['csho']['health_score'],
            'cso_tech': self.reports['cso_tech']['health_score'],
        }
        
        overall_health = int(sum(scores.values()) / len(scores))
        
        # Overall status
        if overall_health >= 80:
            overall_status = 'excellent'
        elif overall_health >= 60:
            overall_status = 'good'
        elif overall_health >= 40:
            overall_status = 'warning'
        else:
            overall_status = 'critical'
        
        # Collect all warnings, opportunities, recommendations
        all_warnings = []
        all_opportunities = []
        all_recommendations = []
        
        for member_type, report in self.reports.items():
            for w in report.get('warnings', []):
                all_warnings.append({
                    'source': member_type,
                    **w
                })
            for o in report.get('opportunities', []):
                all_opportunities.append({
                    'source': member_type,
                    **o
                })
            for r in report.get('recommendations', []):
                all_recommendations.append({
                    'source': member_type,
                    **r
                })
        
        # Top priorities
        priority_order = {'critical': 0, 'urgent': 1, 'high': 2, 'medium': 3, 'low': 4}
        
        top_priorities = []
        
        for w in sorted(all_warnings, key=lambda x: priority_order.get(x.get('severity', 'medium'), 3)):
            top_priorities.append({
                'priority': w.get('severity', 'medium'),
                'source': w['source'],
                'title': w['title'],
                'description': w.get('message', ''),
            })
        
        for r in sorted(all_recommendations, key=lambda x: priority_order.get(x.get('priority', 'medium'), 3)):
            if len(top_priorities) >= 10:
                break
            top_priorities.append({
                'priority': r.get('priority', 'medium'),
                'source': r['source'],
                'title': r['title'],
                'description': r.get('description', ''),
            })
        
        # Action plan
        action_plan = {
            'next_7_days': [p for p in top_priorities if p['priority'] in ['critical', 'urgent', 'high']][:5],
            'next_30_days': [p for p in top_priorities if p['priority'] in ['high', 'medium']][:8],
            'next_90_days': [p for p in top_priorities if p['priority'] in ['medium', 'low']][:10],
        }
        
        # Executive summary
        executive_summary = self._generate_executive_summary(scores, overall_health)
        
        # Total impact
        total_savings = sum(
            Decimal(str(r.get('potential_savings', 0))) 
            for r in self.reports.values()
        )
        
        total_revenue = sum(
            Decimal(str(r.get('potential_revenue', 0))) 
            for r in self.reports.values()
        )
        
        # Create meeting
        meeting = AIBoardMeeting.objects.create(
            meeting_date=self.today,
            title=title,
            overall_health_score=overall_health,
            overall_status=overall_status,
            ceo_score=scores['ceo'],
            cfo_score=scores['cfo'],
            ca_score=scores['ca'],
            coo_score=scores['coo'],
            cso_score=scores['cso'],
            csho_score=scores['csho'],
            cso_tech_score=scores['cso_tech'],
            executive_summary=executive_summary,
            top_priorities=top_priorities,
            action_plan=action_plan,
            risks=all_warnings,
            opportunities=all_opportunities,
            total_potential_savings=total_savings,
            total_potential_revenue=total_revenue,
            net_impact=total_savings + total_revenue,
            critical_decisions=[w for w in all_warnings if w.get('severity') == 'critical'],
            quick_wins=action_plan['next_7_days'],
            long_term_goals=action_plan['next_90_days'],
            confidence_score=Decimal('85'),
        )
        
        meeting.board_members.set(board_members)
        
        return meeting
    
    def _generate_executive_summary(self, scores, overall_health):
        """Generate executive summary with 7 experts"""
        
        best_member = max(scores.items(), key=lambda x: x[1])
        worst_member = min(scores.items(), key=lambda x: x[1])
        
        best_names = {
            'ceo': '👑 CEO',
            'cfo': '💰 CFO',
            'ca': '📊 CA',
            'coo': '⚙️ COO',
            'cso': '🎯 CSO',
            'csho': '👥 CSHO',
            'cso_tech': '💻 CSO Tech',
        }
        
        if overall_health >= 80:
            status = "business is thriving"
        elif overall_health >= 60:
            status = "business is stable and growing"
        elif overall_health >= 40:
            status = "business needs attention"
        else:
            status = "business requires immediate action"
        
        summary = f"""
📊 OVERALL BUSINESS HEALTH: {overall_health}/100

The {status}. Here's what your AI board says:

🌟 BEST PERFORMING: {best_names[best_member[0]]} ({best_member[1]}/100)
⚠️ NEEDS ATTENTION: {best_names[worst_member[0]]} ({worst_member[1]}/100)

🎯 EXPERT SCORES:
• 👑 CEO:       {scores['ceo']}/100 (Business vision)
• 💰 CFO:       {scores['cfo']}/100 (Financial health)
• 📊 CA:        {scores['ca']}/100 (Tax & compliance)
• ⚙️ COO:       {scores['coo']}/100 (Operations)
• 🎯 CSO:       {scores['cso']}/100 (Strategy)
• 👥 CSHO:      {scores['csho']}/100 (Shareholder relations)
• 💻 CSO Tech:  {scores['cso_tech']}/100 (Software & tech)

💡 Review the top priorities below to take action.
"""
        
        return summary.strip()
    
    # ==========================================
    # CREATE ALERTS
    # ==========================================
    
    def create_board_alerts(self):
        """Create alerts from board reports (7 experts)"""
        
        from .models import AIBoardAlert
        
        count = 0
        
        for member_type, report in self.reports.items():
            # Create alerts for critical warnings
            for warning in report.get('warnings', []):
                severity = warning.get('severity', 'medium')
                
                if severity in ['critical', 'high', 'medium']:
                    AIBoardAlert.objects.create(
                        source=member_type,
                        severity=severity,
                        title=warning['title'],
                        message=warning.get('message', ''),
                        suggested_action='Review and take action',
                        meeting=self.meeting,
                        data_snapshot={'member_type': member_type},
                    )
                    count += 1
            
            # Create alerts for high-priority opportunities
            for opp in report.get('opportunities', []):
                if opp.get('priority') == 'high':
                    AIBoardAlert.objects.create(
                        source=member_type,
                        severity='info',
                        alert_type='opportunity',
                        title=f"🎯 {opp['title']}",
                        message=opp.get('description', ''),
                        suggested_action='Consider this opportunity',
                        meeting=self.meeting,
                    )
                    count += 1
        
        return count
    
    # ==========================================
    # SAVE KPIs
    # ==========================================
    
    def save_kpis(self):
        """Save board-level KPIs"""
        
        from .models import AIBoardKPI
        
        last_30 = self.today - timedelta(days=30)
        
        revenue = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        profit = self.Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__profit'))['total'] or Decimal('0')
        
        cash = Decimal(str(self.CashBalance.get_balance()))
        
        profit_margin = (float(profit) / float(revenue) * 100) if revenue > 0 else 0
        
        inventory_value = Decimal('0')
        for inv in self.Inventory.objects.all()[:500]:
            inventory_value += inv.stock_value()
        
        total_shareholders = self.Shareholder.objects.filter(status='active').count()
        
        # System health from CSO Tech
        system_health = self.reports.get('cso_tech', {}).get('health_score', 100)
        
        overall_health = int(sum(
            self.reports[k]['health_score'] for k in self.reports
        ) / len(self.reports))
        
        AIBoardKPI.objects.update_or_create(
            date=self.today,
            defaults={
                'revenue': revenue,
                'profit': profit,
                'cash_balance': cash,
                'profit_margin': Decimal(str(round(profit_margin, 2))),
                'inventory_value': inventory_value,
                'total_shareholders': total_shareholders,
                'performance_score': system_health,
                'overall_health': overall_health,
            }
        )