from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from execucao.tests import SENHA, criar_usuario
from saude.models import HistoricoMedida

from . import servicos


class EvolucaoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()  # 80 kg, 180 cm, hipertrofia
        self.client.login(username='caio@email.com', password=SENHA)
        self.url = reverse('evolucao:peso')

    def pesar(self, peso, dias_atras=0):
        data = timezone.localdate() - timedelta(days=dias_atras)
        return self.client.post(self.url, {'peso': peso, 'data': data.isoformat()})

    def test_pesagem_de_hoje_corrige_a_de_hoje_e_recalcula_metas(self):
        calorias_antes = self.usuario.meta_atual().meta_calorias
        resposta = self.pesar('85')
        self.assertRedirects(resposta, self.url)
        self.assertEqual(HistoricoMedida.objects.count(), 1)  # já havia pesagem hoje: foi corrigida
        self.assertEqual(self.usuario.medida_atual().peso_kg, Decimal('85'))
        self.assertGreater(self.usuario.meta_atual().meta_calorias, calorias_antes)

    def test_pesagem_antiga_entra_no_historico_sem_mudar_as_metas(self):
        calorias = self.usuario.meta_atual().meta_calorias
        self.pesar('83,5', dias_atras=10)
        self.assertEqual(HistoricoMedida.objects.count(), 2)
        antiga = HistoricoMedida.objects.order_by('data_registro').first()
        self.assertEqual((antiga.peso_kg, antiga.objetivo_momento), (Decimal('83.5'), 'hipertrofia'))
        self.assertEqual(self.usuario.medida_atual().peso_kg, Decimal('80'))
        self.assertEqual(self.usuario.meta_atual().meta_calorias, calorias)

    def test_data_futura_e_peso_fora_da_faixa(self):
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = self.client.post(self.url, {'peso': '80', 'data': amanha.isoformat()})
        self.assertContains(resposta, 'A pesagem não pode ser numa data futura.')
        resposta = self.pesar('20')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(HistoricoMedida.objects.count(), 1)

    def test_resumo_variacao_meta_e_imc(self):
        self.usuario.peso_meta_kg = Decimal('75')
        self.usuario.save()
        self.pesar('84', dias_atras=30)
        medidas = servicos.pesagens(self.usuario)
        resumo = servicos.resumo(self.usuario, medidas)
        self.assertEqual((resumo.inicial, resumo.atual, resumo.variacao, resumo.falta),
                         (Decimal('84'), Decimal('80'), Decimal('-4'), Decimal('5')))
        self.assertEqual(resumo.imc, (Decimal('24.7'), 'Peso adequado'))

    def test_imc_por_faixa(self):
        self.assertEqual(servicos.imc(Decimal('55'), 180)[1], 'Abaixo do peso')
        self.assertEqual(servicos.imc(Decimal('100'), 180)[1], 'Obesidade grau I')
        self.assertIsNone(servicos.imc(Decimal('80'), None))

    def test_grafico(self):
        self.pesar('84', dias_atras=20)
        self.pesar('82', dias_atras=10)
        grafico = servicos.grafico(servicos.pesagens(self.usuario), Decimal('78'))
        xs = [p.x for p in grafico.pontos]
        self.assertEqual(xs, sorted(xs))  # da mais antiga para a mais recente
        self.assertEqual(xs[0], servicos.MARGEM_ESQ)
        self.assertEqual(xs[-1], servicos.LARGURA - servicos.MARGEM_DIR)
        ys = [p.y for p in grafico.pontos]
        self.assertLess(ys[0], ys[-1])  # 84 kg fica mais alto (y menor) que 80 kg
        self.assertGreater(grafico.meta_y, ys[-1])  # a meta (78 kg) fica abaixo de tudo

    def test_tabela_com_variacao(self):
        self.pesar('82', dias_atras=10)
        linhas = servicos.linhas_da_tabela(servicos.pesagens(self.usuario))
        self.assertEqual([(m.peso_kg, d) for m, d in linhas], [(Decimal('80'), Decimal('-2')), (Decimal('82'), None)])

    def test_pagina(self):
        self.assertContains(self.client.get(self.url), 'O gráfico aparece a partir da segunda pesagem')
        self.pesar('82', dias_atras=10)
        pagina = self.client.get(self.url)
        self.assertContains(pagina, '<polyline')
        self.assertContains(pagina, '−2 kg')

    def test_excluir_pesagem_mantem_pelo_menos_uma(self):
        unica = self.usuario.medida_atual()
        self.client.post(reverse('evolucao:excluir', args=[unica.id]))
        self.assertEqual(HistoricoMedida.objects.count(), 1)
        self.pesar('82', dias_atras=10)
        antiga = HistoricoMedida.objects.order_by('data_registro').first()
        self.client.post(reverse('evolucao:excluir', args=[antiga.id]))
        self.assertEqual(list(HistoricoMedida.objects.values_list('peso_kg', flat=True)), [Decimal('80')])

    def test_excluir_a_atual_recalcula_metas(self):
        self.pesar('90', dias_atras=10)
        calorias_com_80 = self.usuario.meta_atual().meta_calorias
        self.client.post(reverse('evolucao:excluir', args=[self.usuario.medida_atual().id]))
        self.assertEqual(self.usuario.medida_atual().peso_kg, Decimal('90'))
        self.assertGreater(self.usuario.meta_atual().meta_calorias, calorias_com_80)

    def test_menu_tem_link_do_peso(self):
        self.assertContains(self.client.get(reverse('metas:perfil_metas')), self.url)
