"""
Histórico de treinos: os treinos feitos (de qualquer esporte), agrupados por semana, com tempo,
calorias gastas e volume (carga x repetições) da musculação.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from metas.calculo import arredondar, gasto_semanal_do_esporte
from rotina.semana import aparencia
from saude.models import SerieExecutada, SessaoAtividade

SEMANAS_NO_HISTORICO = 12


def peso_na_data(usuario, data):
    """Peso registrado até o fim daquele dia (ou o primeiro peso, se o treino é anterior a ele)."""
    fim_do_dia = timezone.make_aware(datetime.combine(data, time.max))
    medidas = usuario.historicomedida_set
    medida = medidas.filter(data_registro__lte=fim_do_dia).order_by('-data_registro').first()
    return medida or medidas.order_by('data_registro').first()


def gasto_da_sessao(sessao, peso_kg):
    """kcal gastas no treino: o mesmo cálculo por MET usado na meta (sem o repouso, que já está na TMB)."""
    if peso_kg is None:
        return None
    return arredondar(gasto_semanal_do_esporte(
        peso_kg, sessao.esporte.met, 1, sessao.intensidade, sessao.duracao_minutos,
    ))


@dataclass
class TreinoFeito:
    sessao: object  # SessaoAtividade
    kcal: int | None
    volume_kg: Decimal
    total_series: int

    @property
    def emoji(self):
        return aparencia(self.sessao.esporte)[0]

    @property
    def titulo(self):
        return self.sessao.ficha.nome_ficha if self.sessao.ficha else self.sessao.esporte.nome


@dataclass
class SemanaDeTreinos:
    inicio: object  # segunda-feira
    treinos: list = field(default_factory=list)

    @property
    def fim(self):
        return self.inicio + timedelta(days=6)

    @property
    def minutos(self):
        return sum(t.sessao.duracao_minutos for t in self.treinos)

    @property
    def horas(self):
        return '%dh%02d' % divmod(self.minutos, 60)

    @property
    def kcal(self):
        return sum(t.kcal or 0 for t in self.treinos)

    @property
    def volume_kg(self):
        return sum((t.volume_kg for t in self.treinos), Decimal('0'))


def treino_feito(sessao, peso_kg):
    series = list(sessao.series.all())
    return TreinoFeito(
        sessao=sessao,
        kcal=gasto_da_sessao(sessao, peso_kg),
        volume_kg=sum((s.volume_kg() for s in series), Decimal('0')),
        total_series=len(series),
    )


def semanas_do_usuario(usuario, hoje=None, quantas=SEMANAS_NO_HISTORICO):
    """As últimas semanas com treino, da mais recente para a mais antiga (semanas vazias ficam de fora)."""
    hoje = hoje or timezone.localdate()
    primeira = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=quantas - 1)
    sessoes = (
        SessaoAtividade.objects.filter(usuario=usuario, inicio__gte=timezone.make_aware(datetime.combine(primeira, time.min)))
        .select_related('esporte', 'ficha').prefetch_related('series').order_by('-inicio')
    )
    semanas = {}
    for sessao in sessoes:
        data = timezone.localdate(sessao.inicio)
        inicio = data - timedelta(days=data.weekday())
        medida = peso_na_data(usuario, data)
        semanas.setdefault(inicio, SemanaDeTreinos(inicio)).treinos.append(
            treino_feito(sessao, medida.peso_kg if medida else None)
        )
    return list(semanas.values())


@dataclass
class ExercicioFeito:
    exercicio: object  # ExercicioFicha
    series: list
    recorde: bool  # bateu a maior carga (ou o maior tempo) de antes deste treino

    @property
    def volume_kg(self):
        return sum((s.volume_kg() for s in self.series), Decimal('0'))


def exercicios_da_sessao(sessao):
    """As séries feitas, agrupadas por exercício na ordem da ficha, marcando os recordes batidos."""
    series = list(sessao.series.select_related('exercicio').order_by('exercicio__ordem_execucao', 'numero_serie'))
    grupos = {}
    for serie in series:
        grupos.setdefault(serie.exercicio, []).append(serie)
    feitos = []
    for exercicio, lista in grupos.items():
        antes = SerieExecutada.objects.filter(exercicio=exercicio, sessao__inicio__lt=sessao.inicio)
        if exercicio.tempo_segundos:
            melhor_antes = antes.aggregate(maior=Max('tempo_segundos'))['maior']
            melhor_agora = max(s.tempo_segundos or 0 for s in lista)
        else:
            melhor_antes = antes.filter(repeticoes__isnull=False).aggregate(maior=Max('carga_kg'))['maior']
            melhor_agora = max(s.carga_kg for s in lista)
        recorde = melhor_antes is not None and melhor_agora > melhor_antes
        feitos.append(ExercicioFeito(exercicio, lista, recorde))
    return feitos
