"""
AI Shareholder Engine
Complete AI-powered investor relations with 8 engines
"""

from django.db.models import Sum, Avg, Count, F, Q, Max, Min
from django.utils.timezone import now, localdate
from datetime import timedelta, date, datetime
from decimal import Decimal
from collections import defaultdict
import logging
import statistics

logger = logging.getLogger(__name__)


class AIShareholderEngine:
    """
    AI Engine for Shareholder Module
    
    Features:
    - Dividend optimization
    - Churn prediction
    - Fraud detection
    - Investor scoring
    - Impact simulation
    - Investment suggestions
    - Personalized communication
    - 6-month forecasting
    """
    
    def __init__(self):
        self.today = localdate()
        
        # Import models
        from .models import (
            Shareholder, Share, ShareholderCashBalance, 
            ShareholderCashTransaction, Dividend, BalanceDividend,
            DividendPayment, BalanceDividendPayment, Sale, Purchase,
            CashBalance, ShareTransfer, ShareholderWithdrawalRequest,
            ShareholderDepositRequest
        )
        
        self.Shareholder = Shareholder
        self.Share = Share
        self.ShareholderCashBalance = ShareholderCashBalance
        self.ShareholderCashTransaction = ShareholderCashTransaction
        self.Dividend = Dividend
        self.BalanceDividend = BalanceDividend
        self.DividendPayment = DividendPayment
        self.BalanceDividendPayment = BalanceDividendPayment
        self.Sale = Sale
        self.Purchase = Purchase
        self.CashBalance = CashBalance
        self.ShareTransfer = ShareTransfer
        self.ShareholderWithdrawalRequest = ShareholderWithdrawalRequest
        self.ShareholderDepositRequest = ShareholderDepositRequest
    
    # ==========================================
    # MAIN ANALYSIS
    # ==========================================
    
    def run_full_analysis(self):
        """Run complete shareholder analysis"""
        
        logger.info("🤖 Starting AI Shareholder Analysis...")
        
        results = {
            'success': True,
            'scores_calculated': 0,
            'churn_predictions': 0,
            'fraud_alerts': 0,
            'dividend_recommendation': None,
            'forecast': None,
            'alerts_created': 0,
            'total_shareholders': 0,
            'healthy_shareholders': 0,
            'at_risk_shareholders': 0,
        }
        
        try:
            # 1. Score all shareholders
            scores_count = self.score_all_shareholders()
            results['scores_calculated'] = scores_count
            
            # 2. Predict churn
            churn_count = self.predict_all_churn()
            results['churn_predictions'] = churn_count
            
            # 3. Detect fraud
            fraud_count = self.detect_fraud()
            results['fraud_alerts'] = fraud_count
            
            # 4. Recommend dividend
            recommendation = self.recommend_dividend()
            if recommendation:
                results['dividend_recommendation'] = recommendation.id
            
            # 5. Generate forecast
            forecast = self.generate_forecast()
            if forecast:
                results['forecast'] = forecast.id
            
            # 6. Generate alerts
            alerts = self.generate_alerts()
            results['alerts_created'] = alerts
            
            # Stats
            results['total_shareholders'] = self.Shareholder.objects.filter(status='active').count()
            results['healthy_shareholders'] = self.Shareholder.objects.filter(
                status='active',
                ai_score__overall_score__gte=75
            ).count()
            results['at_risk_shareholders'] = self.Shareholder.objects.filter(
                status='active',
                ai_churn_risk__risk_level__in=['high', 'critical']
            ).count()
            
            logger.info(f"✅ Shareholder Analysis Complete: {results}")
            
        except Exception as e:
            logger.error(f"❌ Shareholder Analysis failed: {e}")
            results['success'] = False
            results['error'] = str(e)
        
        return results
    
    # ==========================================
    # ENGINE 1: INVESTOR SCORING
    # ==========================================
    
    def score_all_shareholders(self):
        """Score all active shareholders (0-100)"""
        
        from .models import AIShareholderScore
        
        count = 0
        shareholders = self.Shareholder.objects.filter(status='active')
        
        for shareholder in shareholders:
            try:
                score_data = self._calculate_score(shareholder)
                
                AIShareholderScore.objects.update_or_create(
                    shareholder=shareholder,
                    defaults=score_data
                )
                count += 1
                
            except Exception as e:
                logger.error(f"Failed to score {shareholder.name}: {e}")
        
        return count
    
    def _calculate_score(self, shareholder):
        """Calculate 5-factor score"""
        
        # ==========================================
        # FACTOR 1: Loyalty (25 points)
        # ==========================================
        first_share = shareholder.shares.order_by('issue_date').first()
        
        if first_share:
            days_as_shareholder = (self.today - first_share.issue_date).days
            years = days_as_shareholder / 365
            
            if years >= 3:
                loyalty_score = 25
            elif years >= 2:
                loyalty_score = 20
            elif years >= 1:
                loyalty_score = 15
            elif years >= 0.5:
                loyalty_score = 10
            else:
                loyalty_score = 5
        else:
            years = 0
            loyalty_score = 0
        
        # ==========================================
        # FACTOR 2: Financial (25 points)
        # ==========================================
        total_investment = float(shareholder.total_investment())
        
        if total_investment >= 1000000:  # 10 lakh+
            financial_score = 25
        elif total_investment >= 500000:
            financial_score = 20
        elif total_investment >= 100000:
            financial_score = 15
        elif total_investment >= 50000:
            financial_score = 10
        else:
            financial_score = 5
        
        # ==========================================
        # FACTOR 3: Activity (20 points)
        # ==========================================
        last_year = self.today - timedelta(days=365)
        
        activities = self.ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            created_at__date__gte=last_year
        ).count()
        
        if activities >= 20:
            activity_score = 20
        elif activities >= 10:
            activity_score = 15
        elif activities >= 5:
            activity_score = 10
        elif activities >= 2:
            activity_score = 5
        else:
            activity_score = 0
        
        # ==========================================
        # FACTOR 4: Growth (15 points)
        # ==========================================
        # Check if investment grew
        recent_sales = self.Sale.objects.filter(
            sale_date__date__gte=last_year
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
        
        # Simple: if business grew, shareholder grew
        if float(recent_sales) > 0:
            # Check YoY
            old_sales = self.Sale.objects.filter(
                sale_date__date__gte=last_year - timedelta(days=365),
                sale_date__date__lt=last_year
            ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
            
            if float(old_sales) > 0:
                growth = ((float(recent_sales) - float(old_sales)) / float(old_sales)) * 100
                
                if growth >= 30:
                    growth_score = 15
                elif growth >= 10:
                    growth_score = 12
                elif growth >= 0:
                    growth_score = 8
                else:
                    growth_score = 5
            else:
                growth_score = 10
        else:
            growth_score = 10
        
        # ==========================================
        # FACTOR 5: Risk (15 points - inverse)
        # ==========================================
        risk_score = 15
        
        # Check for withdrawal requests
        recent_withdrawals = self.ShareholderWithdrawalRequest.objects.filter(
            shareholder=shareholder,
            created_at__date__gte=self.today - timedelta(days=180)
        ).count()
        
        if recent_withdrawals > 3:
            risk_score -= 10
        elif recent_withdrawals > 1:
            risk_score -= 5
        
        # Check for account inactivity
        if activities == 0:
            risk_score -= 10
        
        risk_score = max(0, risk_score)
        
        # ==========================================
        # TOTAL
        # ==========================================
        total_score = loyalty_score + financial_score + activity_score + growth_score + risk_score
        
        # Risk level
        if total_score >= 85:
            risk_level = 'excellent'
        elif total_score >= 65:
            risk_level = 'good'
        elif total_score >= 45:
            risk_level = 'warning'
        else:
            risk_level = 'critical'
        
        # Recommendations
        recommendations = self._get_score_recommendations(
            loyalty_score, financial_score, activity_score, 
            growth_score, risk_score, total_score
        )
        
        return {
            'overall_score': total_score,
            'risk_level': risk_level,
            'loyalty_score': loyalty_score,
            'financial_score': financial_score,
            'activity_score': activity_score,
            'growth_score': growth_score,
            'risk_score': risk_score,
            'years_as_shareholder': round(years, 1),
            'total_investment': Decimal(str(total_investment)),
            'activity_frequency': activities,
            'factors': {
                'loyalty': {'score': loyalty_score, 'max': 25, 'years': round(years, 1)},
                'financial': {'score': financial_score, 'max': 25, 'investment': total_investment},
                'activity': {'score': activity_score, 'max': 20, 'activities': activities},
                'growth': {'score': growth_score, 'max': 15},
                'risk': {'score': risk_score, 'max': 15, 'withdrawals': recent_withdrawals},
            },
            'recommendations': recommendations,
        }
    
    def _get_score_recommendations(self, loyalty, financial, activity, growth, risk, total):
        """Generate recommendations based on scores"""
        recommendations = []
        
        if total >= 85:
            recommendations.append({
                'type': 'appreciation',
                'title': '🌟 Top Investor',
                'description': 'Give bonus dividend or special acknowledgment',
                'priority': 'high'
            })
        
        if activity < 10:
            recommendations.append({
                'type': 'engagement',
                'title': '📱 Re-engagement Needed',
                'description': 'Send personalized message to increase engagement',
                'priority': 'medium'
            })
        
        if risk < 8:
            recommendations.append({
                'type': 'retention',
                'title': '🚨 Retention Required',
                'description': 'Schedule personal call or meeting',
                'priority': 'high'
            })
        
        if financial < 15:
            recommendations.append({
                'type': 'growth',
                'title': '💼 Upsell Opportunity',
                'description': 'Suggest additional investment options',
                'priority': 'medium'
            })
        
        if loyalty < 15:
            recommendations.append({
                'type': 'loyalty',
                'title': '🎁 Loyalty Bonus',
                'description': 'Offer loyalty benefits to build relationship',
                'priority': 'low'
            })
        
        return recommendations
    
    # ==========================================
    # ENGINE 2: CHURN PREDICTION
    # ==========================================
    
    def predict_all_churn(self):
        """Predict churn for all shareholders"""
        
        from .models import AIShareholderChurn
        
        count = 0
        shareholders = self.Shareholder.objects.filter(status='active')
        
        for shareholder in shareholders:
            try:
                churn_data = self._calculate_churn_risk(shareholder)
                
                AIShareholderChurn.objects.update_or_create(
                    shareholder=shareholder,
                    defaults=churn_data
                )
                
                # Create alert if high risk
                if churn_data['risk_level'] in ['high', 'critical']:
                    self._create_churn_alert(shareholder, churn_data)
                
                count += 1
                
            except Exception as e:
                logger.error(f"Failed churn for {shareholder.name}: {e}")
        
        return count
    
    def _calculate_churn_risk(self, shareholder):
        """Calculate churn probability"""
        
        # ==========================================
        # Factor 1: Last Activity
        # ==========================================
        last_transaction = self.ShareholderCashTransaction.objects.filter(
            shareholder=shareholder
        ).order_by('-created_at').first()
        
        if last_transaction:
            days_since_activity = (self.today - last_transaction.created_at.date()).days
        else:
            days_since_activity = 999
        
        # ==========================================
        # Factor 2: Last Deposit
        # ==========================================
        last_deposit = self.ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            transaction_type='deposit'
        ).order_by('-created_at').first()
        
        if last_deposit:
            days_since_deposit = (self.today - last_deposit.created_at.date()).days
        else:
            days_since_deposit = 999
        
        # ==========================================
        # Factor 3: Withdrawal Requests
        # ==========================================
        recent_withdrawals = self.ShareholderWithdrawalRequest.objects.filter(
            shareholder=shareholder,
            created_at__date__gte=self.today - timedelta(days=90)
        ).count()
        
        # ==========================================
        # Factor 4: Recent Deposits
        # ==========================================
        recent_deposits = self.ShareholderCashTransaction.objects.filter(
            shareholder=shareholder,
            transaction_type='deposit',
            created_at__date__gte=self.today - timedelta(days=90)
        ).count()
        
        # ==========================================
        # Calculate Churn Probability
        # ==========================================
        probability = 0
        
        # Days since activity
        if days_since_activity > 180:
            probability += 40
        elif days_since_activity > 120:
            probability += 30
        elif days_since_activity > 90:
            probability += 20
        elif days_since_activity > 60:
            probability += 10
        
        # Days since deposit
        if days_since_deposit > 180:
            probability += 25
        elif days_since_deposit > 90:
            probability += 15
        elif days_since_deposit > 60:
            probability += 5
        
        # Withdrawal requests
        if recent_withdrawals > 2:
            probability += 20
        elif recent_withdrawals > 0:
            probability += 10
        
        # Recent deposits (negative factor)
        if recent_deposits >= 3:
            probability -= 20
        elif recent_deposits >= 1:
            probability -= 10
        
        # Cap
        probability = max(0, min(95, probability))
        
        # Risk level
        if probability >= 70:
            risk_level = 'critical'
        elif probability >= 50:
            risk_level = 'high'
        elif probability >= 30:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        # Risk factors
        risk_factors = []
        if days_since_activity > 90:
            risk_factors.append(f"Inactive for {days_since_activity} days")
        if days_since_deposit > 90:
            risk_factors.append(f"No deposits for {days_since_deposit} days")
        if recent_withdrawals > 2:
            risk_factors.append(f"{recent_withdrawals} withdrawal requests recently")
        
        # Retention actions
        retention_actions = []
        if probability >= 30:
            retention_actions.append("📞 Personal call within 7 days")
            retention_actions.append("💌 Send appreciation message")
        if probability >= 50:
            retention_actions.append("🎁 Offer special bonus dividend")
            retention_actions.append("📊 Show portfolio performance")
        if probability >= 70:
            retention_actions.append("🚨 URGENT: Meet in person")
            retention_actions.append("💰 Consider additional benefits")
        
        # Investment at risk
        investment_at_risk = shareholder.total_investment() * Decimal(str(probability / 100))
        
        return {
            'churn_probability': Decimal(str(probability)),
            'risk_level': risk_level,
            'days_since_last_activity': days_since_activity if days_since_activity < 999 else 0,
            'days_since_last_deposit': days_since_deposit if days_since_deposit < 999 else 0,
            'withdrawal_requests_count': recent_withdrawals,
            'recent_deposits': recent_deposits,
            'risk_factors': risk_factors,
            'retention_actions': retention_actions,
            'investment_at_risk': investment_at_risk,
        }
    
    def _create_churn_alert(self, shareholder, churn_data):
        """Create alert for high churn risk"""
        
        from .models import AIShareholderAlert
        
        # Check if alert already exists
        existing = AIShareholderAlert.objects.filter(
            shareholder=shareholder,
            alert_type='churn',
            is_resolved=False,
            created_at__gte=now() - timedelta(days=7)
        ).exists()
        
        if existing:
            return
        
        severity = 'critical' if churn_data['risk_level'] == 'critical' else 'high'
        
        AIShareholderAlert.objects.create(
            shareholder=shareholder,
            alert_type='churn',
            severity=severity,
            title=f"🚨 {shareholder.name} may leave!",
            message=f"Churn risk: {churn_data['churn_probability']:.0f}%\n"
                    f"Investment at risk: Rs. {churn_data['investment_at_risk']:,.2f}",
            suggested_action="Contact immediately with retention offer",
            action_url=f"/shareholders/{shareholder.id}/",
            amount_involved=churn_data['investment_at_risk'],
            data_snapshot=churn_data,
        )
    
    # ==========================================
    # ENGINE 3: FRAUD DETECTION
    # ==========================================
    
    def detect_fraud(self):
        """Detect suspicious shareholder activities"""
        
        from .models import AIShareholderAlert
        
        alerts_count = 0
        shareholders = self.Shareholder.objects.filter(status='active')
        
        for shareholder in shareholders:
            try:
                # Check 1: Unusual withdrawal pattern
                recent_withdrawals = self.ShareholderWithdrawalRequest.objects.filter(
                    shareholder=shareholder,
                    created_at__date__gte=self.today - timedelta(days=7)
                )
                
                if recent_withdrawals.count() >= 3:
                    AIShareholderAlert.objects.create(
                        shareholder=shareholder,
                        alert_type='fraud',
                        severity='high',
                        title=f"🔒 Multiple withdrawals by {shareholder.name}",
                        message=f"{recent_withdrawals.count()} withdrawals in last 7 days",
                        suggested_action="Verify with shareholder before processing",
                        amount_involved=recent_withdrawals.aggregate(
                            total=Sum('amount')
                        )['total'] or 0,
                    )
                    alerts_count += 1
                
                # Check 2: Sudden large withdrawal
                avg_withdrawal = self.ShareholderWithdrawalRequest.objects.filter(
                    shareholder=shareholder,
                    status='approved'
                ).aggregate(avg=Avg('amount'))['avg'] or Decimal('0')
                
                if avg_withdrawal > 0:
                    large_withdrawal = self.ShareholderWithdrawalRequest.objects.filter(
                        shareholder=shareholder,
                        status='approved',
                        amount__gt=avg_withdrawal * 3,
                        created_at__date__gte=self.today - timedelta(days=30)
                    ).first()
                    
                    if large_withdrawal:
                        AIShareholderAlert.objects.create(
                            shareholder=shareholder,
                            alert_type='fraud',
                            severity='medium',
                            title=f"⚠️ Large withdrawal: {shareholder.name}",
                            message=f"Withdrawal of Rs. {large_withdrawal.amount:,.0f} is 3x larger than average",
                            suggested_action="Verify this transaction",
                            amount_involved=large_withdrawal.amount,
                        )
                        alerts_count += 1
                
                # Check 3: Rapid share transfers
                recent_transfers = self.ShareTransfer.objects.filter(
                    from_shareholder=shareholder,
                    created_at__date__gte=self.today - timedelta(days=30)
                ).count()
                
                if recent_transfers >= 3:
                    AIShareholderAlert.objects.create(
                        shareholder=shareholder,
                        alert_type='fraud',
                        severity='medium',
                        title=f"🔄 Multiple transfers by {shareholder.name}",
                        message=f"{recent_transfers} share transfers in 30 days",
                        suggested_action="Monitor for patterns",
                    )
                    alerts_count += 1
                    
            except Exception as e:
                logger.error(f"Fraud check failed for {shareholder.name}: {e}")
        
        return alerts_count
    
    # ==========================================
    # ENGINE 4: DIVIDEND OPTIMIZER
    # ==========================================
    
    def recommend_dividend(self):
        """Recommend optimal dividend percentage"""
        
        from .models import AIDividendRecommendation
        
        # ==========================================
        # Get current financial situation
        # ==========================================
        
        # Total profit (last 90 days)
        last_90 = self.today - timedelta(days=90)
        
        sales = self.Sale.objects.filter(
            sale_date__date__gte=last_90
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        purchases = self.Purchase.objects.filter(
            pur_date__date__gte=last_90
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        expenses_total = Decimal('0')  # Could add Expense model
        
        total_profit = sales - purchases - expenses_total
        
        # Current cash
        current_cash = self.CashBalance.get_balance()
        
        # ==========================================
        # Calculate recommendation
        # ==========================================
        
        if total_profit <= 0:
            # No profit - can't recommend dividend
            return None
        
        # Monthly expenses (estimated)
        monthly_expense = purchases / 3 if purchases > 0 else Decimal('100000')
        
        # Calculate optimal %
        # Rule: Keep 3 months of expenses + 20% growth buffer
        
        reserve_needed = monthly_expense * 3 * Decimal('1.2')
        
        if current_cash > reserve_needed * 2:
            # Healthy cash - can give more
            recommended_pct = 60
        elif current_cash > reserve_needed * 1.5:
            recommended_pct = 50
        elif current_cash > reserve_needed:
            recommended_pct = 40
        elif current_cash > reserve_needed * 0.7:
            recommended_pct = 30
        else:
            recommended_pct = 20
        
        # Adjust for trend
        # Check if cash is growing
        last_month_cash = self.CashBalance.get_balance()  # Simplified
        
        # Confidence
        confidence = 75
        if total_profit > 100000:
            confidence += 10
        if current_cash > reserve_needed:
            confidence += 5
        
        confidence = min(95, confidence)
        
        # Recommended amount
        recommended_amount = total_profit * Decimal(str(recommended_pct / 100))
        
        # Cash after
        cash_after = current_cash - recommended_amount
        buffer_days = int(cash_after / (monthly_expense / 30)) if monthly_expense > 0 else 0
        
        # Reasoning
        reasoning = [
            f"Total profit (90 days): Rs. {total_profit:,.2f}",
            f"Current cash: Rs. {current_cash:,.2f}",
            f"Monthly expenses: ~Rs. {monthly_expense:,.2f}",
            f"Reserve needed (3 months): Rs. {reserve_needed:,.2f}",
            f"Recommended: {recommended_pct}% = Rs. {recommended_amount:,.2f}",
            f"Cash after payment: Rs. {cash_after:,.2f}",
            f"Buffer: {buffer_days} days",
        ]
        
        # Warnings
        warnings = []
        
        if buffer_days < 30:
            warnings.append(f"⚠️ Buffer only {buffer_days} days")
        
        if cash_after < monthly_expense:
            warnings.append(f"⚠️ Cash after will be less than 1 month expenses")
        
        if recommended_pct < 40:
            warnings.append(f"⚠️ Low dividend may upset shareholders")
        
        if not warnings:
            warnings.append("✅ All safety checks passed")
        
        # Create recommendation
        recommendation = AIDividendRecommendation.objects.create(
            analysis_date=self.today,
            period_start=last_90,
            period_end=self.today,
            recommended_percentage=Decimal(str(recommended_pct)),
            recommended_amount=recommended_amount,
            total_profit=total_profit,
            current_cash=current_cash,
            min_percentage=Decimal('30'),
            max_percentage=Decimal('70'),
            confidence_score=Decimal(str(confidence)),
            reasoning=reasoning,
            warnings=warnings,
            cash_after=cash_after,
            buffer_days=buffer_days,
        )
        
        return recommendation
    
    # ==========================================
    # ENGINE 5: IMPACT SIMULATOR
    # ==========================================
    
    def simulate_dividend_impact(self, percentage):
        """Simulate dividend impact"""
        
        # Get recommendation base
        last_90 = self.today - timedelta(days=90)
        
        sales = self.Sale.objects.filter(
            sale_date__date__gte=last_90
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        purchases = self.Purchase.objects.filter(
            pur_date__date__gte=last_90
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        total_profit = sales - purchases
        current_cash = self.CashBalance.get_balance()
        
        dividend_amount = total_profit * Decimal(str(percentage / 100))
        cash_after = current_cash - dividend_amount
        
        # Distribution breakdown
        shareholders = self.Shareholder.objects.filter(status='active')
        total_shares = sum(s.total_shares() for s in shareholders)
        
        distribution = []
        for sh in shareholders:
            sh_shares = sh.total_shares()
            if sh_shares > 0 and total_shares > 0:
                sh_amount = dividend_amount * Decimal(str(sh_shares / total_shares))
                distribution.append({
                    'name': sh.name,
                    'code': sh.shareholder_code,
                    'shares': sh_shares,
                    'amount': float(sh_amount),
                })
        
        distribution.sort(key=lambda x: x['amount'], reverse=True)
        
        return {
            'percentage': percentage,
            'dividend_amount': float(dividend_amount),
            'cash_before': float(current_cash),
            'cash_after': float(cash_after),
            'distribution_count': len(distribution),
            'top_recipients': distribution[:10],
            'safe': cash_after > 0,
        }
    
    # ==========================================
    # ENGINE 6: INVESTMENT SUGGESTER
    # ==========================================
    
    def suggest_investments(self):
        """Suggest investments to shareholders with idle balance"""
        
        suggestions = []
        
        shareholders = self.Shareholder.objects.filter(status='active')
        
        for shareholder in shareholders:
            balance = shareholder.get_balance()
            
            # Idle if balance > 50K and no deposit in 60 days
            if balance > 50000:
                last_deposit = self.ShareholderCashTransaction.objects.filter(
                    shareholder=shareholder,
                    transaction_type='deposit'
                ).order_by('-created_at').first()
                
                if last_deposit:
                    days_since = (self.today - last_deposit.created_at.date()).days
                else:
                    days_since = 999
                
                if days_since > 60:
                    suggestions.append({
                        'shareholder_id': shareholder.id,
                        'name': shareholder.name,
                        'code': shareholder.shareholder_code,
                        'balance': float(balance),
                        'days_idle': days_since,
                        'potential_return': float(balance) * 0.15,  # 15% return
                        'suggestion': 'Offer 15% fixed return',
                    })
        
        suggestions.sort(key=lambda x: x['balance'], reverse=True)
        
        return suggestions
    
    # ==========================================
    # ENGINE 7: COMMUNICATION AI
    # ==========================================
    
    def generate_retention_message(self, shareholder):
        """Generate personalized retention message"""
        
        balance = shareholder.get_balance()
        shares = shareholder.total_shares()
        
        message = f"""Assalam-o-Alaikum {shareholder.name}!

🌟 Aapka {shareholder.shareholder_code} account ke liye shukriya!

📊 Aapki current position:
• Shares: {shares:,}
• Cash Balance: Rs. {balance:,.2f}
• Total Investment: Rs. {shareholder.total_investment():,.2f}

💡 Hum aapko kuch special offers dena chahte hain:
✅ Bonus dividend eligibility
✅ Priority support
✅ Free account review

📞 Please call for more details.

Thank you for your trust!

Regards,
[Business Name]"""
        
        return message
    
    def generate_appreciation_message(self, shareholder):
        """Generate appreciation message for loyal shareholder"""
        
        years = 0
        first_share = shareholder.shares.order_by('issue_date').first()
        if first_share:
            years = (self.today - first_share.issue_date).days / 365
        
        message = f"""🌟 Assalam-o-Alaikum {shareholder.name}!

🎉 Aapko {years:.0f} saal ki loyalty ke liye special thanks!

📊 Aapki journey:
• {years:.1f} years with us
• {shareholder.total_shares():,} shares
• Rs. {shareholder.total_investment():,.2f} investment

💐 Aap humare top shareholders mein se hain!

🎁 Aap 15% bonus return ke haqdar hain!

Regards,
[Business Name]"""
        
        return message
    
    # ==========================================
    # ENGINE 8: FORECAST
    # ==========================================
    
    def generate_forecast(self):
        """Generate 6-month forecast"""
        
        from .models import AIShareholderForecast
        
        # Current stats
        current_count = self.Shareholder.objects.filter(status='active').count()
        current_investment = sum(
            s.total_investment() 
            for s in self.Shareholder.objects.filter(status='active')
        )
        
        # Historical trend
        six_months_ago = self.today - timedelta(days=180)
        
        # New shareholders last 6 months
        new_six_months = self.Shareholder.objects.filter(
            created_at__date__gte=six_months_ago
        ).count()
        
        # Monthly average
        monthly_new = new_six_months / 6
        
        # Churn rate
        churn_count = self.Shareholder.objects.filter(
            status='inactive',
            updated_at__date__gte=six_months_ago
        ).count()
        
        monthly_churn = churn_count / 6
        
        # 6-month forecast
        monthly_forecast = []
        running_count = current_count
        
        for i in range(1, 7):
            forecast_date = self.today + timedelta(days=30 * i)
            running_count = running_count + monthly_new - monthly_churn
            
            monthly_forecast.append({
                'month': forecast_date.strftime('%b %Y'),
                'expected_shareholders': int(running_count),
                'new_expected': round(monthly_new, 1),
                'churn_expected': round(monthly_churn, 1),
            })
        
        # Total expected
        expected_new = monthly_new * 6
        expected_churn = monthly_churn * 6
        expected_total = current_count + expected_new - expected_churn
        
        # Confidence
        confidence = 70
        if current_count > 20:
            confidence += 10
        if new_six_months > 5:
            confidence += 10
        
        confidence = min(90, confidence)
        
        # Risks
        risks = []
        if monthly_churn > monthly_new:
            risks.append("⚠️ Churn rate higher than growth")
        if current_count < 10:
            risks.append("⚠️ Small shareholder base")
        
        # Opportunities
        opportunities = []
        if monthly_new > 1:
            opportunities.append(f"📈 Adding {monthly_new:.1f} shareholders/month")
        if current_investment > 1000000:
            opportunities.append("💰 Strong investment base")
        
        forecast = AIShareholderForecast.objects.create(
            forecast_date=self.today,
            total_shareholders=int(expected_total),
            new_shareholders_expected=int(expected_new),
            churn_expected=int(expected_churn),
            total_investment=current_investment * Decimal('1.15'),  # 15% growth assumption
            total_dividends=current_investment * Decimal('0.08'),
            confidence_score=Decimal(str(confidence)),
            monthly_forecast=monthly_forecast,
            risks=risks,
            opportunities=opportunities,
        )
        
        return forecast
    
    # ==========================================
    # ALERTS GENERATOR
    # ==========================================
    
    def generate_alerts(self):
        """Generate all types of alerts"""
        
        from .models import AIShareholderAlert
        
        count = 0
        
        # Milestone alerts - Top shareholders
        top_shareholders = sorted(
            self.Shareholder.objects.filter(status='active'),
            key=lambda s: s.total_investment(),
            reverse=True
        )[:5]
        
        for shareholder in top_shareholders:
            investment = shareholder.total_investment()
            
            # Check if milestone crossed
            milestones = [100000, 500000, 1000000, 5000000]
            
            for milestone in milestones:
                if float(investment) >= milestone:
                    # Check if alert already exists
                    existing = AIShareholderAlert.objects.filter(
                        shareholder=shareholder,
                        alert_type='milestone',
                        data_snapshot__milestone=milestone,
                        created_at__gte=now() - timedelta(days=30)
                    ).exists()
                    
                    if not existing:
                        AIShareholderAlert.objects.create(
                            shareholder=shareholder,
                            alert_type='milestone',
                            severity='info',
                            title=f"🎉 {shareholder.name} crossed Rs. {milestone:,}!",
                            message=f"Investment milestone achieved: Rs. {investment:,.2f}",
                            suggested_action="Send appreciation message",
                            amount_involved=investment,
                            data_snapshot={'milestone': milestone},
                        )
                        count += 1
                    break
        
        return count