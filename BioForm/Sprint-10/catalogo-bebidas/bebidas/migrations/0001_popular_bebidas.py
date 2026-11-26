"""
Base de bebidas do catálogo de alimentos (RF09/RF10 e Escopo 1.5 - Hidratação).

A TACO tem poucas bebidas (cerveja pilsen, cachaça, refrigerantes, isotônico, chás, café, água de coco)
e quase nenhuma medida para elas. Esta migração:
1. acrescenta as bebidas que faltavam (alcoólicas e não alcoólicas), com valores por 100 ml;
2. cria as medidas do dia a dia (lata, long neck, garrafa, taça, dose, copo, caixinha, xícara)
   para as bebidas novas e para as da TACO.

Assim elas aparecem na busca de "Adicionar alimento" do diário como qualquer alimento, e as
calorias entram no total do dia.

Os valores são APROXIMADOS, de referência (TBCA/USP e USDA FoodData Central), para uma bebida média
de cada tipo; rótulos de marcas diferentes variam. Bebidas são lançadas em ml, contando 1 ml = 1 g,
como nas tabelas de medidas caseiras. O grupo pode corrigir ou acrescentar pelo admin.

UUIDs fixos (bebida e medida): rodar de novo não duplica nada.
"""
import uuid
from decimal import Decimal

from django.db import migrations

NAMESPACE_TACO = uuid.UUID('6f1d1c3a-6a8e-4c55-9a39-0d9b6e2f7a10')  # o mesmo da 0002_popular_alimentos_taco
NAMESPACE_BEBIDAS = uuid.UUID('9b2f6c1e-4d7a-4e3b-8f5c-2a1d0e9b7c64')
NAMESPACE_MEDIDAS_BEBIDAS = uuid.UUID('5e8a3d2c-7b1f-4c6e-9a4d-1f0b2c3e8d75')

# ----------------------------------------------------------------- medidas mais usadas
LATA = ('1 lata (350 ml)', '350')
LATINHA = ('1 lata pequena (269 ml)', '269')
LATAO = ('1 latão (473 ml)', '473')
LONG_NECK = ('1 long neck (355 ml)', '355')
GARRAFA_600 = ('1 garrafa (600 ml)', '600')
COPO_AMERICANO = ('1 copo americano (190 ml)', '190')
COPO = ('1 copo (250 ml)', '250')
COPO_GRANDE = ('1 copo grande (300 ml)', '300')
CAIXINHA = ('1 caixinha (200 ml)', '200')
TACA_VINHO = ('1 taça (150 ml)', '150')
GARRAFA_VINHO = ('1 garrafa (750 ml)', '750')
TACA_ESPUMANTE = ('1 taça (120 ml)', '120')
DOSE = ('1 dose (50 ml)', '50')
SHOT = ('1 shot (30 ml)', '30')
XICARA = ('1 xícara (200 ml)', '200')

CERVEJA = [LATA, LATINHA, LONG_NECK, LATAO, GARRAFA_600]
REFRIGERANTE = [LATA, COPO_AMERICANO, COPO_GRANDE, GARRAFA_600]
SUCO = [COPO_AMERICANO, COPO_GRANDE, CAIXINHA]
DESTILADO = [DOSE, SHOT]

# ----------------------------------------------------------------- bebidas novas
# chave: (nome no catálogo, kcal, proteína g, carboidrato g, gordura g) por 100 ml, [medidas]
BEBIDAS = {
    # ----- Cervejas -----
    'cerveja-puro-malte': (('Cerveja, puro malte', '45', '0.5', '3.6', '0'), CERVEJA),
    'cerveja-sem-alcool': (('Cerveja, sem álcool', '25', '0.3', '5.5', '0'), CERVEJA),
    'chope-claro': (('Chope, claro', '42', '0.4', '3.3', '0'),
                    [('1 tulipa (300 ml)', '300'), ('1 caneca (500 ml)', '500'), COPO_AMERICANO]),
    # ----- Vinhos -----
    'vinho-tinto': (('Vinho, tinto, seco', '85', '0.1', '2.6', '0'), [TACA_VINHO, GARRAFA_VINHO]),
    'vinho-branco': (('Vinho, branco, seco', '82', '0.1', '2.6', '0'), [TACA_VINHO, GARRAFA_VINHO]),
    'vinho-rose': (('Vinho, rosé', '71', '0.4', '3.8', '0'), [TACA_VINHO, GARRAFA_VINHO]),
    'vinho-suave': (('Vinho, tinto, suave (de mesa)', '98', '0.1', '8.5', '0'), [TACA_VINHO, GARRAFA_VINHO]),
    'espumante': (('Espumante, brut', '76', '0.1', '1.2', '0'), [TACA_ESPUMANTE, GARRAFA_VINHO]),
    # ----- Destilados (40% de álcool) -----
    'vodka': (('Vodka', '231', '0', '0', '0'), DESTILADO),
    'gin': (('Gin', '231', '0', '0', '0'), DESTILADO),
    'whisky': (('Whisky', '231', '0', '0', '0'), DESTILADO),
    'rum': (('Rum', '231', '0', '0', '0'), DESTILADO),
    'tequila': (('Tequila', '231', '0', '0', '0'), DESTILADO),
    'sake': (('Saquê', '134', '0.5', '5', '0'), [DOSE, ('1 copo (100 ml)', '100')]),
    # ----- Drinks -----
    'caipirinha': (('Caipirinha, de cachaça, com açúcar', '120', '0.1', '16', '0'), [COPO]),
    'gin-tonica': (('Gin tônica', '81', '0', '6', '0'), [('1 taça (300 ml)', '300'), COPO]),
    # ----- Refrigerantes e energéticos -----
    'refrigerante-cola-zero': (('Refrigerante, tipo cola, zero açúcar', '0', '0', '0', '0'), REFRIGERANTE),
    'refrigerante-guarana-zero': (('Refrigerante, tipo guaraná, zero açúcar', '0', '0', '0', '0'), REFRIGERANTE),
    'energetico': (('Energético', '45', '0', '11', '0'), [('1 lata (250 ml)', '250'), LATAO]),
    'energetico-zero': (('Energético, sem açúcar', '3', '0', '0.5', '0'), [('1 lata (250 ml)', '250'), LATAO]),
    'kombucha': (('Kombucha', '18', '0', '4', '0'), [('1 garrafa (275 ml)', '275'), COPO_AMERICANO]),
    'cha-gelado': (('Chá, mate, pronto, adoçado', '30', '0', '7.4', '0'), [COPO_AMERICANO, LATA, ('1 garrafa (450 ml)', '450')]),
    # ----- Sucos -----
    'suco-laranja-integral': (('Suco, de laranja, integral (caixinha)', '45', '0.7', '10.4', '0.2'), SUCO),
    'suco-uva-integral': (('Suco, de uva, integral (caixinha)', '60', '0.4', '14.8', '0.1'), SUCO),
    'nectar-fruta': (('Néctar, de fruta (caixinha)', '50', '0.2', '12.5', '0'), SUCO),
    # ----- Leites e bebidas vegetais -----
    'leite-integral': (('Leite, de vaca, integral, líquido', '61', '3.2', '4.8', '3.3'), [COPO, XICARA, CAIXINHA]),
    'leite-desnatado': (('Leite, de vaca, desnatado, líquido', '34', '3.4', '5', '0.1'), [COPO, XICARA, CAIXINHA]),
    'bebida-soja': (('Bebida vegetal, de soja, original', '54', '3.3', '6.3', '1.8'), [COPO, CAIXINHA]),
    'bebida-amendoas': (('Bebida vegetal, de amêndoas, sem açúcar', '15', '0.4', '0.3', '1.1'), [COPO, CAIXINHA]),
    'bebida-aveia': (('Bebida vegetal, de aveia', '46', '1', '6.6', '1.5'), [COPO, CAIXINHA]),
    # ----- Cafés -----
    'cafe-com-leite': (('Café, com leite integral, sem açúcar', '32', '1.6', '2.4', '1.6'), [XICARA, ('1 xícara pequena (100 ml)', '100')]),
    'cappuccino': (('Cappuccino, preparado com pó', '55', '1.2', '9.5', '1.5'), [XICARA, ('1 xícara pequena (100 ml)', '100')]),
}

# ----------------------------------------------------------------- medidas para bebidas da TACO
# código TACO: (nome do alimento, só para conferir) -> [medidas]
MEDIDAS_TACO = {
    455: ('Leite, de vaca, achocolatado', [CAIXINHA, COPO]),
    470: ('Bebida isotônica, sabores variados', [('1 garrafa (500 ml)', '500'), COPO_AMERICANO]),
    471: ('Café, infusão 10%', [('1 xícara (100 ml)', '100'), ('1 caneca (250 ml)', '250')]),
    472: ('Cana, aguardente 1', DESTILADO),
    473: ('Cana, caldo de', [COPO_GRANDE, ('1 copo de 500 ml', '500')]),
    474: ('Cerveja, pilsen 2', CERVEJA),
    475: ('Chá, erva-doce, infusão 5%', [XICARA]),
    476: ('Chá, mate, infusão 5%', [XICARA, COPO_GRANDE]),
    477: ('Chá, preto, infusão 5%', [XICARA]),
    478: ('Coco, água de', [('1 coco (300 ml)', '300'), CAIXINHA, COPO_AMERICANO]),
    479: ('Refrigerante, tipo água tônica', [LATA, COPO_AMERICANO]),
    480: ('Refrigerante, tipo cola', REFRIGERANTE),
    481: ('Refrigerante, tipo guaraná', REFRIGERANTE),
    482: ('Refrigerante, tipo laranja', REFRIGERANTE),
    483: ('Refrigerante, tipo limão', REFRIGERANTE),
}


def id_da_bebida(chave):
    return uuid.uuid5(NAMESPACE_BEBIDAS, 'bebida-%s' % chave)


def id_do_alimento_taco(taco_id):
    return uuid.uuid5(NAMESPACE_TACO, 'taco-%s' % taco_id)


def id_da_medida(dono, nome):
    return uuid.uuid5(NAMESPACE_MEDIDAS_BEBIDAS, '%s-%s' % (dono, nome))


def todas_as_medidas():
    """(id do alimento, chave para o id da medida, nome, ml) de tudo o que esta migração cria."""
    for chave, (_, medidas) in BEBIDAS.items():
        for nome, ml in medidas:
            yield id_da_bebida(chave), chave, nome, ml
    for taco_id, (_, medidas) in MEDIDAS_TACO.items():
        for nome, ml in medidas:
            yield id_do_alimento_taco(taco_id), 'taco-%s' % taco_id, nome, ml


def popular(apps, schema_editor):
    Alimento = apps.get_model('saude', 'Alimento')
    MedidaCaseira = apps.get_model('saude', 'MedidaCaseira')
    for chave, ((nome, kcal, proteina, carbo, gordura), _) in BEBIDAS.items():
        Alimento.objects.update_or_create(
            id=id_da_bebida(chave),
            defaults={
                'nome': nome, 'porcao_padrao': '100 ml', 'porcao_gramas': Decimal('100'),
                'kcal': Decimal(kcal), 'proteina_g': Decimal(proteina),
                'carbo_g': Decimal(carbo), 'gordura_g': Decimal(gordura),
            },
        )
    for taco_id, (nome, _) in MEDIDAS_TACO.items():
        alimento = Alimento.objects.get(id=id_do_alimento_taco(taco_id))
        if alimento.nome != nome:
            raise ValueError('Código TACO %s é "%s", não "%s"' % (taco_id, alimento.nome, nome))
    for alimento_id, dono, nome, ml in todas_as_medidas():
        MedidaCaseira.objects.update_or_create(
            id=id_da_medida(dono, nome),
            defaults={'alimento_id': alimento_id, 'nome': nome, 'gramas': Decimal(ml)},
        )


def despopular(apps, schema_editor):
    Alimento = apps.get_model('saude', 'Alimento')
    MedidaCaseira = apps.get_model('saude', 'MedidaCaseira')
    MedidaCaseira.objects.filter(id__in=[id_da_medida(dono, nome) for _, dono, nome, _ in todas_as_medidas()]).delete()
    Alimento.objects.filter(id__in=[id_da_bebida(chave) for chave in BEBIDAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('saude', '0003_popular_esportes'),
    ]

    operations = [
        migrations.RunPython(popular, despopular),
    ]
