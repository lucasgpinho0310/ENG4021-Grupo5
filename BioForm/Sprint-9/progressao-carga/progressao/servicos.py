"""
Progressão de carga de um exercício: a melhor série de cada treino (maior carga ou, em exercício
por tempo, maior tempo), o gráfico treino a treino, o recorde e quanto evoluiu desde o primeiro treino.

Conta as séries feitas pela série de academia ("Começar treino" / "Treinar agora") e também as do
treino livre com o mesmo nome de exercício.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from saude.models import SerieExecutada

# Tamanho do desenho do gráfico (o SVG se ajusta à largura da tela)
LARGURA, ALTURA = 640, 220
MARGEM_ESQ, MARGEM_DIR, MARGEM_TOPO, MARGEM_BAIXO = 48, 16, 16, 28


def series_do_exercicio(usuario, exercicio):
    return (
        SerieExecutada.objects.filter(sessao__usuario=usuario)
        .filter(Q(exercicio=exercicio) | Q(exercicio__isnull=True, nome_exercicio__iexact=exercicio.nome_exercicio))
        .select_related('sessao').order_by('sessao__inicio', 'numero_serie')
    )


@dataclass
class Marca:
    """A melhor série de um treino."""
    sessao: object  # SessaoAtividade
    melhor: object  # SerieExecutada
    total_series: int
    volume_kg: Decimal

    @property
    def data(self):
        return timezone.localdate(self.sessao.inicio)


def valor(serie, por_tempo):
    """O número que entra no gráfico: segundos (por tempo) ou carga em kg."""
    return (serie.tempo_segundos or 0) if por_tempo else serie.carga_kg


def marcas_por_treino(series, por_tempo):
    """Uma marca por treino, do mais antigo para o mais recente. Empate na carga: vence quem fez mais repetições."""
    por_sessao = {}
    for serie in series:
        por_sessao.setdefault(serie.sessao_id, []).append(serie)
    marcas = []
    for lista in por_sessao.values():
        melhor = max(lista, key=lambda s: (valor(s, por_tempo), s.repeticoes or 0))
        marcas.append(Marca(
            sessao=lista[0].sessao, melhor=melhor, total_series=len(lista),
            volume_kg=sum((s.volume_kg() for s in lista), Decimal('0')),
        ))
    return marcas


@dataclass
class Ponto:
    x: float
    y: float
    marca: Marca


@dataclass
class Grafico:
    pontos: list
    linha: str
    marcas_y: list  # [(y, rótulo)]
    largura: int = LARGURA
    altura: int = ALTURA
    esquerda: int = MARGEM_ESQ
    direita: int = LARGURA - MARGEM_DIR


def grafico(marcas, por_tempo):
    """Treinos no eixo X (um depois do outro, espaçados igualmente), carga ou tempo no eixo Y."""
    if len(marcas) < 2:
        return None
    valores = [float(valor(m.melhor, por_tempo)) for m in marcas]
    folga = 5 if por_tempo else 1  # 5 s ou 1 kg de folga em cima e embaixo
    menor, maior = max(min(valores) - folga, 0), max(valores) + folga
    area_x = LARGURA - MARGEM_ESQ - MARGEM_DIR
    area_y = ALTURA - MARGEM_TOPO - MARGEM_BAIXO

    def y_do_valor(v):
        return round(MARGEM_TOPO + (maior - v) / (maior - menor) * area_y, 1)

    pontos = [
        Ponto(round(MARGEM_ESQ + posicao * area_x / (len(marcas) - 1), 1), y_do_valor(v), marca)
        for posicao, (v, marca) in enumerate(zip(valores, marcas))
    ]
    rotulos = [(y_do_valor(v), '%g' % round(v, 1)) for v in (maior, (maior + menor) / 2, menor)]
    return Grafico(pontos=pontos, linha=' '.join('%s,%s' % (p.x, p.y) for p in pontos), marcas_y=rotulos)


@dataclass
class Progressao:
    exercicio: object  # ExercicioFicha
    por_tempo: bool
    marcas: list  # Marca, do treino mais antigo para o mais recente

    @property
    def recorde(self):
        return max(self.marcas, key=lambda m: (valor(m.melhor, self.por_tempo), m.melhor.repeticoes or 0)) if self.marcas else None

    @property
    def primeira(self):
        return self.marcas[0] if self.marcas else None

    @property
    def ultima(self):
        return self.marcas[-1] if self.marcas else None

    @property
    def evolucao(self):
        """Diferença entre a melhor série do último treino e a do primeiro (kg ou segundos)."""
        if len(self.marcas) < 2:
            return None
        return valor(self.ultima.melhor, self.por_tempo) - valor(self.primeira.melhor, self.por_tempo)

    @property
    def percentual(self):
        inicial = valor(self.primeira.melhor, self.por_tempo) if self.marcas else 0
        if self.evolucao is None or not inicial:
            return None
        return round(float(self.evolucao) * 100 / float(inicial))

    @property
    def grafico(self):
        return grafico(self.marcas, self.por_tempo)

    @property
    def mais_recentes_primeiro(self):
        return list(reversed(self.marcas))


def progressao(usuario, exercicio):
    por_tempo = bool(exercicio.tempo_segundos)
    return Progressao(exercicio, por_tempo, marcas_por_treino(series_do_exercicio(usuario, exercicio), por_tempo))
