"""Models: trade/monthly_plans (split from the former purchasing.py)."""
from django.db import models
from django.db import transaction
from decimal import Decimal
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User

class MonthlyPlanBatch(models.Model):
    """
    Multi-product monthly plan.

    One plan for a month that holds many products (its lines) and shows one grand total.
    Every line is a normal MonthlyPurchasePlan row linked through `batch`, so approve, edit,
    complete, Purchase Order and history keep working for each line exactly as before.
    """
    batch_no = models.CharField(max_length=20, unique=True, editable=False, default='')
    title = models.CharField(max_length=200, blank=True, default='')
    month = models.DateField(help_text="First day of the month")
    warehouse = models.ForeignKey(
        'Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plan_batches',
        help_text="Warehouse used for all lines"
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_plan_batches'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "📦 Multi-Product Monthly Plans"
        ordering = ['-month', '-id']

    def __str__(self):
        return f"{self.batch_no} - {self.month.strftime('%B %Y')}"

    def save(self, *args, **kwargs):
        if not self.batch_no:
            last = MonthlyPlanBatch.objects.order_by('-id').first()
            try:
                num = int(last.batch_no.split('-')[1]) + 1 if last and last.batch_no else 1
            except (ValueError, IndexError):
                num = 1
            self.batch_no = f'MB-{str(num).zfill(4)}'
        super().save(*args, **kwargs)

    # ---------------- totals ---------------- #
    def get_totals(self):
        """Grand totals of all lines that are not cancelled."""
        from django.db.models import Count
        agg = self.lines.exclude(status='cancelled').aggregate(
            products=Count('id'),
            sale_qty=Sum('expected_sales_quantity'),
            buy_qty=Sum('purchase_quantity'),
            sales_amount=Sum('expected_sales_amount'),
            purchase_amount=Sum('total_purchase_amount'),
        )
        return {
            'products': agg['products'] or 0,
            'sale_qty': agg['sale_qty'] or 0,
            'buy_qty': agg['buy_qty'] or 0,
            'sales_amount': agg['sales_amount'] or Decimal('0.00'),
            'purchase_amount': agg['purchase_amount'] or Decimal('0.00'),
        }

    @property
    def overall_status(self):
        """One status for the whole plan, worked out from its lines."""
        statuses = list(self.lines.values_list('status', flat=True))
        active = [s for s in statuses if s != 'cancelled']
        if not statuses:
            return 'draft'
        if not active:
            return 'cancelled'
        if all(s == 'completed' for s in active):
            return 'completed'
        if any(s == 'in_progress' for s in active):
            return 'in_progress'
        if all(s == 'approved' for s in active):
            return 'approved'
        if any(s == 'draft' for s in active):
            return 'draft'
        return 'in_progress'

    @property
    def overall_status_display(self):
        return dict(MonthlyPurchasePlan.STATUS_CHOICES).get(self.overall_status, self.overall_status)

    @property
    def overall_status_color(self):
        return {
            'draft': 'secondary',
            'approved': 'primary',
            'in_progress': 'warning',
            'completed': 'success',
            'cancelled': 'danger',
        }.get(self.overall_status, 'secondary')


class MonthlyPurchasePlan(models.Model):
    """
    Monthly Purchase Plan - Complete with Version Tracking, Inventory Integration & Safe Conversion
    Allows multiple plans per month with version history
    """
    
    STATUS_CHOICES = [
        ('draft', '📝 Draft'),
        ('approved', '✅ Approved'),
        ('in_progress', '⚙️ In Progress'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    STOCK_STATUS_CHOICES = [
        ('sufficient', '✅ Sufficient'),
        ('low', '⚠️ Low Stock'),
        ('critical', '🔴 Critical'),
        ('out_of_stock', '❌ Out of Stock'),
    ]
    
    # ========================================== #
    # BASIC INFORMATION                         #
    # ========================================== #
    month = models.DateField(help_text="First day of the month")
    plan_no = models.CharField(max_length=20, unique=True, editable=False, default='')
    
    # ========================================== #
    # VERSION TRACKING                          #
    # ========================================== #
    version = models.PositiveIntegerField(default=1, help_text="Plan version for the month")
    is_latest = models.BooleanField(default=True, help_text="Is this the latest version?")
    previous_plan = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='improved_plans',
        help_text="Previous plan that was improved"
    )
    batch = models.ForeignKey(
        'MonthlyPlanBatch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lines',
        help_text="Multi-product plan this line belongs to"
    )
    
    # ========================================== #
    # PRODUCT & WAREHOUSE                       #
    # ========================================== #
    product = models.ForeignKey(
        'Product', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='purchase_plans'
    )
    product_name = models.CharField(max_length=200, blank=True, null=True)
    
    warehouse = models.ForeignKey(
        'Warehouse', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='purchase_plans',
        help_text="Warehouse for this plan"
    )
    
    # ========================================== #
    # PLANNING DETAILS                          #
    # ========================================== #
    expected_sales_quantity = models.IntegerField(default=0, help_text="Expected units to sell")
    expected_sales_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    purchase_quantity = models.IntegerField(default=0, help_text="Planned purchase quantity")
    purchase_price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_purchase_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ========================================== #
    # INVESTOR REQUIREMENTS                     #
    # ========================================== #
    required_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    existing_investment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    additional_investment_needed = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    current_investors = models.IntegerField(default=0)
    required_investors = models.IntegerField(default=0)
    additional_investors_needed = models.IntegerField(default=0)
    
    # ========================================== #
    # ✅ INVENTORY INTEGRATION FIELDS            #
    # ========================================== #
    current_stock = models.FloatField(default=0, help_text="Current stock of product")
    reserved_stock = models.FloatField(default=0, help_text="Reserved stock")
    available_stock = models.FloatField(default=0, help_text="Available stock")
    
    stock_required = models.FloatField(default=0, help_text="Total stock required")
    stock_to_purchase = models.FloatField(default=0, help_text="Stock to purchase")
    stock_after_purchase = models.FloatField(default=0, help_text="Stock after purchase")
    
    purchase_order = models.ForeignKey(
        'PurchaseOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='monthly_plans',
        help_text="Generated Purchase Order"
    )
    
    stock_status = models.CharField(
        max_length=20,
        choices=STOCK_STATUS_CHOICES,
        default='sufficient',
        help_text="Current stock status"
    )
    
    # ========================================== #
    # ACTUAL ACHIEVEMENT                        #
    # ========================================== #
    actual_purchase_quantity = models.IntegerField(default=0)
    actual_purchase_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_sales_quantity = models.IntegerField(default=0)
    actual_sales_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    actual_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # ========================================== #
    # VARIANCE ANALYSIS                         #
    # ========================================== #
    purchase_variance_qty = models.IntegerField(default=0, help_text="Actual - Planned")
    purchase_variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    sales_variance_qty = models.IntegerField(default=0)
    sales_variance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    achievement_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # ========================================== #
    # STATUS & TRACKING                         #
    # ========================================== #
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_plans'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # ========================================== #
    # NOTES & DOCUMENTATION                     #
    # ========================================== #
    notes = models.TextField(blank=True, null=True)
    achievements = models.TextField(blank=True, null=True, help_text="What was achieved?")
    challenges = models.TextField(blank=True, null=True, help_text="What challenges were faced?")
    lessons_learned = models.TextField(blank=True, null=True, help_text="What was learned?")
    
    # ========================================== #
    # SYSTEM FIELDS                             #
    # ========================================== #
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_plans'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "📊 Monthly Purchase Plans"
        ordering = ['-month', '-version']  # Latest version first
        indexes = [
            models.Index(fields=['month', 'version']),
            models.Index(fields=['status']),
            models.Index(fields=['is_latest']),
            models.Index(fields=['plan_no']),
            models.Index(fields=['stock_status']),
        ]
    
    def __str__(self):
        return f"Plan #{self.plan_no} (v{self.version}) - {self.month.strftime('%B %Y')}"
    
    # ========================================== #
    # SAVE METHOD WITH SAFE CONVERSION          #
    # ========================================== #
    def save(self, *args, **kwargs):
        """Override save with safe conversion and inventory integration"""
        
        # ========================================== #
        # AUTO-GENERATE PLAN NUMBER                 #
        # ========================================== #
        if not self.plan_no:
            last_plan = MonthlyPurchasePlan.objects.order_by('-id').first()
            if last_plan and last_plan.plan_no:
                try:
                    last_num = int(last_plan.plan_no.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            self.plan_no = f'MP-{new_num}'
        
        # ========================================== #
        # SET PRODUCT NAME                          #
        # ========================================== #
        if self.product and not self.product_name:
            self.product_name = self.product.name
        
        # ========================================== #
        # SAFE DECIMAL CONVERSION FUNCTION          #
        # ========================================== #
        def safe_decimal(value, default='0.00'):
            """Safely convert value to Decimal"""
            try:
                if value is None or value == '':
                    return Decimal(default)
                if isinstance(value, Decimal):
                    return value
                if isinstance(value, (int, float)):
                    return Decimal(str(value))
                cleaned = str(value).replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '').strip()
                if cleaned == '':
                    return Decimal(default)
                return Decimal(cleaned)
            except:
                return Decimal(default)
        
        def safe_int(value, default=0):
            """Safely convert value to Integer"""
            try:
                if value is None or value == '':
                    return default
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                cleaned = str(value).replace(',', '').replace(' ', '').strip()
                if cleaned == '':
                    return default
                return int(float(cleaned))
            except:
                return default
        
        def safe_float(value, default=0.0):
            """Safely convert value to Float"""
            try:
                if value is None or value == '':
                    return default
                return float(value)
            except:
                return default
        
        # ========================================== #
        # CALCULATE TOTAL PURCHASE                  #
        # ========================================== #
        qty = safe_decimal(self.purchase_quantity)
        price = safe_decimal(self.purchase_price_per_unit)
        self.total_purchase_amount = qty * price
        
        # ========================================== #
        # CALCULATE REQUIRED INVESTMENT             #
        # ========================================== #
        self.required_investment = self.total_purchase_amount
        
        # ========================================== #
        # CALCULATE ADDITIONAL INVESTMENT NEEDED    #
        # ========================================== #
        existing = safe_decimal(self.existing_investment)
        self.additional_investment_needed = max(
            Decimal('0.00'), 
            self.required_investment - existing
        )
        
        # ========================================== #
        # CALCULATE REQUIRED INVESTORS              #
        # ========================================== #
        avg_investment = Decimal('10000')
        if avg_investment > 0:
            self.required_investors = int(self.required_investment / avg_investment)
        else:
            self.required_investors = 0
        
        self.additional_investors_needed = max(
            0, 
            self.required_investors - safe_int(self.current_investors)
        )
        
        # ========================================== #
        # ✅ INVENTORY CALCULATIONS                  #
        # ========================================== #
        
        # Get current stock from inventory
        if self.product and self.warehouse:
            inventory = Inventory.objects.filter(
                product=self.product,
                warehouse=self.warehouse
            ).first()
            
            if inventory:
                self.current_stock = safe_float(inventory.stock)
                self.reserved_stock = safe_float(inventory.reserved_stock)
                self.available_stock = self.current_stock - self.reserved_stock
            else:
                self.current_stock = 0
                self.reserved_stock = 0
                self.available_stock = 0
        else:
            self.current_stock = 0
            self.reserved_stock = 0
            self.available_stock = 0
        
        # Calculate stock requirements
        self.stock_required = safe_float(self.expected_sales_quantity)
        
        # Calculate stock to purchase
        self.stock_to_purchase = max(0, self.stock_required - self.available_stock)
        
        # Calculate stock after purchase
        self.stock_after_purchase = self.available_stock + self.stock_to_purchase
        
        # ========================================== #
        # ✅ STOCK STATUS DETERMINATION              #
        # ========================================== #
        
        if self.available_stock <= 0:
            self.stock_status = 'out_of_stock'
        elif self.available_stock < (self.stock_required * 0.25):
            self.stock_status = 'critical'
        elif self.available_stock < self.stock_required:
            self.stock_status = 'low'
        else:
            self.stock_status = 'sufficient'
        
        # ========================================== #
        # CALCULATE VARIANCES                       #
        # ========================================== #
        self.purchase_variance_qty = safe_int(self.actual_purchase_quantity) - safe_int(self.purchase_quantity)
        self.purchase_variance_amount = safe_decimal(self.actual_purchase_amount) - safe_decimal(self.total_purchase_amount)
        self.sales_variance_qty = safe_int(self.actual_sales_quantity) - safe_int(self.expected_sales_quantity)
        self.sales_variance_amount = safe_decimal(self.actual_sales_amount) - safe_decimal(self.expected_sales_amount)
        
        # ========================================== #
        # CALCULATE PROFIT VARIANCE                 #
        # ========================================== #
        expected_profit = safe_decimal(self.expected_sales_amount) - safe_decimal(self.total_purchase_amount)
        self.profit_variance = safe_decimal(self.actual_profit) - expected_profit
        
        # ========================================== #
        # CALCULATE ACHIEVEMENT PERCENTAGE          #
        # ========================================== #
        expected = safe_decimal(self.expected_sales_amount)
        actual = safe_decimal(self.actual_sales_amount)
        
        if expected > 0:
            self.achievement_percentage = (actual / expected) * Decimal('100')
        else:
            self.achievement_percentage = Decimal('0.00')
        
        # ========================================== #
        # ROUND VALUES                              #
        # ========================================== #
        self.total_purchase_amount = round(self.total_purchase_amount, 2)
        self.required_investment = round(self.required_investment, 2)
        self.additional_investment_needed = round(self.additional_investment_needed, 2)
        self.purchase_variance_amount = round(self.purchase_variance_amount, 2)
        self.sales_variance_amount = round(self.sales_variance_amount, 2)
        self.profit_variance = round(self.profit_variance, 2)
        self.achievement_percentage = round(self.achievement_percentage, 2)
        
        super().save(*args, **kwargs)
    
    # ========================================== #
    # PROPERTIES                                #
    # ========================================== #
    @property
    def status_badge(self):
        colors = {
            'draft': 'secondary',
            'approved': 'primary',
            'in_progress': 'warning',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'
    
    @property
    def stock_status_badge(self):
        colors = {
            'sufficient': 'success',
            'low': 'warning',
            'critical': 'danger',
            'out_of_stock': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.stock_status, "secondary")}">{self.get_stock_status_display()}</span>'
    
    @property
    def achievement_color(self):
        if self.achievement_percentage >= 100:
            return 'success'
        elif self.achievement_percentage >= 75:
            return 'warning'
        else:
            return 'danger'
    
    @property
    def is_achieved(self):
        return self.achievement_percentage >= 100
    
    @property
    def is_pending(self):
        return self.status in ['draft', 'approved', 'in_progress']
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_cancelled(self):
        return self.status == 'cancelled'
    
    @property
    def needs_purchase(self):
        return self.stock_to_purchase > 0
    
    @property
    def formatted_total(self):
        return f"Rs. {self.total_purchase_amount:,.2f}"
    
    @property
    def formatted_achievement(self):
        return f"{self.achievement_percentage:.1f}%"
    
    @property
    def version_badge(self):
        if self.is_latest:
            return f'<span class="badge bg-success">v{self.version} (Latest)</span>'
        return f'<span class="badge bg-secondary">v{self.version}</span>'
    
    # ========================================== #
    # METHODS                                   #
    # ========================================== #
    def approve(self, user):
        """Approve plan"""
        from django.utils.timezone import now
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = now()
        self.save()
        return True
    
    def start_progress(self):
        """Start progress"""
        self.status = 'in_progress'
        self.save()
        return True
    
    def complete(self, user):
        """Mark plan as completed"""
        from django.utils.timezone import now
        self.status = 'completed'
        self.completed_at = now()
        self.save()
        return True
    
    def cancel(self, user, reason=''):
        """Cancel plan"""
        self.status = 'cancelled'
        self.notes = f"{self.notes or ''}\nCancelled: {reason}".strip()
        self.save()
        return True
    
    def get_variance_summary(self):
        """Get variance summary"""
        return {
            'purchase_qty_variance': self.purchase_variance_qty,
            'purchase_amount_variance': float(self.purchase_variance_amount),
            'sales_qty_variance': self.sales_variance_qty,
            'sales_amount_variance': float(self.sales_variance_amount),
            'profit_variance': float(self.profit_variance),
            'achievement': float(self.achievement_percentage),
        }
    
    def get_investor_requirement(self):
        """Get investor requirement summary"""
        return {
            'total_investment': float(self.total_purchase_amount),
            'existing_investment': float(self.existing_investment),
            'additional_needed': float(self.additional_investment_needed),
            'current_investors': self.current_investors,
            'required_investors': self.required_investors,
            'additional_investors': self.additional_investors_needed,
        }
    
    def get_stock_summary(self):
        """Get stock summary"""
        return {
            'current_stock': self.current_stock,
            'reserved_stock': self.reserved_stock,
            'available_stock': self.available_stock,
            'stock_required': self.stock_required,
            'stock_to_purchase': self.stock_to_purchase,
            'stock_after_purchase': self.stock_after_purchase,
            'stock_status': self.stock_status,
            'stock_status_display': self.get_stock_status_display(),
        }
    
    def refresh_stock(self):
        """Refresh stock data from inventory"""
        if self.product and self.warehouse:
            inventory = Inventory.objects.filter(
                product=self.product,
                warehouse=self.warehouse
            ).first()
            
            if inventory:
                self.current_stock = float(inventory.stock)
                self.reserved_stock = float(inventory.reserved_stock)
                self.available_stock = self.current_stock - self.reserved_stock
                self.stock_to_purchase = max(0, self.stock_required - self.available_stock)
                self.stock_after_purchase = self.available_stock + self.stock_to_purchase
                self.save()
                return True
        return False
    
    # ========================================== #
    # CLASS METHODS                             #
    # ========================================== #
    @classmethod
    def get_latest_plan(cls, month):
        """Get latest plan for a month"""
        return cls.objects.filter(month=month, is_latest=True, batch__isnull=True).first()
    
    @classmethod
    def get_all_plans_for_month(cls, month):
        """Get all plans for a month"""
        return cls.objects.filter(month=month, batch__isnull=True).order_by('-version')
    
    @classmethod
    def create_new_version(cls, month, user, **kwargs):
        """Create a new version of plan for a month"""
        from django.db import transaction
        
        with transaction.atomic():
            # Mark all existing as not latest
            cls.objects.filter(month=month, batch__isnull=True).update(is_latest=False)
            
            # Get last version
            last_plan = cls.objects.filter(month=month, batch__isnull=True).order_by('-version').first()
            new_version = (last_plan.version + 1) if last_plan else 1
            
            # Create new plan
            plan = cls.objects.create(
                month=month,
                version=new_version,
                is_latest=True,
                previous_plan=last_plan,
                created_by=user,
                **kwargs
            )
            
            return plan


class MonthlyPlanHistory(models.Model):
    """
    Track all changes to monthly plans
    """
    ACTION_TYPES = [
        ('created', '📝 Created'),
        ('updated', '✏️ Updated'),
        ('approved', '✅ Approved'),
        ('completed', '🎯 Completed'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    plan = models.ForeignKey(
        MonthlyPurchasePlan, 
        on_delete=models.CASCADE, 
        related_name='history'
    )
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changes = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📊 Monthly Plan History"
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['plan', '-performed_at']),
        ]
    
    def __str__(self):
        return f"{self.plan.plan_no} - {self.get_action_display()}"
