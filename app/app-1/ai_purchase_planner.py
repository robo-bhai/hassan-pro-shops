"""
AI-Powered Purchase Planner Engine
Smart recommendations for monthly purchase planning
"""

from django.db.models import Sum, Avg, Count, F, Q, Max
from django.utils.timezone import now, localdate
from datetime import timedelta, date, datetime
from decimal import Decimal
from collections import defaultdict
import logging
import statistics
import math

logger = logging.getLogger(__name__)


class AIPurchasePlanner:
    """
    AI Engine for Monthly Purchase Planning
    
    Features:
    - Smart quantity suggestions
    - Confidence scoring
    - Risk assessment
    - Cash flow impact
    - Seasonal analysis
    - Trend detection
    """
    
    def __init__(self, product, warehouse=None):
        self.product = product
        self.warehouse = warehouse
        self.today = localdate()
        self.analysis_days = 90  # Last 90 days analysis
        
        # Import models
        from .models import (
            SaleItem, Inventory, StockBatch, PurchaseItem,
            CashBalance, Shareholder, SystemSetting
        )
        
        self.SaleItem = SaleItem
        self.Inventory = Inventory
        self.StockBatch = StockBatch
        self.PurchaseItem = PurchaseItem
        self.CashBalance = CashBalance
        self.Shareholder = Shareholder
        self.SystemSetting = SystemSetting
    
    # ==========================================
    # MAIN ANALYSIS METHOD
    # ==========================================
    
    def analyze(self):
        """Run complete AI analysis"""
        
        logger.info(f"🤖 AI Analysis for: {self.product.name}")
        
        try:
            # 1. Get sales data
            sales_data = self._get_sales_data()
            
            # 2. Calculate velocity
            velocity = self._calculate_velocity(sales_data)
            
            # 3. Analyze trend
            trend = self._analyze_trend(sales_data)
            
            # 4. Get current stock
            stock_data = self._get_stock_data()
            
            # 5. Calculate stock coverage
            coverage = self._calculate_coverage(stock_data['available'], velocity['recent'])
            
            # 6. Suggest optimal quantity
            suggested = self._suggest_quantity(velocity, stock_data, trend)
            
            # 7. Calculate confidence
            confidence = self._calculate_confidence(
                sales_data, velocity, trend, stock_data
            )
            
            # 8. Calculate cost & cash impact
            financial = self._calculate_financial(suggested['quantity'])
            
            # 9. Assess risks
            risks = self._assess_risks(
                velocity, stock_data, trend, financial, suggested
            )
            
            # 10. Generate reasoning
            reasoning = self._generate_reasoning(
                velocity, stock_data, trend, suggested, financial
            )
            
            # 11. Find opportunities
            opportunities = self._find_opportunities(velocity, trend, stock_data)
            
            # 12. Get seasonal factor
            seasonal = self._get_seasonal_factor()
            
            # Build result
            result = {
                'success': True,
                'product_id': self.product.id,
                'product_name': self.product.name,
                
                # Quantity
                'suggested_quantity': suggested['quantity'],
                'min_quantity': suggested['min_quantity'],
                'max_quantity': suggested['max_quantity'],
                'is_urgent': suggested['is_urgent'],
                
                # Analysis
                'avg_daily_sales': float(velocity['average']),
                'recent_daily_sales': float(velocity['recent']),
                'sales_trend': float(trend['percentage']),
                'trend_direction': trend['direction'],
                
                # Stock
                'current_stock': stock_data['current'],
                'reserved_stock': stock_data['reserved'],
                'available_stock': stock_data['available'],
                'stock_coverage_days': coverage,
                
                # Confidence
                'confidence_score': confidence['score'],
                'confidence_level': confidence['level'],
                'confidence_reasons': confidence['reasons'],
                
                # Financial
                'unit_cost': float(financial['unit_cost']),
                'estimated_cost': float(financial['total_cost']),
                'cash_before': float(financial['cash_before']),
                'cash_after': float(financial['cash_after']),
                'margin_percentage': float(financial['margin']),
                
                # Risk
                'risk_level': risks['level'],
                'risk_factors': risks['factors'],
                'warnings': risks['warnings'],
                
                # Reasoning
                'reasoning': reasoning,
                'opportunities': opportunities,
                
                # Seasonal
                'seasonal_factor': float(seasonal['factor']),
                'seasonal_note': seasonal['note'],
                
                # Historical
                'historical_sales': sales_data['monthly'],
                
                # Timestamp
                'analyzed_at': now().isoformat(),
            }
            
            logger.info(f"✅ Analysis complete: {suggested['quantity']} units ({confidence['score']}% confidence)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ AI Analysis failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }
    
    # ==========================================
    # 1. GET SALES DATA
    # ==========================================
    
    def _get_sales_data(self):
        """Get historical sales data"""
        
        start_date = self.today - timedelta(days=self.analysis_days)
        
        # Get all sales
        sales = self.SaleItem.objects.filter(
            product=self.product,
            sale__sale_date__date__gte=start_date
        ).values(
            'sale__sale_date__date',
            'qty',
            'price',
            'total_amt'
        ).order_by('sale__sale_date__date')
        
        # Group by month
        monthly = defaultdict(lambda: {'qty': 0, 'amount': 0, 'orders': 0})
        
        for sale in sales:
            month_key = sale['sale__sale_date__date'].strftime('%Y-%m')
            monthly[month_key]['qty'] += float(sale['qty'])
            monthly[month_key]['amount'] += float(sale['total_amt'])
            monthly[month_key]['orders'] += 1
        
        # Get last 30 days daily
        last_30 = self.today - timedelta(days=30)
        recent_sales = self.SaleItem.objects.filter(
            product=self.product,
            sale__sale_date__date__gte=last_30
        ).values('sale__sale_date__date').annotate(
            qty=Sum('qty')
        ).order_by('sale__sale_date__date')
        
        daily_recent = {}
        for r in recent_sales:
            daily_recent[r['sale__sale_date__date'].strftime('%Y-%m-%d')] = float(r['qty'])
        
        # Get last 90 days daily
        last_90 = self.today - timedelta(days=90)
        older_sales = self.SaleItem.objects.filter(
            product=self.product,
            sale__sale_date__date__gte=last_90,
            sale__sale_date__date__lt=last_30
        ).values('sale__sale_date__date').annotate(
            qty=Sum('qty')
        ).order_by('sale__sale_date__date')
        
        daily_older = {}
        for r in older_sales:
            daily_older[r['sale__sale_date__date'].strftime('%Y-%m-%d')] = float(r['qty'])
        
        # Convert monthly to list
        monthly_list = []
        for month_key in sorted(monthly.keys()):
            data = monthly[month_key]
            monthly_list.append({
                'month': month_key,
                'qty': data['qty'],
                'amount': data['amount'],
                'orders': data['orders'],
            })
        
        return {
            'total_orders': sales.count(),
            'monthly': monthly_list,
            'daily_recent': daily_recent,
            'daily_older': daily_older,
            'total_qty': sum(s['qty'] for s in sales),
        }
    
    # ==========================================
    # 2. CALCULATE VELOCITY
    # ==========================================
    
    def _calculate_velocity(self, sales_data):
        """Calculate sales velocity (units/day)"""
        
        # Average over 90 days
        total_qty_90 = sum(m['qty'] for m in sales_data['monthly'])
        avg_daily = total_qty_90 / self.analysis_days if self.analysis_days > 0 else 0
        
        # Recent (last 30 days)
        recent_total = sum(sales_data['daily_recent'].values())
        recent_daily = recent_total / 30 if recent_total > 0 else 0
        
        # Weighted average (recent gets more weight)
        weighted_daily = (avg_daily * 0.3) + (recent_daily * 0.7)
        
        return {
            'average': Decimal(str(round(avg_daily, 2))),
            'recent': Decimal(str(round(recent_daily, 2))),
            'weighted': Decimal(str(round(weighted_daily, 2))),
        }
    
    # ==========================================
    # 3. ANALYZE TREND
    # ==========================================
    
    def _analyze_trend(self, sales_data):
        """Analyze sales trend"""
        
        monthly = sales_data['monthly']
        
        if len(monthly) < 2:
            return {
                'percentage': 0,
                'direction': 'stable',
                'strength': 'unknown',
            }
        
        # Get last 3 months
        recent_months = monthly[-3:] if len(monthly) >= 3 else monthly
        older_months = monthly[:-3] if len(monthly) > 3 else monthly[:-1]
        
        recent_avg = sum(m['qty'] for m in recent_months) / len(recent_months)
        older_avg = sum(m['qty'] for m in older_months) / len(older_months) if older_months else recent_avg
        
        if older_avg > 0:
            change = ((recent_avg - older_avg) / older_avg) * 100
        else:
            change = 0
        
        # Direction
        if change > 10:
            direction = 'up'
            strength = 'strong' if change > 30 else 'moderate'
        elif change < -10:
            direction = 'down'
            strength = 'strong' if change < -30 else 'moderate'
        else:
            direction = 'stable'
            strength = 'stable'
        
        return {
            'percentage': Decimal(str(round(change, 2))),
            'direction': direction,
            'strength': strength,
        }
    
    # ==========================================
    # 4. GET STOCK DATA
    # ==========================================
    
    def _get_stock_data(self):
        """Get current stock information"""
        
        if self.warehouse:
            inventory = self.Inventory.objects.filter(
                product=self.product,
                warehouse=self.warehouse
            ).first()
        else:
            # Get total across all warehouses
            inventories = self.Inventory.objects.filter(product=self.product)
            current = sum(inv.stock for inv in inventories)
            reserved = sum(inv.reserved_stock for inv in inventories)
            
            return {
                'current': current,
                'reserved': reserved,
                'available': current - reserved,
            }
        
        if inventory:
            return {
                'current': inventory.stock,
                'reserved': inventory.reserved_stock,
                'available': inventory.stock - inventory.reserved_stock,
            }
        
        return {'current': 0, 'reserved': 0, 'available': 0}
    
    # ==========================================
    # 5. CALCULATE COVERAGE
    # ==========================================
    
    def _calculate_coverage(self, available_stock, daily_velocity):
        """Calculate how many days stock will last"""
        
        if daily_velocity <= 0:
            return 999
        
        coverage = float(available_stock) / float(daily_velocity)
        return int(coverage)
    
    # ==========================================
    # 6. SUGGEST QUANTITY (MAIN LOGIC)
    # ==========================================
    
    def _suggest_quantity(self, velocity, stock_data, trend):
        """
        Suggest optimal purchase quantity
        
        Formula:
        - Target coverage: 45 days (1.5 months)
        - Consider trend
        - Consider current stock
        """
        
        daily_velocity = float(velocity['weighted'])
        available = stock_data['available']
        trend_pct = float(trend['percentage'])
        
        # ==========================================
        # STEP 1: Calculate target stock
        # ==========================================
        # Base: 45 days coverage
        base_days = 45
        
        # Adjust for trend
        if trend['direction'] == 'up':
            base_days += int(trend_pct / 2)  # Increase for growing demand
        elif trend['direction'] == 'down':
            base_days -= int(abs(trend_pct) / 3)  # Decrease for declining
        
        # Ensure minimum 15 days, max 90 days
        base_days = max(15, min(90, base_days))
        
        # Target stock
        target_stock = daily_velocity * base_days
        
        # ==========================================
        # STEP 2: Calculate required purchase
        # ==========================================
        required = target_stock - available
        
        # ==========================================
        # STEP 3: Apply safety margins
        # ==========================================
        if required <= 0:
            # Stock sufficient
            suggested = 0
            min_qty = 0
            max_qty = 0
            is_urgent = False
        else:
            # Add 10% buffer
            suggested = required * 1.1
            min_qty = required * 0.8  # Can do 80%
            max_qty = required * 1.3  # Can do up to 130%
            is_urgent = available < (daily_velocity * 15)  # Less than 15 days
        
        # Round to nearest whole number
        suggested = max(0, int(round(suggested)))
        min_qty = max(0, int(round(min_qty)))
        max_qty = max(0, int(round(max_qty)))
        
        # ==========================================
        # STEP 4: Seasonal adjustment
        # ==========================================
        seasonal = self._get_seasonal_factor()
        if seasonal['factor'] != 1.0:
            suggested = int(suggested * float(seasonal['factor']))
        
        return {
            'quantity': suggested,
            'min_quantity': min_qty,
            'max_quantity': max_qty,
            'is_urgent': is_urgent,
            'target_days': base_days,
            'target_stock': int(target_stock),
        }
    
    # ==========================================
    # 7. CALCULATE CONFIDENCE
    # ==========================================
    
    def _calculate_confidence(self, sales_data, velocity, trend, stock_data):
        """
        Calculate confidence score (0-100%)
        
        Factors:
        - Data availability (40%)
        - Trend stability (30%)
        - Velocity consistency (30%)
        """
        
        score = 0
        reasons = []
        
        # ==========================================
        # Factor 1: Data availability (40 points)
        # ==========================================
        months_data = len(sales_data['monthly'])
        
        if months_data >= 6:
            score += 40
            reasons.append("✅ 6+ months of historical data")
        elif months_data >= 3:
            score += 30
            reasons.append("✅ 3+ months of data available")
        elif months_data >= 1:
            score += 15
            reasons.append("⚠️ Only recent data available")
        else:
            score += 0
            reasons.append("❌ No historical data")
        
        # ==========================================
        # Factor 2: Trend stability (30 points)
        # ==========================================
        trend_strength = trend['strength']
        
        if trend_strength == 'stable':
            score += 30
            reasons.append("✅ Stable sales pattern")
        elif trend_strength == 'moderate':
            score += 20
            reasons.append("📊 Moderate trend detected")
        else:
            score += 10
            reasons.append("⚠️ Volatile sales pattern")
        
        # ==========================================
        # Factor 3: Velocity consistency (30 points)
        # ==========================================
        daily_values = list(sales_data['daily_recent'].values())
        
        if len(daily_values) >= 10:
            try:
                stdev = statistics.stdev(daily_values)
                mean = statistics.mean(daily_values)
                
                if mean > 0:
                    cv = stdev / mean  # Coefficient of variation
                    
                    if cv < 0.5:
                        score += 30
                        reasons.append("✅ Consistent daily sales")
                    elif cv < 1.0:
                        score += 20
                        reasons.append("📊 Some daily variation")
                    else:
                        score += 10
                        reasons.append("⚠️ High daily variation")
                else:
                    score += 15
            except:
                score += 15
        else:
            score += 15
            reasons.append("⚠️ Limited recent data")
        
        # ==========================================
        # Determine level
        # ==========================================
        if score >= 85:
            level = 'high'
        elif score >= 60:
            level = 'medium'
        else:
            level = 'low'
        
        return {
            'score': Decimal(str(round(score, 1))),
            'level': level,
            'reasons': reasons,
        }
    
    # ==========================================
    # 8. CALCULATE FINANCIAL
    # ==========================================
    
    def _calculate_financial(self, quantity):
        """Calculate financial impact"""
        
        # Get unit cost (latest batch price or last purchase)
        latest_batch = self.StockBatch.objects.filter(
            product=self.product
        ).order_by('-id').first()
        
        if latest_batch:
            unit_cost = Decimal(str(latest_batch.price))
        else:
            unit_cost = self.product.price
        
        total_cost = unit_cost * Decimal(str(quantity))
        
        # Current cash
        cash_before = self.CashBalance.get_balance()
        cash_after = cash_before - total_cost
        
        # Calculate margin
        if unit_cost > 0:
            selling_price = latest_batch.selling_price if latest_batch else self.product.price
            if selling_price > 0:
                margin = ((selling_price - unit_cost) / unit_cost) * 100
            else:
                margin = Decimal('0')
        else:
            margin = Decimal('0')
        
        return {
            'unit_cost': unit_cost,
            'total_cost': total_cost,
            'cash_before': cash_before,
            'cash_after': cash_after,
            'margin': margin,
        }
    
    # ==========================================
    # 9. ASSESS RISKS
    # ==========================================
    
    def _assess_risks(self, velocity, stock_data, trend, financial, suggested):
        """Assess purchase risks"""
        
        risks = []
        warnings = []
        risk_level = 'safe'
        
        # ==========================================
        # Risk 1: Cash shortage
        # ==========================================
        if financial['cash_after'] < 0:
            risks.append('cash_shortage')
            warnings.append(
                f"🚨 Cash will go NEGATIVE after purchase! "
                f"Available: Rs. {financial['cash_before']:,.2f}, "
                f"Required: Rs. {financial['total_cost']:,.2f}"
            )
            risk_level = 'danger'
        elif financial['cash_after'] < financial['cash_before'] * Decimal('0.2'):
            risks.append('low_cash_after')
            warnings.append(
                f"⚠️ Cash will be tight after purchase. "
                f"Remaining: Rs. {financial['cash_after']:,.2f}"
            )
            if risk_level != 'danger':
                risk_level = 'warning'
        
        # ==========================================
        # Risk 2: Overstock
        # ==========================================
        coverage = self._calculate_coverage(
            stock_data['available'] + suggested['quantity'],
            velocity['weighted']
        )
        
        if coverage > 120:  # More than 4 months
            risks.append('overstock')
            warnings.append(
                f"⚠️ Overstock risk! Stock will last {coverage} days (4+ months)"
            )
            if risk_level != 'danger':
                risk_level = 'warning'
        
        # ==========================================
        # Risk 3: Declining sales
        # ==========================================
        if trend['direction'] == 'down' and abs(float(trend['percentage'])) > 30:
            risks.append('declining_sales')
            warnings.append(
                f"⚠️ Sales declining by {abs(float(trend['percentage'])):.1f}%! "
                f"Consider smaller order."
            )
            if risk_level != 'danger':
                risk_level = 'warning'
        
        # ==========================================
        # Risk 4: High cost
        # ==========================================
        cash_ratio = float(financial['total_cost']) / float(financial['cash_before']) if financial['cash_before'] > 0 else 1
        if cash_ratio > 0.5:
            risks.append('high_cost')
            warnings.append(
                f"⚠️ Purchase is {cash_ratio*100:.0f}% of available cash"
            )
        
        # ==========================================
        # Risk 5: Low margin
        # ==========================================
        if 0 < financial['margin'] < 10:
            risks.append('low_margin')
            warnings.append(
                f"⚠️ Low profit margin: {financial['margin']:.1f}%"
            )
        
        # ==========================================
        # Positive factors
        # ==========================================
        if not warnings:
            warnings.append("✅ No major risks detected. Safe to purchase!")
        
        return {
            'level': risk_level,
            'factors': risks,
            'warnings': warnings,
        }
    
    # ==========================================
    # 10. GENERATE REASONING
    # ==========================================
    
    def _generate_reasoning(self, velocity, stock_data, trend, suggested, financial):
        """Generate human-readable reasoning"""
        
        reasoning = []
        
        # Sales velocity
        reasoning.append(
            f"📊 Average daily sales: {float(velocity['weighted']):.1f} units/day"
        )
        
        # Recent trend
        trend_pct = float(trend['percentage'])
        if trend['direction'] == 'up':
            reasoning.append(f"📈 Sales growing {trend_pct:+.1f}% (trending UP)")
        elif trend['direction'] == 'down':
            reasoning.append(f"📉 Sales declining {trend_pct:+.1f}% (trending DOWN)")
        else:
            reasoning.append(f"➡️ Sales stable ({trend_pct:+.1f}%)")
        
        # Stock position
        available = stock_data['available']
        daily = float(velocity['weighted'])
        coverage = int(available / daily) if daily > 0 else 999
        
        reasoning.append(
            f"📦 Current stock: {available} units (~{coverage} days coverage)"
        )
        
        # Suggested quantity
        reasoning.append(
            f"🎯 Target coverage: {suggested['target_days']} days = {suggested['target_stock']} units"
        )
        reasoning.append(
            f"✅ Suggested order: {suggested['quantity']} units"
        )
        
        # Financial
        reasoning.append(
            f"💰 Estimated cost: Rs. {financial['total_cost']:,.2f}"
        )
        
        # Margin
        if financial['margin'] > 0:
            reasoning.append(
                f"📈 Profit margin: {financial['margin']:.1f}%"
            )
        
        return reasoning
    
    # ==========================================
    # 11. FIND OPPORTUNITIES
    # ==========================================
    
    def _find_opportunities(self, velocity, trend, stock_data):
        """Find purchase opportunities"""
        
        opportunities = []
        
        # Opportunity 1: Fast growth
        if trend['direction'] == 'up' and float(trend['percentage']) > 20:
            opportunities.append({
                'type': 'growth',
                'title': '📈 High Growth Product',
                'description': f'Sales growing {float(trend["percentage"]):.0f}%! Stock up more.',
                'action': 'Increase order quantity',
            })
        
        # Opportunity 2: Low stock + high demand
        if stock_data['available'] < 10 and float(velocity['weighted']) > 0:
            opportunities.append({
                'type': 'urgent',
                'title': '🚨 Urgent Reorder',
                'description': 'Very low stock with good demand',
                'action': 'Order immediately',
            })
        
        # Opportunity 3: Stable high seller
        if trend['strength'] == 'stable' and float(velocity['weighted']) > 10:
            opportunities.append({
                'type': 'reliable',
                'title': '✅ Reliable Product',
                'description': 'Consistent high sales - safe investment',
                'action': 'Regular ordering recommended',
            })
        
        return opportunities
    
    # ==========================================
    # 12. SEASONAL FACTOR
    # ==========================================
    
    def _get_seasonal_factor(self):
        """Get seasonal adjustment factor"""
        
        month = self.today.month
        
        # Ramadan/Eid effect (approximate)
        # Ramadan typically moves, but let's use common months
        # For Pakistan market
        
        # Winter (Nov-Feb): Higher for warm clothes/blankets
        # Summer (May-Jul): Higher for cold items
        
        factors = {
            1: {'factor': 1.0, 'note': 'Normal month'},
            2: {'factor': 1.0, 'note': 'Normal month'},
            3: {'factor': 1.15, 'note': 'Spring - moderate demand'},
            4: {'factor': 1.0, 'note': 'Normal month'},
            5: {'factor': 1.1, 'note': 'Summer starts'},
            6: {'factor': 1.2, 'note': 'Peak summer'},
            7: {'factor': 1.15, 'note': 'Monsoon season'},
            8: {'factor': 1.0, 'note': 'Normal month'},
            9: {'factor': 1.0, 'note': 'Normal month'},
            10: {'factor': 1.05, 'note': 'Pre-winter'},
            11: {'factor': 1.1, 'note': 'Winter starts'},
            12: {'factor': 1.2, 'note': 'Peak winter'},
        }
        
        return factors.get(month, {'factor': 1.0, 'note': 'Normal month'})
    
    # ==========================================
    # SAVE ANALYSIS
    # ==========================================
    
    def save_analysis(self, plan=None):
        """Save analysis to database"""
        
        from .models import AIPurchaseAnalysis
        
        result = self.analyze()
        
        if not result['success']:
            return None
        
        # Delete old analyses for this product (keep last 5)
        old_analyses = AIPurchaseAnalysis.objects.filter(
            product=self.product
        ).order_by('-created_at')[5:]
        
        for old in old_analyses:
            old.delete()
        
        # Create new analysis
        analysis = AIPurchaseAnalysis.objects.create(
            plan=plan,
            product=self.product,
            warehouse=self.warehouse,
            suggested_quantity=result['suggested_quantity'],
            min_quantity=result['min_quantity'],
            max_quantity=result['max_quantity'],
            confidence_score=result['confidence_score'],
            confidence_level=result['confidence_level'],
            avg_daily_sales=result['avg_daily_sales'],
            current_stock=result['current_stock'],
            stock_coverage_days=result['stock_coverage_days'],
            sales_trend=result['sales_trend'],
            risk_level=result['risk_level'],
            risk_factors=result['risk_factors'],
            estimated_cost=result['estimated_cost'],
            cash_after_purchase=result['cash_after'],
            margin_percentage=result['margin_percentage'],
            reasoning=result['reasoning'],
            warnings=result['warnings'],
            opportunities=result['opportunities'],
        )
        
        return analysis