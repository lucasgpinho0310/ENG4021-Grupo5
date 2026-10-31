"""
Calculadora de metas nutricionais (RF15 Metas / RF20 Recomendações).

Segue as fórmulas descritas no mockup "App Saúde/Mockup Login/perfil-4-resultado.html":

- TMB (Mifflin-St Jeor)  homens:   10 x peso + 6,25 x altura - 5 x idade + 5
                         mulheres: 10 x peso + 6,25 x altura - 5 x idade - 161
- Gasto dos esportes     (MET x fator da intensidade - 1) x peso x horas, por semana, dividido por 7.
                         Desconta 1 MET porque o repouso já está na TMB. As horas vêm da duração
                         média de cada treino informada no perfil (1 hora se não houver).
- Atividade diária       NEAT (15% da TMB) + efeito térmico dos alimentos (10% do gasto)
- TDEE                   TMB + esportes + atividade diária
- Meta de calorias       TDEE + ajuste do objetivo (-500 perder | 0 manter | +400 ganhar),
                         nunca abaixo da TMB (piso de segurança)
- Proteína / gordura     g por kg de peso; carboidrato = calorias que sobram / 4
- Água                   35 ml por kg

É uma estimativa: não substitui nutricionista ou médico.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

AJUSTE_OBJETIVO = {
    'emagrecimento': -500,
    'manutencao': 0,
    'hipertrofia': 400,
    'saude': 0,
}

PROTEINA_G_POR_KG = {
    'emagrecimento': 2.1,  # preserva massa magra no déficit
    'manutencao': 1.8,
    'hipertrofia': 2.0,
    'saude': 1.6,
}
GORDURA_G_POR_KG = 0.8
AGUA_ML_POR_KG = 35

FATOR_INTENSIDADE = {
    'leve': 0.8,
    'moderada': 1.0,
    'intensa': 1.2,
    'maxima': 1.4,
}
MINUTOS_POR_SESSAO = 60  # quando a duração do treino não é informada

NEAT_DA_TMB = 0.15
EFEITO_TERMICO = 0.10

KCAL_POR_G = {'proteina': 4, 'carbo': 4, 'gordura': 9}


def arredondar(valor):
    """Arredonda para o inteiro mais próximo (0,5 sobe), sem o arredondamento bancário do round()."""
    return int(Decimal(str(valor)).quantize(Decimal('1'), rounding='ROUND_HALF_UP'))


@dataclass
class Metas:
    tmb: int
    gasto_esportes: int
    atividade_diaria: int
    tdee: int
    ajuste: int  # quanto a meta ficou acima (+) ou abaixo (-) do TDEE
    calorias: int
    proteina_g: int
    carbo_g: int
    gordura_g: int
    agua_ml: int
    piso_tmb: bool = False  # True quando o déficit foi limitado para não ficar abaixo da TMB

    def percentual(self, macro):
        """Fatia das calorias da meta que vem de cada macronutriente."""
        gramas = getattr(self, '%s_g' % macro)
        return arredondar(gramas * KCAL_POR_G[macro] * 100 / self.calorias) if self.calorias else 0

    @property
    def percentual_proteina(self):
        return self.percentual('proteina')

    @property
    def percentual_carbo(self):
        return self.percentual('carbo')

    @property
    def percentual_gordura(self):
        return self.percentual('gordura')

    @property
    def copos_agua(self):
        return arredondar(self.agua_ml / 250)

    @property
    def garrafinhas_agua(self):
        return arredondar(self.agua_ml / 500)


def calcular_tmb(sexo, idade, peso_kg, altura_cm):
    base = 10 * peso_kg + 6.25 * altura_cm - 5 * idade
    return base + 5 if sexo == 'masculino' else base - 161


def gasto_semanal_do_esporte(peso_kg, met, frequencia, intensidade, minutos=MINUTOS_POR_SESSAO):
    """kcal gastas por semana num esporte (sem o repouso, que já está na TMB)."""
    met_liquido = max(float(met) * FATOR_INTENSIDADE[intensidade] - 1, 0)
    return met_liquido * float(peso_kg) * minutos / 60 * frequencia


def calcular_gasto_esportes(peso_kg, esportes):
    """esportes: lista de (met, vezes por semana, intensidade[, minutos por treino]). Devolve kcal por dia."""
    return sum(gasto_semanal_do_esporte(peso_kg, *esporte) for esporte in esportes) / 7


def calcular_metas(sexo, idade, peso_kg, altura_cm, objetivo, esportes=()):
    peso_kg = float(peso_kg)
    tmb = calcular_tmb(sexo, idade, peso_kg, altura_cm)
    esportes_kcal = calcular_gasto_esportes(peso_kg, esportes)
    neat = NEAT_DA_TMB * tmb
    efeito_termico = EFEITO_TERMICO * (tmb + esportes_kcal + neat)

    tmb = arredondar(tmb)
    esportes_kcal = arredondar(esportes_kcal)
    atividade = arredondar(neat + efeito_termico)
    tdee = tmb + esportes_kcal + atividade

    calorias = tdee + AJUSTE_OBJETIVO[objetivo]
    piso = calorias < tmb
    if piso:
        calorias = tmb

    proteina = arredondar(PROTEINA_G_POR_KG[objetivo] * peso_kg)
    gordura = arredondar(GORDURA_G_POR_KG * peso_kg)
    sobra = calorias - proteina * KCAL_POR_G['proteina'] - gordura * KCAL_POR_G['gordura']
    carbo = max(arredondar(sobra / KCAL_POR_G['carbo']), 0)

    return Metas(
        tmb=tmb,
        gasto_esportes=esportes_kcal,
        atividade_diaria=atividade,
        tdee=tdee,
        ajuste=calorias - tdee,
        calorias=calorias,
        proteina_g=proteina,
        carbo_g=carbo,
        gordura_g=gordura,
        agua_ml=arredondar(peso_kg * AGUA_ML_POR_KG / 50) * 50,  # múltiplo de 50 ml
        piso_tmb=piso,
    )


def metas_do_usuario(usuario, hoje=None):
    """Calcula as metas a partir do perfil salvo. Exige onboarding com dados, peso e objetivo."""
    medida = usuario.medida_atual()
    esportes = [
        (e.esporte.met, e.frequencia_semanal, e.intensidade, e.duracao_minutos)
        for e in usuario.esportes.select_related('esporte')
    ]
    return calcular_metas(
        sexo=usuario.sexo_biologico,
        idade=usuario.idade(hoje),
        peso_kg=medida.peso_kg,
        altura_cm=usuario.altura_cm,
        objetivo=medida.objetivo_momento,
        esportes=esportes,
    )


def salvar_meta(usuario, hoje=None):
    """Grava (ou atualiza) a meta nutricional que vale a partir de hoje."""
    from saude.models import MetaNutricional

    hoje = hoje or timezone.localdate()
    metas = metas_do_usuario(usuario, hoje)
    valores = {
        'meta_calorias': metas.calorias,
        'meta_proteina_g': Decimal(metas.proteina_g),
        'meta_carbo_g': Decimal(metas.carbo_g),
        'meta_gordura_g': Decimal(metas.gordura_g),
        'meta_agua_ml': metas.agua_ml,
    }
    meta = MetaNutricional.objects.filter(usuario=usuario, data_inicio=hoje).first()
    if meta:
        for campo, valor in valores.items():
            setattr(meta, campo, valor)
        meta.save()
    else:
        meta = MetaNutricional.objects.create(usuario=usuario, data_inicio=hoje, **valores)
    return meta, metas


# Alimentos do catálogo TACO usados no "Na prática" da tela de metas
ALIMENTO_PROTEINA = 'Frango, peito, sem pele, grelhado'
ALIMENTO_CARBO = 'Arroz, tipo 1, cozido'
ALIMENTO_GORDURA = 'Azeite, de oliva, extra virgem'


def equivalencias(metas):
    """Traduz os gramas de nutriente em comida de verdade, usando o catálogo e as medidas caseiras."""
    from saude.models import Alimento, MedidaCaseira

    resultado = {}
    frango = Alimento.objects.filter(nome=ALIMENTO_PROTEINA).first()
    if frango and frango.proteina_g:
        resultado['frango_g'] = arredondar(metas.proteina_g * frango.porcao_gramas / frango.proteina_g / 10) * 10
    arroz = Alimento.objects.filter(nome=ALIMENTO_CARBO).first()
    if arroz and arroz.carbo_g:
        resultado['arroz_g'] = arredondar(metas.carbo_g * arroz.porcao_gramas / arroz.carbo_g / 10) * 10
    colher = MedidaCaseira.objects.filter(alimento__nome=ALIMENTO_GORDURA, nome='1 colher de sopa').first()
    if colher:
        gordura_por_colher = colher.gramas * colher.alimento.gordura_g / colher.alimento.porcao_gramas
        resultado['colheres_azeite'] = arredondar(metas.gordura_g / gordura_por_colher)
    return resultado
