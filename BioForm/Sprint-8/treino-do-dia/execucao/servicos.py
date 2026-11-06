"""
Regras do treino do dia: montar as séries de cada exercício já preenchidas (com o que foi feito
da última vez ou, na primeira vez, com o planejado na série), mostrar o recorde e salvar o treino feito.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from saude.models import Esporte, SerieExecutada, SessaoAtividade

MET_MUSCULACAO = Decimal('5.0')  # o mesmo da migração que popula os esportes


@dataclass
class Linha:
    """Uma série do treino: o que aparece preenchido e, depois do envio, o que foi feito."""
    numero: int
    carga_kg: Decimal
    repeticoes: int | None
    tempo_segundos: int | None
    feita: bool = False
    erro: str = ''


@dataclass
class ExercicioDoTreino:
    exercicio: object  # ExercicioFicha
    linhas: list
    ultima_vez: list = field(default_factory=list)  # SerieExecutada da última sessão com este exercício
    recorde: object = None  # maior carga (ou maior tempo) já feita

    @property
    def por_tempo(self):
        return bool(self.exercicio.tempo_segundos)


def esporte_musculacao():
    esporte, _ = Esporte.objects.get_or_create(nome='Musculação', defaults={'met': MET_MUSCULACAO})
    return esporte


def ultima_vez(exercicio):
    """As séries da sessão mais recente em que o exercício foi feito."""
    ultima = (
        SerieExecutada.objects.filter(exercicio=exercicio)
        .order_by('-sessao__inicio').values_list('sessao_id', flat=True).first()
    )
    if ultima is None:
        return []
    return list(SerieExecutada.objects.filter(exercicio=exercicio, sessao_id=ultima).order_by('numero_serie'))


def recorde(exercicio):
    """Maior carga já feita (exercício por repetições) ou maior tempo (exercício por tempo)."""
    series = SerieExecutada.objects.filter(exercicio=exercicio)
    if exercicio.tempo_segundos:
        return series.aggregate(maior=Max('tempo_segundos'))['maior']
    return series.filter(repeticoes__isnull=False).aggregate(maior=Max('carga_kg'))['maior']


def plano_do_treino(exercicios):
    """
    Uma linha por série planejada. Cada série vem preenchida com o que foi feito na mesma série
    da última vez; se ainda não foi feita, com a carga e as repetições (ou o tempo) da ficha.
    """
    plano = []
    for exercicio in exercicios:
        anteriores = ultima_vez(exercicio)
        feitas = {s.numero_serie: s for s in anteriores}
        linhas = []
        for numero in range(1, exercicio.series_planejadas + 1):
            antes = feitas.get(numero)
            if antes:
                linhas.append(Linha(numero, antes.carga_kg, antes.repeticoes, antes.tempo_segundos))
            else:
                linhas.append(Linha(
                    numero, exercicio.carga_kg,
                    None if exercicio.tempo_segundos else exercicio.repeticoes_planejadas,
                    exercicio.tempo_segundos,
                ))
        plano.append(ExercicioDoTreino(exercicio, linhas, anteriores, recorde(exercicio)))
    return plano


def _numero(texto, tipo, minimo, maximo):
    texto = (texto or '').strip().replace(',', '.')
    if not texto:
        return None
    try:
        valor = tipo(texto)
        if not minimo <= valor <= maximo:
            return None
    except (ValueError, ArithmeticError):  # texto que não é número, ou NaN
        return None
    return valor.quantize(Decimal('0.01')) if tipo is Decimal else valor


def ler_series(plano, dados):
    """
    Lê do formulário o que foi feito em cada série (campos feita-, carga-, reps- e tempo-).
    Atualiza as linhas do plano (para mostrar de novo se houver erro) e devolve quantas foram marcadas.
    """
    marcadas = 0
    for item in plano:
        chave = item.exercicio.id
        for linha in item.linhas:
            sufixo = '%s-%d' % (chave, linha.numero)
            linha.feita = dados.get('feita-' + sufixo) == 'on'
            carga = dados.get('carga-' + sufixo, '').strip()
            linha.carga_kg = _numero(carga, Decimal, 0, 999) if carga else Decimal('0')  # vazio = sem carga
            if item.por_tempo:
                linha.tempo_segundos = _numero(dados.get('tempo-' + sufixo), int, 1, 3600)
            else:
                linha.repeticoes = _numero(dados.get('reps-' + sufixo), int, 1, 999)
            if not linha.feita:
                continue
            marcadas += 1
            if linha.carga_kg is None:
                linha.erro = 'Carga entre 0 e 999 kg.'
            elif item.por_tempo and linha.tempo_segundos is None:
                linha.erro = 'Tempo entre 1 e 3600 segundos.'
            elif not item.por_tempo and linha.repeticoes is None:
                linha.erro = 'Repetições entre 1 e 999.'
    return marcadas


def inicio_do_treino(data, minutos, agora=None):
    """Treino de hoje: começou "minutos" atrás. Treino de outro dia: às 08:00 daquele dia."""
    agora = agora or timezone.localtime()
    if data == agora.date():
        return agora - timedelta(minutes=minutos)
    return timezone.make_aware(datetime.combine(data, time(8, 0)))


@transaction.atomic
def salvar_treino(usuario, ficha, plano, data, minutos, intensidade):
    sessao = SessaoAtividade.objects.create(
        usuario=usuario, esporte=esporte_musculacao(), ficha=ficha,
        inicio=inicio_do_treino(data, minutos), duracao_minutos=minutos, intensidade=intensidade,
    )
    SerieExecutada.objects.bulk_create([
        SerieExecutada(
            sessao=sessao, exercicio=item.exercicio, numero_serie=linha.numero, carga_kg=linha.carga_kg,
            repeticoes=None if item.por_tempo else linha.repeticoes,
            tempo_segundos=linha.tempo_segundos if item.por_tempo else None,
        )
        for item in plano for linha in item.linhas if linha.feita
    ])
    return sessao
