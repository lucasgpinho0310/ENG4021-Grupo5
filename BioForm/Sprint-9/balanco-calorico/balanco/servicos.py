"""
Balanço calórico do dia: a meta de calorias passa a contar os treinos feitos de verdade.

A meta salva (MetaNutricional) já inclui a MÉDIA diária dos esportes do perfil ("gasto dos esportes").
No dia, essa média é trocada pelo gasto dos treinos registrados, para não contar o mesmo esporte duas vezes:

- dia que já passou: vale só o que foi registrado (dia sem treino = 0 kcal de esportes);
- hoje: enquanto não houver treino registrado, continua valendo a média (o dia ainda não acabou).

A diferença entra (ou sai) nos carboidratos, a fonte de energia do treino; proteína, gordura e água não mudam.
A meta do dia nunca fica abaixo da TMB, o mesmo piso de segurança da calculadora de metas.
"""
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal

from django.utils import timezone

from historico.servicos import peso_na_data, treino_feito
from metas.calculo import KCAL_POR_G, metas_do_usuario
from saude.models import SessaoAtividade


def treinos_do_dia(usuario, data):
    """Os treinos registrados naquele dia (de qualquer esporte), com o gasto de cada um."""
    sessoes = (
        SessaoAtividade.objects.filter(
            usuario=usuario,
            inicio__gte=timezone.make_aware(datetime.combine(data, time.min)),
            inicio__lte=timezone.make_aware(datetime.combine(data, time.max)),
        )
        .select_related('esporte', 'ficha').prefetch_related('series').order_by('inicio')
    )
    medida = peso_na_data(usuario, data)
    peso = medida.peso_kg if medida else None
    return [treino_feito(sessao, peso) for sessao in sessoes]


@dataclass
class MetaComTreinos:
    """A meta do dia já ajustada. Tem os mesmos campos de MetaNutricional, então o diário usa sem mudar nada."""
    base: object  # MetaNutricional que valia no dia
    data: object
    tmb: int
    atividade_diaria: int  # NEAT + efeito térmico, como na calculadora de metas
    previsto: int  # média diária dos esportes do perfil (já contada na meta salva)
    usando_previsto: bool  # hoje sem treino registrado: a média continua valendo
    treinos: list = field(default_factory=list)  # TreinoFeito do dia
    meta_calorias: int = 0
    meta_carbo_g: Decimal = Decimal('0')

    @property
    def meta_proteina_g(self):
        return self.base.meta_proteina_g

    @property
    def meta_gordura_g(self):
        return self.base.meta_gordura_g

    @property
    def meta_agua_ml(self):
        return self.base.meta_agua_ml

    @property
    def real(self):
        """kcal dos treinos registrados no dia."""
        return sum(t.kcal or 0 for t in self.treinos)

    @property
    def gasto_esportes(self):
        """O que conta no dia: a média (hoje sem treino) ou o que foi feito."""
        return self.previsto if self.usando_previsto else self.real

    @property
    def gasto_total(self):
        """Quanto o corpo gastou no dia: TMB + atividade diária + esportes."""
        return self.tmb + self.atividade_diaria + self.gasto_esportes

    @property
    def ajuste(self):
        """Quanto a meta do dia ficou acima (+) ou abaixo (-) da meta salva."""
        return self.meta_calorias - self.base.meta_calorias


def meta_com_treinos(usuario, data, meta, hoje=None):
    """Ajusta a meta daquele dia pelos treinos feitos. Sem meta ou sem peso, devolve a meta como está."""
    if meta is None or usuario.medida_atual() is None:
        return meta
    hoje = hoje or timezone.localdate()
    calculo = metas_do_usuario(usuario, data)
    treinos = treinos_do_dia(usuario, data)
    usando_previsto = data >= hoje and not treinos
    ajustada = MetaComTreinos(
        base=meta, data=data, tmb=calculo.tmb, atividade_diaria=calculo.atividade_diaria,
        previsto=calculo.gasto_esportes, usando_previsto=usando_previsto, treinos=treinos,
    )
    diferenca = ajustada.gasto_esportes - ajustada.previsto
    ajustada.meta_calorias = max(meta.meta_calorias + diferenca, calculo.tmb)  # piso: a TMB
    aplicada = ajustada.meta_calorias - meta.meta_calorias
    carbo = Decimal(meta.meta_carbo_g) + Decimal(aplicada) / KCAL_POR_G['carbo']
    ajustada.meta_carbo_g = max(carbo, Decimal('0')).quantize(Decimal('0.1'))
    return ajustada


@dataclass
class Balanco:
    meta: MetaComTreinos
    comido_kcal: Decimal

    @property
    def saldo(self):
        """Comido - gasto: negativo = déficit (perde peso), positivo = superávit."""
        return int(self.comido_kcal) - self.meta.gasto_total

    @property
    def restante(self):
        return self.meta.meta_calorias - int(self.comido_kcal)
