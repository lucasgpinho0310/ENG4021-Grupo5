"""
A semana de treinos do usuário, montada a partir dos esportes do perfil:
o que cai em cada dia fixo, quantos treinos ficam livres e quanto cada esporte gasta.
"""
from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.text import slugify

from contas.forms import APARENCIA_ESPORTES
from metas.calculo import arredondar, gasto_semanal_do_esporte
from saude.models import DIAS_DA_SEMANA

CODIGOS_DOS_DIAS = list(DIAS_DA_SEMANA)  # seg ... dom, na ordem do weekday() do Python


@dataclass
class EsporteNaSemana:
    registro: object  # EsporteUsuario
    emoji: str
    nome: str
    minutos_semana: int
    kcal_semana: int | None  # None quando ainda não há peso registrado

    @property
    def dias_fixos(self):
        return self.registro.lista_dias_fixos()

    @property
    def livres(self):
        return self.registro.treinos_livres


@dataclass
class DiaDaSemana:
    codigo: str
    nome: str
    hoje: bool
    esportes: list = field(default_factory=list)


@dataclass
class Semana:
    dias: list
    esportes: list

    @property
    def livres(self):
        return [e for e in self.esportes if e.livres]

    @property
    def treinos_semana(self):
        return sum(e.registro.frequencia_semanal for e in self.esportes)

    @property
    def minutos_semana(self):
        return sum(e.minutos_semana for e in self.esportes)

    @property
    def horas_semana(self):
        return '%dh%02d' % divmod(self.minutos_semana, 60)

    @property
    def kcal_semana(self):
        if any(e.kcal_semana is None for e in self.esportes):
            return None
        return sum(e.kcal_semana for e in self.esportes)

    @property
    def kcal_por_dia(self):
        """Média diária: é o "gasto dos esportes" que entra na meta de calorias."""
        total = self.kcal_semana
        return None if total is None else arredondar(total / 7)


def aparencia(esporte):
    return APARENCIA_ESPORTES.get(slugify(esporte.nome), ('🏅', esporte.nome))


def semana_do_usuario(usuario, hoje=None):
    hoje = hoje or timezone.localdate()
    medida = usuario.medida_atual()
    peso = medida.peso_kg if medida else None

    esportes = []
    for registro in usuario.esportes.select_related('esporte').order_by('-frequencia_semanal', 'esporte__nome'):
        emoji, nome = aparencia(registro.esporte)
        kcal = None
        if peso:
            kcal = arredondar(gasto_semanal_do_esporte(
                peso, registro.esporte.met, registro.frequencia_semanal,
                registro.intensidade, registro.duracao_minutos,
            ))
        esportes.append(EsporteNaSemana(
            registro=registro,
            emoji=emoji,
            nome=nome,
            minutos_semana=registro.duracao_minutos * registro.frequencia_semanal,
            kcal_semana=kcal,
        ))

    dias = []
    for codigo, nome in DIAS_DA_SEMANA.items():
        dia = DiaDaSemana(codigo=codigo, nome=nome, hoje=CODIGOS_DOS_DIAS[hoje.weekday()] == codigo)
        dia.esportes = [e for e in esportes if codigo in e.dias_fixos]
        dias.append(dia)
    return Semana(dias=dias, esportes=esportes)
