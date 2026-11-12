from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_ficha, criar_usuario
from saude.models import SerieExecutada, SessaoAtividade

from . import servicos


class ProgressaoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.ficha, self.agachamento, self.prancha = criar_ficha(self.usuario)
        self.client.login(username='caio@email.com', password=SENHA)
        self.dia = 0

    def treino(self, series, exercicio=None, livre=False):
        """series: [(carga, reps)] para o agachamento ou [segundos] para a prancha."""
        self.dia += 1
        exercicio = exercicio or self.agachamento
        sessao = SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=esporte_musculacao(), ficha=None if livre else self.ficha,
            inicio=timezone.now() - timedelta(days=30 - self.dia), duracao_minutos=50, intensidade='moderada',
        )
        for numero, feito in enumerate(series, 1):
            dados = {'tempo_segundos': feito} if exercicio.tempo_segundos else {'carga_kg': Decimal(feito[0]), 'repeticoes': feito[1]}
            SerieExecutada.objects.create(
                sessao=sessao, exercicio=None if livre else exercicio, nome_exercicio=exercicio.nome_exercicio,
                numero_serie=numero, carga_kg=dados.pop('carga_kg', Decimal('0')), **dados,
            )
        return sessao

    def test_melhor_serie_de_cada_treino(self):
        self.treino([(40, 10), (45, 8), (45, 6)])
        self.treino([(50, 8), (50, 10)])
        progressao = servicos.progressao(self.usuario, self.agachamento)
        self.assertEqual([(m.melhor.carga_kg, m.melhor.repeticoes) for m in progressao.marcas],
                         [(Decimal('45'), 8), (Decimal('50'), 10)])  # empate na carga: mais repetições
        self.assertEqual(progressao.marcas[0].volume_kg, Decimal('1030'))  # 400 + 360 + 270
        self.assertEqual((progressao.evolucao, progressao.percentual), (Decimal('5'), 11))
        self.assertEqual(progressao.recorde.melhor.carga_kg, Decimal('50'))

    def test_treino_livre_com_o_mesmo_nome_conta(self):
        self.treino([(40, 10)])
        self.treino([(42.5, 10)], livre=True)
        progressao = servicos.progressao(self.usuario, self.agachamento)
        self.assertEqual(len(progressao.marcas), 2)
        self.assertEqual(progressao.ultima.melhor.carga_kg, Decimal('42.5'))

    def test_exercicio_por_tempo(self):
        self.treino([30, 40], exercicio=self.prancha)
        self.treino([45], exercicio=self.prancha)
        progressao = servicos.progressao(self.usuario, self.prancha)
        self.assertTrue(progressao.por_tempo)
        self.assertEqual([m.melhor.tempo_segundos for m in progressao.marcas], [40, 45])
        self.assertEqual(progressao.evolucao, 5)

    def test_grafico_aparece_a_partir_do_segundo_treino(self):
        self.treino([(40, 10)])
        self.assertIsNone(servicos.progressao(self.usuario, self.agachamento).grafico)
        self.treino([(50, 10)])
        grafico = servicos.progressao(self.usuario, self.agachamento).grafico
        self.assertEqual([p.x for p in grafico.pontos], [servicos.MARGEM_ESQ, servicos.LARGURA - servicos.MARGEM_DIR])
        self.assertGreater(grafico.pontos[0].y, grafico.pontos[1].y)  # 50 kg fica mais alto que 40 kg

    def test_pagina(self):
        url = reverse('progressao:exercicio', args=[self.agachamento.id])
        self.assertContains(self.client.get(url), 'Ainda sem treinos')
        self.treino([(40, 10)])
        self.treino([(45, 10)])
        pagina = self.client.get(url)
        self.assertContains(pagina, '<polyline')
        self.assertContains(pagina, '+5 kg')
        self.assertContains(pagina, '45 kg × 10 🏆')

    def test_links_na_ficha_e_no_historico(self):
        url = reverse('progressao:exercicio', args=[self.agachamento.id])
        self.assertContains(self.client.get(reverse('treinos:treinos_ficha', args=[self.ficha.id])), url)
        sessao = self.treino([(40, 10)])
        self.assertContains(self.client.get(reverse('historico:sessao', args=[sessao.id])), url)

    def test_nao_abre_exercicio_de_outra_pessoa(self):
        outra = criar_usuario('bia@email.com', '11144477735')
        _, agachamento_dela, _ = criar_ficha(outra)
        self.assertEqual(self.client.get(reverse('progressao:exercicio', args=[agachamento_dela.id])).status_code, 404)
