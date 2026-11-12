from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_usuario
from saude.models import Esporte, EsporteUsuario, SessaoAtividade

from . import servicos

HOJE = date(2026, 11, 12)  # quinta-feira; a semana vai de 09/11 (seg) a 15/11 (dom)


class SemanaFeitaTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()  # 80 kg
        self.musculacao = esporte_musculacao()
        self.corrida, _ = Esporte.objects.get_or_create(nome='Corrida', defaults={'met': Decimal('9.8')})
        # Musculação 3x: segunda e quarta fixas + 1 livre
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=self.musculacao, frequencia_semanal=3,
                                      intensidade='moderada', duracao_minutos=60, dias_fixos='seg,qua')
        self.client.login(username='caio@email.com', password=SENHA)

    def treino(self, data, esporte=None, minutos=60):
        return SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=esporte or self.musculacao, duracao_minutos=minutos,
            intensidade='moderada', inicio=timezone.make_aware(datetime.combine(data, time(18, 0))),
        )

    def semana(self, **extra):
        return servicos.semana_feita(self.usuario, hoje=HOJE, **extra)

    def test_dias_fixos_feitos_e_que_faltaram(self):
        self.treino(date(2026, 11, 9))  # segunda: feito
        semana = self.semana()           # quarta (11/11) passou sem treino
        segunda, quarta, sexta = semana.dias[0], semana.dias[2], semana.dias[4]
        self.assertEqual(semana.inicio, date(2026, 11, 9))
        self.assertTrue(segunda.previstos[0].feito)
        self.assertTrue(quarta.previstos[0].faltou)
        self.assertEqual(sexta.previstos, [])
        self.assertTrue(semana.dias[3].hoje)
        self.assertTrue(semana.dias[5].futuro)

    def test_aderencia_e_gasto(self):
        self.treino(date(2026, 11, 9))
        self.treino(date(2026, 11, 10))  # treino livre na terça
        semana = self.semana()
        musculacao = semana.esportes[0]
        self.assertEqual((musculacao.previstos, musculacao.feitos, musculacao.percentual), (3, 2, 67))
        self.assertEqual((semana.total_previsto, semana.total_feito, semana.aderencia), (3, 2, 67))
        self.assertEqual(semana.kcal_real, 640)  # 2 x 320 kcal
        self.assertEqual(semana.kcal_previsto, 960)  # 3 x 320 kcal

    def test_treino_a_mais_nao_passa_de_100_por_cento(self):
        for dia in (9, 10, 11, 12):
            self.treino(date(2026, 11, dia))
        semana = self.semana()
        self.assertEqual((semana.esportes[0].feitos, semana.aderencia), (4, 100))

    def test_esporte_fora_do_perfil_vira_extra(self):
        self.treino(date(2026, 11, 10), esporte=self.corrida, minutos=30)
        semana = self.semana()
        self.assertEqual(len(semana.extras), 1)
        self.assertEqual(semana.aderencia, 0)
        self.assertEqual(len(semana.dias[1].feitos), 1)

    def test_semana_passada(self):
        self.treino(date(2026, 11, 4))  # quarta da semana anterior
        semana = self.semana(semanas_atras=1)
        self.assertEqual((semana.inicio, semana.total_feito), (date(2026, 11, 2), 1))
        self.assertTrue(semana.dias[2].previstos[0].feito)
        self.assertTrue(semana.dias[0].previstos[0].faltou)  # semana passada inteira já passou

    def test_pagina_e_navegacao(self):
        hoje = timezone.localdate()
        self.treino(hoje)
        pagina = self.client.get(reverse('aderencia:semana'))
        self.assertContains(pagina, 'Esta semana')
        self.assertContains(pagina, '?semana=1')
        self.assertContains(self.client.get(reverse('aderencia:semana') + '?semana=1'), 'Semana passada')
        self.assertEqual(self.client.get(reverse('aderencia:semana') + '?semana=abc').status_code, 200)
        self.assertContains(self.client.get(reverse('aderencia:semana') + '?semana=99'), 'Há 11 semanas')

    def test_link_na_pagina_da_rotina(self):
        self.assertContains(self.client.get(reverse('rotina:rotina_semana')), reverse('aderencia:semana'))
