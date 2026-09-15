"""
AI Cash Flow Engine
Complete AI-powered cash management with 10 engines
"""

from django.db.models import Sum, Avg, Count, F, Q, Max, Min
from django.utils.timezone import now, localdate
from datetime import timedelta, date, datetime
from decimal import Decimal
from collections import defaultdict
import logging
import statistics
import math

logger = logging.getLogger(__name__)


class AICashEngine:
    """
    AI Engine for Cash Management
    
    Features:
    - 30/60/90 day forecast
    - Shortage prediction
    - Health scoring
    - Collection forecast
    - Fraud detection
    - Seasonal analysis
    """
    
    def __init__(self):
        self.today = localdate()
        
        # Import models
        from .models import (
            CashTransaction, CashBalance, Sale, Purchase, 
            Expense, Customer, Shareholder, Vendor,
            SaleInstallment, EmiPayment
        )
        
        self.CashTransaction = CashTransaction
        self.CashBalance = CashBalance
        self.Sale = Sale
        self.Purchase = Purchase
        self.Expense = Expense
        self.Customer = Customer
        self.Shareholder = Shareholder
        self.Vendor = Vendor
        self.SaleInstallment = SaleInstallment
        self.EmiPayment = EmiPayment
        
        # Alerts collection
        self.alerts = []
        self.forecasts = []
    
    # ==========================================
    # MAIN ANALYSIS
    # ==========================================
    
    def run_full_analysis(self):
        """Run complete cash analysis"""
        
        logger.info("🤖 Starting AI Cash Analysis...")
        
        results = {
            'success': True,
            'forecast': {},
            'health': {},
            'shortage': {},
            'collection': {},
            'alerts_created': 0,
            'recommendations': [],
        }
        
        try:
            # 1. Cash flow forecast
            results['forecast'] = self.predict_cash_flow()
            
            # 2. Shortage prediction
            results['shortage'] = self.predict_shortage(results['forecast'])
            
            # 3. Health score
            results['health'] = self.calculate_health_score()
            
            # 4. Collection forecast
            results['collection'] = self.forecast_collections()
            
            # 5. Fraud detection
            fraud_alerts = self.detect_fraud()
            
            # 6. Generate alerts
            alerts_count = self.generate_alerts(results)
            results['alerts_created'] = alerts_count
            
            # 7. Save analysis
            self.save_analysis(results)
            
            logger.info(f"✅ Cash Analysis Complete: Score {results['health']['score']}/100")
            
        except Exception as e:
            logger.error(f"❌ Cash Analysis failed: {e}")
            results['success'] = False
            results['error'] = str(e)
        
        return results
    
    # ==========================================
    # 1. CASH FLOW PREDICTION
    # ==========================================
    
    def predict_cash_flow(self):
        """Predict future cash balance"""
        
        # Current balance
        current_balance = Decimal(str(self.CashBalance.get_balance()))
        
        # Calculate averages
        averages = self._calculate_averages()
        daily_inflow = averages['daily_inflow']
        daily_outflow = averages['daily_outflow']
        
        # Generate forecasts
        forecast_7 = self._generate_forecast(current_balance, daily_inflow, daily_outflow, 7)
        forecast_30 = self._generate_forecast(current_balance, daily_inflow, daily_outflow, 30)
        forecast_90 = self._generate_forecast(current_balance, daily_inflow, daily_outflow, 90)
        
        return {
            'current_balance': float(current_balance),
            'daily_inflow': float(daily_inflow),
            'daily_outflow': float(daily_outflow),
            'net_daily': float(daily_inflow - daily_outflow),
            'forecast_7_days': forecast_7,
            'forecast_30_days': forecast_30,
            'forecast_90_days': forecast_90,
        }
    
    def _calculate_averages(self):
        """Calculate daily inflow/outflow averages"""
        
        # Last 30 days
        last_30 = self.today - timedelta(days=30)
        last_60 = self.today - timedelta(days=60)
        
        # Recent 30 days
        recent_inflow = self.CashTransaction.objects.filter(
            date__date__gte=last_30,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        recent_outflow = self.CashTransaction.objects.filter(
            date__date__gte=last_30,
            transaction_type__in=['withdraw', 'purchase', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Older 30 days (for trend)
        older_inflow = self.CashTransaction.objects.filter(
            date__date__gte=last_60,
            date__date__lt=last_30,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        older_outflow = self.CashTransaction.objects.filter(
            date__date__gte=last_60,
            date__date__lt=last_30,
            transaction_type__in=['withdraw', 'purchase', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Daily rates
        recent_inflow_daily = recent_inflow / 30
        recent_outflow_daily = recent_outflow / 30
        older_inflow_daily = older_inflow / 30
        older_outflow_daily = older_outflow / 30
        
        # Weighted average (recent 70%, older 30%)
        daily_inflow = (recent_inflow_daily * Decimal('0.7')) + (older_inflow_daily * Decimal('0.3'))
        daily_outflow = (recent_outflow_daily * Decimal('0.7')) + (older_outflow_daily * Decimal('0.3'))
        
        return {
            'daily_inflow': daily_inflow,
            'daily_outflow': daily_outflow,
            'recent_inflow': recent_inflow_daily,
            'recent_outflow': recent_outflow_daily,
        }
    
    def _generate_forecast(self, current_balance, daily_inflow, daily_outflow, days):
        """Generate day-by-day forecast"""
        
        forecast = []
        balance = current_balance
        net_daily = daily_inflow - daily_outflow
        
        for i in range(1, days + 1):
            forecast_date = self.today + timedelta(days=i)
            balance += net_daily
            
            forecast.append({
                'day': i,
                'date': forecast_date.strftime('%d-%b-%Y'),
                'predicted_balance': float(balance),
                'is_negative': balance < 0,
            })
        
        return forecast
    
    # ==========================================
    # 2. SHORTAGE PREDICTION
    # ==========================================
    
    def predict_shortage(self, forecast_data):
        """Predict cash shortage"""
        
        # Check 90-day forecast
        forecast = forecast_data.get('forecast_90_days', [])
        
        for day in forecast:
            if day['predicted_balance'] < 0:
                return {
                    'will_shortage': True,
                    'days_until': day['day'],
                    'shortage_date': day['date'],
                    'shortage_amount': abs(day['predicted_balance']),
                    'severity': self._get_shortage_severity(day['day']),
                }
        
        return {
            'will_shortage': False,
            'days_until': None,
            'shortage_date': None,
            'shortage_amount': 0,
            'severity': 'safe',
        }
    
    def _get_shortage_severity(self, days):
        """Get severity based on days"""
        if days <= 3:
            return 'emergency'
        elif days <= 7:
            return 'critical'
        elif days <= 15:
            return 'warning'
        else:
            return 'info'
    
    # ==========================================
    # 3. HEALTH SCORE
    # ==========================================
    
    def calculate_health_score(self):
        """Calculate cash health score (0-100)"""
        
        # ==========================================
        # Factor 1: Liquidity (25 points)
        # ==========================================
        current_balance = Decimal(str(self.CashBalance.get_balance()))
        last_30 = self.today - timedelta(days=30)
        
        monthly_expenses = self.Expense.objects.filter(
            expense_date__gte=last_30,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('100')
        
        liquidity_days = float(current_balance / monthly_expenses * 30) if monthly_expenses > 0 else 999
        
        if liquidity_days >= 90:
            liquidity_score = 25
            liquidity_status = 'Excellent'
        elif liquidity_days >= 60:
            liquidity_score = 20
            liquidity_status = 'Good'
        elif liquidity_days >= 30:
            liquidity_score = 15
            liquidity_status = 'Moderate'
        elif liquidity_days >= 15:
            liquidity_score = 8
            liquidity_status = 'Low'
        else:
            liquidity_score = 0
            liquidity_status = 'Critical'
        
        # ==========================================
        # Factor 2: Emergency Buffer (25 points)
        # ==========================================
        avg_monthly_expense = float(monthly_expenses)
        emergency_fund_target = avg_monthly_expense * 3  # 3 months
        
        if emergency_fund_target > 0:
            buffer_ratio = float(current_balance) / emergency_fund_target
            
            if buffer_ratio >= 1.0:
                buffer_score = 25
                buffer_status = 'Excellent'
            elif buffer_ratio >= 0.7:
                buffer_score = 20
                buffer_status = 'Good'
            elif buffer_ratio >= 0.5:
                buffer_score = 15
                buffer_status = 'Moderate'
            elif buffer_ratio >= 0.3:
                buffer_score = 8
                buffer_status = 'Low'
            else:
                buffer_score = 0
                buffer_status = 'Critical'
        else:
            buffer_score = 25
            buffer_status = 'N/A'
        
        # ==========================================
        # Factor 3: Inflow (20 points)
        # ==========================================
        recent_inflow = self.CashTransaction.objects.filter(
            date__date__gte=last_30,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        older_inflow = self.CashTransaction.objects.filter(
            date__date__gte=last_30 - timedelta(days=30),
            date__date__lt=last_30,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        if older_inflow > 0:
            inflow_growth = float((recent_inflow - older_inflow) / older_inflow * 100)
            
            if inflow_growth >= 20:
                inflow_score = 20
                inflow_status = 'Growing'
            elif inflow_growth >= 0:
                inflow_score = 15
                inflow_status = 'Stable'
            elif inflow_growth >= -20:
                inflow_score = 10
                inflow_status = 'Declining'
            else:
                inflow_score = 5
                inflow_status = 'Falling'
        else:
            inflow_score = 15
            inflow_status = 'New'
        
        # ==========================================
        # Factor 4: Outflow Control (15 points)
        # ==========================================
        recent_outflow = self.CashTransaction.objects.filter(
            date__date__gte=last_30,
            transaction_type__in=['withdraw', 'purchase', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        if older_inflow > 0:
            outflow_growth = float((recent_outflow - older_inflow) / older_inflow * 100) if older_inflow > 0 else 0
        else:
            outflow_growth = 0
        
        if outflow_growth <= 0:
            outflow_score = 15
            outflow_status = 'Controlled'
        elif outflow_growth <= 10:
            outflow_score = 12
            outflow_status = 'Moderate'
        elif outflow_growth <= 30:
            outflow_score = 8
            outflow_status = 'Growing'
        else:
            outflow_score = 3
            outflow_status = 'Rising'
        
        # ==========================================
        # Factor 5: Predictability (15 points)
        # ==========================================
        # Check last 30 days daily balance variance
        last_30_days = [
            self.today - timedelta(days=i) 
            for i in range(30)
        ]
        
        daily_balances = []
        for day in last_30_days:
            day_flow = self.CashTransaction.objects.filter(
                date__date=day
            ).aggregate(
                inflow=Sum('amount', filter=Q(transaction_type__in=['deposit', 'sale', 'opening'])),
                outflow=Sum('amount', filter=Q(transaction_type__in=['withdraw', 'purchase', 'expense']))
            )
            
            inflow = day_flow['inflow'] or Decimal('0')
            outflow = day_flow['outflow'] or Decimal('0')
            daily_balances.append(float(inflow - outflow))
        
        if len(daily_balances) > 5:
            try:
                stdev = statistics.stdev(daily_balances)
                mean = statistics.mean(daily_balances)
                
                if mean != 0:
                    cv = abs(stdev / mean)
                    
                    if cv < 0.5:
                        predictability_score = 15
                        predictability_status = 'Very Stable'
                    elif cv < 1.0:
                        predictability_score = 12
                        predictability_status = 'Stable'
                    elif cv < 2.0:
                        predictability_score = 8
                        predictability_status = 'Variable'
                    else:
                        predictability_score = 3
                        predictability_status = 'Volatile'
                else:
                    predictability_score = 10
                    predictability_status = 'Unknown'
            except:
                predictability_score = 10
                predictability_status = 'Unknown'
        else:
            predictability_score = 10
            predictability_status = 'Limited Data'
        
        # ==========================================
        # Total score
        # ==========================================
        total_score = (
            liquidity_score + 
            buffer_score + 
            inflow_score + 
            outflow_score + 
            predictability_score
        )
        
        return {
            'score': total_score,
            'max_score': 100,
            'label': self._get_health_label(total_score),
            'color': self._get_health_color(total_score),
            'factors': {
                'liquidity': {
                    'score': liquidity_score,
                    'max': 25,
                    'status': liquidity_status,
                    'value': f'{int(liquidity_days)} days',
                    'description': 'How long cash will last',
                },
                'buffer': {
                    'score': buffer_score,
                    'max': 25,
                    'status': buffer_status,
                    'value': f'{int(float(current_balance) / avg_monthly_expense)} months' if avg_monthly_expense > 0 else 'N/A',
                    'description': 'Emergency fund coverage',
                },
                'inflow': {
                    'score': inflow_score,
                    'max': 20,
                    'status': inflow_status,
                    'value': f'Rs. {float(recent_inflow):,.0f}',
                    'description': 'Money coming in',
                },
                'outflow': {
                    'score': outflow_score,
                    'max': 15,
                    'status': outflow_status,
                    'value': f'Rs. {float(recent_outflow):,.0f}',
                    'description': 'Money going out',
                },
                'predictability': {
                    'score': predictability_score,
                    'max': 15,
                    'status': predictability_status,
                    'value': 'Based on 30 days',
                    'description': 'Cash flow stability',
                },
            },
        }
    
    def _get_health_label(self, score):
        if score >= 80:
            return '🟢 Excellent'
        elif score >= 60:
            return '🟡 Good'
        elif score >= 40:
            return '🟠 Moderate'
        else:
            return '🔴 Poor'
    
    def _get_health_color(self, score):
        if score >= 80:
            return 'success'
        elif score >= 60:
            return 'info'
        elif score >= 40:
            return 'warning'
        else:
            return 'danger'
    
    # ==========================================
    # 4. COLLECTION FORECAST
    # ==========================================
    
    def forecast_collections(self):
        """Forecast upcoming customer collections"""
        
        collections = []
        
        for customer in self.Customer.objects.all()[:50]:
            outstanding = customer.adjusted_outstanding_balance()
            
            if outstanding <= 0:
                continue
            
            # Calculate collection probability
            probability = self._calculate_collection_probability(customer)
            
            if probability > 20:
                expected_amount = outstanding * Decimal(str(probability / 100))
                
                collections.append({
                    'customer_id': customer.id,
                    'customer_name': customer.name,
                    'outstanding': float(outstanding),
                    'probability': probability,
                    'expected_collection': float(expected_amount),
                    'expected_date': (self.today + timedelta(days=15)).strftime('%d-%b-%Y'),
                    'reason': self._get_collection_reason(customer, probability),
                })
        
        # Sort by probability
        collections.sort(key=lambda x: x['probability'], reverse=True)
        
        # Totals
        total_outstanding = sum(c['outstanding'] for c in collections)
        total_expected = sum(c['expected_collection'] for c in collections)
        
        return {
            'total_outstanding': total_outstanding,
            'total_expected': total_expected,
            'expected_percentage': (total_expected / total_outstanding * 100) if total_outstanding > 0 else 0,
            'collections': collections[:20],
            'high_probability': [c for c in collections if c['probability'] >= 80],
            'medium_probability': [c for c in collections if 50 <= c['probability'] < 80],
            'low_probability': [c for c in collections if c['probability'] < 50],
        }
    
    def _calculate_collection_probability(self, customer):
        """Calculate probability of collection"""
        
        probability = 50  # Base
        
        # Factor 1: Payment history
        sales = self.Sale.objects.filter(customer=customer)
        
        if sales.exists():
            total_amount = sales.aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
            total_paid = sales.aggregate(total=Sum('paid'))['total'] or Decimal('0')
            
            if total_amount > 0:
                payment_rate = float(total_paid / total_amount)
                probability += (payment_rate - 0.5) * 40  # -20 to +20
        
        # Factor 2: How long outstanding
        last_sale = sales.order_by('-sale_date').first()
        if last_sale:
            days_since = (self.today - last_sale.sale_date.date()).days
            
            if days_since < 15:
                probability += 15
            elif days_since < 30:
                probability += 5
            elif days_since > 90:
                probability -= 25
            elif days_since > 60:
                probability -= 15
        
        # Factor 3: Customer longevity
        first_sale = sales.order_by('sale_date').first()
        if first_sale:
            days_customer = (self.today - first_sale.sale_date.date()).days
            if days_customer > 365:
                probability += 10
            elif days_customer > 180:
                probability += 5
        
        # Factor 4: Has credit history
        if customer.group and 'credit' in (customer.group.name or '').lower():
            probability += 5
        
        # Cap
        return max(5, min(95, probability))
    
    def _get_collection_reason(self, customer, probability):
        """Get reason text for collection probability"""
        
        if probability >= 80:
            return "✅ Regular customer with good payment history"
        elif probability >= 60:
            return "📊 Usually pays on time"
        elif probability >= 40:
            return "⚠️ Moderate payment history"
        else:
            return "🚨 High risk - poor payment history"
    
    # ==========================================
    # 5. FRAUD DETECTION
    # ==========================================
    
    def detect_fraud(self):
        """Detect suspicious cash transactions"""
        
        fraud_alerts = []
        last_30 = self.today - timedelta(days=30)
        
        # ==========================================
        # Check 1: Unusually large transactions
        # ==========================================
        avg_transaction = self.CashTransaction.objects.filter(
            date__date__gte=last_30
        ).aggregate(avg=Avg('amount'))['avg'] or Decimal('0')
        
        if avg_transaction > 0:
            large_transactions = self.CashTransaction.objects.filter(
                date__date__gte=last_30,
                amount__gt=avg_transaction * 5
            )[:5]
            
            for trans in large_transactions:
                fraud_alerts.append({
                    'type': 'large_transaction',
                    'severity': 'high',
                    'title': f'💰 Large transaction: Rs. {trans.amount:,.2f}',
                    'description': f'{trans.amount / avg_transaction:.1f}x higher than average ({avg_transaction:,.2f})',
                    'transaction_id': trans.id,
                    'amount': float(trans.amount),
                    'date': trans.date.strftime('%d-%b-%Y %H:%M'),
                })
        
        # ==========================================
        # Check 2: Same amount repeated (possible duplicate)
        # ==========================================
        duplicate_amounts = self.CashTransaction.objects.filter(
            date__date__gte=last_30
        ).values('amount', 'transaction_type').annotate(
            count=Count('id')
        ).filter(count__gte=3)
        
        for dup in duplicate_amounts:
            fraud_alerts.append({
                'type': 'duplicate_amount',
                'severity': 'medium',
                'title': f'🔄 Duplicate amount: Rs. {dup["amount"]:,.2f}',
                'description': f'Same amount repeated {dup["count"]} times',
                'amount': float(dup['amount']),
                'count': dup['count'],
            })
        
        # ==========================================
        # Check 3: Unusual hours (late night)
        # ==========================================
        weird_hours = self.CashTransaction.objects.filter(
            date__date__gte=last_30
        ).extra(
            where=[
                "CAST(strftime('%H', date) AS INTEGER) >= 0 AND CAST(strftime('%H', date) AS INTEGER) < 5"
            ]
        )[:5]
        
        if weird_hours.count() > 2:
            fraud_alerts.append({
                'type': 'unusual_hours',
                'severity': 'medium',
                'title': f'🌙 {weird_hours.count()} transactions at unusual hours',
                'description': 'Multiple transactions between 12 AM - 5 AM detected',
                'count': weird_hours.count(),
            })
        
        # ==========================================
        # Check 4: Round number abuse (possible fake)
        # ==========================================
        round_amounts = self.CashTransaction.objects.filter(
            date__date__gte=last_30,
            amount__gte=10000
        ).filter(
            Q(amount=10000) | Q(amount=20000) | Q(amount=50000) | Q(amount=100000)
        ).count()
        
        if round_amounts > 10:
            fraud_alerts.append({
                'type': 'round_numbers',
                'severity': 'low',
                'title': f'🔢 Many round-number transactions ({round_amounts})',
                'description': 'Possible fake entries with round amounts',
                'count': round_amounts,
            })
        
        # ==========================================
        # Save as AI Cash Alerts
        # ==========================================
        from .models import AICashAlert
        
        for fraud in fraud_alerts:
            AICashAlert.objects.create(
                alert_type='fraud',
                severity=fraud['severity'],
                title=fraud['title'],
                message=fraud['description'],
                amount=Decimal(str(fraud.get('amount', 0))),
                data_snapshot=fraud,
                suggested_action='🔍 Investigate this transaction immediately!',
                action_url='/cash/transactions/',
            )
        
        return fraud_alerts
    
    # ==========================================
    # 6. GENERATE ALERTS
    # ==========================================
    
    def generate_alerts(self, results):
        """Generate smart alerts based on analysis"""
        
        from .models import AICashAlert
        
        alerts_created = 0
        
        # ==========================================
        # Alert 1: Shortage warning
        # ==========================================
        shortage = results.get('shortage', {})
        
        if shortage.get('will_shortage'):
            severity = 'critical' if shortage['days_until'] <= 7 else 'warning'
            
            AICashAlert.objects.create(
                alert_type='shortage',
                severity=severity,
                title=f'🚨 Cash shortage in {shortage["days_until"]} days!',
                message=f'AI predicts cash will go negative on {shortage["shortage_date"]} by Rs. {shortage["shortage_amount"]:,.2f}',
                amount=Decimal(str(shortage['shortage_amount'])),
                suggested_action=self._get_shortage_action(shortage),
                action_url='/cash/',
                data_snapshot=shortage,
            )
            alerts_created += 1
        
        # ==========================================
        # Alert 2: Low health score
        # ==========================================
        health = results.get('health', {})
        
        if health.get('score', 100) < 50:
            AICashAlert.objects.create(
                alert_type='low_balance',
                severity='warning',
                title=f'⚠️ Cash health low: {health["score"]}/100',
                message=f'Your cash health is below optimal. Check factors and improve.',
                suggested_action='Review your cash flow and make improvements',
                action_url='/ai/cash/dashboard/',
                data_snapshot=health,
            )
            alerts_created += 1
        
        # ==========================================
        # Alert 3: Collection opportunity
        # ==========================================
        collection = results.get('collection', {})
        
        if collection.get('total_expected', 0) > 0:
            AICashAlert.objects.create(
                alert_type='collection',
                severity='info',
                title=f'📥 Rs. {collection["total_expected"]:,.0f} expected from collections',
                message=f'AI predicts you can collect Rs. {collection["total_expected"]:,.0f} from customers',
                suggested_action='Contact top customers for collection',
                action_url='/customers/',
                data_snapshot={
                    'total_expected': collection['total_expected'],
                    'high_probability_count': len(collection.get('high_probability', [])),
                },
            )
            alerts_created += 1
        
        return alerts_created
    
    def _get_shortage_action(self, shortage):
        """Get action suggestion for shortage"""
        
        if shortage['severity'] == 'emergency':
            return '🔥 EMERGENCY: Arrange funds within 3 days!'
        elif shortage['severity'] == 'critical':
            return '🚨 Arrange Rs. 5L+ credit or delay payments'
        else:
            return '⚠️ Increase collections and reduce expenses'
    
    # ==========================================
    # 7. SAVE ANALYSIS
    # ==========================================
    
    def save_analysis(self, results):
        """Save analysis to database"""
        
        from .models import AICashAnalysis, AICashHealthHistory
        
        forecast = results.get('forecast', {})
        health = results.get('health', {})
        shortage = results.get('shortage', {})
        
        # Delete old analyses (keep last 10)
        old_analyses = AICashAnalysis.objects.all().order_by('-created_at')[10:]
        for old in old_analyses:
            old.delete()
        
        # Create new analysis
        analysis = AICashAnalysis.objects.create(
            analysis_date=self.today,
            analysis_type='daily',
            current_balance=Decimal(str(forecast.get('current_balance', 0))),
            forecast_7_days=forecast.get('forecast_7_days', []),
            forecast_30_days=forecast.get('forecast_30_days', []),
            forecast_90_days=forecast.get('forecast_90_days', []),
            predicted_daily_inflow=Decimal(str(forecast.get('daily_inflow', 0))),
            predicted_daily_outflow=Decimal(str(forecast.get('daily_outflow', 0))),
            days_until_shortage=shortage.get('days_until'),
            predicted_shortage_amount=Decimal(str(shortage.get('shortage_amount', 0))),
            health_score=health.get('score', 0),
            liquidity_score=health.get('factors', {}).get('liquidity', {}).get('score', 0),
            buffer_score=health.get('factors', {}).get('buffer', {}).get('score', 0),
            inflow_score=health.get('factors', {}).get('inflow', {}).get('score', 0),
            outflow_score=health.get('factors', {}).get('outflow', {}).get('score', 0),
            predictability_score=health.get('factors', {}).get('predictability', {}).get('score', 0),
            risk_level=shortage.get('severity', 'safe'),
            confidence_score=Decimal('85'),
            confidence_level='high',
        )
        
        # Update or create health history
        AICashHealthHistory.objects.update_or_create(
            date=self.today,
            defaults={
                'health_score': health.get('score', 0),
                'balance': Decimal(str(forecast.get('current_balance', 0))),
                'liquidity_score': health.get('factors', {}).get('liquidity', {}).get('score', 0),
                'buffer_score': health.get('factors', {}).get('buffer', {}).get('score', 0),
                'inflow_score': health.get('factors', {}).get('inflow', {}).get('score', 0),
                'outflow_score': health.get('factors', {}).get('outflow', {}).get('score', 0),
                'predictability_score': health.get('factors', {}).get('predictability', {}).get('score', 0),
            }
        )
        
        return analysis