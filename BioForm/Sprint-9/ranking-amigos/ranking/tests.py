from datetime import date, datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_usuario
from saude.models import (
    Amizade,
    DiarioConsumo,
    PerfilGamificacao,
    RegistroRefeicao,
    RegistroXP,
    SessaoAtividade,
)

from . import servicos

HOJE = date(2026, 11, 12)  # quinta-feira; a semana vai de 09/11 (seg) a 15/11 (dom)
SEGUNDA, DOMINGO = date(2026, 11, 9), date(2026, 11, 15)


def criar_pessoa(nome, cpf):
    usuario = criar_usuario(email='%s@email.com' % nome.lower(), cpf=cpf)
    usuario.nome_completo, usuario.apelido = '%s Souza' % nome, nome
    usuario.save()
    return usuario


class Base(TestCase):
    def setUp(self):
        self.caio = criar_usuario()  # caio@email.com
        self.ana = criar_pessoa('Ana', '11144477735')
        self.bia = criar_pessoa('Bia', '39053344705')
        self.musculacao = esporte_musculacao()

    def treino(self, usuario, dia, hora=18):
        return SessaoAtividade.objects.create(
            usuario=usuario, esporte=self.musculacao, duracao_minutos=60, intensidade='moderada',
            inicio=timezone.make_aware(datetime.combine(dia, time(hora, 0))),
        )

    def refeicao(self, usuario, dia, tipo='almoco'):
        diario, _ = DiarioConsumo.objects.get_or_create(usuario=usuario, data_referencia=dia)
        return RegistroRefeicao.objects.create(
            diario=diario, tipo_refeicao=tipo, horario=timezone.make_aware(datetime.combine(dia, time(12, 0))),
        )


class AmigosTest(Base):
    def test_adicionar_vale_para_os_dois_lados(self):
        amigo = servicos.adicionar_amigo(self.caio, 'ANA@email.com ')
        self.assertEqual(amigo, self.ana)
        self.assertEqual(list(servicos.amigos_de(self.caio)), [self.ana])
        self.assertEqual(list(servicos.amigos_de(self.ana)), [self.caio])

    def test_nao_adiciona_desconhecido_a_si_mesmo_nem_repetido(self):
        for email in ('ninguem@email.com', 'caio@email.com'):
            with self.assertRaises(servicos.AmigoInvalido):
                servicos.adicionar_amigo(self.caio, email)
        servicos.adicionar_amigo(self.caio, 'ana@email.com')
        with self.assertRaises(servicos.AmigoInvalido):
            servicos.adicionar_amigo(self.ana, 'caio@email.com')  # já são amigos, pelo outro lado
        self.assertEqual(Amizade.objects.count(), 1)

    def test_remover_desfaz_pelos_dois_lados(self):
        servicos.adicionar_amigo(self.caio, 'ana@email.com')
        self.assertTrue(servicos.remover_amigo(self.ana, self.caio.id))
        self.assertFalse(servicos.remover_amigo(self.ana, self.caio.id))
        self.assertEqual(servicos.amigos_de(self.caio).count(), 0)


class XPTest(Base):
    def test_treinos_e_refeicoes_viram_xp(self):
        self.treino(self.caio, date(2026, 11, 9))
        self.treino(self.caio, date(2026, 11, 9), hora=20)  # 2º treino do dia vale 20
        self.treino(self.caio, date(2026, 11, 10))
        self.refeicao(self.caio, date(2026, 11, 10))
        self.refeicao(self.caio, date(2026, 11, 10), tipo='jantar')
        self.assertEqual(servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO), 50 + 20 + 50 + 10 + 10)
        self.assertEqual(PerfilGamificacao.objects.get(usuario=self.caio).pontos_experiencia, 140)

    def test_sincronizar_de_novo_nao_duplica(self):
        self.treino(self.caio, date(2026, 11, 9))
        servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO)
        self.assertEqual(servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO), 0)
        self.treino(self.caio, date(2026, 11, 11))
        self.assertEqual(servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO), 50)
        self.assertEqual(RegistroXP.objects.filter(usuario=self.caio).count(), 2)

    def test_aproveita_xp_que_ja_existia(self):
        RegistroXP.objects.create(usuario=self.caio, acao='treino', pontos=50, data_referencia=date(2026, 11, 9))
        self.treino(self.caio, date(2026, 11, 9))
        self.assertEqual(servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO), 0)

    def test_treino_de_outra_semana_fica_de_fora(self):
        self.treino(self.caio, date(2026, 11, 8))  # domingo da semana anterior
        self.assertEqual(servicos.sincronizar_xp(self.caio, SEGUNDA, DOMINGO), 0)


class RankingTest(Base):
    def setUp(self):
        super().setUp()
        servicos.adicionar_amigo(self.caio, 'ana@email.com')
        servicos.adicionar_amigo(self.bia, 'caio@email.com')

    def ranking(self, usuario=None, **extra):
        return servicos.ranking_semanal(usuario or self.caio, hoje=HOJE, **extra)

    def test_ordena_pelo_xp_da_semana(self):
        self.treino(self.ana, date(2026, 11, 9))
        self.treino(self.ana, date(2026, 11, 10))
        self.treino(self.caio, date(2026, 11, 9))
        self.refeicao(self.caio, date(2026, 11, 9))
        ranking = self.ranking()
        self.assertEqual((ranking.inicio, ranking.fim), (SEGUNDA, DOMINGO))
        self.assertEqual([(l.posicao, l.usuario, l.xp, l.treinos) for l in ranking.linhas],
                         [(1, self.ana, 100, 2), (2, self.caio, 60, 1), (3, self.bia, 0, 0)])
        self.assertTrue(ranking.voce.voce)
        self.assertEqual((ranking.voce.posicao, ranking.falta_para_o_proximo), (2, 40))
        self.assertEqual([l.percentual for l in ranking.linhas], [100, 60, 0])

    def test_empate_divide_a_posicao(self):
        self.treino(self.ana, date(2026, 11, 9))
        self.treino(self.caio, date(2026, 11, 10))
        ranking = self.ranking()
        self.assertEqual([l.posicao for l in ranking.linhas], [1, 1, 3])
        self.assertEqual(ranking.falta_para_o_proximo, 0)

    def test_so_entram_os_meus_amigos(self):
        ranking = self.ranking(self.ana)  # Ana é amiga só do Caio
        self.assertEqual({l.usuario for l in ranking.linhas}, {self.ana, self.caio})

    def test_semana_passada(self):
        self.treino(self.caio, date(2026, 11, 3))
        self.assertEqual(self.ranking().voce.xp, 0)
        passada = self.ranking(semanas_atras=1)
        self.assertEqual((passada.inicio, passada.voce.xp), (date(2026, 11, 2), 50))

    def test_sem_amigos(self):
        ranking = servicos.ranking_semanal(criar_pessoa('Davi', '86288366757'), hoje=HOJE)
        self.assertFalse(ranking.tem_amigos)
        self.assertEqual((len(ranking.linhas), ranking.voce.posicao), (1, 1))


class TelasTest(Base):
    def setUp(self):
        super().setUp()
        self.client.login(username='caio@email.com', password=SENHA)

    def test_ranking_pede_login(self):
        self.client.logout()
        resposta = self.client.get(reverse('ranking:semana'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/accounts/login/', resposta.url)

    def test_ranking_mostra_a_classificacao(self):
        servicos.adicionar_amigo(self.caio, 'ana@email.com')
        self.treino(self.ana, timezone.localdate())
        resposta = self.client.get(reverse('ranking:semana'))
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, '50 <span>XP</span>')
        self.assertContains(resposta, reverse('ranking:amigos'))

    def test_ranking_sem_amigos_convida_a_adicionar(self):
        resposta = self.client.get(reverse('ranking:semana') + '?semana=abc')
        self.assertContains(resposta, 'Adicionar amigo')

    def test_adicionar_amigo_pela_tela(self):
        resposta = self.client.post(reverse('ranking:amigos'), {'email': 'ana@email.com'})
        self.assertRedirects(resposta, reverse('ranking:amigos'))
        self.assertEqual(list(servicos.amigos_de(self.caio)), [self.ana])

    def test_email_desconhecido_mostra_o_erro(self):
        resposta = self.client.post(reverse('ranking:amigos'), {'email': 'ninguem@email.com'})
        self.assertContains(resposta, 'Não encontramos ninguém')
        self.assertEqual(Amizade.objects.count(), 0)

    def test_remover_amigo_pela_tela(self):
        servicos.adicionar_amigo(self.caio, 'ana@email.com')
        self.assertEqual(self.client.get(reverse('ranking:remover', args=[self.ana.id])).status_code, 405)
        resposta = self.client.post(reverse('ranking:remover', args=[self.ana.id]))
        self.assertRedirects(resposta, reverse('ranking:amigos'))
        self.assertEqual(Amizade.objects.count(), 0)

    def test_menu_e_home_tem_o_link(self):
        self.assertContains(self.client.get(reverse('evolucao:peso')), reverse('ranking:semana'))
        self.assertContains(self.client.get(reverse('home')), reverse('ranking:semana'))
