"""
Painel do dia (RF12 Integração treino + alimentação): o resumo de tudo numa tela só.

Não tem tabela nem regra nova: junta o que as outras apps já calculam.
- alimentação de hoje: diario.servicos.resumo_do_dia (meta já ajustada pelos treinos, Sprint 9)
- treino de hoje e gráficos da semana: aderencia.servicos.semana_feita (previsto x feito)
- peso: evolucao.servicos
- ranking da semana: ranking.servicos (se a app estiver instalada)
"""
from dataclasses import dataclass
from datetime import timedelta

from django.apps import apps
from django.utils import timezone

from aderencia.servicos import semana_feita
from diario.servicos import resumo_do_dia
from evolucao import servicos as evolucao
from saude.models import FichaTreino

DIAS_CURTOS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
CODIGOS_DOS_DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom']
DIAS_DO_PESO = 30  # o mini gráfico de peso mostra o último mês


# -------------------------------------------------------------- gráficos da semana
@dataclass
class DiaDoGrafico:
    data: object
    nome: str  # "Seg", "Ter"...
    hoje: bool
    futuro: bool
    kcal: int  # consumidas no diário
    meta: int | None  # meta do dia (já com os treinos)
    gasto_treinos: int  # kcal dos treinos feitos
    treinos: int  # quantos treinos foram registrados
    previstos: int  # quantos esportes tinham dia fixo nesse dia
    altura_kcal: int = 0  # % da altura da barra (preenchido por montar_semana)
    altura_meta: int | None = None
    altura_gasto: int = 0

    @property
    def na_meta(self):
        """Comeu entre 90% e 110% da meta (a mesma tolerância do check-in da dieta)."""
        return bool(self.meta) and self.kcal and 0.9 * self.meta <= self.kcal <= 1.1 * self.meta


@dataclass
class Semana:
    inicio: object
    dias: list
    total_feito: int
    total_previsto: int
    aderencia: int | None
    kcal_treinos: int

    @property
    def fim(self):
        return self.inicio + timedelta(days=6)

    @property
    def dias_na_meta(self):
        return sum(1 for d in self.dias if d.na_meta)

    @property
    def dias_com_registro(self):
        return sum(1 for d in self.dias if d.kcal)

    @property
    def media_kcal(self):
        """Média de kcal consumidas nos dias que tiveram registro no diário."""
        com_registro = [d.kcal for d in self.dias if d.kcal]
        return round(sum(com_registro) / len(com_registro)) if com_registro else None


def _percentual(valor, maior):
    return round(valor * 100 / maior) if maior else 0


def montar_semana(usuario, hoje):
    feita = semana_feita(usuario, hoje=hoje)
    dias = []
    for posicao, dia in enumerate(feita.dias):
        if dia.futuro:
            kcal, meta = 0, None
        else:
            resumo = resumo_do_dia(usuario, dia.data)
            kcal = int(resumo.total['kcal'])
            meta = resumo.meta.meta_calorias if resumo.meta else None
        dias.append(DiaDoGrafico(
            data=dia.data, nome=DIAS_CURTOS[posicao], hoje=dia.hoje, futuro=dia.futuro,
            kcal=kcal, meta=meta,
            gasto_treinos=sum(t.kcal or 0 for t in dia.feitos),
            treinos=len(dia.feitos), previstos=len(dia.previstos),
        ))
    maior_kcal = max([d.kcal for d in dias] + [d.meta or 0 for d in dias])
    maior_gasto = max(d.gasto_treinos for d in dias)
    for dia in dias:
        dia.altura_kcal = _percentual(dia.kcal, maior_kcal)
        dia.altura_meta = _percentual(dia.meta, maior_kcal) if dia.meta else None
        dia.altura_gasto = _percentual(dia.gasto_treinos, maior_gasto)
    return Semana(
        inicio=feita.inicio, dias=dias, total_feito=feita.total_feito,
        total_previsto=feita.total_previsto, aderencia=feita.aderencia,
        kcal_treinos=feita.kcal_real,
    ), feita


# -------------------------------------------------------------- treino de hoje
@dataclass
class TreinoDeHoje:
    previstos: list  # aderencia.servicos.Previsto (esportes com dia fixo hoje)
    feitos: list  # historico.servicos.TreinoFeito registrados hoje
    fichas: list  # FichaTreino ativas marcadas para hoje

    @property
    def descanso(self):
        """Nada previsto e nada feito: dia livre."""
        return not (self.previstos or self.feitos or self.fichas)

    @property
    def kcal(self):
        return sum(t.kcal or 0 for t in self.feitos)


def fichas_de_hoje(usuario, hoje):
    codigo = CODIGOS_DOS_DIAS[hoje.weekday()]
    return [
        ficha for ficha in FichaTreino.objects.filter(usuario=usuario, ativa=True, exercicios__isnull=False).distinct()
        if codigo in ficha.lista_dias()
    ]


# -------------------------------------------------------------- peso
@dataclass
class Peso:
    atual: object
    ultima_pesagem: object
    variacao_mes: object | None  # kg desde a pesagem mais antiga dos últimos 30 dias
    falta: object | None
    linha: str  # pontos "x,y x,y" do mini gráfico (viewBox 0 0 100 32), vazio com menos de 2 pesagens
    dias_sem_pesar: int


def resumo_do_peso(usuario, hoje):
    medidas = evolucao.pesagens(usuario)
    if not medidas:
        return None
    resumo = evolucao.resumo(usuario, medidas)
    ultima = medidas[-1]
    do_mes = [m for m in medidas if timezone.localdate(m.data_registro) >= hoje - timedelta(days=DIAS_DO_PESO)]
    linha = ''
    if len(do_mes) > 1:
        pesos = [float(m.peso_kg) for m in do_mes]
        menor, maior = min(pesos), max(pesos)
        faixa = (maior - menor) or 1
        inicio = do_mes[0].data_registro.timestamp()
        duracao = (do_mes[-1].data_registro.timestamp() - inicio) or 1
        linha = ' '.join(
            '%.1f,%.1f' % ((m.data_registro.timestamp() - inicio) / duracao * 100, 28 - (float(m.peso_kg) - menor) / faixa * 24)
            for m in do_mes
        )
    return Peso(
        atual=resumo.atual,
        ultima_pesagem=ultima.data_registro,
        variacao_mes=(ultima.peso_kg - do_mes[0].peso_kg) if len(do_mes) > 1 else None,
        falta=resumo.falta,
        linha=linha,
        dias_sem_pesar=(hoje - timezone.localdate(ultima.data_registro)).days,
    )


# -------------------------------------------------------------- ranking
def posicao_no_ranking(usuario, hoje):
    """Sua posição na semana entre os amigos (None se a app ranking não estiver instalada)."""
    if not apps.is_installed('ranking'):
        return None
    from ranking.servicos import ranking_semanal
    return ranking_semanal(usuario, hoje=hoje)


# -------------------------------------------------------------- painel
@dataclass
class Painel:
    hoje: object
    alimentacao: object  # diario.servicos.ResumoDoDia
    treino: TreinoDeHoje
    semana: Semana
    peso: Peso | None
    ranking: object | None


def painel_do_dia(usuario, hoje=None):
    hoje = hoje or timezone.localdate()
    semana, feita = montar_semana(usuario, hoje)
    dia = feita.dias[hoje.weekday()]
    return Painel(
        hoje=hoje,
        alimentacao=resumo_do_dia(usuario, hoje),
        treino=TreinoDeHoje(previstos=dia.previstos, feitos=dia.feitos, fichas=fichas_de_hoje(usuario, hoje)),
        semana=semana,
        peso=resumo_do_peso(usuario, hoje),
        ranking=posicao_no_ranking(usuario, hoje),
    )
