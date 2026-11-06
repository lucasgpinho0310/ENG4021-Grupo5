import re
from decimal import Decimal

from django import template

register = template.Library()

YOUTUBE = re.compile(r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})')


@register.filter
def intervalo(segundos):
    """45 -> "45s"; 90 -> "90s"; 120 -> "2 min"; 150 -> "2min30"."""
    if not segundos:
        return ''
    segundos = int(segundos)
    if segundos < 120:
        return '%ds' % segundos
    minutos, resto = divmod(segundos, 60)
    return '%d min' % minutos if resto == 0 else '%dmin%02d' % (minutos, resto)


@register.filter
def carga(valor):
    """Decimal('12.50') -> "12,5 kg"; Decimal('0') -> "0 kg"."""
    if valor is None:
        return ''
    valor = Decimal(valor).normalize()
    texto = '{:f}'.format(valor).replace('.', ',')
    return '%s kg' % texto


@register.filter
def series_de(exercicio):
    """Como mostrar as séries: o texto da ficha (3x10+10), séries x repetições ou séries x tempo (3x30s)."""
    if exercicio.series_texto:
        texto = exercicio.series_texto
    elif exercicio.tempo_segundos:
        texto = '%dx%s' % (exercicio.series_planejadas, intervalo(exercicio.tempo_segundos).replace(' ', ''))
    else:
        texto = '%dx%d' % (exercicio.series_planejadas, exercicio.repeticoes_planejadas)
    if exercicio.cada_lado and 'cada lado' not in texto.lower():
        texto += ' cada lado'
    return texto


@register.filter
def video_embed(url):
    """Endereço para incorporar o vídeo do YouTube na página; vazio para outros sites."""
    achado = YOUTUBE.search(url or '')
    return 'https://www.youtube-nocookie.com/embed/%s' % achado.group(1) if achado else ''


@register.filter
def serie_feita(serie):
    """Uma série feita: "40 kg × 10", "12 reps" (sem carga), "30s" ou "5 kg × 45s"."""
    feito = intervalo(serie.tempo_segundos) if serie.tempo_segundos else str(serie.repeticoes)
    if serie.carga_kg:
        return '%s × %s' % (carga(serie.carga_kg), feito)
    return feito if serie.tempo_segundos else '%s reps' % feito


@register.filter
def series_feitas(series):
    """Todas as séries de um exercício numa linha: "40 kg × 10 · 40 kg × 9 · 42,5 kg × 8"."""
    return ' · '.join(serie_feita(serie) for serie in series)


@register.filter
def toneladas(kg):
    """Volume do treino: 850 -> "850 kg"; 12340 -> "12,3 t"."""
    if not kg:
        return '—'
    kg = Decimal(kg)
    if kg >= 1000:
        return ('%.1f t' % (kg / 1000)).replace('.', ',')
    return '%s kg' % '{:,.0f}'.format(kg).replace(',', '.')
