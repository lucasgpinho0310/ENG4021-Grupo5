from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from diario.servicos import registrar_item
from execucao.servicos import esporte_musculacao
from execucao.tests import SENHA, criar_ficha, criar_usuario
from saude.models import Alimento, EsporteUsuario, HistoricoMedida, SessaoAtividade

from . import servicos

HOJE = date(2026, 11, 12)  # quinta-feira; a semana vai de 09/11 (seg) a 15/11 (dom)
CODIGOS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom']


class PainelTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()  # 80 kg, perfil completo
        self.musculacao = esporte_musculacao()
        self.arroz = Alimento.objects.create(
            nome='Arroz teste', porcao_padrao='100g', porcao_gramas=Decimal('100'),
            kcal=Decimal('200'), proteina_g=Decimal('4'), carbo_g=Decimal('40'), gordura_g=Decimal('1'),
        )
        self.client.login(username='caio@email.com', password=SENHA)

    def treino(self, data, minutos=60):
        return SessaoAtividade.objects.create(
            usuario=self.usuario, esporte=self.musculacao, duracao_minutos=minutos,
            intensidade='moderada', inicio=timezone.make_aware(datetime.combine(data, time(7, 0))),
        )

    # ---------------------------------------------------------- abre direto no painel
    def test_home_de_quem_entrou_e_o_painel(self):
        resposta = self.client.get(reverse('home'))
        self.assertTemplateUsed(resposta, 'painel/painel.html')
        for texto in ('Olá, Caio!', 'Alimentação', 'Treino de hoje', 'Esta semana', 'Peso'):
            with self.subTest(texto=texto):
                self.assertContains(resposta, texto)

    def test_depois_do_login_vai_para_a_home(self):
        self.assertRedirects(self.client.get(reverse('contas:inicio')), reverse('home'))

    def test_menu_tem_hoje_marcado(self):
        resposta = self.client.get(reverse('painel:hoje'))
        self.assertContains(resposta, '<a href="%s" class="ativo">Hoje</a>' % reverse('home'), html=True)

    def test_sem_login_a_home_continua_com_entrar(self):
        self.client.logout()
        resposta = self.client.get(reverse('home'))
        self.assertTemplateUsed(resposta, 'home.html')
        self.assertContains(resposta, reverse('login'))

    # ---------------------------------------------------------- alimentação de hoje
    def test_alimentacao_de_hoje(self):
        registrar_item(self.usuario, timezone.localdate(), 'almoco', self.arroz, Decimal('2'))
        painel = servicos.painel_do_dia(self.usuario)
        self.assertEqual(painel.alimentacao.total['kcal'], Decimal('400'))
        resposta = self.client.get(reverse('home'))
        self.assertContains(resposta, '<strong>400</strong>', html=True)
        self.assertContains(resposta, 'para a meta')

    # ---------------------------------------------------------- treino de hoje
    def test_ficha_do_dia_tem_botao_comecar_treino(self):
        ficha, _, _ = criar_ficha(self.usuario)
        ficha.dias_semana = CODIGOS[timezone.localdate().weekday()]
        ficha.save()
        resposta = self.client.get(reverse('home'))
        self.assertContains(resposta, 'Inferiores')
        self.assertContains(resposta, reverse('execucao:fazer', args=[ficha.id]))

    def test_ficha_de_outro_dia_nao_aparece(self):
        ficha, _, _ = criar_ficha(self.usuario)
        ficha.dias_semana = CODIGOS[(timezone.localdate().weekday() + 1) % 7]
        ficha.save()
        self.assertEqual(servicos.fichas_de_hoje(self.usuario, timezone.localdate()), [])

    def test_dia_sem_nada_previsto_e_descanso(self):
        self.assertContains(self.client.get(reverse('home')), 'Dia de descanso')

    def test_treino_feito_hoje_e_previsto_marcado(self):
        hoje = timezone.localdate()
        EsporteUsuario.objects.create(usuario=self.usuario, esporte=self.musculacao, frequencia_semanal=3,
                                      intensidade='moderada', duracao_minutos=60, dias_fixos=CODIGOS[hoje.weekday()])
        self.treino(hoje)
        painel = servicos.painel_do_dia(self.usuario)
        self.assertEqual(len(painel.treino.feitos), 1)
        self.assertTrue(painel.treino.previstos[0].feito)
        self.assertFalse(painel.treino.descanso)
        self.assertContains(self.client.get(reverse('home')), 'chip feito')

    # ---------------------------------------------------------- gráficos da semana
    def test_semana_com_calorias_e_treinos_por_dia(self):
        registrar_item(self.usuario, date(2026, 11, 9), 'almoco', self.arroz, Decimal('5'))   # seg: 1.000 kcal
        registrar_item(self.usuario, date(2026, 11, 10), 'almoco', self.arroz, Decimal('10'))  # ter: 2.000 kcal
        self.treino(date(2026, 11, 10))
        semana, _ = servicos.montar_semana(self.usuario, HOJE)
        segunda, terca, sexta = semana.dias[0], semana.dias[1], semana.dias[4]
        self.assertEqual([d.nome for d in semana.dias], ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'])
        self.assertEqual((segunda.kcal, terca.kcal), (1000, 2000))
        self.assertEqual((terca.treinos, terca.gasto_treinos > 0, terca.altura_gasto), (1, True, 100))
        self.assertTrue(semana.dias[3].hoje)
        self.assertTrue(sexta.futuro)
        self.assertEqual((sexta.kcal, sexta.meta, sexta.altura_kcal), (0, None, 0))
        maior = max([d.kcal for d in semana.dias] + [d.meta or 0 for d in semana.dias])
        self.assertEqual(max(d.altura_kcal for d in semana.dias), round(2000 * 100 / maior))
        self.assertEqual((semana.dias_com_registro, semana.media_kcal), (2, 1500))

    def test_dia_na_meta(self):
        dia = servicos.DiaDoGrafico(data=HOJE, nome='Qui', hoje=True, futuro=False, kcal=2050, meta=2000,
                                    gasto_treinos=0, treinos=0, previstos=0)
        self.assertTrue(dia.na_meta)
        dia.kcal = 2300
        self.assertFalse(dia.na_meta)

    # ---------------------------------------------------------- peso
    def test_peso_do_mes_e_quanto_falta(self):
        self.usuario.peso_meta_kg = Decimal('75')
        self.usuario.save()
        HistoricoMedida.objects.create(usuario=self.usuario, data_registro=timezone.now() - timedelta(days=10),
                                       peso_kg=Decimal('82'), objetivo_momento='hipertrofia')
        peso = servicos.resumo_do_peso(self.usuario, timezone.localdate())
        self.assertEqual((peso.atual, peso.variacao_mes, peso.falta), (Decimal('80'), Decimal('-2'), Decimal('5')))
        self.assertEqual(len(peso.linha.split()), 2)
        self.assertEqual(peso.dias_sem_pesar, 0)
        resposta = self.client.get(reverse('home'))
        self.assertContains(resposta, 'Faltam 5 kg para perder')
        self.assertContains(resposta, '<polyline')

    # ---------------------------------------------------------- ranking
    def test_ranking_sem_amigos_convida_a_adicionar(self):
        painel = servicos.painel_do_dia(self.usuario)
        self.assertFalse(painel.ranking.tem_amigos)
        self.assertContains(self.client.get(reverse('home')), reverse('ranking:amigos'))
