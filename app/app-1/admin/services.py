"""Admin: services models."""
from ..models import *
from django.contrib import admin, messages
from django.utils.timezone import now
from django.utils.html import format_html
from ..models import ServiceCategory, Service, ServiceProductRequirement, ServiceRequest, ServiceProductUsed, ServiceAppointment, ServiceTechnicianAssignment, ServiceFeedback, ServiceInventoryCategory, ServiceInventory, ServiceInventoryTransaction, ServicePartUsage, ServiceInventoryPurchaseOrder, ServiceInventoryPODetail, ServiceInventoryStockAdjustment


class ServiceProductRequirementInline(admin.TabularInline):
    model = ServiceProductRequirement
    fields = ('product', 'quantity', 'is_optional')
    extra = 1
    raw_id_fields = ('product',)  # ✅ FIXED: Using raw_id_fields


class ServiceProductUsedInline(admin.TabularInline):
    model = ServiceProductUsed
    fields = ('product', 'quantity', 'price', 'total')
    readonly_fields = ('total',)
    extra = 1
    raw_id_fields = ('product',)  # ✅ FIXED: Using raw_id_fields


@admin.register(ServiceCategory, site=admin.site)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)


@admin.register(Service, site=admin.site)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('service_code', 'name', 'service_type', 'price', 'pricing_type', 'is_active')
    list_filter = ('service_type', 'pricing_type', 'is_active', 'category')
    search_fields = ('service_code', 'name', 'description')
    list_editable = ('price', 'is_active')
    inlines = [ServiceProductRequirementInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('service_code', 'name', 'service_type', 'category', 'description')
        }),
        ('Pricing', {
            'fields': ('pricing_type', 'price', 'estimated_hours', 'min_charge', 'max_charge')
        }),
        ('Staff & Settings', {
            'fields': ('requires_technician', 'default_technician', 'needs_appointment', 'warranty_months')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('System', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate', 'deactivate']
    
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"✅ {queryset.count()} services activated")
    activate.short_description = "Activate Selected Services"
    
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"⚠️ {queryset.count()} services deactivated")
    deactivate.short_description = "Deactivate Selected Services"


class ServiceAppointmentInline(admin.TabularInline):
    model = ServiceAppointment
    fields = ('technician', 'appointment_date', 'start_time', 'end_time', 'status')
    extra = 1


@admin.register(ServiceRequest, site=admin.site)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('request_no', 'customer', 'service', 'status', 'priority', 
                    'scheduled_date', 'technician', 'total_amount_display', 'is_overdue_display')
    list_filter = ('status', 'priority', 'scheduled_date', 'service__service_type')
    search_fields = ('request_no', 'customer__name', 'customer__customer_code', 'service__name')
    list_editable = ('status', 'priority')
    inlines = [ServiceProductUsedInline, ServiceAppointmentInline]
    
    fieldsets = (
        ('Request Information', {
            'fields': ('request_no', 'customer', 'service', 'description', 'priority', 'status')
        }),
        ('Scheduling', {
            'fields': ('requested_date', 'scheduled_date', 'appointment_time', 'estimated_hours', 'completed_date')
        }),
        ('Location & Contact', {
            'fields': ('service_address', 'contact_person', 'contact_phone')
        }),
        ('Pricing', {
            'fields': ('quoted_price', 'actual_price', 'discount')
        }),
        ('Technician', {
            'fields': ('technician', 'assigned_at')
        }),
        ('Follow-up & Invoice', {
            'fields': ('follow_up_required', 'follow_up_date', 'invoice')
        }),
        ('Feedback', {
            'fields': ('feedback_rating', 'feedback_comment')
        }),
        ('System', {
            'fields': ('created_by', 'created_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('request_no', 'assigned_at', 'created_at', 'updated_at')
    
    def total_amount_display(self, obj):
        return f"Rs. {obj.total_amount():,.2f}"
    total_amount_display.short_description = "Total Amount"
    
    def is_overdue_display(self, obj):
        if obj.is_overdue():
            days = obj.days_overdue()
            return format_html('<span style="color: red;">⚠️ {} days overdue</span>', days)
        return format_html('<span style="color: green;">✅ On time</span>')
    is_overdue_display.short_description = "Overdue"
    
    actions = ['mark_assigned', 'mark_in_progress', 'mark_completed', 'generate_invoice']
    
    def mark_assigned(self, request, queryset):
        count = queryset.update(status='assigned', assigned_at=now())
        self.message_user(request, f"✅ {count} requests marked as assigned")
    mark_assigned.short_description = "👤 Mark as Assigned"
    
    def mark_in_progress(self, request, queryset):
        count = queryset.update(status='in_progress')
        self.message_user(request, f"⚙️ {count} requests marked as in progress")
    mark_in_progress.short_description = "⚙️ Mark as In Progress"
    
    def mark_completed(self, request, queryset):
        count = queryset.update(status='completed', completed_date=now().date())
        self.message_user(request, f"✅ {count} requests marked as completed")
    mark_completed.short_description = "✅ Mark as Completed"
    
    def generate_invoice(self, request, queryset):
        """Generate invoice for completed services"""
        count = 0
        for service_request in queryset.filter(status='completed', invoice__isnull=True):
            try:
                with transaction.atomic():
                    sale = Sale.objects.create(
                        customer=service_request.customer,
                        bill_no=f"SVC-{service_request.request_no}",
                        sale_date=now(),
                        paid=0,
                        discount_value=service_request.discount,
                        created_by=request.user,
                        warehouse=Warehouse.objects.first()
                    )
                    
                    SaleItem.objects.create(
                        sale=sale,
                        product=None,
                        qty=1,
                        price=service_request.total_amount(),
                        total_amt=service_request.total_amount(),
                        profit=0,
                        description=f"Service: {service_request.service.name} - {service_request.request_no}"
                    )
                    
                    service_request.invoice = sale
                    service_request.save()
                    count += 1
                    
            except Exception as e:
                messages.error(request, f"❌ Error for {service_request.request_no}: {str(e)}")
        
        if count:
            self.message_user(request, f"✅ {count} invoices generated!")
    generate_invoice.short_description = "📄 Generate Invoice"


@admin.register(ServiceAppointment, site=admin.site)
class ServiceAppointmentAdmin(admin.ModelAdmin):
    list_display = ('service_request', 'technician', 'appointment_date', 'start_time', 'status')
    list_filter = ('status', 'appointment_date', 'technician')
    search_fields = ('service_request__request_no', 'technician__name')
    list_editable = ('status',)


@admin.register(ServiceTechnicianAssignment, site=admin.site)
class ServiceTechnicianAssignmentAdmin(admin.ModelAdmin):
    list_display = ('technician', 'date', 'max_services', 'current_services', 'is_available', 'is_full_display')
    list_filter = ('date', 'is_available')
    search_fields = ('technician__name',)
    list_editable = ('is_available',)
    
    def is_full_display(self, obj):
        return "🔴 Full" if obj.is_full() else "🟢 Available"
    is_full_display.short_description = "Status"


@admin.register(ServiceFeedback, site=admin.site)
class ServiceFeedbackAdmin(admin.ModelAdmin):
    list_display = ('service_request', 'rating', 'average_rating_display', 'would_recommend', 'created_at')
    list_filter = ('rating', 'would_recommend')
    search_fields = ('service_request__request_no', 'comment')
    readonly_fields = ('service_request', 'created_at')
    
    def average_rating_display(self, obj):
        return f"{obj.average_rating()}★"
    average_rating_display.short_description = "Avg Rating"


@admin.register(ServiceInventoryCategory, site=admin.site)
class ServiceInventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    list_editable = ('is_active',)


class ServiceInventoryTransactionInline(admin.TabularInline):
    model = ServiceInventoryTransaction
    fields = ('transaction_type', 'quantity', 'balance_after', 'notes', 'created_at')
    readonly_fields = ('created_at',)
    extra = 0
    can_delete = False


@admin.register(ServiceInventory, site=admin.site)
class ServiceInventoryAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'name', 'item_type', 'category', 'current_stock', 
                    'reorder_level', 'unit_cost', 'selling_price', 'is_low_stock_display', 'is_active')
    list_filter = ('item_type', 'category', 'is_active', 'is_consumable')
    search_fields = ('item_code', 'name', 'description', 'barcode')
    list_editable = ('current_stock', 'reorder_level', 'unit_cost', 'selling_price', 'is_active')
    inlines = [ServiceInventoryTransactionInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('item_code', 'name', 'description', 'item_type', 'category', 'product')
        }),
        ('Stock Management', {
            'fields': ('current_stock', 'min_stock', 'max_stock', 'reorder_level', 'reorder_quantity')
        }),
        ('Pricing', {
            'fields': ('unit_cost', 'selling_price', 'markup_percent')
        }),
        ('Location & Supplier', {
            'fields': ('unit', 'warehouse', 'shelf_location', 'preferred_supplier')
        }),
        ('Barcode & Settings', {
            'fields': ('barcode', 'is_active', 'is_consumable', 'is_serialized')
        }),
        ('System', {
            'fields': ('created_by', 'created_at', 'last_updated', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('item_code', 'created_at', 'last_updated')
    
    def is_low_stock_display(self, obj):
        if obj.is_critical_stock():
            return format_html('<span style="color: red; font-weight: bold;">⚠️ Critical</span>')
        elif obj.is_low_stock():
            return format_html('<span style="color: orange; font-weight: bold;">⚠️ Low</span>')
        return format_html('<span style="color: green;">✅ OK</span>')
    is_low_stock_display.short_description = "Stock Status"
    
    actions = ['mark_active', 'mark_inactive', 'set_reorder_level']
    
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"✅ {queryset.count()} items activated")
    mark_active.short_description = "Activate Selected"
    
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"⚠️ {queryset.count()} items deactivated")
    mark_inactive.short_description = "Deactivate Selected"
    
    def set_reorder_level(self, request, queryset):
        # Custom action to set reorder level
        level = request.POST.get('reorder_level')
        if level:
            queryset.update(reorder_level=level)
            self.message_user(request, f"✅ Reorder level set to {level}")
    set_reorder_level.short_description = "Set Reorder Level"


@admin.register(ServiceInventoryTransaction, site=admin.site)
class ServiceInventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('inventory_item', 'transaction_type', 'quantity', 'balance_after', 'created_at', 'created_by')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('inventory_item__name', 'inventory_item__item_code', 'notes')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False


@admin.register(ServicePartUsage, site=admin.site)
class ServicePartUsageAdmin(admin.ModelAdmin):
    list_display = ('service_request', 'inventory_item', 'quantity', 'total_cost', 'total_charged', 'used_at')
    list_filter = ('used_at', 'charged_to_customer')
    search_fields = ('service_request__request_no', 'inventory_item__name')
    readonly_fields = ('total_cost', 'total_charged', 'used_at')
    
    def has_add_permission(self, request):
        return False


class ServiceInventoryPODetailInline(admin.TabularInline):
    model = ServiceInventoryPODetail
    fields = ('inventory_item', 'quantity', 'unit_price', 'total_price', 'received_quantity')
    readonly_fields = ('total_price',)
    extra = 1


@admin.register(ServiceInventoryPurchaseOrder, site=admin.site)
class ServiceInventoryPurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_no', 'supplier', 'order_date', 'status', 'total_amount', 'net_amount')
    list_filter = ('status', 'order_date')
    search_fields = ('po_no', 'supplier__name')
    inlines = [ServiceInventoryPODetailInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('po_no', 'supplier', 'status')
        }),
        ('Dates', {
            'fields': ('order_date', 'expected_delivery', 'received_date')
        }),
        ('Amounts', {
            'fields': ('total_amount', 'discount', 'net_amount')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    readonly_fields = ('po_no', 'order_date', 'total_amount', 'net_amount')
    
    actions = ['mark_received', 'mark_approved', 'mark_ordered']
    
    def mark_received(self, request, queryset):
        for po in queryset.filter(status__in=['ordered', 'partial']):
            po.mark_received()
        self.message_user(request, f"✅ {queryset.count()} POs marked as received")
    mark_received.short_description = "📥 Mark as Received"
    
    def mark_approved(self, request, queryset):
        queryset.update(status='approved')
        self.message_user(request, f"✅ {queryset.count()} POs approved")
    mark_approved.short_description = "✅ Mark as Approved"
    
    def mark_ordered(self, request, queryset):
        queryset.update(status='ordered')
        self.message_user(request, f"📦 {queryset.count()} POs marked as ordered")
    mark_ordered.short_description = "📦 Mark as Ordered"


@admin.register(ServiceInventoryStockAdjustment, site=admin.site)
class ServiceInventoryStockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_no', 'inventory_item', 'adjustment_type', 'quantity', 
                    'previous_stock', 'new_stock', 'performed_at', 'performed_by')
    list_filter = ('adjustment_type', 'performed_at')
    search_fields = ('inventory_item__name', 'reason')
    readonly_fields = ('adjustment_no', 'previous_stock', 'new_stock', 'performed_at')
    
    def has_change_permission(self, request, obj=None):
        return False
