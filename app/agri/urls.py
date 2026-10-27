"""Agri Edition URLs (added to app/urls.py by install_agri.py)."""
from django.urls import path

from . import views

urlpatterns = [
    path('agri/', views.dashboard, name='agri_dashboard'),
    path('agri/expiry/', views.expiry_manager, name='agri_expiry'),
    path('agri/expiry/save/', views.expiry_save, name='agri_expiry_save'),
    path('agri/expiry/writeoff/', views.expiry_writeoff, name='agri_expiry_writeoff'),
    path('agri/writeoffs/', views.writeoff_list, name='agri_writeoffs'),
    path('agri/grn/<int:grn_id>/expiry/', views.grn_expiry_save, name='agri_grn_expiry'),
    path('agri/credit/', views.credit_list, name='agri_credit'),
    path('agri/credit/farmer/<int:customer_id>/', views.farmer_detail, name='agri_farmer'),
    path('agri/credit/farmer/<int:customer_id>/profile/', views.farmer_profile_save, name='agri_farmer_profile'),
    path('agri/credit/farmer/<int:customer_id>/due/', views.farmer_set_due, name='agri_farmer_due'),
    path('agri/credit/sale/<int:sale_id>/due/', views.sale_set_due, name='agri_sale_due'),
]
