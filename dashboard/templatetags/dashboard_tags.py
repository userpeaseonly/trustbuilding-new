from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key, [])


@register.filter
def formatted_amount(value):
    """
    Format a number with space thousands separator.
    Examples:
        1000000 -> "1 000 000"
        1250000.50 -> "1 250 000.50"
    """
    if value is None or value == '':
        return "0"
    try:
        if isinstance(value, float):
            d_val = Decimal(str(value))
        elif isinstance(value, (int, str)):
            d_val = Decimal(str(value))
        elif isinstance(value, Decimal):
            d_val = value
        else:
            return str(value)
        
        # Check if integer value
        if d_val % 1 == 0:
            return f"{int(d_val):,}".replace(",", " ")
        else:
            return f"{d_val:,.2f}".replace(",", " ")
    except Exception:
        return str(value)


@register.filter
def uzs(value):
    """
    Format a number with space thousands separator and 'UZS' currency suffix.
    Examples:
        1000000 -> "1 000 000 UZS"
        1250000.50 -> "1 250 000.50 UZS"
    """
    formatted = formatted_amount(value)
    return f"{formatted} UZS"
