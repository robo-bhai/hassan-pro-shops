from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


def _num(v):
    try:
        return Decimal(str(v).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


@register.filter
def sub(a, b):
    return _num(a) - _num(b)


@register.filter
def multiply(a, b):
    return _num(a) * _num(b)


@register.filter
def div(a, b):
    b = _num(b)
    return _num(a) / b if b else 0


@register.filter
def intcomma(v):
    try:
        return "{:,}".format(int(round(float(v))))
    except (ValueError, TypeError):
        return v


@register.filter
def humanize_key(v):
    return str(v).replace("_", " ").strip().title()


@register.filter
def mul(a, b):
    return _num(a) * _num(b)


@register.filter
def can(user, keys):
    """Permission-matrix check in templates:  {% if request.user|can:"view_sales" %}
    Several keys separated by commas mean "any of them":  {% if user|can:"edit_sales,manage_orders" %}"""
    from app.security.permissions import has_matrix_perm
    return has_matrix_perm(user, *[k.strip() for k in str(keys).split(',') if k.strip()])
