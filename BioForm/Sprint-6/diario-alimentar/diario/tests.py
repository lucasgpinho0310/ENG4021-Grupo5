from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from saude.models import (
    Alimento,
    DiarioConsumo,
    HistoricoMedida,
    MedidaCaseira,
    MetaNutricional,
    RefeicaoPersonalizada,
    RegistroRefeicao,
    RegistroRefeicaoItem,
    Usuario,
)

from . import servicos

User = get_user_model()
SENHA = 'treino-forte-2026'


def criar_usuario_com_meta(email='ana@email.com', cpf='52998224725'):
    conta = User.objects.create_user(username=email, email=email, password=SENHA)
    usuario = Usuario.objects.create(
        conta=conta, nome_completo='Ana Souza', apelido='Ana', cpf=cpf, celular='21999990000',
        data_nascimento=date(1998, 1, 15), sexo_biologico='feminino', altura_cm=165, biotipo='mesomorfo',
    )
    HistoricoMedida.objects.create(usuario=usuario, data_registro=timezone.now(), peso_kg=Decimal('60'),
                                   objetivo_momento='manutencao')
    # Meta redonda para facilitar as contas dos testes
    MetaNutricional.objects.create(
        usuario=usuario, data_inicio=timezone.localdate() - timedelta(days=30), meta_calorias=2000,
        meta_proteina_g=Decimal('100'), meta_carbo_g=Decimal('250'), meta_gordura_g=Decimal('66'), meta_agua_ml=2000,
    )
    return usuario


def alimento(nome):
    return Alimento.objects.get(nome=nome)


def medida(nome_alimento, nome_medida):
    return MedidaCaseira.objects.get(alimento__nome=nome_alimento, nome=nome_medida)


ARROZ = 'Arroz, tipo 1, cozido'  # 128 kcal / 2,5 P / 28,1 C / 0,2 G por 100 g
FRANGO = 'Frango, peito, sem pele, grelhado'  # 159 kcal / 32 P / 0 C / 2,5 G
FEIJAO = 'Feijão, carioca, cozido'


class RegistroDeRefeicoesTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario_com_meta()
        self.hoje = timezone.localdate()

    def test_registrar_por_medida_caseira_e_por_gramas(self):
        colher = medida(ARROZ, '1 colher de servir')  # 45 g
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', colher.alimento, Decimal('2'), colher)
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(FRANGO), Decimal('1.5'))  # 150 g

        resumo = servicos.resumo_do_dia(self.usuario, self.hoje)
        almoco = next(r for r in resumo.refeicoes if r.tipo == 'almoco')
        self.assertEqual(len(almoco.itens), 2)
        self.assertEqual(RegistroRefeicao.objects.count(), 1)  # os dois no mesmo almoço
        # 90 g de arroz (115,2 kcal) + 150 g de frango (238,5 kcal)
        self.assertEqual(resumo.total['kcal'], Decimal('353.7'))
        self.assertEqual(resumo.total['proteina_g'], Decimal('50.25'))
        self.assertEqual(resumo.restante_kcal, Decimal('1646.3'))

    def test_nao_registra_dia_futuro(self):
        with self.assertRaises(servicos.DiaFuturo):
            servicos.registrar_item(self.usuario, self.hoje + timedelta(days=1), 'almoco', alimento(ARROZ), Decimal('1'))

    def test_registra_dia_passado(self):
        ontem = self.hoje - timedelta(days=1)
        servicos.registrar_item(self.usuario, ontem, 'jantar', alimento(ARROZ), Decimal('1'))
        registro = RegistroRefeicao.objects.get()
        self.assertEqual(registro.diario.data_referencia, ontem)
        self.assertEqual(timezone.localtime(registro.horario).date(), ontem)

    def test_remover_ultimo_item_apaga_a_refeicao(self):
        item = servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        servicos.remover_item(self.usuario, item.id)
        self.assertFalse(RegistroRefeicaoItem.objects.exists())
        self.assertFalse(RegistroRefeicao.objects.exists())

    def test_nao_remove_item_de_outra_pessoa(self):
        item = servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        outra = criar_usuario_com_meta('bruno@email.com', '11144477735')
        with self.assertRaises(RegistroRefeicaoItem.DoesNotExist):
            servicos.remover_item(outra, item.id)

    def test_meta_que_valia_no_dia(self):
        MetaNutricional.objects.create(
            usuario=self.usuario, data_inicio=self.hoje, meta_calorias=2500, meta_proteina_g=Decimal('120'),
            meta_carbo_g=Decimal('300'), meta_gordura_g=Decimal('70'), meta_agua_ml=2500,
        )
        self.assertEqual(servicos.meta_do_dia(self.usuario, self.hoje).meta_calorias, 2500)
        self.assertEqual(servicos.meta_do_dia(self.usuario, self.hoje - timedelta(days=1)).meta_calorias, 2000)


class AguaECheckinTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario_com_meta()
        self.hoje = timezone.localdate()

    def test_agua_soma_e_nao_fica_negativa(self):
        servicos.adicionar_agua(self.usuario, self.hoje, 500)
        servicos.adicionar_agua(self.usuario, self.hoje, 250)
        self.assertEqual(servicos.resumo_do_dia(self.usuario, self.hoje).agua_ml, 750)
        for _ in range(5):
            servicos.adicionar_agua(self.usuario, self.hoje, -250)
        self.assertEqual(servicos.resumo_do_dia(self.usuario, self.hoje).agua_ml, 0)

    def test_meta_de_agua(self):
        for _ in range(4):
            servicos.adicionar_agua(self.usuario, self.hoje, 500)
        resumo = servicos.resumo_do_dia(self.usuario, self.hoje)
        self.assertTrue(resumo.meta_agua_atingida)
        self.assertEqual(resumo.percentual_agua, 100)

    def lancar_dia_na_meta(self):
        # 2000 kcal / 100 P / 250 C / 66 G pedem uma combinação: aproximamos com arroz, frango e azeite
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('8.2'))
        servicos.registrar_item(self.usuario, self.hoje, 'jantar', alimento(FRANGO), Decimal('2.3'))
        azeite = medida('Azeite, de oliva, extra virgem', '1 colher de sopa')
        servicos.registrar_item(self.usuario, self.hoje, 'jantar', azeite.alimento, Decimal('4.2'), azeite)

    def test_checkin_so_dentro_da_meta(self):
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        self.assertFalse(servicos.confirmar_dieta(self.usuario, self.hoje))
        self.lancar_dia_na_meta()
        resumo = servicos.resumo_do_dia(self.usuario, self.hoje)
        self.assertTrue(resumo.dentro_da_meta, resumo.total)
        self.assertTrue(servicos.confirmar_dieta(self.usuario, self.hoje))
        self.assertTrue(DiarioConsumo.objects.get().status_dieta_cumprida)

    def test_checkin_e_desfeito_se_o_dia_sai_da_meta(self):
        self.lancar_dia_na_meta()
        servicos.confirmar_dieta(self.usuario, self.hoje)
        servicos.registrar_item(self.usuario, self.hoje, 'ceia', alimento(ARROZ), Decimal('5'))  # +640 kcal
        self.assertFalse(DiarioConsumo.objects.get().status_dieta_cumprida)


class CombosEBuscaTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario_com_meta()
        self.hoje = timezone.localdate()

    def test_salvar_e_usar_combo(self):
        concha = medida(FEIJAO, '1 concha média')  # 140 g
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1.5'))
        item = servicos.registrar_item(self.usuario, self.hoje, 'almoco', concha.alimento, Decimal('1'), concha)
        combo = servicos.salvar_combo(self.usuario, item.registro_id, 'Arroz e feijão')
        self.assertEqual(
            sorted((i.alimento.nome, i.quantidade_multiplicador) for i in combo.itens.all()),
            [(ARROZ, Decimal('1.50')), (FEIJAO, Decimal('1.40'))],
        )

        ontem = self.hoje - timedelta(days=1)
        servicos.usar_combo(self.usuario, ontem, 'jantar', combo.id)
        resumo_ontem = servicos.resumo_do_dia(self.usuario, ontem)
        resumo_hoje = servicos.resumo_do_dia(self.usuario, self.hoje)
        self.assertEqual(resumo_ontem.total['kcal'], resumo_hoje.total['kcal'])
        self.assertEqual(servicos.combos_do_usuario(self.usuario)[0].total['kcal'], resumo_hoje.total['kcal'])

    def test_combo_e_so_do_dono(self):
        item = servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        combo = servicos.salvar_combo(self.usuario, item.registro_id, 'Arroz')
        outra = criar_usuario_com_meta('bruno@email.com', '11144477735')
        with self.assertRaises(RefeicaoPersonalizada.DoesNotExist):
            servicos.usar_combo(outra, self.hoje, 'almoco', combo.id)

    def test_busca_ignora_acento_e_prioriza_quem_tem_medida(self):
        nomes = [a.nome for a in servicos.buscar_alimentos('feijao')]
        self.assertIn(FEIJAO, nomes)
        self.assertIn(nomes[0], (FEIJAO, 'Feijão, preto, cozido', 'Feijoada'))
        self.assertEqual(servicos.buscar_alimentos('  '), [])
        self.assertEqual([a.nome for a in servicos.buscar_alimentos('peito frango grelhado')], [FRANGO])

    def test_alimentos_recentes(self):
        servicos.registrar_item(self.usuario, self.hoje - timedelta(days=2), 'almoco', alimento(FRANGO), Decimal('1'))
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        self.assertEqual([a.nome for a in servicos.alimentos_recentes(self.usuario)], [ARROZ, FRANGO])


class TelasDoDiarioTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario_com_meta()
        self.hoje = timezone.localdate()
        self.client.login(username='ana@email.com', password=SENHA)

    def test_diario_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse('diario_hoje'))
        self.assertTrue(resposta.url.startswith(reverse('login')))

    def test_diario_exige_perfil_completo(self):
        MetaNutricional.objects.all().delete()
        resposta = self.client.get(reverse('diario_hoje'))
        self.assertRedirects(resposta, reverse('perfil_esportes'))

    def test_dia_futuro_volta_para_hoje(self):
        resposta = self.client.get(reverse('diario_dia', args=[self.hoje + timedelta(days=1)]))
        self.assertRedirects(resposta, reverse('diario_hoje'))

    def test_pagina_do_dia(self):
        servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        resposta = self.client.get(reverse('diario_hoje'))
        self.assertContains(resposta, 'Hoje')
        self.assertContains(resposta, ARROZ)
        self.assertContains(resposta, '1.872')  # 2000 - 128 kcal restantes

    def test_buscar_escolher_e_adicionar(self):
        url = reverse('diario_adicionar', args=[self.hoje])
        resposta = self.client.get(url, {'q': 'pao frances', 'refeicao': 'cafe_manha'})
        self.assertContains(resposta, 'Pão, trigo, francês')

        pao = alimento('Pão, trigo, francês')
        unidade = medida('Pão, trigo, francês', '1 unidade')
        resposta = self.client.get(url, {'alimento': pao.id, 'refeicao': 'cafe_manha'})
        self.assertContains(resposta, '1 unidade (50 g')

        resposta = self.client.post(url + '?refeicao=cafe_manha', {
            'alimento': pao.id, 'medida': unidade.id, 'quantidade': '2', 'tipo_refeicao': 'cafe_manha',
        })
        self.assertRedirects(resposta, reverse('diario_hoje'))
        item = RegistroRefeicaoItem.objects.get()
        self.assertEqual(item.gramas(), Decimal('100'))
        self.assertEqual(item.registro.tipo_refeicao, 'cafe_manha')

    def test_adicionar_em_gramas_valida_no_servidor(self):
        url = reverse('diario_adicionar', args=[self.hoje])
        frango = alimento(FRANGO)
        resposta = self.client.post(url, {'alimento': frango.id, 'medida': 'g', 'quantidade': '5000', 'tipo_refeicao': 'jantar'})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(RegistroRefeicaoItem.objects.exists())
        self.client.post(url, {'alimento': frango.id, 'medida': 'g', 'quantidade': '120', 'tipo_refeicao': 'jantar'})
        self.assertEqual(RegistroRefeicaoItem.objects.get().gramas(), Decimal('120'))

    def test_agua_pela_tela(self):
        self.client.post(reverse('diario_agua', args=[self.hoje]), {'ml': '500'})
        self.client.post(reverse('diario_agua', args=[self.hoje]), {'ml': '9999'})  # valor não permitido
        self.assertEqual(DiarioConsumo.objects.get().total_agua_consumida_ml, 500)

    def test_remover_pela_tela(self):
        item = servicos.registrar_item(self.usuario, self.hoje, 'almoco', alimento(ARROZ), Decimal('1'))
        resposta = self.client.post(reverse('diario_remover_item', args=[item.id]))
        self.assertRedirects(resposta, reverse('diario_hoje'))
        self.assertFalse(RegistroRefeicaoItem.objects.exists())

    def test_combo_pela_tela(self):
        item = servicos.registrar_item(self.usuario, self.hoje, 'cafe_manha', alimento(ARROZ), Decimal('1'))
        self.client.post(reverse('diario_salvar_combo', args=[item.registro_id]), {'nome': 'Meu café'})
        combo = RefeicaoPersonalizada.objects.get(nome_refeicao='Meu café')
        self.client.post(reverse('diario_usar_combo', args=[self.hoje]), {'combo': combo.id, 'tipo_refeicao': 'ceia'})
        self.assertEqual(RegistroRefeicaoItem.objects.filter(registro__tipo_refeicao='ceia').count(), 1)

    def test_historico(self):
        servicos.registrar_item(self.usuario, self.hoje - timedelta(days=1), 'almoco', alimento(ARROZ), Decimal('1'))
        resposta = self.client.get(reverse('diario_historico'))
        self.assertEqual(len(resposta.context['dias']), 14)
        self.assertContains(resposta, 'Ontem')
        self.assertContains(resposta, 'fora da meta')
