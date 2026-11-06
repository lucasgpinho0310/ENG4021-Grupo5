from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def valor_carga(valor):
    """Valor do campo de carga: Decimal('20.00') -> "20"; Decimal('12.50') -> "12.5"; None -> ""."""
    if valor is None:
        return ''
    return '{:f}'.format(Decimal(valor).normalize())
