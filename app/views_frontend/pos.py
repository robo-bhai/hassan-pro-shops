"""
Fast POS screen (shop counter).

URLs (add to urls.py, BEFORE the other sales patterns):
    path('sales/pos/', pos_views.pos_screen, name='pos_screen'),
    path('sales/pos/products/', pos_views.pos_products, name='pos_products'),
    path('sales/pos/customers/', pos_views.pos_customers, name='pos_customers'),
    path('sales/pos/checkout/', pos_views.pos_checkout, name='pos_checkout'),

This uses the existing Sale / SaleItem / SalePayment / CashBalance models, so FIFO, profit,
stock and reports work as before. Checkout is one transaction: if any item fails, the whole
sale is rolled back (a half-saved sale is never created).

Quantities may be decimals (for example 0.25 kg or 1.5 m), up to 3 decimal places.
Payment methods: Cash and Bank only.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import (CashBalance, Category, CompanyInfo, Customer, Inventory, Notification, PaymentMethod, Product,
                      Sale, SaleItem, SalePayment, StockBatch, Warehouse)

from .shift import open_shift_for
from .shop_tools import audit, is_manager, setting_number

REQUIRE_SHIFT = True        # True = bills can be made only while a shift is open
WALKIN_CODE = 'WALKIN'
# Safety rules for cashiers (managers = superuser or staff users are not limited).
BLOCK_BELOW_COST = True          # a cashier cannot sell under the purchase cost
DEFAULT_MAX_DISCOUNT_PCT = 10    # cashier discount limit in %, change it in System Settings: pos_max_discount_pct
METHODS = [('cash', 'Cash', 'bi-cash-coin'), ('bank_transfer', 'Bank', 'bi-bank')]


def _walkin():
    c = Customer.objects.filter(customer_code=WALKIN_CODE).first()
    if not c:
        c = Customer.objects.create(customer_code=WALKIN_CODE, name='Walk-in Customer')
    return c


def _dec(v, default='0'):
    try:
        d = Decimal(str(v if v not in (None, '') else default))
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a valid number.')
    if not d.is_finite():
        raise ValueError('Enter a valid number.')
    return d


@login_required
def pos_screen(request):
    info = CompanyInfo.objects.first()
    walkin = _walkin()
    return render(request, 'sales/pos.html', {
        'company_name': info.name if info else 'ERP System',
        'company': {'name': info.name if info else '', 'address': info.address if info else '',
                    'phone': info.contact_number if info else '', 'footer': (info.footer_note if info else '') or ''},
        'warehouses': Warehouse.objects.order_by('name'),
        'categories': Category.objects.order_by('name')[:40],
        'walkin_id': walkin.pk,
        'methods': METHODS,
        'require_shift': REQUIRE_SHIFT,
    })


def _product_rows(products, warehouse_id):
    """For each product: stock + selling price of the first FIFO batch (few queries)."""
    ids = [p.pk for p in products]
    stock = dict(Inventory.objects.filter(warehouse_id=warehouse_id, product_id__in=ids)
                 .values_list('product_id', 'stock'))
    first_batch = {}
    for b in StockBatch.objects.filter(warehouse_id=warehouse_id, product_id__in=ids,
                                       remaining_qty__gt=0).order_by('id'):
        first_batch.setdefault(b.product_id, b)
    rows = []
    for p in products:
        b = first_batch.get(p.pk)
        sp = float(b.selling_price) if b and b.selling_price and b.selling_price > 0 else 0.0
        rows.append({
            'id': p.pk, 'name': p.name, 'barcode': p.barcode or '', 'serial': p.serial_no or '',
            'unit': p.unit.name if p.unit_id else '', 'category': p.category_id or 0,
            'stock': round(float(stock.get(p.pk, 0)), 3), 'price': sp,
        })
    return rows


@login_required
def pos_products(request):
    wh = request.GET.get('warehouse', '')
    if not wh.isdigit():
        return JsonResponse({'results': []})
    q = (request.GET.get('q') or '').strip()
    barcode = (request.GET.get('barcode') or '').strip()
    cat = request.GET.get('category', '')

    qs = Product.objects.filter(is_active=True).select_related('unit')
    if barcode:
        # Scanner: exact barcode / serial. A match returns exactly one item.
        p = qs.filter(Q(barcode=barcode) | Q(serial_no__iexact=barcode)).first()
        return JsonResponse({'results': _product_rows([p], int(wh)) if p else []})
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(barcode__icontains=q) | Q(serial_no__icontains=q))
    else:
        qs = qs.filter(inventory__warehouse_id=int(wh), inventory__stock__gt=0)   # empty search = items in stock
    if cat.isdigit():
        qs = qs.filter(category_id=int(cat))
    products = list(qs.distinct().order_by('name')[:40])
    return JsonResponse({'results': _product_rows(products, int(wh))})


@login_required
def pos_customers(request):
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': []})
    qs = Customer.objects.filter(Q(name__icontains=q) | Q(customer_code__icontains=q) |
                                 Q(contact_number__icontains=q)).order_by('name')[:15]
    return JsonResponse({'results': [{'id': c.pk, 'name': c.name, 'code': c.customer_code or '',
                                      'phone': c.contact_number or ''} for c in qs]})


@login_required
@require_POST
def pos_checkout(request):
    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    try:
        wh = Warehouse.objects.filter(pk=data.get('warehouse')).first()
        if not wh:
            raise ValueError('Select a store.')
        if REQUIRE_SHIFT:
            shift = open_shift_for(request.user)
            if not shift:
                raise ValueError('Open your shift first (with the opening cash).')
            if shift.warehouse_id != wh.pk:
                raise ValueError(f'Your shift is for {shift.warehouse.name}. You cannot make a bill for another store.')
        walkin = _walkin()
        customer = Customer.objects.filter(pk=data.get('customer')).first() or walkin
        raw_items = data.get('items') or []
        if not raw_items:
            raise ValueError('The cart is empty.')

        lines, subtotal = [], Decimal('0')
        for r in raw_items:
            product = Product.objects.filter(pk=r.get('product_id'), is_active=True).first()
            if not product:
                raise ValueError('One of the items no longer exists.')
            qty = _dec(r.get('qty')).quantize(Decimal('0.001'))
            price = _dec(r.get('price')).quantize(Decimal('0.01'))
            if qty <= 0:
                raise ValueError(f'{product.name}: quantity must be greater than zero.')
            if price <= 0:
                raise ValueError(f'{product.name}: enter a price.')
            if BLOCK_BELOW_COST and not is_manager(request.user):
                batch = (StockBatch.objects.filter(product=product, warehouse=wh, remaining_qty__gt=0)
                         .order_by('id').first())
                if batch and price < batch.price:
                    audit(request, 'Sale', 0, 'rejected', {'reason': 'price below cost', 'product': product.name,
                                                           'price': str(price), 'cost': str(batch.price)})
                    raise ValueError(f'{product.name}: the price is below the cost price. '
                                     'Ask a manager to approve this sale.')
            lines.append((product, float(qty), price))
            subtotal += qty * price

        discount = _dec(data.get('discount'))
        if discount < 0 or discount > subtotal:
            raise ValueError('Invalid discount (it must be between 0 and the bill subtotal).')
        manager = is_manager(request.user)
        if not manager:
            cap = setting_number('pos_max_discount_pct', DEFAULT_MAX_DISCOUNT_PCT)
            if subtotal > 0 and float(discount) * 100 / float(subtotal) > cap + 1e-9:
                audit(request, 'Sale', 0, 'rejected', {'reason': 'discount over limit', 'discount': str(discount),
                                                       'subtotal': str(subtotal), 'limit_pct': cap})
                raise ValueError(f'Discount is more than {cap:g}%. Ask a manager to approve this discount.')
        total = subtotal - discount

        pays, paid = [], Decimal('0')
        for p in data.get('payments') or []:
            amt = _dec(p.get('amount'))
            if amt < 0:
                raise ValueError('Invalid payment amount.')
            if amt == 0:
                continue
            if p.get('method') not in {m[0] for m in METHODS}:
                raise ValueError('Invalid payment method.')
            pays.append((p['method'], amt, (p.get('reference') or '')[:100]))
            paid += amt
        if paid > total:
            raise ValueError('Payment is more than the bill total.')
        if customer.pk == walkin.pk and paid < total:
            raise ValueError('A walk-in customer must pay the full bill. Select a customer to sell on credit.')

        with transaction.atomic():
            sale = Sale.objects.create(customer=customer, warehouse=wh, paid=paid, discount_value=discount,
                                       created_by=request.user)
            for product, qty, price in lines:
                SaleItem.objects.create(sale=sale, product=product, qty=qty, price=price)
            for method, amt, ref in pays:
                pm, _ = PaymentMethod.objects.get_or_create(name=method, defaults={'is_active': True})
                SalePayment.objects.create(sale=sale, method=pm, amount=amt, reference_no=ref or None,
                                           created_by=request.user)
                if method == 'cash':          # only cash goes to the drawer; bank money goes to the bank
                    CashBalance.update_balance(amount=amt, transaction_type='sale', user=request.user,
                                               description=f"POS Sale #{sale.bill_no} - {customer.name}")
            try:
                Notification.send_sale_notification(request.user, sale)
            except Exception:
                pass
    except ValueError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': ' '.join(e.messages)}, status=400)
    except Exception as e:                                   # sale was not saved (transaction rolled back)
        return JsonResponse({'success': False, 'message': f'The sale was not saved: {e}'}, status=500)

    audit(request, 'Sale', sale.pk, 'created', {'bill_no': sale.bill_no, 'customer': customer.name,
          'total': str(total), 'paid': str(paid), 'discount': str(discount), 'lines': len(lines),
          'payments': {m: str(a) for m, a, _ in pays}})
    items = [{'name': i.product.name, 'qty': i.qty, 'price': float(i.price), 'total': float(i.total_amt)}
             for i in sale.saleitem_set.select_related('product')]
    return JsonResponse({
        'success': True, 'sale_id': sale.pk, 'bill_no': sale.bill_no,
        'date': sale.sale_date.strftime('%d-%m-%Y %I:%M %p'), 'cashier': request.user.get_username(),
        'customer': customer.name, 'is_walkin': customer.pk == walkin.pk, 'items': items,
        'subtotal': float(subtotal), 'discount': float(discount), 'total': float(total),
        'paid': float(paid), 'balance': float(total - paid),
        'payments': [{'method': m, 'amount': float(a)} for m, a, _ in pays],
    })
