"""
Semana feita: o que estava previsto na rotina (esportes do perfil, dias fixos e treinos livres)
comparado com os treinos registrados de verdade, dia a dia e por esporte.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.utils import timezone

from historico.servicos import peso_na_data, treino_feito
from rotina.semana import semana_do_usuario
from saude.models import DIAS_DA_SEMANA, SessaoAtividade

SEMANAS_PARA_TRAS = 11  # dá para voltar até 12 semanas (a atual + 11), como no histórico de treinos


@dataclass
class Previsto:
    """Um esporte com dia fixo naquele dia e se ele foi feito."""
    emoji: str
    nome: str
    feito: bool
    faltou: bool  # o dia já passou e o treino não foi registrado


@dataclass
class DiaFeito:
    data: object
    nome: str
    hoje: bool
    futuro: bool
    previstos: list = field(default_factory=list)  # Previsto
    feitos: list = field(default_factory=list)  # TreinoFeito do dia


@dataclass
class EsporteFeito:
    """Um esporte do perfil na semana: quantos treinos previstos e quantos feitos."""
    emoji: str
    nome: str
    previstos: int
    feitos: int
    kcal_previsto: int | None
    kcal_real: int

    @property
    def contam(self):
        """Feitos que contam para a aderência (treinos além do previsto não compensam outro esporte)."""
        return min(self.feitos, self.previstos)

    @property
    def percentual(self):
        return round(self.contam * 100 / self.previstos) if self.previstos else 0


@dataclass
class SemanaFeita:
    inicio: object  # segunda-feira
    dias: list
    esportes: list  # EsporteFeito
    extras: list  # TreinoFeito de esportes que não estão no perfil

    @property
    def fim(self):
        return self.inicio + timedelta(days=6)

    @property
    def total_previsto(self):
        return sum(e.previstos for e in self.esportes)

    @property
    def total_feito(self):
        return sum(len(d.feitos) for d in self.dias)

    @property
    def aderencia(self):
        """Percentual dos treinos previstos que foram feitos."""
        if not self.total_previsto:
            return None
        return round(sum(e.contam for e in self.esportes) * 100 / self.total_previsto)

    @property
    def kcal_real(self):
        return sum(t.kcal or 0 for d in self.dias for t in d.feitos)

    @property
    def kcal_previsto(self):
        valores = [e.kcal_previsto for e in self.esportes]
        return None if any(v is None for v in valores) else sum(valores)


def semana_feita(usuario, hoje=None, semanas_atras=0):
    """A semana (de segunda a domingo) que está `semanas_atras` semanas antes da atual."""
    hoje = hoje or timezone.localdate()
    inicio = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=semanas_atras)
    rotina = semana_do_usuario(usuario, hoje)

    sessoes = (
        SessaoAtividade.objects.filter(
            usuario=usuario,
            inicio__gte=timezone.make_aware(datetime.combine(inicio, time.min)),
            inicio__lte=timezone.make_aware(datetime.combine(inicio + timedelta(days=6), time.max)),
        )
        .select_related('esporte', 'ficha').prefetch_related('series').order_by('inicio')
    )
    por_dia = {}
    for sessao in sessoes:
        data = timezone.localdate(sessao.inicio)
        medida = peso_na_data(usuario, data)
        por_dia.setdefault(data, []).append(treino_feito(sessao, medida.peso_kg if medida else None))

    dias = []
    for posicao, (codigo, nome) in enumerate(DIAS_DA_SEMANA.items()):
        data = inicio + timedelta(days=posicao)
        feitos = por_dia.get(data, [])
        esportes_feitos = {t.sessao.esporte_id for t in feitos}
        dia = DiaFeito(data=data, nome=nome, hoje=data == hoje, futuro=data > hoje, feitos=feitos)
        for esporte in rotina.esportes:
            if codigo in esporte.dias_fixos:
                feito = esporte.registro.esporte_id in esportes_feitos
                dia.previstos.append(Previsto(esporte.emoji, esporte.nome, feito, not feito and data < hoje))
        dias.append(dia)

    do_perfil = {e.registro.esporte_id for e in rotina.esportes}
    todos = [t for d in dias for t in d.feitos]
    esportes = [
        EsporteFeito(
            emoji=e.emoji, nome=e.nome, previstos=e.registro.frequencia_semanal,
            feitos=sum(1 for t in todos if t.sessao.esporte_id == e.registro.esporte_id),
            kcal_previsto=e.kcal_semana,
            kcal_real=sum(t.kcal or 0 for t in todos if t.sessao.esporte_id == e.registro.esporte_id),
        )
        for e in rotina.esportes
    ]
    extras = [t for t in todos if t.sessao.esporte_id not in do_perfil]
    return SemanaFeita(inicio=inicio, dias=dias, esportes=esportes, extras=extras)
