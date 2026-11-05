"""Selling-price rules for stock batches (pure Python, no Django needed).

One place for the rules used by the single-price update and the bulk price tool on the
Stock Batches page:

* a selling price can never be below the batch cost price;
* 0 means "no selling price" (the system falls back to automatic pricing);
* the column is DecimalField(max_digits=10, decimal_places=2), so the largest value is 99,999,999.99;
* rounding is always UPWARDS, so a rounded price can never fall below cost;
* an optional minimum margin (% of cost) can be passed as ``min_margin``: the price may then not be
  lower than cost + that %, rounded UP to the next paisa (so the margin shown is never below the rule).
"""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

CENT = Decimal('0.01')
MAX_PRICE = Decimal('99999999.99')

MODE_PERCENT = 'percent'   # cost + N %
MODE_AMOUNT = 'amount'     # cost + Rs N
MODE_FIXED = 'fixed'       # exactly Rs N
MODES = (MODE_PERCENT, MODE_AMOUNT, MODE_FIXED)

ROUNDING_STEPS = {'none': None, '1': Decimal('1'), '5': Decimal('5'), '10': Decimal('10')}


class PriceError(ValueError):
    """A price the user typed is not acceptable. str(error) is safe to show to the user."""


def money(value):
    """Decimal rounded to 2 places (half up)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    """'Rs. 1,234.50' for messages."""
    return f'Rs. {money(value):,.2f}'


def parse_money(raw, field='Price'):
    """Turn user input into a non-negative Decimal, or raise PriceError."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise PriceError(f'{field} is required.')
    try:
        value = Decimal(str(raw).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        raise PriceError(f'{field} must be a number.')
    if not value.is_finite():
        raise PriceError(f'{field} must be a number.')
    if value < 0:
        raise PriceError(f'{field} cannot be negative.')
    return money(value)


def normalize_margin(value):
    """A minimum-margin setting as a non-negative Decimal. None / blank / invalid / negative -> 0 (no rule)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal('0')
    try:
        pct = Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal('0')
    if not pct.is_finite() or pct < 0:
        return Decimal('0')
    return pct


def effective_min_margin(category_pct, company_pct):
    """Category rule wins when it is set (0 = "no minimum for this category"); else the company rule."""
    if category_pct is not None and str(category_pct).strip() != '':
        return normalize_margin(category_pct)
    return normalize_margin(company_pct)


def min_price_for(cost, min_margin=None):
    """Lowest allowed selling price: cost + min_margin %, rounded UP to the next paisa."""
    cost = money(cost)
    pct = normalize_margin(min_margin)
    if cost <= 0 or pct <= 0:
        return cost
    return (cost * (Decimal('1') + pct / Decimal('100'))).quantize(CENT, rounding=ROUND_CEILING)


def check_selling_price(cost, price, min_margin=None):
    """Validate a final selling price for a batch with this cost. Returns the price (2 dp).

    0 is allowed and means "clear the selling price". ``min_margin`` (% of cost, optional) adds the
    minimum-margin policy on top of the "never below cost" rule.
    """
    cost = money(cost)
    price = money(price)
    if price == 0:
        return price
    if price < cost:
        raise PriceError(f'Selling price ({fmt(price)}) cannot be less than the cost price ({fmt(cost)}).')
    floor = min_price_for(cost, min_margin)
    if price < floor:
        pct = normalize_margin(min_margin).normalize()
        raise PriceError(f'Selling price ({fmt(price)}) is below the minimum margin of {format(pct, "f")}% '
                         f'(cost {fmt(cost)}). It must be at least {fmt(floor)}.')
    if price > MAX_PRICE:
        raise PriceError(f'Selling price is too large (maximum {fmt(MAX_PRICE)}).')
    return price


def round_up(price, rounding='none'):
    """Round a price UP to the next whole 1 / 5 / 10 rupees ('none' keeps paisa)."""
    if rounding not in ROUNDING_STEPS:
        raise PriceError('Unknown rounding option.')
    step = ROUNDING_STEPS[rounding]
    price = money(price)
    if step is None:
        return price
    return ((price / step).to_integral_value(rounding=ROUND_CEILING) * step).quantize(CENT)


def compute_selling_price(cost, mode, value, rounding='none', min_margin=None):
    """Selling price for one batch from a rule. Raises PriceError if the result is not valid."""
    if mode not in MODES:
        raise PriceError('Unknown pricing mode.')
    cost = money(cost)
    value = parse_money(value, 'Value')
    if mode == MODE_PERCENT:
        price = cost * (Decimal('1') + value / Decimal('100'))
    elif mode == MODE_AMOUNT:
        price = cost + value
    else:
        price = value
    if price <= 0:
        raise PriceError('Resulting selling price must be greater than zero.')
    return check_selling_price(cost, round_up(price, rounding), min_margin)


def margin_percent(cost, price):
    """Profit as a % of cost (same definition as StockBatch.profit_margin_percent)."""
    cost, price = money(cost), money(price)
    if price <= 0 or cost <= 0:
        return Decimal('0.00')
    return money((price - cost) / cost * 100)
