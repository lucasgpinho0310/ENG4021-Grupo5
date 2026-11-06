"""
Evolução do peso: registrar pesagens (hoje ou em dias anteriores), montar o gráfico em SVG
no servidor e calcular variação, distância até a meta e IMC.
"""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from metas.calculo import salvar_meta
from saude.models import HistoricoMedida

# Tamanho do desenho do gráfico (o SVG se ajusta à largura da tela)
LARGURA, ALTURA = 640, 240
MARGEM_ESQ, MARGEM_DIR, MARGEM_TOPO, MARGEM_BAIXO = 48, 16, 16, 28


def pesagens(usuario):
    """Todas as pesagens, da mais antiga para a mais recente."""
    return list(HistoricoMedida.objects.filter(usuario=usuario).order_by('data_registro'))


def _momento(data):
    """Pesagem de hoje fica com a hora atual; de outro dia, ao meio-dia daquele dia."""
    if data == timezone.localdate():
        return timezone.now()
    return timezone.make_aware(datetime.combine(data, time(12, 0)))


@transaction.atomic
def registrar_pesagem(usuario, data, peso):
    """
    Grava a pesagem do dia (se já existe uma naquele dia, corrige). Se ela passa a ser a mais recente,
    recalcula as metas, que dependem do peso. Devolve True quando as metas foram recalculadas.
    """
    do_dia = [m for m in pesagens(usuario) if timezone.localdate(m.data_registro) == data]
    if do_dia:
        medida = do_dia[-1]
        medida.peso_kg = peso
        medida.save(update_fields=['peso_kg'])
    else:
        anterior = (
            HistoricoMedida.objects.filter(usuario=usuario, data_registro__lte=_momento(data))
            .order_by('-data_registro').first() or usuario.medida_atual()
        )
        medida = HistoricoMedida.objects.create(
            usuario=usuario, data_registro=_momento(data), peso_kg=peso,
            objetivo_momento=anterior.objetivo_momento if anterior else 'manutencao',
        )
    if usuario.medida_atual() == medida:
        salvar_meta(usuario)
        return True
    return False


@transaction.atomic
def excluir_pesagem(usuario, medida):
    """Apaga uma pesagem (a última que sobrar fica: o perfil precisa de um peso). Recalcula as metas se preciso."""
    if HistoricoMedida.objects.filter(usuario=usuario).count() <= 1:
        return False
    era_a_atual = usuario.medida_atual() == medida
    medida.delete()
    if era_a_atual:
        salvar_meta(usuario)
    return True


@dataclass
class Ponto:
    x: float
    y: float
    medida: object  # HistoricoMedida


@dataclass
class Grafico:
    pontos: list
    linha: str  # pontos da polyline "x,y x,y ..."
    marcas_y: list  # [(y, rótulo em kg)]
    meta_y: float | None
    largura: int = LARGURA
    altura: int = ALTURA
    esquerda: int = MARGEM_ESQ
    direita: int = LARGURA - MARGEM_DIR

    @property
    def primeiro(self):
        return self.pontos[0].medida

    @property
    def ultimo(self):
        return self.pontos[-1].medida


def grafico(medidas, peso_meta=None):
    """Coordenadas do gráfico: datas no eixo X (proporcionais ao tempo), peso no eixo Y."""
    if not medidas:
        return None
    pesos = [float(m.peso_kg) for m in medidas]
    if peso_meta is not None:
        pesos.append(float(peso_meta))
    menor, maior = min(pesos) - 1, max(pesos) + 1  # 1 kg de folga em cima e embaixo
    inicio = medidas[0].data_registro.timestamp()
    duracao = medidas[-1].data_registro.timestamp() - inicio
    area_x = LARGURA - MARGEM_ESQ - MARGEM_DIR
    area_y = ALTURA - MARGEM_TOPO - MARGEM_BAIXO

    def y_do_peso(peso):
        return round(MARGEM_TOPO + (maior - float(peso)) / (maior - menor) * area_y, 1)

    pontos = []
    for medida in medidas:
        fracao = (medida.data_registro.timestamp() - inicio) / duracao if duracao else 0.5
        pontos.append(Ponto(round(MARGEM_ESQ + fracao * area_x, 1), y_do_peso(medida.peso_kg), medida))
    marcas = [(y_do_peso(p), '%g' % round(p, 1)) for p in (maior, (maior + menor) / 2, menor)]
    return Grafico(
        pontos=pontos,
        linha=' '.join('%s,%s' % (p.x, p.y) for p in pontos),
        marcas_y=marcas,
        meta_y=y_do_peso(peso_meta) if peso_meta is not None else None,
    )


def linhas_da_tabela(medidas):
    """[(pesagem, diferença para a pesagem anterior)], da mais recente para a mais antiga."""
    linhas = []
    for posicao, medida in enumerate(medidas):
        diferenca = medida.peso_kg - medidas[posicao - 1].peso_kg if posicao else None
        linhas.append((medida, diferenca))
    return list(reversed(linhas))


FAIXAS_IMC = [
    (Decimal('18.5'), 'Abaixo do peso'),
    (Decimal('25'), 'Peso adequado'),
    (Decimal('30'), 'Sobrepeso'),
    (Decimal('35'), 'Obesidade grau I'),
    (Decimal('40'), 'Obesidade grau II'),
]


def imc(peso_kg, altura_cm):
    """(valor com uma casa, faixa da OMS) ou None sem altura."""
    if not altura_cm:
        return None
    valor = (Decimal(peso_kg) / (Decimal(altura_cm) / 100) ** 2).quantize(Decimal('0.1'))
    faixa = next((nome for limite, nome in FAIXAS_IMC if valor < limite), 'Obesidade grau III')
    return valor, faixa


@dataclass
class Resumo:
    inicial: Decimal
    atual: Decimal
    meta: Decimal | None
    imc: tuple | None

    @property
    def variacao(self):
        return self.atual - self.inicial

    @property
    def falta(self):
        """Quanto falta para o peso desejado (positivo = perder, negativo = ganhar)."""
        return None if self.meta is None else self.atual - self.meta


def resumo(usuario, medidas):
    if not medidas:
        return None
    atual = medidas[-1].peso_kg
    return Resumo(medidas[0].peso_kg, atual, usuario.peso_meta_kg, imc(atual, usuario.altura_cm))
