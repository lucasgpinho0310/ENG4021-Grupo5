from django import template

from saude.models import nomes_curtos_dos_dias

register = template.Library()


@register.filter
def milhar(numero):
    """2180 -> "2.180" (separador de milhar brasileiro)."""
    try:
        return '{:,}'.format(int(numero)).replace(',', '.')
    except (TypeError, ValueError):
        return numero


@register.filter
def absoluto(numero):
    return abs(numero)


@register.filter
def vezes_por_semana(frequencia):
    return 'Diário' if frequencia == 7 else '%dx' % frequencia


@register.filter
def decimal_br(numero):
    """78.5 -> "78,5"."""
    if numero is None:
        return ''
    texto = ('%.1f' % float(numero)).rstrip('0').rstrip('.')
    return texto.replace('.', ',')


@register.filter
def iniciais(nome):
    """"Ana Beatriz Souza" -> "AS"."""
    partes = (nome or '').split()
    if not partes:
        return '?'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter
def cpf_mascarado(cpf):
    """Mostra só o começo e o fim do CPF na listagem: 529.***.***-25."""
    if not cpf or len(cpf) != 11:
        return cpf
    return '%s.***.***-%s' % (cpf[:3], cpf[9:])


@register.filter
def cpf_formatado(cpf):
    if not cpf or len(cpf) != 11:
        return cpf
    return '%s.%s.%s-%s' % (cpf[:3], cpf[3:6], cpf[6:9], cpf[9:])


@register.filter
def celular_formatado(celular):
    if not celular:
        return ''
    if len(celular) == 11:
        return '(%s) %s-%s' % (celular[:2], celular[2:7], celular[7:])
    if len(celular) == 10:
        return '(%s) %s-%s' % (celular[:2], celular[2:6], celular[6:])
    return celular


@register.filter
def dias_curtos(dias):
    """'seg,qua' -> 'Seg, Qua'."""
    return nomes_curtos_dos_dias(dias)
