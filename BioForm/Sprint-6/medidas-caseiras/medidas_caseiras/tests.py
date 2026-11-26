import importlib
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from saude.models import DiarioConsumo, MedidaCaseira, RegistroRefeicao, RegistroRefeicaoItem, Usuario


def criar_usuario(nome, cpf):
    return Usuario.objects.create(
        nome_completo=nome,
        cpf=cpf,
        celular='21999990000',
        data_nascimento=date(2000, 1, 1),
        sexo_biologico='feminino',
        altura_cm=165,
        biotipo='mesomorfo',
    )


class MedidasCaseirasTest(TestCase):
    def test_todas_as_medidas_da_migracao_foram_carregadas(self):
        migracao = importlib.import_module('medidas_caseiras.migrations.0001_popular_medidas_caseiras')
        ids = [migracao.id_da_medida(taco_id, nome)
               for taco_id, (_, medidas) in migracao.MEDIDAS.items() for nome, _ in medidas]
        # conta só as medidas desta migração (a base de bebidas da Sprint 10 acrescenta outras)
        self.assertEqual(MedidaCaseira.objects.filter(id__in=ids).count(), len(ids))

    def test_pao_frances_e_concha_de_feijao(self):
        pao = MedidaCaseira.objects.get(alimento__nome='Pão, trigo, francês', nome='1 unidade')
        self.assertEqual(pao.gramas, Decimal('50'))
        concha = MedidaCaseira.objects.get(alimento__nome='Feijão, carioca, cozido', nome='1 concha média')
        self.assertEqual(concha.gramas, Decimal('140'))

    def test_registrar_refeicao_com_medida_carregada(self):
        ana = criar_usuario('Ana', '12345678901')
        diario = DiarioConsumo.objects.create(usuario=ana, data_referencia=date(2026, 10, 22))
        almoco = RegistroRefeicao.objects.create(diario=diario, tipo_refeicao='almoco', horario=timezone.now())
        colher = MedidaCaseira.objects.get(alimento__nome='Azeite, de oliva, extra virgem', nome='1 colher de sopa')
        item = RegistroRefeicaoItem.objects.create(
            registro=almoco, alimento=colher.alimento, medida_caseira=colher, quantidade=Decimal('2'),
        )
        self.assertEqual(item.gramas(), Decimal('26'))
        self.assertEqual(item.macros()['gordura_g'], Decimal('26'))
        self.assertEqual(item.macros()['kcal'], Decimal('229.84'))
