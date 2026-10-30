from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from metas.calculo import calcular_metas, gasto_semanal_do_esporte, salvar_meta
from saude.models import Esporte, EsporteUsuario, HistoricoMedida, Usuario

from .confirmacao import precisa_confirmar
from .semana import semana_do_usuario

User = get_user_model()
SENHA = 'treino-forte-2026'


def criar_usuario(email='bia@email.com', cpf='52998224725', confirmada=True):
    conta = User.objects.create_user(username=email, email=email, password=SENHA)
    usuario = Usuario.objects.create(
        conta=conta, nome_completo='Bia Lima', apelido='Bia', cpf=cpf, celular='21999990000',
        data_nascimento=date(1996, 5, 10), sexo_biologico='feminino', altura_cm=168, biotipo='mesomorfo',
        rotina_confirmada_em=timezone.localdate() if confirmada else None,
    )
    HistoricoMedida.objects.create(usuario=usuario, data_registro=timezone.now(), peso_kg=Decimal('60'),
                                   objetivo_momento='hipertrofia')
    salvar_meta(usuario)  # com a meta salva, o perfil está completo
    return usuario


def esporte(nome):
    return Esporte.objects.get(nome=nome)


class PassoEsportesTest(TestCase):
    """Passo 3 do perfil: minutos por treino e dias fixos (alguns fixos, o resto livre)."""

    def setUp(self):
        self.usuario = criar_usuario(confirmada=False)
        self.client.login(username='bia@email.com', password=SENHA)

    def enviar(self, **extra):
        dados = {'pratica_musculacao': 'on', 'freq_musculacao': '4', 'int_musculacao': 'intensa',
                 'dur_musculacao': '45', 'fixos_musculacao': 'sim', 'dias_musculacao': ['seg', 'qua']}
        dados.update(extra)
        return self.client.post(reverse('perfil_esportes'), dados)

    def test_salva_minutos_e_dois_dias_fixos_de_quatro(self):
        self.assertRedirects(self.enviar(), reverse('perfil_metas'), fetch_redirect_response=False)
        musculacao = self.usuario.esportes.get()
        self.assertEqual(musculacao.duracao_minutos, 45)
        self.assertEqual(musculacao.dias_fixos, 'seg,qua')
        self.assertEqual(musculacao.treinos_livres, 2)

    def test_dias_ficam_na_ordem_da_semana(self):
        self.enviar(dias_musculacao=['sex', 'seg', 'qua'])
        self.assertEqual(self.usuario.esportes.get().dias_fixos, 'seg,qua,sex')

    def test_nao_aceita_mais_dias_fixos_que_treinos(self):
        resposta = self.enviar(freq_musculacao='2', dias_musculacao=['seg', 'qua', 'sex'])
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'você marcou 3 dias fixos, mas treina 2 vezes por semana')
        self.assertFalse(self.usuario.esportes.exists())

    def test_sim_sem_marcar_dias_pede_os_dias(self):
        resposta = self.enviar(dias_musculacao=[])
        self.assertContains(resposta, 'Marque os dias fixos de Musculação')

    def test_responder_nao_descarta_os_dias_marcados(self):
        self.enviar(fixos_musculacao='nao')
        musculacao = self.usuario.esportes.get()
        self.assertEqual(musculacao.dias_fixos, '')
        self.assertEqual(musculacao.treinos_livres, 4)

    def test_sem_duracao_usa_uma_hora(self):
        self.client.post(reverse('perfil_esportes'), {
            'pratica_corrida': 'on', 'freq_corrida': '3', 'int_corrida': 'moderada'})
        self.assertEqual(self.usuario.esportes.get().duracao_minutos, 60)

    def test_salvar_o_passo_confirma_a_rotina(self):
        self.enviar()
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.rotina_confirmada_em, timezone.localdate())

    def test_tela_mostra_os_valores_salvos(self):
        self.enviar()
        resposta = self.client.get(reverse('perfil_esportes'))
        self.assertContains(resposta, 'name="dur_musculacao" value="45" checked')
        self.assertContains(resposta, 'id="fixos-musculacao" name="fixos_musculacao" value="sim" checked')
        self.assertContains(resposta, 'name="dias_musculacao" value="seg" checked')


class GastoComMinutosTest(TestCase):
    def test_meia_hora_gasta_metade_de_uma_hora(self):
        hora = gasto_semanal_do_esporte(80, Decimal('5.0'), 4, 'moderada', 60)
        meia = gasto_semanal_do_esporte(80, Decimal('5.0'), 4, 'moderada', 30)
        self.assertAlmostEqual(meia, hora / 2)
        self.assertAlmostEqual(hora, (5.0 - 1) * 80 * 4)  # 1.280 kcal por semana

    def test_sem_minutos_conta_uma_hora(self):
        sem = calcular_metas('masculino', 30, 80, 180, 'manutencao', [(5, 4, 'moderada')])
        com = calcular_metas('masculino', 30, 80, 180, 'manutencao', [(5, 4, 'moderada', 60)])
        self.assertEqual(sem.gasto_esportes, com.gasto_esportes)

    def test_treino_longo_aumenta_a_meta(self):
        curto = calcular_metas('feminino', 28, 60, 168, 'manutencao', [(5, 4, 'intensa', 45)])
        longo = calcular_metas('feminino', 28, 60, 168, 'manutencao', [(5, 4, 'intensa', 120)])
        self.assertGreater(longo.calorias, curto.calorias)


class SemanaTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=esporte('Musculação'), frequencia_semanal=4,
                                      intensidade='moderada', duracao_minutos=60, dias_fixos='seg,qua')
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=esporte('Corrida'), frequencia_semanal=2,
                                      intensidade='moderada', duracao_minutos=30, dias_fixos='sab')

    def test_monta_dias_fixos_e_livres(self):
        semana = semana_do_usuario(self.usuario, hoje=date(2026, 10, 26))  # uma segunda-feira
        segunda, sabado = semana.dias[0], semana.dias[5]
        self.assertTrue(segunda.hoje)
        self.assertEqual([e.nome for e in segunda.esportes], ['Musculação'])
        self.assertEqual([e.nome for e in sabado.esportes], ['Corrida'])
        self.assertEqual({e.nome: e.livres for e in semana.livres}, {'Musculação': 2, 'Corrida': 1})

    def test_totais_da_semana(self):
        semana = semana_do_usuario(self.usuario)
        self.assertEqual(semana.treinos_semana, 6)
        self.assertEqual(semana.minutos_semana, 4 * 60 + 2 * 30)
        self.assertEqual(semana.horas_semana, '5h00')
        # musculação: (5 - 1) x 60 kg x 1 h x 4 = 960; corrida: (8 - 1) x 60 x 0,5 h x 2 = 420
        self.assertEqual(semana.kcal_semana, 1380)
        self.assertEqual(semana.kcal_por_dia, 197)

    def test_media_por_dia_e_o_gasto_que_entra_na_meta(self):
        from metas.calculo import metas_do_usuario
        self.assertEqual(semana_do_usuario(self.usuario).kcal_por_dia, metas_do_usuario(self.usuario).gasto_esportes)

    def test_pagina_da_semana(self):
        self.client.login(username='bia@email.com', password=SENHA)
        resposta = self.client.get(reverse('rotina_semana'))
        self.assertContains(resposta, 'Sua semana de treinos')
        self.assertContains(resposta, 'Treinos livres:')
        self.assertContains(resposta, '1.380')


class ConfirmacaoMensalTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=esporte('Musculação'), frequencia_semanal=4,
                                      intensidade='moderada', duracao_minutos=60, dias_fixos='seg,qua')
        self.client.login(username='bia@email.com', password=SENHA)

    def envelhecer(self, dias):
        self.usuario.rotina_confirmada_em = timezone.localdate() - timedelta(days=dias)
        self.usuario.save()

    def test_pergunta_depois_de_30_dias(self):
        self.envelhecer(29)
        self.assertFalse(precisa_confirmar(self.usuario))
        self.envelhecer(30)
        self.assertTrue(precisa_confirmar(self.usuario))

    def test_aviso_aparece_nas_paginas_e_some_ao_confirmar(self):
        self.envelhecer(31)
        resposta = self.client.get(reverse('perfil_metas'))
        self.assertContains(resposta, 'Sua rotina de treinos continua a mesma?')
        self.assertContains(resposta, 'Musculação 4x por semana · 60 min · fixos Seg, Qua')

        resposta = self.client.post(reverse('rotina_confirmar'), {'voltar': reverse('perfil_metas')})
        self.assertRedirects(resposta, reverse('perfil_metas'), fetch_redirect_response=False)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.rotina_confirmada_em, timezone.localdate())
        self.assertNotContains(self.client.get(reverse('perfil_metas')), 'continua a mesma?')

    def test_aviso_nao_aparece_no_proprio_passo_3(self):
        self.envelhecer(31)
        self.assertNotContains(self.client.get(reverse('perfil_esportes')), 'continua a mesma?')

    def test_quem_nunca_confirmou_recebe_o_aviso(self):
        self.usuario.rotina_confirmada_em = None
        self.usuario.save()
        self.assertContains(self.client.get(reverse('perfil_metas')), 'continua a mesma?')

    def test_confirmar_nao_redireciona_para_outro_site(self):
        resposta = self.client.post(reverse('rotina_confirmar'), {'voltar': 'https://site-estranho.com/'})
        self.assertRedirects(resposta, reverse('rotina_semana'), fetch_redirect_response=False)

    def test_confirmar_so_por_post(self):
        self.assertEqual(self.client.get(reverse('rotina_confirmar')).status_code, 405)
