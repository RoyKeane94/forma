"""Template filters for displaying stored prices."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def gbp_amount(value):
    """
    Numeric part after £: strip insignificant trailing zeros (65.00 → 65),
    keep fractional pounds without unnecessary zeros (65.50 → 65.5).
    """
    if value is None or value == '':
        return ''
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    d = d.quantize(Decimal('0.01'))
    s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s
