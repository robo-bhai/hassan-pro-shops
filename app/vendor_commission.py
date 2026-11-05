"""
Vendor commission model (Amazon Seller Central jaisa).

- Vendor apna maal apni selling price par shop par bechta hai.
- Shop har bikri par commission % rakhta hai; baaqi paisa vendor ka hota hai.
- Stock batch ka "cost" = vendor ka hissa = (customer ki ada ki hui price) x (100 - commission) / 100.
  Is tarah FIFO, COGS aur profit ka purana logic waisa hi chalta hai, aur
  shop ka profit per sale = commission.
- Vendor ka discount vendor khud bardasht karta hai (commission discounted price par lagta hai).
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

HUNDRED = Decimal('100')
CENT = Decimal('0.01')
MAX_COMMISSION = Decimal('50')


def default_commission():
    """settings.VENDOR_DEFAULT_COMMISSION_PERCENT (na ho to 10%)."""
    return Decimal(str(getattr(settings, 'VENDOR_DEFAULT_COMMISSION_PERCENT', 10)))


def commission_percent(profile):
    """Is vendor ka commission %; vendor ke liye khaas na ho to default."""
    pct = getattr(profile, 'commission_percent', None)
    return Decimal(pct) if pct is not None else default_commission()


def effective_price(price, discount):
    """Customer jo price ada karta hai (discount ke baad)."""
    price = Decimal(price)
    discount = Decimal(discount or 0)
    return (price * (HUNDRED - discount) / HUNDRED).quantize(CENT, ROUND_HALF_UP)


def vendor_share(price, discount, pct):
    """Vendor ko har unit par milne wali raqam == batch ka 'cost'."""
    eff = effective_price(price, discount)
    share = (eff * (HUNDRED - Decimal(pct)) / HUNDRED).quantize(CENT, ROUND_HALF_UP)
    return max(share, CENT)


def reprice_open_batches(product, price, discount, pct):
    """Price/discount/commission badalne par product ke open batches (selling price + cost) update karo."""
    from .models import StockBatch
    cost = vendor_share(price, discount, pct)
    price = Decimal(price)
    for batch in StockBatch.objects.filter(product=product, remaining_qty__gt=0):
        if batch.selling_price != price or batch.price != cost:
            batch.price = cost
            batch.selling_price = price
            batch.save()


def vendor_earnings(vendor):
    """Vendor ki ab tak ki bikri: sales, shop ka commission, aur vendor ka hissa (payable)."""
    from .models import SaleItem, SaleItemBatchUsage
    agg = SaleItem.objects.filter(product__vendor=vendor).aggregate(sales=Sum('total_amt'), units=Sum('qty'))
    pay = SaleItemBatchUsage.objects.filter(sale_item__product__vendor=vendor).aggregate(
        payable=Sum(ExpressionWrapper(
            F('qty') * F('cost_price'), output_field=DecimalField(max_digits=18, decimal_places=2))))
    sales = Decimal(agg['sales'] or 0)
    payable = Decimal(pay['payable'] or 0).quantize(CENT, ROUND_HALF_UP)
    return {
        'units': agg['units'] or 0,
        'sales': sales,
        'commission': (sales - payable).quantize(CENT, ROUND_HALF_UP),
        'payable': payable,
    }
