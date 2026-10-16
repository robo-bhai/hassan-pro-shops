# forms.py
from django import forms
from .models import Purchase, PurchaseItem

class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['vendor']  # Fields you want to display on the form

class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['product', 'qty', 'price']
