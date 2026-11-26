import importlib
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from diario.servicos import buscar_alimentos, registrar_item, resumo_do_dia
from execucao.tests import SENHA, criar_usuario
from saude.models import Alimento, MedidaCaseira

migracao = importlib.import_module('bebidas.migrations.0001_popular_bebidas')


class BaseDeBebidasTest(TestCase):
    def test_todas_as_bebidas_e_medidas_foram_carregadas(self):
        ids_bebidas = [migracao.id_da_bebida(chave) for chave in migracao.BEBIDAS]
        self.assertEqual(Alimento.objects.filter(id__in=ids_bebidas).count(), len(migracao.BEBIDAS))
        ids_medidas = [migracao.id_da_medida(dono, nome) for _, dono, nome, _ in migracao.todas_as_medidas()]
        self.assertEqual(MedidaCaseira.objects.filter(id__in=ids_medidas).count(), len(ids_medidas))

    def test_bebida_nova_em_100_ml_com_medidas(self):
        vinho = Alimento.objects.get(nome='Vinho, tinto, seco')
        self.assertEqual((vinho.porcao_padrao, vinho.kcal), ('100 ml', Decimal('85')))
        self.assertEqual(sorted(m.nome for m in vinho.medidas.all()), ['1 garrafa (750 ml)', '1 taça (150 ml)'])

    def test_bebidas_da_taco_ganharam_lata_e_dose(self):
        cerveja = Alimento.objects.get(nome='Cerveja, pilsen 2')
        self.assertTrue(cerveja.medidas.filter(nome='1 lata (350 ml)', gramas=Decimal('350')).exists())
        cachaca = Alimento.objects.get(nome='Cana, aguardente 1')
        self.assertTrue(cachaca.medidas.filter(nome='1 dose (50 ml)').exists())

    def test_rodar_de_novo_nao_duplica(self):
        from django.apps import apps
        antes = (Alimento.objects.count(), MedidaCaseira.objects.count())
        migracao.popular(apps, None)
        self.assertEqual((Alimento.objects.count(), MedidaCaseira.objects.count()), antes)

    def test_busca_do_diario_acha_as_bebidas(self):
        nomes = [a.nome for a in buscar_alimentos('cerveja')]
        for nome in ('Cerveja, pilsen 2', 'Cerveja, puro malte', 'Cerveja, sem álcool'):
            with self.subTest(nome=nome):
                self.assertIn(nome, nomes)
        self.assertIn('Caipirinha, de cachaça, com açúcar', [a.nome for a in buscar_alimentos('caipirinha')])
        self.assertIn('Leite, de vaca, integral, líquido', [a.nome for a in buscar_alimentos('leite liquido')])


class BebidaNoDiarioTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.client.login(username='caio@email.com', password=SENHA)

    def test_uma_lata_de_cerveja_entra_nas_calorias_do_dia(self):
        cerveja = Alimento.objects.get(nome='Cerveja, pilsen 2')  # 41 kcal / 100 ml
        lata = cerveja.medidas.get(nome='1 lata (350 ml)')
        hoje = timezone.localdate()
        registrar_item(self.usuario, hoje, 'jantar', cerveja, Decimal('2'), lata)
        self.assertEqual(resumo_do_dia(self.usuario, hoje).total['kcal'], Decimal('287'))  # 2 x 350 ml x 0,41

    def test_tela_de_adicionar_mostra_as_medidas_da_bebida(self):
        espumante = Alimento.objects.get(nome='Espumante, brut')
        url = reverse('diario:diario_adicionar', args=[timezone.localdate()])
        resposta = self.client.get(url, {'q': 'espumante', 'alimento': espumante.id})
        self.assertContains(resposta, 'Espumante, brut')
        self.assertContains(resposta, '1 taça (120 ml)')
