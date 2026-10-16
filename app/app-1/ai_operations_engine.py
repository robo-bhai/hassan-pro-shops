"""
AI Operations Engine
Analyzes business operations and generates intelligent insights
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta, date
from django.db.models import Sum, Count, Avg, Q, F
from django.utils.timezone import now, localdate
from django.db import transaction

logger = logging.getLogger(__name__)


class AIOperationsEngine:
    """
    AI Engine for Business Operations
    Analyzes data and generates insights
    """
    
    def __init__(self):
        from .models import (
            BusinessOperationPlan, OperationTask, OperationsKPI,
            OperationAlert, AIOperationsInsight, AITaskSuggestion,
            DailyChecklist, Sale, Purchase, Inventory, Employee,
            SaleInstallment, Customer, Product
        )
        self.BusinessOperationPlan = BusinessOperationPlan
        self.OperationTask = OperationTask
        self.OperationsKPI = OperationsKPI
        self.OperationAlert = OperationAlert
        self.AIOperationsInsight = AIOperationsInsight
        self.AITaskSuggestion = AITaskSuggestion
        self.DailyChecklist = DailyChecklist
        self.Sale = Sale
        self.Purchase = Purchase
        self.Inventory = Inventory
        self.Employee = Employee
        self.SaleInstallment = SaleInstallment
        self.Customer = Customer
        self.Product = Product
    
    def run_full_analysis(self):
        """Run complete AI analysis"""
        logger.info("🤖 Starting AI Operations Analysis...")
        
        results = {
            'insights_created': 0,
            'alerts_created': 0,
            'task_suggestions': 0,
            'health_score': 0,
            'details': [],
        }
        
        try:
            # 1. Detect anomalies in operations
            anomaly_count = self.detect_anomalies()
            results['insights_created'] += anomaly_count
            results['details'].append(f"✅ Detected {anomaly_count} anomalies")
            
            # 2. Analyze task performance
            task_insights = self.analyze_task_performance()
            results['insights_created'] += task_insights
            results['details'].append(f"✅ Generated {task_insights} task insights")
            
            # 3. Predict KPI trends
            kpi_predictions = self.predict_kpi_trends()
            results['insights_created'] += kpi_predictions
            results['details'].append(f"✅ Generated {kpi_predictions} KPI predictions")
            
            # 4. Generate smart alerts
            alerts = self.generate_smart_alerts()
            results['alerts_created'] += alerts
            results['details'].append(f"✅ Created {alerts} smart alerts")
            
            # 5. Suggest tasks
            suggestions = self.suggest_tasks()
            results['task_suggestions'] += suggestions
            results['details'].append(f"✅ Generated {suggestions} task suggestions")
            
            # 6. Find business opportunities
            opportunities = self.find_opportunities()
            results['insights_created'] += opportunities
            results['details'].append(f"✅ Found {opportunities} opportunities")
            
            # 7. Calculate health score
            health_score = self.calculate_health_score()
            results['health_score'] = health_score
            results['details'].append(f"📊 Health Score: {health_score}/100")
            
            logger.info(f"🤖 AI Analysis Complete! {results}")
            
        except Exception as e:
            logger.error(f"❌ AI Analysis Error: {e}")
            results['error'] = str(e)
        
        return results
    
    # ========================================== #
    # 1. DETECT ANOMALIES                        #
    # ========================================== #
    
    def detect_anomalies(self):
        """Detect anomalies in operations"""
        count = 0
        
        # Anomaly 1: Too many overdue tasks
        overdue_tasks = self.OperationTask.objects.filter(
            status__in=['pending', 'in_progress'],
            due_date__lt=now()
        )
        
        if overdue_tasks.count() > 5:
            insight = self.AIOperationsInsight.objects.create(
                insight_type='anomaly',
                severity='high' if overdue_tasks.count() > 10 else 'medium',
                title=f"⚠️ {overdue_tasks.count()} Overdue Tasks Detected",
                description=f"Currently {overdue_tasks.count()} tasks are overdue. "
                           f"This may impact operations and deadlines.",
                confidence_score=95,
                impact_score=70,
                recommendation="Review overdue tasks and prioritize them. "
                              "Consider reassigning resources or adjusting deadlines.",
                suggested_actions=[
                    "Review each overdue task",
                    "Prioritize by impact",
                    "Reassign resources if needed",
                    "Communicate with stakeholders",
                ],
            )
            self._create_alert(
                title=f"⚠️ {overdue_tasks.count()} Overdue Tasks",
                message=f"You have {overdue_tasks.count()} overdue tasks that need immediate attention.",
                severity='high',
                alert_type='task_overdue',
                ai_generated=True,
            )
            count += 1
        
        # Anomaly 2: Low task completion rate
        thirty_days_ago = now() - timedelta(days=30)
        recent_tasks = self.OperationTask.objects.filter(
            created_at__gte=thirty_days_ago
        )
        
        if recent_tasks.count() > 10:
            completed = recent_tasks.filter(status='completed').count()
            completion_rate = (completed / recent_tasks.count()) * 100
            
            if completion_rate < 50:
                self.AIOperationsInsight.objects.create(
                    insight_type='anomaly',
                    severity='high',
                    title=f"📉 Low Task Completion Rate: {completion_rate:.1f}%",
                    description=f"Only {completion_rate:.1f}% of tasks completed in last 30 days. "
                               f"Industry standard is 75%+.",
                    confidence_score=90,
                    impact_score=80,
                    recommendation="Analyze why tasks are not being completed. "
                                  "Check if workload is too high or resources are insufficient.",
                    suggested_actions=[
                        "Review task assignments",
                        "Check resource allocation",
                        "Reduce task complexity",
                        "Add more team members",
                    ],
                )
                count += 1
        
        # Anomaly 3: Sudden drop in sales
        today = localdate()
        this_week = self.Sale.objects.filter(
            sale_date__date__gte=today - timedelta(days=7)
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
        
        last_week = self.Sale.objects.filter(
            sale_date__date__gte=today - timedelta(days=14),
            sale_date__date__lt=today - timedelta(days=7)
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or 0
        
        if last_week > 0:
            change = ((this_week - last_week) / last_week) * 100
            
            if change < -20:
                self.AIOperationsInsight.objects.create(
                    insight_type='anomaly',
                    severity='high',
                    title=f"📉 Sales Dropped {abs(change):.1f}% This Week",
                    description=f"Sales decreased from Rs. {last_week:,.2f} to Rs. {this_week:,.2f}. "
                               f"This is a significant drop.",
                    confidence_score=85,
                    impact_score=90,
                    affected_value=last_week - this_week,
                    recommendation="Investigate the reason for the drop. "
                                  "Check for stock issues, customer complaints, or market changes.",
                    suggested_actions=[
                        "Check inventory levels",
                        "Contact top customers",
                        "Review marketing activities",
                        "Analyze competitor activity",
                    ],
                )
                count += 1
        
        # Anomaly 4: KPIs in critical state
        critical_kpis = self.OperationsKPI.objects.filter(status='critical')
        if critical_kpis.count() > 0:
            for kpi in critical_kpis[:3]:
                self.AIOperationsInsight.objects.create(
                    insight_type='risk',
                    severity='critical',
                    title=f"🔴 Critical KPI: {kpi.name}",
                    description=f"KPI '{kpi.name}' is at {kpi.progress_percent:.1f}% of target. "
                               f"Current: {kpi.current_value} / Target: {kpi.target_value}",
                    confidence_score=100,
                    impact_score=85,
                    recommendation=f"Immediate action needed for '{kpi.name}'. "
                                  f"Current progress is below critical threshold ({kpi.critical_threshold}%).",
                    suggested_actions=[
                        f"Review {kpi.name} strategy",
                        "Allocate more resources",
                        "Set daily targets",
                        "Track progress hourly",
                    ],
                )
                count += 1
        
        return count
    
    # ========================================== #
    # 2. ANALYZE TASK PERFORMANCE                #
    # ========================================== #
    
    def analyze_task_performance(self):
        """Analyze task performance by employee"""
        count = 0
        
        # Analyze each employee's performance
        thirty_days_ago = now() - timedelta(days=30)
        employees = self.Employee.objects.filter(status='active')
        
        for employee in employees:
            tasks = self.OperationTask.objects.filter(
                assigned_to=employee,
                created_at__gte=thirty_days_ago
            )
            
            if tasks.count() < 5:
                continue
            
            completed = tasks.filter(status='completed').count()
            overdue = sum(1 for t in tasks if t.is_overdue())
            completion_rate = (completed / tasks.count()) * 100
            
            # Top performer
            if completion_rate >= 90 and overdue == 0:
                self.AIOperationsInsight.objects.create(
                    insight_type='opportunity',
                    severity='low',
                    title=f"🌟 Top Performer: {employee.name}",
                    description=f"{employee.name} has completed {completed} tasks with "
                               f"{completion_rate:.1f}% completion rate. Excellent performance!",
                    confidence_score=95,
                    impact_score=60,
                    recommendation=f"Consider giving {employee.name} more responsibilities "
                                  f"or a performance bonus.",
                    suggested_actions=[
                        "Acknowledge performance",
                        "Consider promotion",
                        "Give bonus",
                        "Assign more responsibilities",
                    ],
                )
                count += 1
            
            # Poor performer
            elif completion_rate < 50 and overdue > 3:
                self.AIOperationsInsight.objects.create(
                    insight_type='risk',
                    severity='medium',
                    title=f"⚠️ Performance Issue: {employee.name}",
                    description=f"{employee.name} has only {completion_rate:.1f}% completion rate "
                               f"with {overdue} overdue tasks.",
                    confidence_score=85,
                    impact_score=70,
                    recommendation=f"Schedule a performance review with {employee.name}. "
                                  f"Identify blockers and provide support.",
                    suggested_actions=[
                        "Performance review meeting",
                        "Identify blockers",
                        "Provide training",
                        "Adjust workload",
                    ],
                )
                count += 1
        
        return count
    
    # ========================================== #
    # 3. PREDICT KPI TRENDS                      #
    # ========================================== #
    
    def predict_kpi_trends(self):
        """Predict KPI trends based on historical data"""
        count = 0
        
        kpis = self.OperationsKPI.objects.filter(is_active=True)
        
        for kpi in kpis:
            # Simple linear prediction
            if kpi.target_value > 0 and kpi.progress_percent > 0:
                # Days elapsed
                today = localdate()
                if kpi.period_start and kpi.period_end:
                    total_days = (kpi.period_end - kpi.period_start).days
                    days_passed = (today - kpi.period_start).days
                    
                    if days_passed > 0 and total_days > 0:
                        # Predict final value
                        daily_rate = kpi.current_value / days_passed
                        predicted_value = daily_rate * total_days
                        
                        kpi.ai_prediction = predicted_value
                        kpi.ai_confidence = min(90, 50 + days_passed)
                        
                        # Check if prediction is below target
                        if predicted_value < kpi.target_value:
                            gap = kpi.target_value - predicted_value
                            kpi.ai_notes = f"⚠️ On current pace, will achieve only {predicted_value:.0f} (gap: {gap:.0f})"
                        else:
                            kpi.ai_notes = f"✅ On track to achieve {predicted_value:.0f}"
                        
                        kpi.save()
                        
                        # Create insight if prediction is concerning
                        if predicted_value < kpi.target_value * Decimal('0.8'):
                            self.AIOperationsInsight.objects.create(
                                insight_type='prediction',
                                severity='medium',
                                title=f"🔮 KPI Prediction: {kpi.name}",
                                description=f"Based on current pace, {kpi.name} will reach "
                                           f"{predicted_value:.0f} instead of target {kpi.target_value:.0f}.",
                                confidence_score=float(kpi.ai_confidence),
                                impact_score=75,
                                recommendation=f"Current daily rate: {daily_rate:.2f}. "
                                              f"Required daily rate: {(kpi.target_value / total_days):.2f}. "
                                              f"Need {((kpi.target_value / total_days) - daily_rate):.2f} more per day.",
                                suggested_actions=[
                                    "Increase daily target",
                                    "Allocate more resources",
                                    "Review strategy",
                                    "Track daily progress",
                                ],
                            )
                            count += 1
        
        return count
    
    # ========================================== #
    # 4. GENERATE SMART ALERTS                   #
    # ========================================== #
    
    def generate_smart_alerts(self):
        """Generate intelligent alerts"""
        count = 0
        today = localdate()
        
        # Alert 1: Tasks due today
        today_tasks = self.OperationTask.objects.filter(
            due_date__date=today,
            status__in=['pending', 'in_progress']
        )
        
        if today_tasks.count() > 0:
            self._create_alert(
                title=f"📅 {today_tasks.count()} Tasks Due Today",
                message=f"You have {today_tasks.count()} tasks due today. "
                       f"Make sure to complete them on time.",
                severity='medium',
                alert_type='plan_deadline',
                ai_generated=True,
            )
            count += 1
        
        # Alert 2: Plans ending soon
        ending_plans = self.BusinessOperationPlan.objects.filter(
            end_date__lte=today + timedelta(days=3),
            end_date__gte=today,
            status__in=['active', 'in_progress']
        )
        
        for plan in ending_plans:
            days_left = (plan.end_date - today).days
            if plan.progress_percent < 80:
                self._create_alert(
                    title=f"⚠️ Plan Ending Soon: {plan.plan_no}",
                    message=f"Plan '{plan.title}' ends in {days_left} days but only "
                           f"{plan.progress_percent:.0f}% complete.",
                    severity='high',
                    alert_type='plan_deadline',
                    ai_generated=True,
                )
                count += 1
        
        # Alert 3: Low stock
        try:
            low_stock = self.Inventory.objects.filter(
                stock__lt=F('product__low_stock_threshold')
            )[:5]
            
            for inv in low_stock:
                self._create_alert(
                    title=f"📦 Low Stock: {inv.product.name}",
                    message=f"Only {inv.stock} units left. Threshold: {inv.product.low_stock_threshold}",
                    severity='medium',
                    alert_type='stock_alert',
                    ai_generated=True,
                )
                count += 1
        except:
            pass
        
        # Alert 4: Overdue payments
        try:
            overdue_installments = self.SaleInstallment.objects.filter(
                status__in=['pending', 'partial'],
                next_due_date__lt=today
            )[:5]
            
            for inst in overdue_installments:
                days_overdue = (today - inst.next_due_date).days
                self._create_alert(
                    title=f"💰 Overdue Payment: {inst.sale.bill_no}",
                    message=f"Payment overdue by {days_overdue} days. "
                           f"Amount: Rs. {inst.remaining_amount():,.2f}",
                    severity='high',
                    alert_type='payment_due',
                    ai_generated=True,
                )
                count += 1
        except:
            pass
        
        return count
    
    # ========================================== #
    # 5. SUGGEST TASKS                           #
    # ========================================== #
    
    def suggest_tasks(self):
        """AI suggests new tasks based on data"""
        count = 0
        today = localdate()
        
        # Suggestion 1: Follow up with top customers
        top_customers = self.Customer.objects.annotate(
            total_sales=Sum('sale__saleitem__total_amt')
        ).filter(total_sales__gt=0).order_by('-total_sales')[:5]
        
        for customer in top_customers[:1]:
            suggestion = self.AITaskSuggestion.objects.create(
                title=f"📞 Follow up with {customer.name}",
                description=f"Top customer with Rs. {customer.total_sales:,.2f} in sales. "
                           f"Regular follow-up maintains relationship.",
                department='sales',
                suggested_priority='high',
                reason=f"{customer.name} is a top customer. Regular engagement "
                      f"increases retention and repeat business.",
                confidence=80,
            )
            count += 1
        
        # Suggestion 2: Stock replenishment
        low_stock_products = self.Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).select_related('product')[:3]
        
        for inv in low_stock_products:
            suggestion = self.AITaskSuggestion.objects.create(
                title=f"📦 Reorder {inv.product.name}",
                description=f"Stock: {inv.stock} units (below threshold {inv.product.low_stock_threshold}). "
                           f"Suggest reordering 100+ units.",
                department='purchase',
                suggested_priority='high',
                reason=f"Stock will run out soon. Historical sales indicate "
                      f"reorder quantity of 100+ units.",
                confidence=85,
            )
            count += 1
        
        # Suggestion 3: Payment collection
        overdue_customers = self.Customer.objects.filter(
            sale__saleitem__isnull=False
        ).annotate(
            total_outstanding=Sum('sale__saleitem__total_amt') - Sum('sale__paid')
        ).filter(total_outstanding__gt=10000)[:2]
        
        for customer in overdue_customers:
            suggestion = self.AITaskSuggestion.objects.create(
                title=f"💰 Collect payment from {customer.name}",
                description=f"Outstanding: Rs. {customer.total_outstanding:,.2f}. "
                           f"Follow up for payment collection.",
                department='accounts',
                suggested_priority='urgent',
                reason=f"Outstanding amount is significant. Timely collection "
                      f"improves cash flow.",
                confidence=90,
            )
            count += 1
        
        return count
    
    # ========================================== #
    # 6. FIND OPPORTUNITIES                      #
    # ========================================== #
    
    def find_opportunities(self):
        """Find business opportunities"""
        count = 0
        today = localdate()
        
        # Opportunity 1: Fast growing products
        thirty_days_ago = now() - timedelta(days=30)
        sixty_days_ago = now() - timedelta(days=60)
        
        from .models import SaleItem
        
        recent_sales = SaleItem.objects.filter(
            sale__sale_date__gte=thirty_days_ago
        ).values('product__name').annotate(
            recent_qty=Sum('qty')
        )
        
        older_sales = SaleItem.objects.filter(
            sale__sale_date__gte=sixty_days_ago,
            sale__sale_date__lt=thirty_days_ago
        ).values('product__name').annotate(
            older_qty=Sum('qty')
        )
        
        older_dict = {item['product__name']: item['older_qty'] for item in older_sales}
        
        for item in recent_sales:
            product_name = item['product__name']
            recent_qty = item['recent_qty']
            older_qty = older_dict.get(product_name, 0)
            
            if older_qty > 0:
                growth = ((recent_qty - older_qty) / older_qty) * 100
                
                if growth > 50:
                    self.AIOperationsInsight.objects.create(
                        insight_type='opportunity',
                        severity='low',
                        title=f"🎯 Growth Opportunity: {product_name}",
                        description=f"Sales of '{product_name}' grew {growth:.0f}% "
                                   f"in the last 30 days!",
                        confidence_score=85,
                        impact_score=75,
                        recommendation=f"Increase stock of '{product_name}' and "
                                      f"consider promotions to capitalize on growth.",
                        suggested_actions=[
                            f"Increase {product_name} stock",
                            "Run promotion campaign",
                            "Feature in marketing",
                            "Negotiate bulk purchase",
                        ],
                    )
                    count += 1
                    break  # One opportunity is enough
        
        # Opportunity 2: Best performing department
        best_dept = None
        best_score = 0
        
        for dept_code, dept_name in self.BusinessOperationPlan.DEPARTMENTS:
            dept_tasks = self.OperationTask.objects.filter(plan__department=dept_code)
            total = dept_tasks.count()
            if total > 0:
                completed = dept_tasks.filter(status='completed').count()
                score = (completed / total) * 100
                
                if score > best_score:
                    best_score = score
                    best_dept = dept_name
        
        if best_dept and best_score > 80:
            self.AIOperationsInsight.objects.create(
                insight_type='opportunity',
                severity='low',
                title=f"🌟 Best Department: {best_dept}",
                description=f"{best_dept} has {best_score:.1f}% completion rate. "
                           f"Excellent performance!",
                confidence_score=95,
                impact_score=50,
                recommendation=f"Document {best_dept}'s practices and share with "
                              f"other departments to improve overall performance.",
                suggested_actions=[
                    "Document best practices",
                    "Share with other teams",
                    "Reward the team",
                    "Cross-train employees",
                ],
            )
            count += 1
        
        return count
    
    # ========================================== #
    # 7. CALCULATE HEALTH SCORE                  #
    # ========================================== #
    
    def calculate_health_score(self):
        """Calculate overall operations health score (0-100)"""
        scores = []
        
        # Component 1: Task completion (30 points)
        all_tasks = self.OperationTask.objects.all()
        if all_tasks.count() > 0:
            completed = all_tasks.filter(status='completed').count()
            task_score = (completed / all_tasks.count()) * 30
        else:
            task_score = 30
        scores.append(task_score)
        
        # Component 2: On-time delivery (25 points)
        total_with_due = all_tasks.exclude(due_date__isnull=True)
        if total_with_due.count() > 0:
            on_time = total_with_due.filter(
                Q(status='completed', completed_at__lte=F('due_date')) |
                Q(status__in=['pending', 'in_progress'], due_date__gte=now())
            ).count()
            ontime_score = (on_time / total_with_due.count()) * 25
        else:
            ontime_score = 25
        scores.append(ontime_score)
        
        # Component 3: KPI performance (25 points)
        kpis = self.OperationsKPI.objects.filter(is_active=True)
        if kpis.count() > 0:
            avg_progress = kpis.aggregate(avg=Avg('progress_percent'))['avg'] or 0
            kpi_score = (min(float(avg_progress), 100) / 100) * 25
        else:
            kpi_score = 25
        scores.append(kpi_score)
        
        # Component 4: Alert resolution (10 points)
        unresolved_alerts = self.OperationAlert.objects.filter(is_resolved=False).count()
        if unresolved_alerts == 0:
            alert_score = 10
        elif unresolved_alerts < 5:
            alert_score = 7
        elif unresolved_alerts < 10:
            alert_score = 5
        else:
            alert_score = 2
        scores.append(alert_score)
        
        # Component 5: Plan progress (10 points)
        active_plans = self.BusinessOperationPlan.objects.filter(
            status__in=['active', 'in_progress']
        )
        if active_plans.count() > 0:
            avg_progress = active_plans.aggregate(avg=Avg('progress_percent'))['avg'] or 0
            plan_score = (min(float(avg_progress), 100) / 100) * 10
        else:
            plan_score = 10
        scores.append(plan_score)
        
        total_score = sum(scores)
        return round(total_score, 1)
    
    # ========================================== #
    # HELPER: Create Alert                       #
    # ========================================== #
    
    def _create_alert(self, title, message, severity, alert_type, ai_generated=False):
        """Create an alert"""
        return self.OperationAlert.objects.create(
            title=title,
            message=message,
            severity=severity,
            alert_type=alert_type,
            ai_generated=ai_generated,
        )