"""
AI Board Room - Complete 7-Member Board System with Cash Utilization
Members:
1. CEO - Chief Executive Officer
2. CFO - Chief Financial Officer
3. CA - Chartered Accountant
4. COO - Chief Operating Officer
5. CSO - Chief Strategy Officer
6. CSHO - Chief Shareholder Officer
7. CSO Tech - Chief Strategy Officer (Technology)

✅ Minimum Cash for Strategies: Rs. 1,000
✅ 6 Custom Strategies: Bulk, Seasonal, Credit, Advance, New Product, Fast-Moving
✅ Dynamic allocation from StrategyAllocation
✅ Editable ROI
"""

from decimal import Decimal
from datetime import date, timedelta
from django.utils.timezone import now, localdate
from django.db.models import Sum, Count, Avg, Q, F
import logging

from .models import (
    AIBoardMeeting,
    AIBoardMember,
    AIBoardAlert,
    AIBoardKPI,
    CashInvestmentStrategy,
    StrategyAllocation,
    Sale,
    Purchase,
    Expense,
    Customer,
    Vendor,
    Product,
    Inventory,
    Shareholder,
    Dividend,
    SaleInstallment,
    CashBalance,
    Employee,
    Attendance,
    Payroll,
    LoanGiven,
    ShareholderLoan,
    Loan,
    AIBugReport,
    AIPerformanceIssue,
    AIFeatureSuggestion,
    AISystemHealth,
    AISecurityLog,
)

logger = logging.getLogger(__name__)


class AIBoardRoom:
    """
    AI Board Room - Manages all 7 AI Board Members
    Includes Cash Utilization Analysis
    Minimum Cash: Rs. 1,000
    ✅ 6 Custom Strategies including Fast-Moving
    """
    
    MIN_CASH_FOR_STRATEGIES = 1000
    
    def __init__(self):
        self.today = localdate()
        self.month_start = self.today.replace(day=1)
        self.last_30_days = self.today - timedelta(days=30)
    
    # ========================================== #
    # MAIN ENTRY POINT                           #
    # ========================================== #
    
    def run_full_board_meeting(self):
        """Run complete board meeting with all 7 members"""
        try:
            logger.info("🏢 Starting AI Board Meeting...")
            
            # Generate all 7 reports
            ceo_report = self._generate_ceo_report()
            cfo_report = self._generate_cfo_report()
            ca_report = self._generate_ca_report()
            coo_report = self._generate_coo_report()
            cso_report = self._generate_cso_report()
            csho_report = self._generate_csho_report()
            cso_tech_report = self._generate_cso_tech_report()
            
            reports_map = {
                'ceo': ceo_report,
                'cfo': cfo_report,
                'ca': ca_report,
                'coo': coo_report,
                'cso': cso_report,
                'csho': csho_report,
                'cso_tech': cso_tech_report,
            }
            
            # Save individual member reports
            members = []
            for member_type, report in reports_map.items():
                member = self._save_member_report(member_type, report)
                if member:
                    members.append(member)
            
            # Calculate overall health
            scores = [r['health_score'] for r in reports_map.values()]
            overall_score = int(sum(scores) / len(scores)) if scores else 0
            
            if overall_score >= 80:
                overall_status = 'excellent'
            elif overall_score >= 60:
                overall_status = 'good'
            elif overall_score >= 40:
                overall_status = 'warning'
            else:
                overall_status = 'critical'
            
            # Consolidate recommendations
            consolidated = self._consolidate_recommendations(reports_map)
            
            # Get cash utilization data from CFO report
            cfo_metrics = cfo_report['key_metrics']
            
            # Create/Update Board Meeting
            meeting, created = AIBoardMeeting.objects.update_or_create(
                meeting_date=self.today,
                title=f"Daily Board Meeting - {self.today}",
                defaults={
                    'overall_health_score': overall_score,
                    'overall_status': overall_status,
                    'ceo_score': ceo_report['health_score'],
                    'cfo_score': cfo_report['health_score'],
                    'ca_score': ca_report['health_score'],
                    'coo_score': coo_report['health_score'],
                    'cso_score': cso_report['health_score'],
                    'csho_score': csho_report['health_score'],
                    'cso_tech_score': cso_tech_report['health_score'],
                    
                    'cfo_cash_balance': Decimal(str(cfo_metrics.get('cash_balance', 0))),
                    'idle_cash': Decimal(str(cfo_metrics.get('idle_cash', 0))),
                    'invested_cash': Decimal(str(cfo_metrics.get('invested_cash', 0))),
                    'utilization_rate': Decimal(str(cfo_metrics.get('utilization_rate', 0))),
                    'potential_cash_profit': Decimal(str(cfo_report.get('potential_revenue', 0))),
                    
                    'executive_summary': consolidated['executive_summary'],
                    'top_priorities': consolidated['top_priorities'],
                    'action_plan': consolidated['action_plan'],
                    'risks': consolidated['risks'],
                    'opportunities': consolidated['opportunities'],
                    'total_potential_savings': consolidated['total_savings'],
                    'total_potential_revenue': consolidated['total_revenue'],
                    'net_impact': consolidated['total_savings'] + consolidated['total_revenue'],
                    'critical_decisions': consolidated['critical_decisions'],
                    'quick_wins': consolidated['quick_wins'],
                    'long_term_goals': consolidated['long_term_goals'],
                    'confidence_score': consolidated['confidence'],
                }
            )
            
            # Link members
            if members:
                meeting.board_members.set(members)
            
            # Create/Update Cash Investment Strategies
            self._save_cash_strategies(cso_report, meeting)
            
            # Create alerts
            alerts_created = self._create_board_alerts(reports_map, meeting)
            
            # Save KPI snapshot
            self._save_kpi_snapshot(meeting)
            
            action = "created" if created else "updated"
            logger.info(
                f"✅ Board Meeting {action}! "
                f"Health: {overall_score}/100 | "
                f"Alerts: {alerts_created}"
            )
            
            return {
                'success': True,
                'meeting_id': meeting.id,
                'action': action,
                'overall_health': overall_score,
                'overall_status': overall_status,
                'alerts_created': alerts_created,
                'total_savings': float(consolidated['total_savings']),
                'total_revenue': float(consolidated['total_revenue']),
                'idle_cash': float(cfo_metrics.get('idle_cash', 0)),
                'utilization_rate': float(cfo_metrics.get('utilization_rate', 0)),
                'member_scores': {
                    'ceo': ceo_report['health_score'],
                    'cfo': cfo_report['health_score'],
                    'ca': ca_report['health_score'],
                    'coo': coo_report['health_score'],
                    'cso': cso_report['health_score'],
                    'csho': csho_report['health_score'],
                    'cso_tech': cso_tech_report['health_score'],
                },
            }
            
        except Exception as e:
            logger.error(f"❌ Board meeting error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    # ========================================== #
    # MEMBER 1: CEO                              #
    # ========================================== #
    
    def _generate_ceo_report(self):
        """CEO - Overall business health + cash opportunity"""
        
        monthly_sales = Sale.objects.filter(
            sale_date__date__gte=self.month_start
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        monthly_profit = Sale.objects.filter(
            sale_date__date__gte=self.month_start
        ).aggregate(
            total=Sum('saleitem__profit') - Sum('discount_value')
        )['total'] or Decimal('0')
        
        prev_month_start = (self.month_start - timedelta(days=1)).replace(day=1)
        prev_month_sales = Sale.objects.filter(
            sale_date__date__gte=prev_month_start,
            sale_date__date__lt=self.month_start
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        growth_rate = float((monthly_sales - prev_month_sales) / prev_month_sales * 100) if prev_month_sales > 0 else 0
        
        cash_balance = CashBalance.get_balance()
        potential_profit_from_cash = cash_balance * Decimal('0.25')
        
        health_score = 70
        
        if growth_rate > 10:
            health_score += 15
        elif growth_rate > 0:
            health_score += 10
        elif growth_rate < -10:
            health_score -= 20
        
        if monthly_profit > 0:
            profit_margin = float(monthly_profit / monthly_sales * 100) if monthly_sales > 0 else 0
            if profit_margin > 20:
                health_score += 15
            elif profit_margin > 10:
                health_score += 10
        
        if cash_balance > 100000:
            health_score += 5
        
        health_score = max(0, min(100, health_score))
        
        findings = []
        
        if growth_rate > 10:
            findings.append({
                'type': 'positive',
                'title': '📈 Strong Growth',
                'detail': f'Sales grew by {growth_rate:.1f}% vs last month'
            })
        elif growth_rate < -10:
            findings.append({
                'type': 'negative',
                'title': '📉 Sales Decline',
                'detail': f'Sales dropped by {abs(growth_rate):.1f}% vs last month'
            })
        else:
            findings.append({
                'type': 'info',
                'title': '📊 Stable Performance',
                'detail': f'Sales growth at {growth_rate:+.1f}%'
            })
        
        if cash_balance >= self.MIN_CASH_FOR_STRATEGIES:
            findings.append({
                'type': 'info',
                'title': f'💡 Cash Opportunity: Rs. {potential_profit_from_cash:,.0f}/yr',
                'detail': f'Rs. {cash_balance:,.0f} cash could generate additional profit'
            })
        
        recommendations = []
        
        if growth_rate < 0:
            recommendations.append({
                'priority': 'high',
                'title': 'Boost Sales',
                'detail': 'Focus on marketing and customer retention',
                'impact': float(monthly_sales * Decimal('0.15')),
            })
        
        if cash_balance >= self.MIN_CASH_FOR_STRATEGIES:
            recommendations.append({
                'priority': 'high',
                'title': f'🎯 Invest Idle Cash (Rs. {cash_balance:,.0f})',
                'detail': f'Potential profit: Rs. {potential_profit_from_cash:,.0f}/year',
                'impact': float(potential_profit_from_cash),
            })
        
        return {
            'member_type': 'ceo',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': f'Business at {health_score}/100. Growth: {growth_rate:+.1f}%. Cash: Rs. {cash_balance:,.0f}.',
            'key_metrics': {
                'monthly_sales': float(monthly_sales),
                'monthly_profit': float(monthly_profit),
                'growth_rate': round(growth_rate, 2),
                'cash_available': float(cash_balance),
                'cash_profit_potential': float(potential_profit_from_cash),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': [f['title'] for f in findings if f['type'] == 'negative'],
            'opportunities': [
                f'Invest Rs. {cash_balance:,.0f} for Rs. {potential_profit_from_cash:,.0f}/yr profit'
            ] if cash_balance >= self.MIN_CASH_FOR_STRATEGIES else [],
            'potential_savings': 0,
            'potential_revenue': float(potential_profit_from_cash) if cash_balance >= self.MIN_CASH_FOR_STRATEGIES else 0,
        }
    
    # ========================================== #
    # MEMBER 2: CFO                              #
    # ========================================== #
    
    def _generate_cfo_report(self):
        """CFO - Cash flow + CASH UTILIZATION ANALYSIS"""
        
        cash_balance = CashBalance.get_balance()
        
        try:
            invested_in_loans_given = LoanGiven.objects.filter(
                status='active'
            ).aggregate(total=Sum('principal_amount'))['total'] or Decimal('0')
        except:
            invested_in_loans_given = Decimal('0')
        
        try:
            invested_in_shareholder_loans = ShareholderLoan.objects.filter(
                status__in=['active', 'partial_paid']
            ).aggregate(total=Sum('principal'))['total'] or Decimal('0')
        except:
            invested_in_shareholder_loans = Decimal('0')
        
        total_invested = invested_in_loans_given + invested_in_shareholder_loans
        total_cash_and_invested = cash_balance + total_invested
        
        utilization_rate = float(total_invested / total_cash_and_invested * 100) if total_cash_and_invested > 0 else 0
        idle_cash = cash_balance
        
        expected_profit_from_loans = Decimal('0')
        try:
            for loan in LoanGiven.objects.filter(status='active'):
                if loan.interest_rate > 0:
                    expected_profit_from_loans += loan.principal_amount * (loan.interest_rate / 100)
        except:
            pass
        
        try:
            for loan in ShareholderLoan.objects.filter(status__in=['active', 'partial_paid']):
                if loan.interest_rate > 0:
                    expected_profit_from_loans += loan.outstanding * (loan.interest_rate / 100)
        except:
            pass
        
        potential_profit_from_idle = idle_cash * Decimal('0.25')
        total_potential = expected_profit_from_loans + potential_profit_from_idle
        
        month_inflow = Sale.objects.filter(
            sale_date__date__gte=self.month_start
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        
        month_outflow = Purchase.objects.filter(
            pur_date__date__gte=self.month_start
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        
        month_expenses = Expense.objects.filter(
            expense_date__gte=self.month_start,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        net_cash_flow = month_inflow - month_outflow - month_expenses
        
        health_score = 70
        
        if net_cash_flow > 0:
            health_score += 10
        elif net_cash_flow < 0:
            health_score -= 15
        
        if utilization_rate >= 70:
            health_score += 15
        elif utilization_rate >= 50:
            health_score += 10
        elif utilization_rate >= 30:
            health_score += 5
        else:
            health_score -= 10
        
        if cash_balance > 100000:
            health_score += 10
        elif cash_balance < 1000:
            health_score -= 20
        
        health_score = max(0, min(100, health_score))
        
        findings = []
        
        if utilization_rate >= 70:
            findings.append({
                'type': 'positive',
                'title': f'✅ Excellent Cash Utilization ({utilization_rate:.1f}%)',
                'detail': f'Rs. {total_invested:,.2f} invested and working'
            })
        elif utilization_rate >= 40:
            findings.append({
                'type': 'info',
                'title': f'💡 Moderate Utilization ({utilization_rate:.1f}%)',
                'detail': f'Rs. {idle_cash:,.2f} idle cash could be invested'
            })
        else:
            findings.append({
                'type': 'negative',
                'title': f'⚠️ Low Utilization ({utilization_rate:.1f}%)',
                'detail': f'Rs. {idle_cash:,.2f} sitting idle — profit opportunity!'
            })
        
        if cash_balance < 1000:
            findings.append({
                'type': 'negative',
                'title': '🚨 Very Low Cash Balance',
                'detail': f'Only Rs. {cash_balance:,.2f} available'
            })
        elif cash_balance < 10000:
            findings.append({
                'type': 'warning',
                'title': '⚠️ Low Cash Balance',
                'detail': f'Rs. {cash_balance:,.2f} available'
            })
        
        if expected_profit_from_loans > 0:
            findings.append({
                'type': 'positive',
                'title': f'💰 Expected Profit from Loans',
                'detail': f'Rs. {expected_profit_from_loans:,.2f}/year'
            })
        
        if net_cash_flow < 0:
            findings.append({
                'type': 'negative',
                'title': '📉 Negative Cash Flow',
                'detail': f'Net flow: Rs. {net_cash_flow:,.2f}'
            })
        
        recommendations = []
        
        if idle_cash >= self.MIN_CASH_FOR_STRATEGIES:
            recommendations.append({
                'priority': 'high',
                'title': f'💡 Invest Idle Cash (Rs. {idle_cash:,.0f})',
                'detail': f'Rs. {idle_cash:,.2f} idle. Invest at 25% ROI for Rs. {potential_profit_from_idle:,.2f}/year',
                'impact': float(potential_profit_from_idle),
            })
        
        if net_cash_flow < 0:
            recommendations.append({
                'priority': 'critical',
                'title': 'Improve Cash Flow',
                'detail': 'Reduce expenses or boost collections',
                'impact': float(abs(net_cash_flow)),
            })
        
        return {
            'member_type': 'cfo',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': (
                f'Cash: Rs. {cash_balance:,.0f} | '
                f'Utilization: {utilization_rate:.1f}% | '
                f'Idle: Rs. {idle_cash:,.0f} | '
                f'Potential: Rs. {total_potential:,.0f}/yr'
            ),
            'key_metrics': {
                'cash_balance': float(cash_balance),
                'idle_cash': float(idle_cash),
                'invested_cash': float(total_invested),
                'utilization_rate': round(utilization_rate, 2),
                'net_cash_flow': float(net_cash_flow),
                'expected_profit_from_loans': float(expected_profit_from_loans),
                'potential_profit_from_idle': float(potential_profit_from_idle),
                'total_potential_profit': float(total_potential),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': [f['title'] for f in findings if f['type'] == 'negative'],
            'opportunities': [
                f'Invest Rs. {idle_cash:,.0f} for Rs. {potential_profit_from_idle:,.0f}/yr'
            ] if idle_cash >= self.MIN_CASH_FOR_STRATEGIES else [],
            'potential_savings': 0,
            'potential_revenue': float(total_potential),
        }
    
    # ========================================== #
    # MEMBER 3: CA                               #
    # ========================================== #
    
    def _generate_ca_report(self):
        """CA - Tax, compliance, accounting"""
        
        total_receivables = Decimal('0')
        for customer in Customer.objects.all():
            total_receivables += customer.adjusted_outstanding_balance()
        
        total_payables = Decimal('0')
        for vendor in Vendor.objects.all():
            total_payables += vendor.outstanding_balance()
        
        health_score = 70
        
        if total_receivables > 0 and total_payables > 0:
            ratio = float(total_receivables / total_payables)
            if 0.8 <= ratio <= 1.2:
                health_score += 20
            elif ratio < 0.5:
                health_score -= 15
        elif total_receivables == 0 and total_payables == 0:
            health_score += 15
        
        health_score = max(0, min(100, health_score))
        
        findings = []
        if total_receivables > total_payables * 2:
            findings.append({
                'type': 'negative',
                'title': '⚠️ High Receivables',
                'detail': f'Rs. {total_receivables:,.2f} pending'
            })
        else:
            findings.append({
                'type': 'info',
                'title': '📊 Balanced Books',
                'detail': f'Receivables: Rs. {total_receivables:,.0f}, Payables: Rs. {total_payables:,.0f}'
            })
        
        return {
            'member_type': 'ca',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': f'Receivables: Rs. {total_receivables:,.0f}. Payables: Rs. {total_payables:,.0f}.',
            'key_metrics': {
                'total_receivables': float(total_receivables),
                'total_payables': float(total_payables),
            },
            'findings': findings,
            'recommendations': [],
            'warnings': [f['title'] for f in findings if f['type'] == 'negative'],
            'opportunities': [],
            'potential_savings': 0,
            'potential_revenue': float(total_receivables * Decimal('0.05')),
        }
    
    # ========================================== #
    # MEMBER 4: COO                              #
    # ========================================== #
    
    def _generate_coo_report(self):
        """COO - Operations"""
        
        low_stock_count = Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold')
        ).count()
        
        total_products = Inventory.objects.count()
        
        pending_orders = 0
        try:
            from .models import SaleOrder
            pending_orders = SaleOrder.objects.filter(
                status__in=['pending', 'confirmed', 'processing']
            ).count()
        except:
            pass
        
        health_score = 70
        
        if total_products > 0:
            low_stock_ratio = low_stock_count / total_products
            if low_stock_ratio < 0.1:
                health_score += 15
            elif low_stock_ratio > 0.3:
                health_score -= 20
        
        if pending_orders < 5:
            health_score += 10
        elif pending_orders > 20:
            health_score -= 15
        
        health_score = max(0, min(100, health_score))
        
        findings = []
        if low_stock_count > 0:
            findings.append({
                'type': 'negative',
                'title': f'📦 {low_stock_count} Low Stock Items',
                'detail': 'Reorder required'
            })
        else:
            findings.append({
                'type': 'positive',
                'title': '✅ Inventory Healthy',
                'detail': 'All products above threshold'
            })
        
        return {
            'member_type': 'coo',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': f'Low stock: {low_stock_count}. Pending orders: {pending_orders}.',
            'key_metrics': {
                'low_stock_count': low_stock_count,
                'total_products': total_products,
                'pending_orders': pending_orders,
            },
            'findings': findings,
            'recommendations': [],
            'warnings': [f['title'] for f in findings if f['type'] == 'negative'],
            'opportunities': [],
            'potential_savings': 0,
            'potential_revenue': 0,
        }
    
    # ========================================== #
    # MEMBER 5: CSO - 6 STRATEGIES WITH FAST-MOVING #
    # ========================================== #
    
    def _generate_cso_report(self):
        """
        CSO - 6 CUSTOM CASH INVESTMENT STRATEGIES
        
        1. Bulk Purchase Discount
        2. Seasonal Stock
        3. Trusted Customer Credit
        4. Vendor Advance Payment
        5. New Product Line
        6. ⚡ Fast-Moving Product
        """
        
        cash_balance = CashBalance.get_balance()
        total_customers = Customer.objects.count()
        
        # ✅ Get active allocation + ROI
        config = StrategyAllocation.get_active()
        allocation = config.get_allocation_dict()
        roi_dict = config.get_roi_dict()
        
        logger.info(f"📊 Profile: {config.profile_name} | Avg ROI: {config.get_average_roi()}%")
        
        investment_strategies = []
        
        if cash_balance >= self.MIN_CASH_FOR_STRATEGIES:
            
            # ========================================== #
            # Strategy 1: Bulk Purchase                  #
            # ========================================== #
            if allocation.get('bulk_purchase', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['bulk_purchase']))
                roi = roi_dict.get('bulk_purchase', 25)
                investment_strategies.append({
                    'name': 'Bulk Purchase Discount',
                    'type': 'inventory',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'low',
                    'timeline': 4,
                    'description': f'Buy in bulk for discount ({config.bulk_purchase}%, {roi}% ROI)',
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.bulk_purchase}%',
                        f'Custom ROI: {roi}%',
                    ],
                })
            
            # ========================================== #
            # Strategy 2: Seasonal Stock                 #
            # ========================================== #
            if allocation.get('seasonal_stock', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['seasonal_stock']))
                roi = roi_dict.get('seasonal_stock', 35)
                investment_strategies.append({
                    'name': 'Seasonal Stock Investment',
                    'type': 'inventory',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'medium',
                    'timeline': 3,
                    'description': f'Seasonal items for festivals ({config.seasonal_stock}%, {roi}% ROI)',
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.seasonal_stock}%',
                        f'Custom ROI: {roi}%',
                    ],
                })
            
            # ========================================== #
            # Strategy 3: Customer Credit                #
            # ========================================== #
            if allocation.get('customer_credit', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['customer_credit']))
                roi = roi_dict.get('customer_credit', 18)
                investment_strategies.append({
                    'name': 'Trusted Customer Credit',
                    'type': 'customer_credit',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'medium',
                    'timeline': 3,
                    'description': f'Credit to trusted customers ({config.customer_credit}%, {roi}% ROI)',
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.customer_credit}%',
                        f'Custom ROI: {roi}%',
                    ],
                })
            
            # ========================================== #
            # Strategy 4: Vendor Advance                 #
            # ========================================== #
            if allocation.get('vendor_advance', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['vendor_advance']))
                roi = roi_dict.get('vendor_advance', 28)
                investment_strategies.append({
                    'name': 'Vendor Advance Payment',
                    'type': 'vendor_advance',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'low',
                    'timeline': 2,
                    'description': f'Advance for extra discount ({config.vendor_advance}%, {roi}% ROI)',
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.vendor_advance}%',
                        f'Custom ROI: {roi}%',
                    ],
                })
            
            # ========================================== #
            # Strategy 5: New Product Line               #
            # ========================================== #
            if allocation.get('new_product', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['new_product']))
                roi = roi_dict.get('new_product', 35)
                investment_strategies.append({
                    'name': 'New Product Line Test',
                    'type': 'expansion',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'high',
                    'timeline': 6,
                    'description': f'Test new product ({config.new_product}%, {roi}% ROI)',
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.new_product}%',
                        f'Custom ROI: {roi}%',
                    ],
                })
            
            # ========================================== #
            # ✅ Strategy 6: FAST-MOVING PRODUCT         #
            # ========================================== #
            if allocation.get('fast_moving', 0) > 0:
                amt = cash_balance * Decimal(str(allocation['fast_moving']))
                roi = roi_dict.get('fast_moving', 30)
                investment_strategies.append({
                    'name': 'Fast-Moving Product Investment',
                    'type': 'fast_moving',
                    'amount': float(amt),
                    'expected_roi': roi,
                    'expected_profit': float(amt * Decimal(str(roi / 100))),
                    'risk': 'low',
                    'timeline': 1,  # ✅ Fast cycle
                    'description': (
                        f'⚡ Fast-moving products: Buy in bulk, sell quickly, repeat cycle. '
                        f'({config.fast_moving}%, {roi}% annual ROI)'
                    ),
                    'reasoning': [
                        f'Investment: Rs. {amt:,.2f}',
                        f'Allocation: {config.fast_moving}%',
                        f'Custom ROI: {roi}% (annual)',
                        'Cycle: Monthly (12x/year)',
                        'Buy: Weekly',
                        'Sell: Daily',
                        'Risk: Low',
                    ],
                    'cycle_info': {
                        'buy_cycle': 'Weekly',
                        'sell_cycle': 'Daily',
                        'turnover': '12x/year',
                        'recommended_products': [
                            'Atta / Flour',
                            'Rice / Chawal',
                            'Cooking Oil',
                            'Sugar',
                            'Milk / Dairy',
                            'Bread / Bakery',
                            'Cold Drinks',
                            'Biscuits',
                            'Tea / Coffee',
                            'Spices',
                        ],
                    },
                })
        
        total_expected_profit = sum(s['expected_profit'] for s in investment_strategies)
        
        # Health score
        health_score = 75
        
        if total_customers > 100:
            health_score += 15
        elif total_customers < 20:
            health_score -= 10
        
        if investment_strategies:
            health_score += 10
        
        health_score = max(0, min(100, health_score))
        
        # Findings
        findings = [
            {
                'type': 'info',
                'title': f'👥 {total_customers} Active Customers',
                'detail': 'Customer base analysis'
            },
            {
                'type': 'info',
                'title': f'📊 Profile: {config.profile_name}',
                'detail': f'Average ROI: {config.get_average_roi()}%'
            }
        ]
        
        if investment_strategies:
            findings.append({
                'type': 'positive',
                'title': f'💡 {len(investment_strategies)} Investment Strategies Available',
                'detail': f'Potential profit: Rs. {total_expected_profit:,.0f}/year'
            })
        else:
            findings.append({
                'type': 'warning',
                'title': '⚠️ No Investment Strategies',
                'detail': f'Cash too low. Minimum Rs. {self.MIN_CASH_FOR_STRATEGIES:,} required'
            })
        
        # Recommendations
        recommendations = []
        for strategy in investment_strategies[:3]:
            priority = 'high' if strategy['expected_roi'] >= 20 else 'medium'
            recommendations.append({
                'priority': priority,
                'title': f"📈 {strategy['name']}",
                'detail': (
                    f"Invest Rs. {strategy['amount']:,.0f} "
                    f"for {strategy['expected_roi']}% ROI = "
                    f"Rs. {strategy['expected_profit']:,.0f}/year"
                ),
                'impact': strategy['expected_profit'],
            })
        
        return {
            'member_type': 'cso',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': (
                f'{total_customers} customers | '
                f'Rs. {cash_balance:,.0f} cash | '
                f'Avg ROI: {config.get_average_roi()}% | '
                f'Potential: Rs. {total_expected_profit:,.0f}/yr'
            ),
            'key_metrics': {
                'total_customers': total_customers,
                'cash_available': float(cash_balance),
                'strategies_count': len(investment_strategies),
                'total_expected_profit': total_expected_profit,
                'active_profile': config.profile_name,
                'average_roi': config.get_average_roi(),
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': [],
            'opportunities': [s['name'] for s in investment_strategies],
            'potential_savings': 0,
            'potential_revenue': total_expected_profit,
            'investment_strategies': investment_strategies,
        }
    
    # ========================================== #
    # MEMBER 6: CSHO                             #
    # ========================================== #
    
    def _generate_csho_report(self):
        """CSHO - Shareholders"""
        
        total_shareholders = Shareholder.objects.filter(status='active').count()
        total_shares = 0
        total_balance = Decimal('0')
        
        try:
            from .models import Share
            total_shares = Share.objects.aggregate(
                total=Sum('quantity')
            )['total'] or 0
        except:
            pass
        
        for sh in Shareholder.objects.filter(status='active'):
            balance = sh.get_balance()
            if balance:
                total_balance += Decimal(str(balance))
        
        health_score = 75
        
        if total_shareholders >= 10:
            health_score += 15
        elif total_shareholders >= 5:
            health_score += 10
        elif total_shareholders < 3:
            health_score -= 15
        
        health_score = max(0, min(100, health_score))
        
        findings = [
            {
                'type': 'info',
                'title': f'👥 {total_shareholders} Active Shareholders',
                'detail': f'Total shares: {total_shares:,}'
            }
        ]
        
        return {
            'member_type': 'csho',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': f'Shareholders: {total_shareholders}. Shares: {total_shares:,}.',
            'key_metrics': {
                'total_shareholders': total_shareholders,
                'total_shares': total_shares,
                'total_balance': float(total_balance),
            },
            'findings': findings,
            'recommendations': [],
            'warnings': [],
            'opportunities': [],
            'potential_savings': 0,
            'potential_revenue': 0,
        }
    
    # ========================================== #
    # MEMBER 7: CSO TECH                         #
    # ========================================== #
    
    def _generate_cso_tech_report(self):
        """CSO Tech - System health"""
        
        active_bugs = AIBugReport.objects.filter(status__in=['new', 'investigating'])
        critical_bugs = active_bugs.filter(severity='critical').count()
        high_bugs = active_bugs.filter(severity='high').count()
        total_bugs = active_bugs.count()
        
        try:
            performance_issues = AIPerformanceIssue.objects.filter(is_resolved=False).count()
            critical_performance = AIPerformanceIssue.objects.filter(is_resolved=False, priority__gte=8).count()
        except:
            performance_issues = 0
            critical_performance = 0
        
        try:
            security_alerts = AISecurityLog.objects.filter(is_resolved=False).count()
            critical_security = AISecurityLog.objects.filter(is_resolved=False, severity='critical').count()
        except:
            security_alerts = 0
            critical_security = 0
        
        try:
            latest_health = AISystemHealth.objects.order_by('-date').first()
            system_health_score = latest_health.health_score if latest_health else 100
            memory_usage = float(latest_health.memory_usage) if latest_health else 0
            disk_usage = float(latest_health.disk_usage) if latest_health else 0
        except:
            system_health_score = 100
            memory_usage = 0
            disk_usage = 0
        
        health_score = 100
        health_score -= critical_bugs * 15
        health_score -= high_bugs * 5
        health_score -= max(0, total_bugs - critical_bugs - high_bugs) * 2
        health_score -= critical_performance * 10
        health_score -= max(0, performance_issues - critical_performance) * 3
        health_score -= critical_security * 20
        health_score -= max(0, security_alerts - critical_security) * 3
        
        if memory_usage > 90:
            health_score -= 15
        elif memory_usage > 75:
            health_score -= 5
        
        if disk_usage > 90:
            health_score -= 15
        elif disk_usage > 80:
            health_score -= 5
        
        health_score = max(0, min(100, health_score))
        
        findings = []
        if critical_bugs > 0:
            findings.append({
                'type': 'negative',
                'title': f'🚨 {critical_bugs} Critical Bugs',
                'detail': 'Immediate attention required'
            })
        
        if critical_security > 0:
            findings.append({
                'type': 'negative',
                'title': f'🔒 {critical_security} Critical Security Alerts',
                'detail': 'Security vulnerabilities detected'
            })
        
        if total_bugs == 0 and security_alerts == 0 and performance_issues == 0:
            findings.append({
                'type': 'positive',
                'title': '✅ System Fully Healthy',
                'detail': 'All systems operational'
            })
        
        recommendations = []
        if critical_bugs > 0:
            recommendations.append({
                'priority': 'critical',
                'title': 'Fix Critical Bugs',
                'detail': f'Address {critical_bugs} critical bugs',
                'impact': 0,
            })
        
        if memory_usage > 90:
            recommendations.append({
                'priority': 'high',
                'title': 'Optimize Memory Usage',
                'detail': f'Memory at {memory_usage:.1f}%',
                'impact': 0,
            })
        
        if disk_usage > 90:
            recommendations.append({
                'priority': 'high',
                'title': 'Clean Up Disk Space',
                'detail': f'Disk at {disk_usage:.1f}%',
                'impact': 0,
            })
        
        return {
            'member_type': 'cso_tech',
            'health_score': health_score,
            'status': self._score_to_status(health_score),
            'summary': f'System Health: {health_score}/100. Bugs: {total_bugs} | Security: {security_alerts}',
            'key_metrics': {
                'system_health': system_health_score,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'total_bugs': total_bugs,
                'critical_bugs': critical_bugs,
                'security_alerts': security_alerts,
                'performance_issues': performance_issues,
            },
            'findings': findings,
            'recommendations': recommendations,
            'warnings': [f['title'] for f in findings if f['type'] == 'negative'],
            'opportunities': [],
            'potential_savings': 0,
            'potential_revenue': 0,
        }
    
    # ========================================== #
    # HELPERS                                    #
    # ========================================== #
    
    def _score_to_status(self, score):
        if score >= 80:
            return 'excellent'
        elif score >= 60:
            return 'good'
        elif score >= 40:
            return 'warning'
        return 'critical'
    
    def _save_member_report(self, member_type, report):
        """Save/update member report"""
        try:
            data = {
                'health_score': report['health_score'],
                'status': report['status'],
                'summary': report['summary'],
                'key_metrics': report['key_metrics'],
                'findings': report['findings'],
                'recommendations': report['recommendations'],
                'warnings': report['warnings'],
                'opportunities': report.get('opportunities', []),
                'potential_savings': Decimal(str(report.get('potential_savings', 0))),
                'potential_revenue': Decimal(str(report.get('potential_revenue', 0))),
            }
            
            existing = AIBoardMember.objects.filter(
                member_type=member_type,
                report_date=self.today
            ).first()
            
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.save()
                return existing
            else:
                return AIBoardMember.objects.create(
                    member_type=member_type,
                    report_date=self.today,
                    **data
                )
        except Exception as e:
            logger.error(f"Save member error: {e}")
            return None
    
    def _consolidate_recommendations(self, reports_map):
        """Consolidate all reports"""
        all_risks = []
        all_opportunities = []
        all_recommendations = []
        total_savings = Decimal('0')
        total_revenue = Decimal('0')
        
        for member_type, report in reports_map.items():
            for warning in report.get('warnings', []):
                all_risks.append({'source': member_type, 'title': warning})
            
            for opp in report.get('opportunities', []):
                all_opportunities.append({'source': member_type, 'title': opp})
            
            for rec in report.get('recommendations', []):
                all_recommendations.append({
                    'source': member_type,
                    'priority': rec.get('priority', 'medium'),
                    'title': rec.get('title', ''),
                    'detail': rec.get('detail', ''),
                    'impact': rec.get('impact', 0),
                })
            
            total_savings += Decimal(str(report.get('potential_savings', 0)))
            total_revenue += Decimal(str(report.get('potential_revenue', 0)))
        
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        all_recommendations.sort(key=lambda x: priority_order.get(x['priority'], 2))
        
        avg_score = sum(r['health_score'] for r in reports_map.values()) / len(reports_map)
        executive_summary = (
            f"Board Meeting {self.today}: "
            f"Health {avg_score:.0f}/100. "
            f"{len(all_risks)} risks, {len(all_recommendations)} recommendations. "
            f"Impact: Rs. {(total_savings + total_revenue):,.2f}"
        )
        
        top_priorities = [
            {'rank': i+1, 'title': r['title'], 'source': r['source'], 'priority': r['priority']}
            for i, r in enumerate(all_recommendations[:5])
        ]
        
        quick_wins = [r for r in all_recommendations if r['priority'] in ['critical', 'high']][:5]
        
        long_term_goals = [
            {'title': 'Improve operational efficiency', 'timeline': '6 months'},
            {'title': 'Expand market presence', 'timeline': '12 months'},
        ]
        
        action_plan = {
            'immediate': [r['title'] for r in quick_wins[:3]],
            'short_term': [r['title'] for r in all_recommendations[3:8]],
            'long_term': [g['title'] for g in long_term_goals],
        }
        
        confidence = min(95, max(50, int(avg_score)))
        
        return {
            'executive_summary': executive_summary,
            'top_priorities': top_priorities,
            'action_plan': action_plan,
            'risks': all_risks,
            'opportunities': all_opportunities,
            'critical_decisions': [r for r in all_recommendations if r['priority'] == 'critical'],
            'quick_wins': quick_wins,
            'long_term_goals': long_term_goals,
            'total_savings': total_savings,
            'total_revenue': total_revenue,
            'confidence': confidence,
        }
    
    def _save_cash_strategies(self, cso_report, meeting):
        """Save cash investment strategies from CSO report"""
        try:
            strategies = cso_report.get('investment_strategies', [])
            
            CashInvestmentStrategy.objects.filter(meeting=meeting).delete()
            
            for s in strategies:
                CashInvestmentStrategy.objects.create(
                    name=s['name'],
                    strategy_type=s['type'],
                    description=s['description'],
                    amount=Decimal(str(s['amount'])),
                    expected_roi=Decimal(str(s['expected_roi'])),
                    expected_profit=Decimal(str(s['expected_profit'])),
                    risk_level=s['risk'],
                    timeline_months=s['timeline'],
                    status='recommended',
                    confidence_score=Decimal('75'),
                    meeting=meeting,
                    reasoning=s.get('reasoning', []),
                )
            
            logger.info(f"💰 Saved {len(strategies)} cash investment strategies")
        except Exception as e:
            logger.error(f"Save strategies error: {e}")
    
    def _create_board_alerts(self, reports_map, meeting):
        """Create alerts (no duplicates)"""
        alerts_created = 0
        
        AIBoardAlert.objects.filter(meeting=meeting).delete()
        
        for member_type, report in reports_map.items():
            for warning in report.get('warnings', []):
                try:
                    AIBoardAlert.objects.create(
                        source=member_type,
                        severity='high',
                        title=warning,
                        message=report.get('summary', ''),
                        meeting=meeting,
                    )
                    alerts_created += 1
                except Exception as e:
                    logger.error(f"Alert error: {e}")
        
        for member_type, report in reports_map.items():
            if report['health_score'] < 40:
                try:
                    AIBoardAlert.objects.create(
                        source=member_type,
                        severity='critical',
                        title=f"🚨 {member_type.upper()} Critical",
                        message=f"Health: {report['health_score']}/100",
                        meeting=meeting,
                    )
                    alerts_created += 1
                except:
                    pass
        
        return alerts_created
    
    def _save_kpi_snapshot(self, meeting):
        """Save KPI snapshot"""
        try:
            monthly_sales = Sale.objects.filter(
                sale_date__date__gte=self.month_start
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
            
            monthly_profit = Sale.objects.filter(
                sale_date__date__gte=self.month_start
            ).aggregate(
                total=Sum('saleitem__profit') - Sum('discount_value')
            )['total'] or Decimal('0')
            
            AIBoardKPI.objects.update_or_create(
                date=self.today,
                defaults={
                    'revenue': monthly_sales,
                    'profit': monthly_profit,
                    'cash_balance': CashBalance.get_balance(),
                    'overall_health': meeting.overall_health_score,
                }
            )
        except Exception as e:
            logger.error(f"KPI error: {e}")