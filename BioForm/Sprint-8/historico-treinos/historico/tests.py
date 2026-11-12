from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_ficha, criar_usuario
from saude.models import Esporte, HistoricoMedida, SerieExecutada, SessaoAtividade

from . import servicos


def momento(data, hora=18):
    return timezone.make_aware(datetime.combine(data, time(hora, 0)))


class HistoricoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()  # 80 kg
        self.ficha, self.agachamento, self.prancha = criar_ficha(self.usuario)
        self.client.login(username='caio@email.com', password=SENHA)
        self.hoje = date(2026, 11, 5)  # quinta-feira

    def treino(self, data, cargas=(40, 40), minutos=60, intensidade='moderada'):
        sessao = SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=esporte_musculacao(), ficha=self.ficha,
            inicio=momento(data), duracao_minutos=minutos, intensidade=intensidade,
        )
        for numero, carga in enumerate(cargas, 1):
            SerieExecutada.objects.create(sessao=sessao, exercicio=self.agachamento, nome_exercicio='Agachamento', numero_serie=numero,
                                          carga_kg=Decimal(carga), repeticoes=10)
        return sessao

    def test_gasto_usa_o_mesmo_calculo_da_meta(self):
        sessao = self.treino(self.hoje, minutos=60, intensidade='moderada')
        # (MET 5,0 x 1,0 - 1) x 80 kg x 1 h
        self.assertEqual(servicos.gasto_da_sessao(sessao, Decimal('80')), 320)
        self.assertIsNone(servicos.gasto_da_sessao(sessao, None))

    def test_agrupa_por_semana_de_segunda_a_domingo(self):
        self.treino(self.hoje)                        # quinta 05/11
        self.treino(date(2026, 11, 2))                # segunda 02/11: mesma semana
        self.treino(date(2026, 11, 1))                # domingo 01/11: semana anterior
        semanas = servicos.semanas_do_usuario(self.usuario, hoje=self.hoje)
        self.assertEqual([s.inicio for s in semanas], [date(2026, 11, 2), date(2026, 10, 26)])
        self.assertEqual(len(semanas[0].treinos), 2)
        self.assertEqual(semanas[0].minutos, 120)
        self.assertEqual(semanas[0].kcal, 640)
        self.assertEqual(semanas[0].volume_kg, Decimal('1600'))  # 2 treinos x 2 séries x 40 kg x 10

    def test_treinos_antigos_ficam_de_fora(self):
        self.treino(self.hoje - timedelta(weeks=servicos.SEMANAS_NO_HISTORICO + 1))
        self.assertEqual(servicos.semanas_do_usuario(self.usuario, hoje=self.hoje), [])

    def test_aceita_outros_esportes(self):
        corrida, _ = Esporte.objects.get_or_create(nome='Corrida', defaults={'met': Decimal('9.8')})
        SessaoAtividade.objects.create(usuario=self.usuario, esporte=corrida, inicio=momento(self.hoje),
                                       duracao_minutos=30, intensidade='moderada', distancia_km=Decimal('5'))
        treino = servicos.semanas_do_usuario(self.usuario, hoje=self.hoje)[0].treinos[0]
        self.assertEqual((treino.titulo, treino.emoji, treino.volume_kg), ('Corrida', '🏃', 0))
        self.assertEqual(treino.kcal, round((float(corrida.met) - 1) * 80 * 0.5))  # (MET - 1) x 80 kg x 0,5 h

    def test_peso_da_data_do_treino(self):
        HistoricoMedida.objects.create(usuario=self.usuario, data_registro=momento(date(2026, 1, 10)),
                                       peso_kg=Decimal('90'), objetivo_momento='emagrecimento')
        self.assertEqual(servicos.peso_na_data(self.usuario, date(2026, 2, 1)).peso_kg, Decimal('90'))
        self.assertEqual(servicos.peso_na_data(self.usuario, date(2025, 12, 1)).peso_kg, Decimal('90'))
        self.assertEqual(servicos.peso_na_data(self.usuario, timezone.localdate()).peso_kg, Decimal('80'))

    def test_recorde_batido(self):
        self.treino(self.hoje - timedelta(days=7), cargas=(40, 45))
        sessao = self.treino(self.hoje, cargas=(45, 50))
        igual = self.treino(self.hoje + timedelta(days=1), cargas=(50,))
        self.assertTrue(servicos.exercicios_da_sessao(sessao)[0].recorde)
        self.assertFalse(servicos.exercicios_da_sessao(igual)[0].recorde)  # igualou, não bateu

    def test_paginas(self):
        sessao = self.treino(timezone.localdate())
        lista = self.client.get(reverse('historico:lista'))
        self.assertContains(lista, 'Inferiores')
        self.assertContains(lista, reverse('historico:sessao', args=[sessao.id]))
        detalhe = self.client.get(reverse('historico:sessao', args=[sessao.id]))
        self.assertContains(detalhe, 'Agachamento')
        self.assertContains(detalhe, '320 kcal')
        self.assertContains(detalhe, '800 kg')  # volume: 2 x 40 x 10

    def test_lista_vazia(self):
        self.assertContains(self.client.get(reverse('historico:lista')), 'Nenhum treino ainda')

    def test_excluir_treino(self):
        sessao = self.treino(timezone.localdate())
        resposta = self.client.post(reverse('historico:excluir', args=[sessao.id]))
        self.assertRedirects(resposta, reverse('historico:lista'))
        self.assertFalse(SessaoAtividade.objects.exists())
        self.assertFalse(SerieExecutada.objects.exists())

    def test_nao_abre_treino_de_outra_pessoa(self):
        outra = criar_usuario('bia@email.com', '11144477735')
        sessao = SessaoAtividade.objects.create(usuario=outra, esporte=esporte_musculacao(), inicio=timezone.now(),
                                                duracao_minutos=30, intensidade='leve')
        self.assertEqual(self.client.get(reverse('historico:sessao', args=[sessao.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('historico:excluir', args=[sessao.id])).status_code, 404)
