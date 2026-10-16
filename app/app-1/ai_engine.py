"""
AI-Powered Self-Diagnostic Engine
Complete implementation with 5 AI engines
"""

from django.db.models import Sum, Count, Avg, F, Q
from django.utils.timezone import now
from datetime import timedelta, date
from decimal import Decimal
import logging
import statistics

logger = logging.getLogger(__name__)


class AIEngine:
    """
    Main AI Engine that runs all diagnostic checks
    """
    
    def __init__(self):
        self.insights = []
        self.predictions = []
        self.anomalies = []
    
    def run_full_analysis(self):
        """Run complete AI analysis"""
        logger.info("🤖 Starting AI Analysis...")
        
        # Run all engines
        self.run_data_quality_engine()
        self.run_business_intelligence_engine()
        self.run_performance_engine()
        self.run_security_engine()
        self.run_usability_engine()
        
        # Save all insights
        saved_count = self.save_insights()
        
        # Calculate health score
        score = self.calculate_health_score()
        
        logger.info(f"✅ AI Analysis Complete: {saved_count} insights, Score: {score}")
        
        return {
            'insights_count': saved_count,
            'health_score': score,
            'insights': self.insights,
            'predictions': self.predictions,
            'anomalies': self.anomalies,
        }
    
    def save_insights(self):
        """Save all insights to database"""
        from .models import AIInsight
        
        count = 0
        for insight_data in self.insights:
            # Check if similar insight exists
            existing = AIInsight.objects.filter(
                title=insight_data['title'],
                is_resolved=False,
                detected_at__gte=now() - timedelta(days=1)
            ).first()
            
            if not existing:
                AIInsight.objects.create(**insight_data)
                count += 1
        
        return count
    
    def calculate_health_score(self):
        """Calculate overall health score"""
        from .models import AIInsight
        
        # Get active insights
        active = AIInsight.objects.filter(is_resolved=False, is_ignored=False)
        
        # Calculate score
        critical = active.filter(severity='critical').count()
        high = active.filter(severity='high').count()
        medium = active.filter(severity='medium').count()
        low = active.filter(severity='low').count()
        
        # Deduct points
        score = 100
        score -= critical * 10
        score -= high * 5
        score -= medium * 2
        score -= low * 1
        
        return max(0, score)
    
    # ============================================
    # ENGINE 1: DATA QUALITY
    # ============================================
    
    def run_data_quality_engine(self):
        """AI-powered data quality analysis"""
        logger.info("📊 Running Data Quality Engine...")
        
        from .models import (
            Product, Customer, Vendor, Inventory, 
            Sale, Purchase, SaleItem, PurchaseItem
        )
        
        # Check 1: Negative stocks
        negative_stocks = Inventory.objects.filter(stock__lt=0)
        if negative_stocks.exists():
            self.insights.append({
                'insight_type': 'anomaly',
                'category': 'data_quality',
                'severity': 'critical',
                'title': f'🔴 {negative_stocks.count()} products with negative stock',
                'description': f'AI detected {negative_stocks.count()} products with invalid negative stock values. This indicates data integrity issues.',
                'confidence_score': 100,
                'impact_score': 90,
                'affected_records': negative_stocks.count(),
                'affected_value': sum(abs(inv.stock * inv.product.price) for inv in negative_stocks),
                'recommendation': 'Fix stock records immediately. Check recent transactions for these products.',
                'suggested_actions': [
                    'Review last 10 transactions for affected products',
                    'Correct stock manually via Stock Adjustment',
                    'Investigate if system glitch or user error',
                ],
                'fix_url': '/inventory/?filter=negative',
                'data_snapshot': {
                    'product_ids': list(negative_stocks.values_list('product_id', flat=True)[:20])
                }
            })
        
        # Check 2: Duplicate phone numbers (AI matching)
        from django.db.models import Count
        duplicates = Customer.objects.values('contact_number').annotate(
            count=Count('id')
        ).filter(count__gt=1, contact_number__isnull=False).exclude(contact_number='')
        
        if duplicates.exists():
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'data_quality',
                'severity': 'medium',
                'title': f'🟡 {duplicates.count()} duplicate phone numbers detected',
                'description': f'AI found {duplicates.count()} phone numbers shared by multiple customers. This may indicate duplicate customer records.',
                'confidence_score': 85,
                'impact_score': 60,
                'affected_records': duplicates.count(),
                'recommendation': 'Review these customers and merge duplicates.',
                'suggested_actions': [
                    'Review duplicate customers',
                    'Merge if same person',
                    'Update phone numbers if different',
                ],
                'fix_url': '/reports/duplicate-customers/',
                'data_snapshot': {
                    'phone_numbers': list(duplicates.values_list('contact_number', flat=True)[:10])
                }
            })
        
        # Check 3: Products without category
        no_category = Product.objects.filter(category__isnull=True)
        if no_category.exists():
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'data_quality',
                'severity': 'low',
                'title': f'🔵 {no_category.count()} products without category',
                'description': f'AI detected {no_category.count()} products with no category assignment.',
                'confidence_score': 100,
                'impact_score': 30,
                'affected_records': no_category.count(),
                'recommendation': 'Assign categories to improve reporting and organization.',
                'suggested_actions': [
                    'Review unclassified products',
                    'Assign appropriate categories',
                ],
                'fix_url': '/products/?filter=no-category',
            })
        
        # Check 4: Orphan records (sales without items)
        sales_no_items = Sale.objects.annotate(
            items_count=Count('saleitem')
        ).filter(items_count=0)
        
        if sales_no_items.exists():
            self.insights.append({
                'insight_type': 'anomaly',
                'category': 'data_quality',
                'severity': 'critical',
                'title': f'🔴 {sales_no_items.count()} sales with no items',
                'description': 'AI detected orphan sale records without items. These may be system errors.',
                'confidence_score': 100,
                'impact_score': 70,
                'affected_records': sales_no_items.count(),
                'recommendation': 'Review and either add items or delete these sales.',
                'suggested_actions': [
                    'Check sale details',
                    'Add missing items',
                    'Or delete if erroneous',
                ],
                'fix_url': '/sales/?filter=no-items',
            })
        
        # Check 5: Customers with no contact info
        no_contact = Customer.objects.filter(
            Q(contact_number__isnull=True) | Q(contact_number='')
        )
        if no_contact.exists():
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'data_quality',
                'severity': 'low',
                'title': f'🔵 {no_contact.count()} customers without phone number',
                'description': f'AI found {no_contact.count()} customers with no contact information.',
                'confidence_score': 100,
                'impact_score': 20,
                'affected_records': no_contact.count(),
                'recommendation': 'Collect phone numbers for better communication.',
                'fix_url': '/customers/?filter=no-phone',
            })
    
    # ============================================
    # ENGINE 2: BUSINESS INTELLIGENCE
    # ============================================
    
    def run_business_intelligence_engine(self):
        """AI-powered business analysis"""
        logger.info("💰 Running Business Intelligence Engine...")
        
        from .models import Sale, SaleItem, Product, Inventory, Customer
        
        today = now().date()
        last_30 = today - timedelta(days=30)
        last_60 = today - timedelta(days=60)
        last_90 = today - timedelta(days=90)
        
        # ==========================================
        # 1. SALES TREND ANALYSIS
        # ==========================================
        sales_30 = Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        sales_60_30 = Sale.objects.filter(
            sale_date__date__gte=last_60,
            sale_date__date__lt=last_30
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        if sales_60_30 > 0:
            growth = ((sales_30 - sales_60_30) / sales_60_30) * 100
            
            if growth < -20:
                self.insights.append({
                    'insight_type': 'risk',
                    'category': 'business',
                    'severity': 'high',
                    'title': f'📉 Sales dropped {abs(growth):.1f}% this month',
                    'description': f'AI detected sales decreased from Rs. {sales_60_30:,.0f} to Rs. {sales_30:,.0f}. Significant decline.',
                    'confidence_score': 90,
                    'impact_score': 85,
                    'affected_value': sales_30 - sales_60_30,
                    'recommendation': 'Investigate cause - competitor activity, seasonal, or quality issues.',
                    'suggested_actions': [
                        'Check top product sales decline',
                        'Review customer retention',
                        'Analyze competitor pricing',
                        'Run promotional campaign',
                    ],
                    'fix_url': '/reports/sales-summary/',
                    'data_snapshot': {
                        'current_month': float(sales_30),
                        'previous_month': float(sales_60_30),
                        'growth': float(growth),
                    }
                })
            elif growth > 30:
                self.insights.append({
                    'insight_type': 'opportunity',
                    'category': 'business',
                    'severity': 'info',
                    'title': f'📈 Sales grew {growth:.1f}% this month!',
                    'description': f'AI detected strong sales growth. Current: Rs. {sales_30:,.0f}',
                    'confidence_score': 95,
                    'impact_score': 80,
                    'affected_value': sales_30 - sales_60_30,
                    'recommendation': 'Analyze what worked and scale it.',
                    'suggested_actions': [
                        'Identify top performing products',
                        'Increase stock of fast movers',
                        'Document strategy',
                    ],
                })
        
        # ==========================================
        # 2. INVENTORY PREDICTIONS
        # ==========================================
        self.predict_stockouts()
        
        # ==========================================
        # 3. CASH FLOW PREDICTION
        # ==========================================
        self.predict_cash_flow()
        
        # ==========================================
        # 4. CUSTOMER CHURN DETECTION
        # ==========================================
        self.detect_customer_churn()
    
    def predict_stockouts(self):
        """AI predict which products will be out of stock"""
        from .models import Product, Inventory, SaleItem
        
        today = now().date()
        last_90 = today - timedelta(days=90)
        last_30 = today - timedelta(days=30)
        
        for inventory in Inventory.objects.filter(stock__gt=0).select_related('product'):
            product = inventory.product
            
            # Calculate sales velocity (last 30 days)
            sales_30 = SaleItem.objects.filter(
                product=product,
                sale__sale_date__date__gte=last_30
            ).aggregate(total=Sum('qty'))['total'] or 0
            
            # Calculate sales velocity (last 90 days)
            sales_90 = SaleItem.objects.filter(
                product=product,
                sale__sale_date__date__gte=last_90
            ).aggregate(total=Sum('qty'))['total'] or 0
            
            if sales_90 > 0:
                daily_velocity = sales_90 / 90
                days_until_stockout = inventory.stock / daily_velocity if daily_velocity > 0 else 999
                
                # If stockout within 15 days
                if days_until_stockout <= 15 and days_until_stockout > 0:
                    severity = 'critical' if days_until_stockout <= 7 else 'high'
                    
                    self.insights.append({
                        'insight_type': 'prediction',
                        'category': 'inventory',
                        'severity': severity,
                        'title': f'⚠️ {product.name} will run out in {int(days_until_stockout)} days',
                        'description': f'AI prediction: Based on last 90 days sales average of {daily_velocity:.2f} units/day, current stock ({inventory.stock}) will finish in {int(days_until_stockout)} days.',
                        'confidence_score': 85,
                        'impact_score': 90 if severity == 'critical' else 75,
                        'affected_records': 1,
                        'affected_value': inventory.stock * product.price,
                        'recommendation': f'Order minimum {int(daily_velocity * 30)} units to cover next 30 days.',
                        'suggested_actions': [
                            f'Create Purchase Order for {int(daily_velocity * 30)} units',
                            'Check vendor availability',
                            'Consider alternative vendors',
                        ],
                        'fix_url': f'/purchases/create/?product={product.id}',
                        'data_snapshot': {
                            'product_id': product.id,
                            'product_name': product.name,
                            'current_stock': float(inventory.stock),
                            'daily_velocity': float(daily_velocity),
                            'days_until_stockout': float(days_until_stockout),
                            'recommended_order': float(daily_velocity * 30),
                        }
                    })
    
    def predict_cash_flow(self):
        """AI predict cash flow issues"""
        from .models import Sale, Purchase, CashBalance
        
        today = now().date()
        last_30 = today - timedelta(days=30)
        
        # Get current balance
        current_balance = CashBalance.get_balance()
        
        # Predict next 30 days
        daily_income = Sale.objects.filter(
            sale_date__date__gte=last_30
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        daily_income = daily_income / 30
        
        daily_expense = Purchase.objects.filter(
            pur_date__date__gte=last_30
        ).aggregate(total=Sum('paid'))['total'] or Decimal('0')
        daily_expense = daily_expense / 30
        
        # Predict 30 days
        predicted_balance = current_balance + (daily_income - daily_expense) * 30
        
        if predicted_balance < 0:
            self.insights.append({
                'insight_type': 'risk',
                'category': 'financial',
                'severity': 'critical',
                'title': f'💰 Cash shortage predicted in 30 days',
                'description': f'AI predicts cash balance will go negative. Current: Rs. {current_balance:,.0f}. Predicted (30 days): Rs. {predicted_balance:,.0f}',
                'confidence_score': 75,
                'impact_score': 100,
                'affected_value': predicted_balance,
                'recommendation': 'Arrange cash or increase collections.',
                'suggested_actions': [
                    'Increase customer collections',
                    'Delay non-critical payments',
                    'Arrange short-term loan',
                    'Reduce expenses',
                ],
                'fix_url': '/cash/',
                'data_snapshot': {
                    'current_balance': float(current_balance),
                    'predicted_balance': float(predicted_balance),
                    'daily_income': float(daily_income),
                    'daily_expense': float(daily_expense),
                }
            })
        elif predicted_balance < current_balance * Decimal('0.3'):
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'financial',
                'severity': 'medium',
                'title': f'💰 Cash balance predicted to drop significantly',
                'description': f'AI predicts balance will drop from Rs. {current_balance:,.0f} to Rs. {predicted_balance:,.0f} in 30 days.',
                'confidence_score': 70,
                'impact_score': 70,
                'recommendation': 'Monitor cash flow closely.',
                'fix_url': '/cash/',
            })
    
    def detect_customer_churn(self):
        """AI detect customers likely to churn"""
        from .models import Customer, Sale
        
        today = now().date()
        last_30 = today - timedelta(days=30)
        last_60 = today - timedelta(days=60)
        last_90 = today - timedelta(days=90)
        
        # Get customers who were active but stopped
        active_customers_60_30 = Customer.objects.filter(
            sale__sale_date__date__gte=last_60,
            sale__sale_date__date__lt=last_30
        ).distinct()
        
        churn_risk = []
        for customer in active_customers_60_30:
            # Check if inactive in last 30 days
            recent_sales = customer.sale_set.filter(
                sale_date__date__gte=last_30
            ).count()
            
            if recent_sales == 0:
                # Calculate lifetime value
                lifetime_value = customer.sale_set.aggregate(
                    total=Sum('saleitem__total_amt')
                )['total'] or Decimal('0')
                
                churn_risk.append({
                    'customer': customer,
                    'value': lifetime_value,
                })
        
        if len(churn_risk) >= 3:
            total_value = sum(c['value'] for c in churn_risk)
            
            self.insights.append({
                'insight_type': 'risk',
                'category': 'customer',
                'severity': 'high',
                'title': f'🚫 {len(churn_risk)} customers may have churned',
                'description': f'AI detected {len(churn_risk)} customers who were active last month but have not ordered in 30 days. Total lifetime value: Rs. {total_value:,.0f}',
                'confidence_score': 65,
                'impact_score': 85,
                'affected_records': len(churn_risk),
                'affected_value': total_value,
                'recommendation': 'Reach out to these customers immediately.',
                'suggested_actions': [
                    'Send WhatsApp reminders',
                    'Offer special discount',
                    'Ask for feedback',
                    'Schedule follow-up call',
                ],
                'fix_url': '/reports/customer-churn/',
                'data_snapshot': {
                    'customer_count': len(churn_risk),
                    'total_value': float(total_value),
                }
            })
    
    # ============================================
    # ENGINE 3: PERFORMANCE OPTIMIZER
    # ============================================
    
    def run_performance_engine(self):
        """AI-powered performance analysis"""
        logger.info("⚡ Running Performance Engine...")
        
        from django.db import connection
        
        # Check large tables
        large_tables = []
        
        for model_name in ['Sale', 'Purchase', 'Product', 'Customer', 'SaleItem', 'PurchaseItem']:
            try:
                from . import models
                model = getattr(models, model_name)
                count = model.objects.count()
                
                if count > 50000:
                    large_tables.append({
                        'name': model_name,
                        'count': count
                    })
            except:
                pass
        
        if large_tables:
            self.insights.append({
                'insight_type': 'optimization',
                'category': 'performance',
                'severity': 'info',
                'title': f'⚡ {len(large_tables)} large tables detected',
                'description': f'AI detected {len(large_tables)} tables with 50k+ records. May impact performance.',
                'confidence_score': 100,
                'impact_score': 50,
                'affected_records': sum(t['count'] for t in large_tables),
                'recommendation': 'Consider archiving old records or adding indexes.',
                'suggested_actions': [
                    'Archive records older than 2 years',
                    'Add indexes on frequently used fields',
                    'Consider database optimization',
                ],
                'data_snapshot': {
                    'tables': large_tables,
                }
            })
        
        # Check database size
        try:
            db_size = self.get_database_size()
            if db_size > 500:  # MB
                self.insights.append({
                    'insight_type': 'optimization',
                    'category': 'performance',
                    'severity': 'info',
                    'title': f'⚡ Database size is {db_size:.0f} MB',
                    'description': f'AI detected large database size. May impact backup and performance.',
                    'confidence_score': 100,
                    'impact_score': 40,
                    'recommendation': 'Consider archiving old records.',
                    'fix_url': '/database-backup/',
                })
        except:
            pass
    
    def get_database_size(self):
        """Get database size in MB"""
        import os
        from django.conf import settings
        
        try:
            db_path = settings.DATABASES['default']['NAME']
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                return size / (1024 * 1024)
        except:
            pass
        return 0
    
    # ============================================
    # ENGINE 4: SECURITY AI
    # ============================================
    
    def run_security_engine(self):
        """AI-powered security analysis"""
        logger.info("🔐 Running Security Engine...")
        
        from .models import Employee, Shareholder
        from django.contrib.auth.models import User
        
        today = now().date()
        last_90 = today - timedelta(days=90)
        
        # Check 1: Inactive users
        inactive_users = User.objects.filter(
            last_login__lt=now() - timedelta(days=90),
            is_active=True
        )
        
        if inactive_users.count() > 5:
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'security',
                'severity': 'low',
                'title': f'🔵 {inactive_users.count()} users inactive 90+ days',
                'description': f'AI detected {inactive_users.count()} users who have not logged in for 90+ days.',
                'confidence_score': 100,
                'impact_score': 30,
                'affected_records': inactive_users.count(),
                'recommendation': 'Consider deactivating unused accounts.',
                'fix_url': '/users/?filter=inactive',
            })
        
        # Check 2: Superuser count
        superusers = User.objects.filter(is_superuser=True, is_active=True)
        if superusers.count() > 3:
            self.insights.append({
                'insight_type': 'risk',
                'category': 'security',
                'severity': 'medium',
                'title': f'⚠️ {superusers.count()} superuser accounts found',
                'description': f'AI detected {superusers.count()} active superuser accounts. Consider reducing for security.',
                'confidence_score': 90,
                'impact_score': 60,
                'affected_records': superusers.count(),
                'recommendation': 'Review superuser permissions.',
                'fix_url': '/users/?filter=superuser',
            })
        
        # Check 3: Backup status
        self.check_backup_status()
    
    def check_backup_status(self):
        """Check backup status"""
        import os
        from django.conf import settings
        
        try:
            backup_dir = getattr(settings, 'BACKUP_DIR', '/storage/emulated/0/Download/Backups')
            
            if os.path.exists(backup_dir):
                files = os.listdir(backup_dir)
                backup_files = [f for f in files if f.endswith(('.sqlite3', '.sqlite3.gz', '.json'))]
                
                if not backup_files:
                    self.insights.append({
                        'insight_type': 'risk',
                        'category': 'security',
                        'severity': 'critical',
                        'title': '🔴 No backup files found!',
                        'description': 'AI detected zero backup files. High risk!',
                        'confidence_score': 100,
                        'impact_score': 100,
                        'recommendation': 'Create backup immediately!',
                        'fix_url': '/database-backup/',
                    })
                else:
                    # Check latest backup
                    latest = max(
                        [os.path.join(backup_dir, f) for f in backup_files],
                        key=os.path.getmtime
                    )
                    last_modified = os.path.getmtime(latest)
                    days_since = (now().timestamp() - last_modified) / 86400
                    
                    if days_since > 7:
                        self.insights.append({
                            'insight_type': 'risk',
                            'category': 'security',
                            'severity': 'high',
                            'title': f'⚠️ Last backup was {int(days_since)} days ago',
                            'description': f'AI detected backup was taken {int(days_since)} days ago. Recommended: Every 3 days.',
                            'confidence_score': 100,
                            'impact_score': 85,
                            'recommendation': 'Take fresh backup now.',
                            'fix_url': '/database-backup/',
                        })
        except Exception as e:
            logger.error(f"Backup check error: {e}")
    
    # ============================================
    # ENGINE 5: USABILITY INTELLIGENCE
    # ============================================
    
    def run_usability_engine(self):
        """AI-powered usability analysis"""
        logger.info("📱 Running Usability Engine...")
        
        from .models import Sale, Purchase, Product, Customer
        from django.contrib.auth.models import User
        
        today = now().date()
        last_30 = today - timedelta(days=30)
        last_60 = today - timedelta(days=60)
        
        # Check 1: User engagement
        active_users = User.objects.filter(
            last_login__gte=now() - timedelta(days=7)
        ).count()
        
        total_users = User.objects.filter(is_active=True).count()
        
        if total_users > 0:
            engagement = (active_users / total_users) * 100
            
            if engagement < 30:
                self.insights.append({
                    'insight_type': 'recommendation',
                    'category': 'usability',
                    'severity': 'medium',
                    'title': f'📱 Only {engagement:.0f}% of users are active',
                    'description': f'AI detected low user engagement. Only {active_users}/{total_users} users logged in this week.',
                    'confidence_score': 95,
                    'impact_score': 60,
                    'recommendation': 'Consider training or re-engagement.',
                    'suggested_actions': [
                        'Identify inactive users',
                        'Send training invitations',
                        'Check for system issues',
                    ],
                })
        
        # Check 2: Module usage analysis
        modules_usage = {
            'Sales': Sale.objects.filter(sale_date__date__gte=last_30).count(),
            'Purchases': Purchase.objects.filter(pur_date__date__gte=last_30).count(),
            'Products': Product.objects.count(),
            'Customers': Customer.objects.count(),
        }
        
        # Check which modules have no activity
        inactive_modules = []
        if modules_usage['Sales'] == 0 and Sale.objects.count() > 0:
            inactive_modules.append('Sales')
        if modules_usage['Purchases'] == 0 and Purchase.objects.count() > 0:
            inactive_modules.append('Purchases')
        
        if inactive_modules:
            self.insights.append({
                'insight_type': 'recommendation',
                'category': 'usability',
                'severity': 'info',
                'title': f'📱 {len(inactive_modules)} modules inactive',
                'description': f'AI detected no activity in: {", ".join(inactive_modules)}',
                'confidence_score': 100,
                'impact_score': 40,
                'recommendation': 'Check if these modules are being used.',
                'data_snapshot': {
                    'inactive_modules': inactive_modules,
                }
            })