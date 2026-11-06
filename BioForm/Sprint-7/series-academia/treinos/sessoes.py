"""
Treino feito (RF06 Registro de exercícios / RF07 Histórico de treinos).

A ficha diz o que fazer; a sessão guarda o que foi feito de verdade: cada série com a carga e
as repetições (ou o tempo, em exercícios como a prancha). Na próxima vez, o formulário já vem
com o que a pessoa fez da última vez.
"""
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

from saude.models import Esporte, SerieExecutada, SessaoAtividade

from .servicos import musculacao_do_perfil

ESPORTE = 'Musculação'
MET_MUSCULACAO = Decimal('5.0')  # o mesmo da migração 0003_popular_esportes
DURACAO_PADRAO = 60
INTENSIDADE_PADRAO = 'moderada'
SERIES_MAXIMAS = 10  # linhas por exercício no formulário


@dataclass
class SerieFeita:
    numero: int
    carga_kg: Decimal
    repeticoes: int = None
    tempo_segundos: int = None


def esporte_musculacao():
    """O esporte das sessões de academia (vem da migração 0003; criado aqui só se alguém apagou)."""
    esporte = Esporte.objects.filter(nome__iexact=ESPORTE).first()
    return esporte or Esporte.objects.create(nome=ESPORTE, met=MET_MUSCULACAO)


def padroes_do_perfil(usuario):
    """Duração e intensidade que já vêm marcadas: as da musculação no perfil (passo 3)."""
    musculacao = musculacao_do_perfil(usuario)
    if musculacao is None:
        return DURACAO_PADRAO, INTENSIDADE_PADRAO
    return musculacao.duracao_minutos, musculacao.intensidade


def ultimas_series(usuario, exercicios):
    """
    {id do exercício: (sessão, [séries])} com o treino mais recente em que cada exercício foi feito.
    Serve para mostrar "Última vez" na ficha e para preencher o formulário do próximo treino.
    """
    ultimas = {}
    series = (
        SerieExecutada.objects
        .filter(exercicio__in=exercicios, sessao__usuario=usuario)
        .select_related('sessao')
        .order_by('-sessao__inicio', 'sessao_id', 'numero_serie')
    )
    for serie in series.iterator():
        atual = ultimas.get(serie.exercicio_id)
        if atual is None:
            ultimas[serie.exercicio_id] = (serie.sessao, [serie])
        elif atual[0].id == serie.sessao_id:
            atual[1].append(serie)
    return ultimas


@transaction.atomic
def registrar_treino(usuario, ficha, inicio, duracao_minutos, intensidade, feitos):
    """
    Grava a sessão e as séries feitas.
    feitos: lista de (exercício, [SerieFeita]) — só os exercícios com pelo menos uma série.
    """
    sessao = SessaoAtividade.objects.create(
        usuario=usuario,
        esporte=esporte_musculacao(),
        ficha=ficha,
        inicio=inicio,
        duracao_minutos=duracao_minutos,
        intensidade=intensidade,
    )
    SerieExecutada.objects.bulk_create([
        SerieExecutada(
            sessao=sessao,
            exercicio=exercicio,
            numero_serie=serie.numero,
            carga_kg=serie.carga_kg,
            repeticoes=serie.repeticoes,
            tempo_segundos=serie.tempo_segundos,
        )
        for exercicio, series in feitos
        for serie in series
    ])
    return sessao


def sessoes_do_usuario(usuario):
    """Treinos de academia da pessoa, do mais novo para o mais antigo, com os totais de cada um."""
    volume = ExpressionWrapper(
        F('series__carga_kg') * F('series__repeticoes'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    return (
        SessaoAtividade.objects
        .filter(usuario=usuario, esporte__nome__iexact=ESPORTE)
        .select_related('ficha')
        .annotate(
            total_series=Count('series'),
            total_exercicios=Count('series__exercicio', distinct=True),
            volume_kg=Sum(volume),  # carga x repetições; séries por tempo não entram
        )
        .order_by('-inicio')
    )


def exercicios_da_sessao(sessao):
    """[(exercício, [séries])] na ordem da ficha."""
    series = sessao.series.select_related('exercicio').order_by(
        'exercicio__ordem_execucao', 'exercicio_id', 'numero_serie',
    )
    return [(exercicio, list(grupo)) for exercicio, grupo in groupby(series, key=lambda s: s.exercicio)]


def volume(series):
    """Soma de carga x repetições (kg levantados no total)."""
    return sum((s.carga_kg * s.repeticoes for s in series if s.repeticoes), Decimal('0'))
