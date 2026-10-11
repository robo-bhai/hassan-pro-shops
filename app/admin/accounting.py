"""Admin: accounting models."""
from ..models import *
from django.contrib import admin


@admin.register(Saving, site=admin.site)
class SavingAdmin(admin.ModelAdmin):
    list_display = ('description', 'amount', 'date', 'category')
    list_filter = ('category', 'date')
    search_fields = ('description',)


@admin.register(Debt, site=admin.site)
class DebtAdmin(admin.ModelAdmin):
    list_display = ('lender', 'amount', 'interest_rate', 'start_date', 'due_date')
    list_filter = ('start_date', 'due_date')
    search_fields = ('lender',)
