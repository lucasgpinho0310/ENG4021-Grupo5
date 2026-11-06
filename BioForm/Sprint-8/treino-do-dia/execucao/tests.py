from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from metas.calculo import salvar_meta
from saude.models import ExercicioFicha, FichaTreino, HistoricoMedida, SerieExecutada, SessaoAtividade, Usuario

from . import servicos

User = get_user_model()
SENHA = 'treino-forte-2026'


def criar_usuario(email='caio@email.com', cpf='52998224725'):
    conta = User.objects.create_user(username=email, email=email, password=SENHA)
    usuario = Usuario.objects.create(
        conta=conta, nome_completo='Caio Melo', apelido='Caio', cpf=cpf, celular='21999990000',
        data_nascimento=date(1995, 3, 2), sexo_biologico='masculino', altura_cm=180, biotipo='mesomorfo',
        rotina_confirmada_em=timezone.localdate(),
    )
    HistoricoMedida.objects.create(usuario=usuario, data_registro=timezone.now(), peso_kg=Decimal('80'),
                                   objetivo_momento='hipertrofia')
    salvar_meta(usuario)  # com a meta salva, o perfil está completo
    return usuario


def criar_ficha(usuario):
    ficha = FichaTreino.objects.create(usuario=usuario, nome_ficha='Inferiores')
    agachamento = ExercicioFicha.objects.create(
        ficha=ficha, nome_exercicio='Agachamento', ordem_execucao=1, series_planejadas=3,
        repeticoes_planejadas=10, carga_kg=Decimal('40'), intervalo_segundos=90,
    )
    prancha = ExercicioFicha.objects.create(
        ficha=ficha, nome_exercicio='Prancha', ordem_execucao=2, series_planejadas=2, tempo_segundos=30,
    )
    return ficha, agachamento, prancha


def dados_treino(agachamento, prancha, **extra):
    """As 3 séries de agachamento e as 2 de prancha marcadas como feitas."""
    dados = {'data': timezone.localdate().isoformat(), 'duracao': '50', 'intensidade': 'intensa'}
    for n in (1, 2, 3):
        dados.update({'feita-%s-%d' % (agachamento.id, n): 'on', 'carga-%s-%d' % (agachamento.id, n): '42,5',
                      'reps-%s-%d' % (agachamento.id, n): '10'})
    for n in (1, 2):
        dados.update({'feita-%s-%d' % (prancha.id, n): 'on', 'tempo-%s-%d' % (prancha.id, n): '45'})
    dados.update(extra)
    return dados


class PlanoDoTreinoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.ficha, self.agachamento, self.prancha = criar_ficha(self.usuario)

    def test_primeira_vez_vem_com_o_planejado(self):
        agachamento, prancha = servicos.plano_do_treino([self.agachamento, self.prancha])
        self.assertEqual(len(agachamento.linhas), 3)
        self.assertEqual((agachamento.linhas[0].carga_kg, agachamento.linhas[0].repeticoes), (Decimal('40'), 10))
        self.assertEqual(prancha.linhas[1].tempo_segundos, 30)
        self.assertIsNone(prancha.linhas[1].repeticoes)
        self.assertEqual(agachamento.ultima_vez, [])
        self.assertIsNone(agachamento.recorde)

    def test_depois_vem_com_o_que_foi_feito_da_ultima_vez(self):
        sessao = SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=servicos.esporte_musculacao(), ficha=self.ficha,
            inicio=timezone.now() - timedelta(days=2), duracao_minutos=40, intensidade='moderada',
        )
        SerieExecutada.objects.create(sessao=sessao, exercicio=self.agachamento, numero_serie=1,
                                      carga_kg=Decimal('45'), repeticoes=8)
        agachamento = servicos.plano_do_treino([self.agachamento])[0]
        self.assertEqual((agachamento.linhas[0].carga_kg, agachamento.linhas[0].repeticoes), (Decimal('45'), 8))
        self.assertEqual(agachamento.linhas[1].carga_kg, Decimal('40'))  # série 2 não foi feita: planejado
        self.assertEqual(agachamento.recorde, Decimal('45'))
        self.assertEqual(len(agachamento.ultima_vez), 1)


class FazerTreinoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.ficha, self.agachamento, self.prancha = criar_ficha(self.usuario)
        self.client.login(username='caio@email.com', password=SENHA)
        self.url = reverse('execucao:fazer', args=[self.ficha.id])

    def test_pagina_mostra_as_series_preenchidas(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Agachamento')
        self.assertContains(resposta, 'name="reps-%s-3"' % self.agachamento.id)
        self.assertContains(resposta, 'name="tempo-%s-2"' % self.prancha.id)
        self.assertContains(resposta, 'data-descanso="90"')

    def test_ficha_tem_botao_comecar_treino(self):
        resposta = self.client.get(reverse('treinos:treinos_ficha', args=[self.ficha.id]))
        self.assertContains(resposta, self.url)

    def test_salvar_treino_grava_sessao_e_series(self):
        resposta = self.client.post(self.url, dados_treino(self.agachamento, self.prancha))
        sessao = SessaoAtividade.objects.get()
        self.assertRedirects(resposta, reverse('historico:sessao', args=[sessao.id]))
        self.assertEqual((sessao.ficha, sessao.esporte.nome, sessao.duracao_minutos, sessao.intensidade),
                         (self.ficha, 'Musculação', 50, 'intensa'))
        self.assertEqual(sessao.series.count(), 5)
        serie = sessao.series.get(exercicio=self.agachamento, numero_serie=1)
        self.assertEqual((serie.carga_kg, serie.repeticoes, serie.tempo_segundos), (Decimal('42.50'), 10, None))
        prancha = sessao.series.get(exercicio=self.prancha, numero_serie=2)
        self.assertEqual((prancha.repeticoes, prancha.tempo_segundos), (None, 45))

    def test_so_salva_as_series_marcadas(self):
        dados = dados_treino(self.agachamento, self.prancha)
        del dados['feita-%s-3' % self.agachamento.id]
        self.client.post(self.url, dados)
        self.assertEqual(SerieExecutada.objects.filter(exercicio=self.agachamento).count(), 2)

    def test_sem_nenhuma_serie_marcada_nao_salva(self):
        dados = {k: v for k, v in dados_treino(self.agachamento, self.prancha).items() if not k.startswith('feita-')}
        resposta = self.client.post(self.url, dados)
        self.assertContains(resposta, 'Marque pelo menos uma série feita.')
        self.assertFalse(SessaoAtividade.objects.exists())

    def test_valores_invalidos_voltam_com_erro(self):
        dados = dados_treino(self.agachamento, self.prancha, **{'reps-%s-1' % self.agachamento.id: '0'})
        resposta = self.client.post(self.url, dados)
        self.assertContains(resposta, 'Repetições entre 1 e 999.')
        self.assertFalse(SessaoAtividade.objects.exists())

    def test_treino_de_outro_dia_e_data_futura(self):
        ontem = timezone.localdate() - timedelta(days=1)
        self.client.post(self.url, dados_treino(self.agachamento, self.prancha, data=ontem.isoformat()))
        self.assertEqual(timezone.localdate(SessaoAtividade.objects.get().inicio), ontem)
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = self.client.post(self.url, dados_treino(self.agachamento, self.prancha, data=amanha.isoformat()))
        self.assertContains(resposta, 'O treino não pode ser numa data futura.')
        self.assertEqual(SessaoAtividade.objects.count(), 1)

    def test_serie_vazia_volta_para_a_ficha(self):
        vazia = FichaTreino.objects.create(usuario=self.usuario, nome_ficha='Vazia')
        resposta = self.client.get(reverse('execucao:fazer', args=[vazia.id]))
        self.assertRedirects(resposta, reverse('treinos:treinos_ficha', args=[vazia.id]))

    def test_nao_abre_serie_de_outra_pessoa(self):
        outra = criar_usuario('bia@email.com', '11144477735')
        ficha_da_outra, _, _ = criar_ficha(outra)
        self.assertEqual(self.client.get(reverse('execucao:fazer', args=[ficha_da_outra.id])).status_code, 404)

    def test_exige_login(self):
        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertTrue(resposta.url.startswith(reverse('login')))
