# app/templatetags/custom_filters.py

from django import template
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json

register = template.Library()

# ============================================
# SAFE DECIMAL CONVERSION HELPER
# ============================================

def safe_decimal(value, default=Decimal('0.00')):
    """Safely convert value to Decimal"""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        # Clean the string
        if isinstance(value, str):
            # Remove commas, spaces, currency symbols
            cleaned = value.replace(',', '').replace(' ', '').replace('Rs.', '').replace('$', '')
            if cleaned == '':
                return default
            return Decimal(cleaned)
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

# ============================================
# SUM FILTERS
# ============================================

@register.filter(name='sum_attribute')
def sum_attribute(objects, attr):
    """
    Sum the values of a specific attribute across a queryset.
    Usage: {{ queryset|sum_attribute:'field_name' }}
    """
    total = Decimal('0.00')
    if objects:
        for obj in objects:
            try:
                value = getattr(obj, attr, Decimal('0.00'))
                if callable(value):
                    value = value()
                if value:
                    total += safe_decimal(value)
            except (ValueError, TypeError, AttributeError):
                continue
    return total

# ============================================
# DICTIONARY FILTERS
# ============================================

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Get an item from a dictionary by key safely."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

@register.filter(name='get_attr')
def get_attr(obj, attr):
    """Get attribute from an object safely."""
    if obj is None:
        return ''
    try:
        value = getattr(obj, attr, '')
        if callable(value):
            return value()
        return value
    except (AttributeError, TypeError):
        return ''

# ============================================
# MATH FILTERS - FIXED
# ============================================

@register.filter(name='multiply')
def multiply(value, arg):
    """Multiply value by arg."""
    try:
        v = safe_decimal(value)
        a = safe_decimal(arg)
        return v * a
    except (ValueError, TypeError):
        return Decimal('0.00')

@register.filter(name='add')
def add_filter(value, arg):
    """Add arg to value - FIXED with safe_decimal"""
    try:
        v = safe_decimal(value)
        a = safe_decimal(arg)
        return v + a
    except (ValueError, TypeError):
        return Decimal('0.00')

@register.filter(name='subtract')
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        v = safe_decimal(value)
        a = safe_decimal(arg)
        return v - a
    except (ValueError, TypeError):
        return Decimal('0.00')

@register.filter(name='div')
def div(value, arg):
    """Divide value by arg. Returns 0 if division by zero occurs."""
    try:
        v = safe_decimal(value)
        a = safe_decimal(arg)
        if a == 0:
            return Decimal('0.00')
        return v / a
    except (ValueError, TypeError):
        return Decimal('0.00')

@register.filter(name='percentage')
def percentage(value, total):
    """Calculate percentage: (value / total) * 100"""
    try:
        v = safe_decimal(value)
        t = safe_decimal(total)
        if t == 0:
            return Decimal('0.00')
        return (v / t) * 100
    except (ValueError, TypeError):
        return Decimal('0.00')

# ============================================
# FORMATTING FILTERS
# ============================================

@register.filter(name='currency')
def currency(value, symbol='Rs.'):
    """Format value as currency."""
    try:
        val = safe_decimal(value)
        return f"{symbol} {val:,.2f}"
    except (ValueError, TypeError):
        return f"{symbol} 0.00"

@register.filter(name='floatformat')
def floatformat_filter(value, arg=2):
    """Format a float with given decimal places."""
    try:
        val = safe_decimal(value)
        return f"{val:.{int(arg)}f}"
    except (ValueError, TypeError):
        return str(value)

@register.filter(name='intcomma')
def intcomma(value):
    """Add commas to number"""
    try:
        val = safe_decimal(value)
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return str(value)

@register.filter(name='abs')
def abs_filter(value):
    """Return absolute value of a number"""
    try:
        val = safe_decimal(value)
        return abs(val)
    except (TypeError, ValueError):
        return value

# ============================================
# JSON FILTERS
# ============================================

@register.filter(name='jsonify')
def jsonify(value):
    """Convert value to JSON string."""
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return '{}'

@register.filter(name='dict_values')
def dict_values(dictionary):
    """Get values from dictionary as list."""
    if dictionary and isinstance(dictionary, dict):
        return list(dictionary.values())
    return []

@register.filter(name='dict_keys')
def dict_keys(dictionary):
    """Get keys from dictionary as list."""
    if dictionary and isinstance(dictionary, dict):
        return list(dictionary.keys())
    return []

# ============================================
# LIST FILTERS
# ============================================

@register.filter(name='first')
def first_filter(value):
    """Get first item from a list."""
    if value and hasattr(value, '__getitem__'):
        try:
            return value[0]
        except (IndexError, TypeError):
            return None
    return None

@register.filter(name='last')
def last_filter(value):
    """Get last item from a list."""
    if value and hasattr(value, '__getitem__'):
        try:
            return value[-1]
        except (IndexError, TypeError):
            return None
    return None

@register.filter(name='length')
def length_filter(value):
    """Get length of a list or dictionary."""
    if value is None:
        return 0
    try:
        return len(value)
    except (TypeError):
        return 0

@register.filter(name='is_empty')
def is_empty(value):
    """Check if a list or dictionary is empty."""
    if value is None:
        return True
    try:
        return len(value) == 0
    except (TypeError):
        return True

# ============================================
# VENDOR PRICING REPORT FILTERS
# ============================================

@register.filter(name='list_values')
def list_values(dictionary):
    """Convert dictionary values to list."""
    if dictionary is None:
        return []
    if isinstance(dictionary, dict):
        return list(dictionary.values())
    return []

@register.filter(name='filter_none')
def filter_none(values):
    """Filter out None/empty values from a list."""
    if values is None:
        return []
    return [v for v in values if v is not None]

@register.filter(name='min')
def min_filter(values):
    """Get minimum value from a list of numbers."""
    if values is None:
        return None
    if isinstance(values, dict):
        values = list(values.values())
    if not values:
        return None
    try:
        numeric_values = [float(v) for v in values if v is not None]
        if not numeric_values:
            return None
        return min(numeric_values)
    except (ValueError, TypeError):
        return None

@register.filter(name='max')
def max_filter(values):
    """Get maximum value from a list of numbers."""
    if values is None:
        return None
    if isinstance(values, dict):
        values = list(values.values())
    if not values:
        return None
    try:
        numeric_values = [float(v) for v in values if v is not None]
        if not numeric_values:
            return None
        return max(numeric_values)
    except (ValueError, TypeError):
        return None

@register.filter(name='avg')
def avg_filter(values):
    """Get average value from a list of numbers."""
    if values is None:
        return None
    if isinstance(values, dict):
        values = list(values.values())
    if not values:
        return None
    try:
        numeric_values = [float(v) for v in values if v is not None]
        if not numeric_values:
            return None
        return sum(numeric_values) / len(numeric_values)
    except (ValueError, TypeError):
        return None