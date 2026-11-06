"""
Treino feito (RF06 Registro de exercícios / RF07 Histórico de treinos).

Dois jeitos de registrar, que vão para as mesmas tabelas e o mesmo histórico:
- "Registrar treino" (treino livre): qualquer esporte, com nome, observações e, se quiser, uma lista
  de exercícios com séries, repetições e carga. Tela vinda do protótipo App Saúde/Registro de treino.
- "Treinar agora" (a partir de uma série de academia): uma linha por série planejada, já preenchida
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


@dataclass
class ExercicioLivre:
    """Uma linha da lista de exercícios do treino livre: vira `series` séries iguais."""
    nome: str
    series: int
    repeticoes: int
    carga_kg: Decimal = Decimal('0')


def esporte_musculacao():
    """O esporte das sessões de academia (vem da migração 0003; criado aqui só se alguém apagou)."""
    esporte = Esporte.objects.filter(nome__iexact=ESPORTE).first()
    return esporte or Esporte.objects.create(nome=ESPORTE, met=MET_MUSCULACAO)


def esportes_para_escolher(usuario):
    """Esportes do catálogo, com os que a pessoa pratica (perfil, passo 3) primeiro."""
    do_perfil = list(
        Esporte.objects.filter(esporteusuario__usuario=usuario).order_by('nome')
    )
    outros = Esporte.objects.exclude(id__in=[e.id for e in do_perfil]).order_by('nome')
    return do_perfil + list(outros)


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
            nome_exercicio=exercicio.nome_exercicio,
            ordem=posicao,
            numero_serie=serie.numero,
            carga_kg=serie.carga_kg,
            repeticoes=serie.repeticoes,
            tempo_segundos=serie.tempo_segundos,
        )
        for posicao, (exercicio, series) in enumerate(feitos, start=1)
        for serie in series
    ])
    return sessao


@transaction.atomic
def registrar_treino_livre(usuario, esporte, inicio, duracao_minutos, intensidade,
                           nome='', observacoes='', distancia_km=None, exercicios=()):
    """Grava um treino livre ("Registrar treino"). exercicios: lista de ExercicioLivre (pode ser vazia)."""
    sessao = SessaoAtividade.objects.create(
        usuario=usuario,
        esporte=esporte,
        inicio=inicio,
        duracao_minutos=duracao_minutos,
        intensidade=intensidade,
        nome=nome,
        observacoes=observacoes,
        distancia_km=distancia_km,
    )
    SerieExecutada.objects.bulk_create([
        SerieExecutada(
            sessao=sessao,
            nome_exercicio=exercicio.nome,
            ordem=posicao,
            numero_serie=numero,
            carga_kg=exercicio.carga_kg,
            repeticoes=exercicio.repeticoes,
        )
        for posicao, exercicio in enumerate(exercicios, start=1)
        for numero in range(1, exercicio.series + 1)
    ])
    return sessao


def sessoes_do_usuario(usuario):
    """Todos os treinos da pessoa (livres e de série), do mais novo para o mais antigo, com os totais."""
    volume = ExpressionWrapper(
        F('series__carga_kg') * F('series__repeticoes'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    return (
        SessaoAtividade.objects
        .filter(usuario=usuario)
        .select_related('ficha', 'esporte')
        .annotate(
            total_series=Count('series'),
            total_exercicios=Count('series__ordem', distinct=True),
            volume_kg=Sum(volume),  # carga x repetições; séries por tempo não entram
        )
        .order_by('-inicio')
    )


def exercicios_da_sessao(sessao):
    """[(nome do exercício, [séries])] na ordem em que foram feitos."""
    series = sessao.series.order_by('ordem', 'numero_serie')
    return [
        (grupo[0].nome_exercicio, grupo)
        for grupo in (list(g) for _, g in groupby(series, key=lambda s: s.ordem))
    ]


def volume(series):
    """Soma de carga x repetições (kg levantados no total)."""
    return sum((s.carga_kg * s.repeticoes for s in series if s.repeticoes), Decimal('0'))
