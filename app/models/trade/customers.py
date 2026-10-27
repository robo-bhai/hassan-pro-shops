"""Models: trade/customers (split from the former sales.py)."""
from django.db import models
from decimal import Decimal
from django.utils.timezone import now
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

                               # ( Sale Part )
# CustomerGroup model to group customers together
class CustomerGroup(models.Model):
    name = models.CharField(max_length=20, unique=True)
    description = models.TextField(null=True, blank=True)

    def total_outstanding_balance(self):
        return sum(customer.adjusted_outstanding_balance() for customer in self.customers.all())

    class Meta:
        verbose_name_plural = '2.1 Customer Groups'

    def __str__(self):
        return self.name


# Customer model to store customer 
class Customer(models.Model):
    customer_code = models.CharField(
        max_length=50, 
        unique=True, 
        null=True,          # ✅ Temporarily allow null for the migration
        blank=True,         # ✅ Temporarily allow blank in the form
        verbose_name=_("Customer Code"),
        help_text="Enter unique customer code manually (e.g., CUS-001, WALKIN)"
    )
    name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    
    
    # ✅ ADD THIS LINE
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name="Email")
   
    ref_name_1 = models.CharField(max_length=100, null=True, blank=True)
    ref_contact_number_1 = models.CharField(max_length=15, null=True, blank=True)
    ref_name_2 = models.CharField(max_length=100, null=True, blank=True)
    ref_contact_number_2 = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    # [agri-edition:customer] farmer details
    village = models.CharField(max_length=100, null=True, blank=True)
    main_crop = models.CharField(max_length=100, null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_margin = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        help_text="Set profit margin percentage (e.g., 20.00 for 20%)"
    )
    group = models.ForeignKey(
        'CustomerGroup', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customers'
    )

    class Meta:
        verbose_name_plural = '2. Customers'
        indexes = [
            models.Index(fields=['customer_code']),
            models.Index(fields=['name']),
            models.Index(fields=['group']),
        ]

    def __str__(self):
        if self.customer_code:
            return f"{self.customer_code} - {self.name}"
        return self.name

    def adjusted_outstanding_balance(self):
        # Calculate the total outstanding balance from sales
        total_outstanding = self.sale_set.aggregate(
            total=(Sum('saleitem__total_amt') - Sum('discount_value')) - Sum('paid')
        )['total'] or Decimal('0.0')

        # Calculate the total amount returned in sale returns
        total_returned = SaleRetrn.objects.filter(sale__customer=self).aggregate(
            total_returned=Sum('return_items__total_amt')
        )['total_returned'] or Decimal('0.0')

        # Subtract the returned amount from the outstanding balance
        adjusted_balance = total_outstanding - total_returned

        return adjusted_balance

    def save(self, *args, **kwargs):
        # ✅ If customer_code is empty, auto-generate it
        if not self.customer_code:
            last_customer = Customer.objects.exclude(
                customer_code__isnull=True
            ).exclude(
                customer_code=''
            ).order_by('-id').first()
            
            if last_customer and last_customer.customer_code and last_customer.customer_code.startswith('CUS-'):
                try:
                    last_num = int(last_customer.customer_code.split('-')[1])
                    new_num = str(last_num + 1).zfill(4)
                except (ValueError, IndexError):
                    new_num = '0001'
            else:
                new_num = '0001'
            
            self.customer_code = f'CUS-{new_num}'
        
        super().save(*args, **kwargs)


class CustomerPayment(models.Model):
    """Customer payment record - Separate from SalePayment"""
    
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='payments')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_payments')  # ✅ Changed
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateTimeField(default=now)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Customer Payments"
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['customer', 'payment_date']),
            models.Index(fields=['sale']),
        ]
    
    def __str__(self):
        return f"{self.customer.name} - Rs. {self.amount:,.2f} - {self.payment_date.strftime('%d-%m-%Y')}"
