from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from diario import servicos as diario
from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_usuario
from metas.calculo import salvar_meta
from saude.models import EsporteUsuario, SessaoAtividade

from .servicos import MetaComTreinos, meta_com_treinos

# Musculação 4x por semana, 60 min, moderada, 80 kg: (5,0 - 1) x 80 x 1 h x 4 / 7 = 183 kcal por dia (média)
PREVISTO = 183
# Um treino de 60 min moderado: (5,0 - 1) x 80 x 1 h = 320 kcal
TREINO = 320


class BalancoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()  # 80 kg
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=esporte_musculacao(), frequencia_semanal=4,
                                      intensidade='moderada', duracao_minutos=60)
        self.meta, _ = salvar_meta(self.usuario)  # a meta salva já conta a média de 183 kcal
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)
        self.client.login(username='caio@email.com', password=SENHA)

    def treino(self, data, minutos=60):
        return SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=esporte_musculacao(), duracao_minutos=minutos, intensidade='moderada',
            inicio=timezone.make_aware(datetime.combine(data, time(7, 0))),
        )

    def ajustada(self, data):
        return meta_com_treinos(self.usuario, data, self.meta, hoje=self.hoje)

    def test_hoje_sem_treino_usa_a_media(self):
        meta = self.ajustada(self.hoje)
        self.assertTrue(meta.usando_previsto)
        self.assertEqual((meta.previsto, meta.gasto_esportes, meta.ajuste), (PREVISTO, PREVISTO, 0))
        self.assertEqual(meta.meta_calorias, self.meta.meta_calorias)

    def test_dia_com_treino_troca_a_media_pelo_gasto_real(self):
        self.treino(self.ontem)
        meta = self.ajustada(self.ontem)
        self.assertFalse(meta.usando_previsto)
        self.assertEqual((meta.real, meta.ajuste), (TREINO, TREINO - PREVISTO))
        self.assertEqual(meta.meta_calorias, self.meta.meta_calorias + TREINO - PREVISTO)
        # a diferença vai toda para os carboidratos; proteína, gordura e água não mudam
        self.assertEqual(meta.meta_carbo_g, (self.meta.meta_carbo_g + Decimal(TREINO - PREVISTO) / 4).quantize(Decimal('0.1')))
        self.assertEqual((meta.meta_proteina_g, meta.meta_gordura_g, meta.meta_agua_ml),
                         (self.meta.meta_proteina_g, self.meta.meta_gordura_g, self.meta.meta_agua_ml))

    def test_dia_passado_sem_treino_tira_a_media(self):
        meta = self.ajustada(self.ontem)
        self.assertEqual((meta.real, meta.ajuste), (0, -PREVISTO))

    def test_treino_de_hoje_tambem_conta(self):
        self.treino(self.hoje)
        self.treino(self.hoje, minutos=30)  # dois treinos no mesmo dia somam
        meta = self.ajustada(self.hoje)
        self.assertEqual((meta.real, len(meta.treinos)), (TREINO + TREINO // 2, 2))

    def test_meta_nunca_fica_abaixo_da_tmb(self):
        self.meta.meta_calorias = meta_com_treinos(self.usuario, self.hoje, self.meta).tmb + 50
        meta = self.ajustada(self.ontem)  # dia sem treino: tiraria 183 kcal
        self.assertEqual(meta.meta_calorias, meta.tmb)

    def test_gasto_total(self):
        meta = self.ajustada(self.ontem)
        self.assertEqual(meta.gasto_total, meta.tmb + meta.atividade_diaria)  # sem treino
        self.treino(self.ontem)
        meta = self.ajustada(self.ontem)
        self.assertEqual(meta.gasto_total, meta.tmb + meta.atividade_diaria + TREINO)

    def test_diario_usa_a_meta_ajustada(self):
        self.treino(self.hoje)
        resumo = diario.resumo_do_dia(self.usuario, self.hoje)
        self.assertIsInstance(resumo.meta, MetaComTreinos)
        self.assertEqual(resumo.meta.meta_calorias, self.meta.meta_calorias + TREINO - PREVISTO)
        pagina = self.client.get(reverse('diario:diario_hoje'))
        self.assertContains(pagina, 'a meta subiu %d kcal' % (TREINO - PREVISTO))
        self.assertContains(pagina, reverse('balanco:dia', args=[self.hoje]))

    def test_historico_do_diario_mostra_o_gasto(self):
        self.treino(self.ontem)
        pagina = self.client.get(reverse('diario:diario_historico'))
        self.assertContains(pagina, '1 treino')
        self.assertContains(pagina, reverse('balanco:dia', args=[self.ontem]))

    def test_pagina_do_balanco(self):
        self.treino(self.ontem)
        pagina = self.client.get(reverse('balanco:dia', args=[self.ontem]))
        self.assertContains(pagina, 'Balanço do dia')
        self.assertContains(pagina, '+%d kcal' % TREINO)
        self.assertContains(pagina, 'Déficit')  # nada comido no dia
        self.assertEqual(self.client.get(reverse('balanco:hoje')).status_code, 200)

    def test_dia_futuro_nao_abre(self):
        amanha = self.hoje + timedelta(days=1)
        self.assertRedirects(self.client.get(reverse('balanco:dia', args=[amanha])), reverse('diario:diario_hoje'))

    def test_perfil_sem_esportes_nao_muda_a_meta_sem_treino(self):
        self.usuario.esportes.all().delete()
        meta, _ = salvar_meta(self.usuario)
        ajustada = meta_com_treinos(self.usuario, self.ontem, meta, hoje=self.hoje)
        self.assertEqual(ajustada.meta_calorias, meta.meta_calorias)
